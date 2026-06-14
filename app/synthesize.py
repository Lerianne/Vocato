"""One-time (re-runnable) synthesis: digest the document index into
memory/career-history.md — standing context for every coaching session.

Usage: python synthesize.py
"""

from collections import Counter
from datetime import date
from pathlib import Path

import ollama

from store import VectorStore

CHAT_MODEL = "llama3.2:3b"
MEMORY = Path(__file__).parent / "memory"

QUERIES = [
    ("resume", "skills, experience, education, technical background"),
    ("cover-letter", "motivation, strengths, why this company, career narrative"),
    ("job-description", "role title, company, seniority, requirements"),
]


def main():
    store = VectorStore()
    if not store.chunks:
        print("Index is empty — run ingest.py first.")
        return

    counts = Counter(c["doc_type"] for c in store.chunks)
    docs = Counter()
    for c in store.chunks:
        docs[(c["doc_type"], c["name"])] = 1
    doc_counts = Counter(t for t, _ in docs)

    # Gather representative excerpts per document type.
    sections = []
    for doc_type, query in QUERIES:
        hits = store.search(query, k=10, doc_type=doc_type)
        if not hits:
            continue
        excerpts = "\n\n".join(f"({h['name']})\n{h['text'][:900]}" for h in hits[:8])
        sections.append(f"## {doc_type} excerpts\n{excerpts}")

    # Filename list is itself a signal: which roles/companies she targeted.
    names_by_type = {}
    for (t, name) in docs:
        names_by_type.setdefault(t, []).append(name)
    listing = "\n".join(
        f"### {t} ({len(ns)} files)\n" + "\n".join(f"- {n}" for n in sorted(ns)[:80])
        for t, ns in names_by_type.items()
    )

    # Ground truth: the human-verified record. Section 1 must come from THIS, not
    # be re-inferred from messy résumé excerpts (which previously fabricated titles).
    experience = (MEMORY / "experience.md").read_text() if (MEMORY / "experience.md").exists() else ""

    prompt = f"""You are analyzing a job seeker's document archive to build a career profile.

CRITICAL distinction between source types — do not blur them:
- VERIFIED EXPERIENCE (below) = the authoritative, human-confirmed record of what she has ACTUALLY DONE. This is ground truth — section 1 must come from here, copied faithfully, NOT re-inferred or embellished.
- RÉSUMÉ excerpts = tailored supporting detail. Titles/dates vary between versions; if they disagree with VERIFIED EXPERIENCE, the verified record wins.
- COVER-LETTER excerpts = jobs she APPLIED FOR. Proof she applied, NOT that she worked there. Present-tense enthusiasm in a cover letter is intent, not history.
- JOB-DESCRIPTION excerpts = roles she was INTERESTED IN — targets, not jobs held.

## VERIFIED EXPERIENCE (authoritative — use verbatim for section 1)
{experience or "(none provided — fall back to résumé excerpts, and be conservative)"}

## Document inventory
{listing}

## Representative excerpts (each tagged by type above)
{chr(10).join(sections)}

Write a markdown digest titled "Career history (auto-synthesized {date.today().isoformat()})" with these EXACT sections:
1. **What she has actually done** — taken from VERIFIED EXPERIENCE above (roles, projects, education, skills). Do NOT add a company here from a cover letter, and do NOT alter her job titles. If VERIFIED EXPERIENCE is empty, use only résumé content and stay conservative.
2. **What she has applied for / targeted** — companies and role types drawn from cover letters and job postings, clearly framed as applications/targets she pursued (and may not have landed). Exclude anything already in section 1.
3. **Recurring strengths & narrative** — themes her materials consistently emphasize.
4. **Observations & possible tensions** — e.g., gap between what she's done vs. what she applies for, breadth vs. focus, evolution over time.

If unsure whether a company is real experience or just an application, put it under section 2, not 1. Be factual; cite document names. Max 700 words."""

    print(f"Synthesizing from {sum(doc_counts.values())} documents "
          f"({dict(doc_counts)})...")
    resp = ollama.chat(model=CHAT_MODEL,
                       messages=[{"role": "user", "content": prompt}],
                       options={"num_ctx": 16384})
    out = MEMORY / "career-history.md"
    out.write_text(resp["message"]["content"] + "\n")
    print(f"Wrote {out} — review and edit it; it loads into every session.")


if __name__ == "__main__":
    main()
