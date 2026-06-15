"""Vocato — a local career & personal development coach.

Free, private, runs entirely on this Mac via Ollama.

Usage: python coach.py            # start a coaching session
       python coach.py --checkin  # start in weekly-review mode

In-chat commands:
  /note <person>, <company> [path]  capture coffee-chat notes (saved + indexed);
                                    optional path reads a .pdf/.docx/.txt/.md file
                                    instead of pasting (quote paths with spaces)
  /web <query>      search the web    /jobs <query>  search live job postings
  /goals      show goals          /progress   review trajectory
  /action     open action items   /contacts   coffee-chat network recap
  /ingest     re-index documents  /bye        summarize session & exit
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path

import ollama
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

import web
from store import VectorStore

console = Console()

CHAT_MODEL = "llama3.2:3b"
NUM_CTX = 8192  # ollama default is 2048 — too small for RAG context
ROOT = Path(__file__).parent
MEMORY = ROOT / "memory"
SESSIONS = MEMORY / "sessions"
COFFEE = MEMORY / "coffee-chats"
EXAMPLES = ROOT / "examples"


def bootstrap_memory() -> None:
    """First-run setup: create the (git-ignored) memory/ working files from the
    shipped templates so a fresh clone is usable immediately. Never overwrites
    files that already exist, so a user's filled-in data is always safe."""
    import shutil
    MEMORY.mkdir(exist_ok=True)
    SESSIONS.mkdir(exist_ok=True)
    COFFEE.mkdir(exist_ok=True)
    for example in (("profile.example.md", "profile.md"),
                    ("goals.example.md", "goals.md")):
        src, dst = EXAMPLES / example[0], MEMORY / example[1]
        if not dst.exists() and src.exists():
            shutil.copyfile(src, dst)


IDENTITY_FILE = MEMORY / "identity.json"


