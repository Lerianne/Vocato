"""Free web access for the coach via DuckDuckGo (ddgs) — no API key.

- search(query)        general web results (company/role research)
- search_jobs(query)   results biased toward live job postings
- decide(user_msg)     ask the local model whether a search would help

Only the search *query* leaves the machine — never your documents.
"""

import json

import ollama

DECIDE_MODEL = "llama3.2:3b"
JOB_SITES = ("linkedin.com/jobs", "greenhouse.io", "lever.co", "ashbyhq.com",
             "indeed.com", "weworkremotely.com", "wellfound.com")


def search(query: str, max_results: int = 5) -> list[dict]:
    from ddgs import DDGS
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"  ! web search failed: {e}")
        return []


def search_jobs(query: str, max_results: int = 6) -> list[dict]:
    site_filter = " OR ".join(f"site:{s.split('/')[0]}" for s in JOB_SITES)
    return search(f"{query} jobs ({site_filter})", max_results=max_results)


def format_results(results: list[dict]) -> str:
    if not results:
        return ""
    blocks = []
    for r in results:
        title = r.get("title", "")
        url = r.get("href") or r.get("url", "")
        body = r.get("body", "")[:400]
        blocks.append(f"• {title}\n  {url}\n  {body}")
    return ("\n\n<web_results>\nLive web search results "
            "(cite the URLs when you use them):\n\n"
            + "\n\n".join(blocks) + "\n</web_results>")


def decide(user_msg: str) -> dict | None:
    """Return {'kind': 'web'|'jobs', 'query': str} if a search would help, else None."""
    prompt = (
        "You decide whether a career coach should run a live web search to answer the "
        "user. Search ONLY for: current company/role research, recent news about a "
        "company, or live job postings. Do NOT search for advice, reflection, or "
        "anything answerable from the user's own history.\n\n"
        f'User message: "{user_msg}"\n\n'
        'Reply with ONLY compact JSON. If a search helps: '
        '{"search": true, "kind": "web"|"jobs", "query": "<concise query>"}. '
        'Otherwise: {"search": false}.'
    )
    try:
        resp = ollama.chat(
            model=DECIDE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"temperature": 0, "num_ctx": 2048},
        )
        data = json.loads(resp["message"]["content"])
    except Exception:
        return None
    if not data.get("search") or not data.get("query"):
        return None
    return {"kind": data.get("kind", "web"), "query": data["query"]}
