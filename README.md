# Vocato 🎯

**Answer the calling.**

A private career coach that runs **entirely on your machine** — free, no cloud, no API keys, no account. Vocato reads the real resumes, cover letters, and job descriptions you've actually written, remembers every session, tracks your networking, and proactively checks in.

> **Your data never leaves your laptop.** Career conversations are among the most sensitive things you'll ever type — salary, why you really left each job, who you've networked with. Vocato keeps all of it local. Memory is plain markdown files you own and can edit.

Powered by [Ollama](https://ollama.com) (`llama3.2:3b` + `nomic-embed-text`) with RAG over your own documents.

---

## Why Vocato

- 🔒 **100% local.** No cloud, no API keys required, no sign-up. Nothing phones home.
- 📄 **Grounded in your real history.** It reasons over your actual application documents — not a profile form you fill in once.
- 🧭 **A real relationship.** Remembers every session, tracks your network, checks in weekly.
- 💸 **Free to run.** Open source. Optionally plug in the Claude API (your own key) for sharper coaching.

## Quick start (one line)

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/vocato/main/install.sh | bash
```

This installs Ollama, pulls the models (~2 GB, first time only), sets up the
Python environment, and adds a `vocato` command. Then just run:

```bash
vocato
```

First run auto-creates `memory/profile.md` and `memory/goals.md` from the
templates in `app/examples/` for you to fill in. Re-run the installer any time
to update to the latest version.

### Manual install (if you'd rather do it by hand)

```bash
git clone https://github.com/<you>/vocato.git
cd vocato/app
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ollama pull llama3.2:3b && ollama pull nomic-embed-text
./coach
# (optional) point ingest.py at your documents folder, then index them
.venv/bin/python ingest.py
```

Weekly review mode (the installer schedules this to auto-open Fridays at 4pm):

```bash
vocato --checkin
```

## In-chat commands

| Command | What it does |
|---|---|
| `/note Sarah, Stripe` | Capture coffee-chat notes — coach asks follow-ups, saves a structured note, indexes it |
| `/web <query>` | Search the web (company/role research) |
| `/jobs <query>` | Search live job postings (LinkedIn, Greenhouse, Lever, Ashby, etc.) |
| `/goals` | Review your goals one by one |
| `/progress` | Honest trajectory review based on your history |
| `/action` | List open action items (incl. coffee-chat follow-ups) |
| `/contacts` | Recap your coffee-chat network & pending follow-ups |
| `/ingest` | Re-index new/changed documents |
| `/bye` | Summarize the session to memory and exit |

## First-run checklist

1. **Fill in `app/memory/profile.md`** — who you are, how you want to be coached.
2. **Fill in `app/memory/goals.md`** — concrete goals with dates.
3. **Point `ingest.py` at your documents** (`DOCS_DIR` near the top) and run it.
4. Review the auto-generated `app/memory/career-history.md` and fix anything wrong — it loads into every session.

## How it remembers

- `app/memory/sessions/` — every session is auto-summarized on `/bye`
- `app/memory/coffee-chats/` — structured notes from `/note`
- `app/db/` — a local vector index over your documents + notes (never committed)

## Privacy

Everything runs locally by default. The **only** thing that can leave your machine is a web/job-search *query* you explicitly trigger (`/web`, `/jobs`) — never your documents or conversation. To go fully offline, remove the `/web` and `/jobs` handlers in `app/coach.py`.

If you opt into the Claude API for sharper coaching, you bring your own key and pay Anthropic directly — only the prompt is sent, never your document store.

## Repository layout

```
vocato/
├── app/        ← the coach (Python CLI) — this is the product
│   ├── coach.py  ingest.py  store.py  synthesize.py  web.py
│   ├── examples/ ← starter templates for profile & goals
│   └── prompts/
├── web/        ← marketing website (deploys to Vercel)
└── README.md
```

> Your personal data — `app/memory/`, `app/db/`, conversation history — is **git-ignored** and never committed.

## License

MIT — see [LICENSE](LICENSE).