def load_identity() -> dict:
    """Read the user's name + pronouns captured at setup (git-ignored). Returns
    {} if setup hasn't run yet."""
    import json
    try:
        return json.loads(IDENTITY_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def identity_block() -> str:
    """A prompt fragment telling the coach how to address the user. Injected at
    runtime so the shipped prompt stays generic and the user's name never lands
    in a tracked file."""
    ident = load_identity()
    name = ident.get("name", "").strip()
    p = ident.get("pronouns", {})  # {subject, object, possessive, possessive_pronoun, reflexive}
    if not name and not p:
        return ""
    lines = ["\n## About the user"]
    if name:
        lines.append(f"The user's name is {name}. Address them by name naturally.")
    if p.get("subject"):
        lines.append(
            "Refer to them using these pronouns: "
            f"{p['subject']}/{p['object']}/{p.get('possessive','')} "
            f"(e.g. \"{p['subject']} applied for…\", \"I'm challenging {p['object']} on…\", "
            f"\"{p.get('possessive','')} goals\"). Use them consistently.")
    return "\n".join(lines)

CYAN, DIM, BOLD, RESET = "\033[96m", "\033[2m", "\033[1m", "\033[0m"

# -- input -------------------------------------------------------------------
# prompt_toolkit fixes the old single-line input() bug: a pasted or typed line
# break used to submit the message early. Now Enter sends, Option/Alt+Enter
# inserts a newline, and multi-line pastes are captured as one whole message.
_kb = KeyBindings()


@_kb.add("escape", "enter")  # Option/Alt+Enter → newline instead of send
def _(event):
    event.current_buffer.insert_text("\n")


_session = PromptSession(history=FileHistory(str(ROOT / ".coach_history")),
                         key_bindings=_kb)


def ask(prompt_text: str, multiline: bool = False) -> str:
    """Read a line (or block). Raises EOFError on Ctrl-D. Paste-safe."""
    toolbar = None
    if multiline:
        toolbar = ANSI(f"{DIM} Enter = new line · Esc then Enter (or Alt+Enter) "
                       f"= finish{RESET}")
    return _session.prompt(
        ANSI(prompt_text),
        multiline=multiline,
        bottom_toolbar=toolbar,
    ).strip()


def llm(messages, stream=True):
    """Stream a chat completion, printing as it goes; returns full text."""
    if not stream:
        resp = ollama.chat(model=CHAT_MODEL, messages=messages,
                           options={"num_ctx": NUM_CTX})
        return resp["message"]["content"]
    out = []
    for part in ollama.chat(model=CHAT_MODEL, messages=messages, stream=True,
                            options={"num_ctx": NUM_CTX}):
        token = part["message"]["content"]
        out.append(token)
        print(token, end="", flush=True)
    print()
    return "".join(out)


def respond(messages) -> str:
    """Show a 'thinking…' spinner while the coach generates, then print the
    reply once as a rendered-markdown panel.

    We collect the full response behind a single-line spinner (which redraws
    cleanly in any terminal) and render the markdown panel only when complete.
    Re-rendering a growing panel on every token caused it to stack endlessly
    once the text outgrew the window — so we don't do that.
    """
    buffer = ""
    with console.status("[cyan]coach is thinking…[/cyan]", spinner="dots"):
        for part in ollama.chat(model=CHAT_MODEL, messages=messages, stream=True,
                                options={"num_ctx": NUM_CTX}):
            buffer += part["message"]["content"]
    console.print(Panel(Markdown(buffer), title="coach", title_align="left",
                        border_style="cyan", padding=(0, 1)))
    return buffer


def read(path: Path, default: str = "") -> str:
    return path.read_text() if path.exists() else default


_PLACEHOLDER = re.compile(r"<[^>\n]{2,}>")  # e.g. <e.g. ...>, <city / timezone>


def is_template(path: Path) -> bool:
    """True if a memory file is still the unfilled starter template (empty, or
    most of its content lines are still <placeholders>)."""
    text = read(path)
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return True
    placeholders = sum(1 for ln in lines if _PLACEHOLDER.search(ln))
    return placeholders >= max(1, len(lines) // 2)


def recent_sessions(n: int = 5) -> str:
    files = sorted(SESSIONS.glob("*.md"))[-n:]
    return "\n\n".join(f"### {f.stem}\n{f.read_text()}" for f in files)


def build_system_prompt() -> str:
    parts = [read(ROOT / "prompts" / "coach.md")]
    parts.append(identity_block())
    parts.append(f"\nToday's date: {date.today().isoformat()}")
    profile = read(MEMORY / "profile.md")
    goals = read(MEMORY / "goals.md")
    experience = read(MEMORY / "experience.md")
    history = read(MEMORY / "career-history.md")
    sessions = recent_sessions()
    if profile:
        parts.append(f"\n## Their profile\n{profile}")
    if goals:
        parts.append(f"\n## Their goals\n{goals}")
    if experience:
        # Authoritative, human-verified record. This is the source of truth for
        # what they have actually done — it OUTRANKS retrieved snippets and the
        # auto-synthesized history below. Flag leftover ⚠️ VERIFY markers so an
        # unconfirmed line can't silently be stated as fact.
        if "⚠️ VERIFY" in experience or "VERIFY" in experience:
            experience += ("\n\n(NOTE: lines marked VERIFY are unconfirmed — "
                           "hedge on those; do not state them as established fact.)")
        parts.append(
            "\n## ✅ VERIFIED EXPERIENCE (authoritative — source of truth)\n"
            "This is the human-verified record of what they have ACTUALLY done. "
            "Trust it over anything retrieved or synthesized. If a retrieved cover "
            "letter or job posting names a company NOT here, they applied — they did "
            f"not work there.\n{experience}")
    if history:
        parts.append(
            "\n## Career history (AUTO-SYNTHESIZED — may contain errors)\n"
            "Generated by a small model from their documents; useful for themes and "
            "observations only. Where it conflicts with VERIFIED EXPERIENCE above, "
            f"the verified record wins.\n{history}")
    if sessions:
        parts.append(f"\n## Recent coaching sessions\n{sessions}")
    return "\n".join(parts)


# How to read each source. CRITICAL: a cover letter or job posting is something
# the user APPLIED FOR / WANTED — never proof they actually held that role.
PROVENANCE = {
    "resume": "✅ ACTUAL EXPERIENCE — from their résumé; things they have really done",
    "cover-letter": "📨 A JOB APPLICATION THEY SENT — they applied for this role/company; "
                    "this is NOT proof they worked there or did this job",
    "job-description": "🎯 A ROLE THEY WERE INTERESTED IN — a posting they saved/applied to; "
                       "a target, NOT a job they held",
    "coffee-chat": "☕ Notes from a networking conversation",
    "session": "🗒️ A past coaching session summary",
    "other": "📄 Document of unclear type — do not assume it reflects real experience",
}


# Provenance-aware retrieval. Each bucket: (doc_type, k, score_floor).
# Résumé (real experience) gets the most slots and a SOFTER floor so accomplishments
# surface even on indirect questions — this fixes "things I've done that never come
# up." Applications keep a stricter floor; unknown-type docs the strictest, so they
# can't masquerade as experience. Display order = trust order.
RETRIEVAL_BUCKETS = [
    ("resume", 6, 0.35),
    ("coffee-chat", 3, 0.42),
    ("session", 2, 0.42),
    ("cover-letter", 3, 0.45),
    ("job-description", 2, 0.45),
    ("other", 2, 0.52),
]


def rag_context(store: VectorStore, query: str) -> str:
    grouped = store.search_grouped(query, RETRIEVAL_BUCKETS)
    sections = []
    for dtype, _k, _floor in RETRIEVAL_BUCKETS:
        hits = grouped.get(dtype, [])
        if not hits:
            continue
        label = PROVENANCE.get(dtype, PROVENANCE["other"])
        blocks = [f"File: {h['name']} (relevance {h['score']:.2f}):\n{h['text'][:1100]}"
                  for h in hits]
        sections.append(f"### {label}\n" + "\n\n".join(blocks))
    if not sections:
        return ""
    return (
        "\n\n<retrieved_documents>\n"
        "Excerpts from the user's files, grouped by source type (most trustworthy "
        "first). Only the RÉSUMÉ group is evidence of what they actually did; cover "
        "letters and job postings are roles they applied for or wanted, not jobs they "
        "held. Cross-check against the VERIFIED EXPERIENCE in your instructions — it "
        "wins over anything here.\n\n"
        + "\n\n".join(sections)
        + "\n</retrieved_documents>"
    )


# -- commands ------------------------------------------------------------------

_NOTE_EXTS = "pdf|docx|md|txt|csv|xlsx"


def _split_note_path(args: str):
    """Pull a trailing file path out of `/note` args, if present.

    Returns (who, path_or_None). Recognizes a quoted path, or a trailing token
    that ends in a supported extension. Quote paths that contain spaces.
    """
    m = (re.search(rf'''["']([^"']+\.(?:{_NOTE_EXTS}))["']\s*$''', args, re.I)
         or re.search(rf'(\S+\.(?:{_NOTE_EXTS}))\s*$', args, re.I))
    if not m:
        return args.strip(), None
    who = args[:m.start()].strip().rstrip(",").strip()
    return who, Path(m.group(1)).expanduser()


def _extract_file_text(path: Path) -> str | None:
    """Extract text from a notes file using the ingest parsers. Returns None on
    failure (e.g. a scanned/handwritten PDF with no text layer — there's no OCR)."""
    import ingest
    parser = ingest.PARSERS.get(path.suffix.lower())
    if not parser:
        print(f"Unsupported file type: {path.suffix}. "
              f"Supported: {_NOTE_EXTS.replace('|', ', ')}.")
        return None
    text = parser(path).strip()
    if not text:
        print(f"{DIM}Couldn't extract text from {path.name} — a scanned or "
              f"handwritten PDF has no text layer, and there's no OCR.{RESET}")
        return None
    return text


def cmd_note(args: str, store: VectorStore, messages: list) -> None:
    who, note_path = _split_note_path(args)
    if note_path is not None:
        if not note_path.exists():
            print(f"File not found: {note_path}")
            return
        raw = _extract_file_text(note_path)
        if not raw:
            return
        print(f"{DIM}Read {len(raw)} characters from {note_path.name}.{RESET}")
    else:
        print(f"{DIM}Paste or type your raw notes:{RESET}")
        raw = ask("", multiline=True)
        if not raw:
            print("No notes captured.")
            return
    if not who:
        who = ask("Who did you chat with (person, company)? ")
    # Coach asks follow-ups, then we structure and save.
    messages.append({
        "role": "user",
        "content": (
            f"I just had a coffee chat with {who}. Here are my raw notes:\n\n{raw}\n\n"
            "Ask me 2-3 short follow-up questions to make these notes more useful "
            "(key insights, follow-ups I promised, referral potential)."
        ),
    })
    messages.append({"role": "assistant", "content": respond(messages)})
    answers = ask(f"\n{BOLD}you ❯{RESET} ")
    messages.append({"role": "user", "content": answers})
    structured = llm(messages + [{
        "role": "user",
        "content": (
            "Now write a structured coffee-chat note in markdown with sections: "
            "Person & context, Key insights, Follow-up commitments (with dates), "
            "Referral potential, Relevance to my goals. Output only the note."
        ),
    }], stream=False)
    messages.append({"role": "assistant", "content": "(saved structured note)"})
    slug = re.sub(r"[^a-z0-9]+", "-", who.lower()).strip("-")[:50]
    path = COFFEE / f"{date.today().isoformat()}-{slug}.md"
    path.write_text(f"# Coffee chat — {who} ({date.today().isoformat()})\n\n{structured}\n")
    # Index immediately so future sessions recall it.
    store.remove_source(str(path))
    store.add([{"text": structured, "source": str(path), "name": path.name,
                "doc_type": "coffee-chat", "part": 0}])
    store.save()
    print(f"\n{DIM}Saved & indexed: {path.relative_to(ROOT)}{RESET}")


def run_search(kind: str, query: str) -> str:
    label = "live job postings" if kind == "jobs" else "the web"
    print(f"{DIM}Searching {label}: {query}{RESET}")
    results = web.search_jobs(query) if kind == "jobs" else web.search(query)
    if not results:
        print(f"{DIM}No results.{RESET}")
        return ""
    print(f"{DIM}Found {len(results)} results.{RESET}")
    return web.format_results(results)


def cmd_ingest() -> None:
    import ingest
    ingest.main()


def save_session(messages: list) -> None:
    convo = [m for m in messages if m["role"] in ("user", "assistant")]
    if len(convo) < 2:
        return
    print(f"\n{DIM}Summarizing session...{RESET}")
    summary = llm(messages + [{
        "role": "user",
        "content": (
            "Session is over. Write a concise summary for your records: "
            "**Topics**, **Decisions/insights**, **Action items** (with owner and date), "
            "**Open threads**. Output only the summary in markdown."
        ),
    }], stream=False)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    path = SESSIONS / f"{stamp}.md"
    path.write_text(summary + "\n")
    print(f"{DIM}Session saved: {path.relative_to(ROOT)}{RESET}")


CANNED = {
    "/goals": "Let's review my goals. Walk through each one: am I on track? What's the next move?",
    "/progress": "Based on my recent sessions and history, how is my trajectory? Be honest about patterns you see.",
    "/action": "List all open action items from my past sessions and coffee-chat follow-ups. Which are overdue?",
    "/contacts": "Summarize my coffee-chat network: who I've met, key takeaways per person, and pending follow-ups.",
}

CHECKIN_OPENER = (
    "This is my weekly check-in. Start by listing the action items I committed to "
    "in recent sessions and ask me for a status on each, one at a time. "
    "Then help me set focus for next week."
)


def main():
    bootstrap_memory()
    # First run (or `--setup`): capture name, pronouns, and reminder preference.
    if "--setup" in sys.argv or not IDENTITY_FILE.exists():
        from setup import run_setup
        run_setup()
        if "--setup" in sys.argv:
            return
    store = VectorStore()
    system = build_system_prompt()
    messages = [{"role": "system", "content": system}]
    n_chunks = len(store.chunks)
    console.print(Panel(
        "[bold]Vocato[/bold]   [dim]local · free · private · "
        f"{n_chunks} document chunks indexed[/dim]\n"
        "[dim]Enter sends · Option/Alt+Enter = new line · "
        "/help for commands · /bye to end[/dim]",
        border_style="cyan", padding=(0, 1)))

    unset = [name for name, fn in (("profile", "profile.md"), ("goals", "goals.md"))
             if is_template(MEMORY / fn)]
    if unset:
        files = " and ".join(f"memory/{n}.md" for n in unset)
        console.print(Panel(
            f"[bold yellow]Setup incomplete:[/bold yellow] your "
            f"{' and '.join(unset)} {'is' if len(unset) == 1 else 'are'} "
            f"not filled in yet.\n"
            f"[dim]Edit {files} (or just tell me here) so I can coach you "
            f"toward real goals instead of guessing.[/dim]",
            border_style="yellow", padding=(0, 1)))

    if "--checkin" in sys.argv:
        messages.append({"role": "user", "content": CHECKIN_OPENER})
        messages.append({"role": "assistant", "content": respond(messages)})

    while True:
        try:
            user = ask(f"\n{BOLD}you ❯{RESET} ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user in ("/bye", "/exit", "/quit"):
            break
        if user.startswith("/note"):
            cmd_note(user[5:], store, messages)
            continue
        if user.startswith(("/web", "/jobs")):
            kind = "jobs" if user.startswith("/jobs") else "web"
            query = user.split(maxsplit=1)
            query = query[1] if len(query) > 1 else ask("Search for: ")
            if not query:
                continue
            web_ctx = run_search(kind, query)
            messages.append({"role": "user", "content":
                             f"Here's what I found on the web for '{query}'. "
                             f"Help me make sense of it for my situation.{web_ctx}"})
            messages.append({"role": "assistant", "content": respond(messages)})
            continue
        if user == "/ingest":
            cmd_ingest()
            store = VectorStore()  # reload index
            continue
        if user == "/help":
            print(__doc__)
            continue
        if user == "/goals" and is_template(MEMORY / "goals.md"):
            console.print(Panel(
                "[bold yellow]Your goals aren't set yet.[/bold yellow]\n\n"
                "[dim]memory/goals.md still has the starter template, so there's "
                "nothing to review. Either:[/dim]\n"
                "  • edit [bold]memory/goals.md[/bold] with your 1-year & 3-year "
                "goals and what you're working on, or\n"
                "  • just tell me your goals here and I'll help you write them down.",
                title="goals not set", title_align="left",
                border_style="yellow", padding=(0, 1)))
            continue
        prompt = CANNED.get(user, user)
        context = rag_context(store, prompt)
        # Auto-decide whether a live web search would help (company/role/jobs).
        decision = web.decide(prompt)
        if decision:
            context += run_search(decision["kind"], decision["query"])
        messages.append({"role": "user", "content": prompt + context})
        reply = respond(messages)
        messages.append({"role": "assistant", "content": reply})

    save_session(messages)
    print("À la prochaine! 👋")


if __name__ == "__main__":
    main()
