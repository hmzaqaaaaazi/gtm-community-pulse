import json
import os
import sqlite3

from openai import OpenAI

DB_PATH = os.environ.get("DB_PATH", "/data/gtm.db")
MODEL = "gpt-5.4-mini"

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "to", "of", "in", "on", "at", "for",
    "with", "by", "from", "what", "how", "why", "when", "where", "who",
    "which", "that", "this", "these", "those", "and", "or", "but", "not",
    "i", "me", "my", "we", "our", "you", "your", "it", "its", "they",
    "about", "tell", "show", "give", "find", "list", "get", "any", "all",
}

SYSTEM_PROMPT = (
    "You are a GTM (Go-To-Market) engineering intelligence assistant. "
    "You answer questions based on real community data extracted from GTM engineering subreddits. "
    "Be specific, cite the posts that support your answer by their titles, "
    "and be direct and practical. No filler, no generic advice — "
    "only what the community data actually shows."
)

SEARCH_COLS = [
    "p.title",
    "p.selftext",
    "e.key_insight",
    "e.tools_mentioned",
    "e.skills_mentioned",
    "e.project_ideas",
]

SELECT_CLAUSE = """
    SELECT DISTINCT
        p.id, p.title, p.url, p.score, p.created_date, p.subreddit,
        e.key_insight, e.tools_mentioned, e.skills_mentioned,
        e.project_ideas, e.job_signals, e.post_category, e.gtm_relevance
    FROM posts p
    JOIN enriched e ON p.id = e.post_id
"""


def extract_keywords(question):
    tokens = question.lower().split()
    cleaned = [t.strip("?.,!;:\"'()[]") for t in tokens]
    return [t for t in cleaned if t and t not in STOP_WORDS and len(t) > 2]


def search_posts(conn, keywords):
    if not keywords:
        return conn.execute(
            SELECT_CLAUSE + "ORDER BY e.gtm_relevance DESC, p.score DESC LIMIT 15"
        ).fetchall()

    per_kw = " OR ".join(f"{col} LIKE ?" for col in SEARCH_COLS)
    conditions = " OR ".join(f"({per_kw})" for _ in keywords)
    params = [f"%{kw}%" for kw in keywords for _ in SEARCH_COLS]

    return conn.execute(
        SELECT_CLAUSE + f"WHERE {conditions} ORDER BY e.gtm_relevance DESC, p.score DESC LIMIT 15",
        params,
    ).fetchall()


def format_block(index, row):
    (_, title, url, score, created_date, subreddit,
     key_insight, tools_json, skills_json, projects_json,
     signals_json, post_category, gtm_relevance) = row

    tools    = json.loads(tools_json    or "[]")
    skills   = json.loads(skills_json   or "[]")
    projects = json.loads(projects_json or "[]")
    signals  = json.loads(signals_json  or "[]")

    tools_str = (
        ", ".join(t["name"] for t in tools if isinstance(t, dict) and "name" in t)
        or "none"
    )
    skills_str = ", ".join(skills) if skills else "none"
    projects_str = (
        "; ".join(p["title"] for p in projects if isinstance(p, dict) and "title" in p)
        or "none"
    )
    signals_str = (
        " | ".join(
            f'{s.get("signal_type")}: {s.get("detail")}'
            for s in signals if isinstance(s, dict)
        )
        or "none"
    )

    title_short = (title or "")[:70]
    category    = post_category or "Unknown"
    relevance   = gtm_relevance if gtm_relevance is not None else "?"

    return (
        f"[{index}] \"{title_short}\" | r/{subreddit} | {created_date} | "
        f"Score: {score} | {category} | Relevance: {relevance}/10\n"
        f"    Insight: {key_insight}\n"
        f"    Tools: {tools_str}\n"
        f"    Skills: {skills_str}\n"
        f"    Projects: {projects_str}\n"
        f"    Job Signals: {signals_str}"
    )


def ask_claude(question, blocks):
    context = "\n\n".join(blocks)
    prompt = (
        f"Community data ({len(blocks)} posts):\n\n"
        f"{context}\n\n"
        f"Question: {question}\n\n"
        "Answer specifically based on the posts above. "
        "Cite post titles that support your answer. "
        "Be direct and practical — no filler, no generic advice."
    )
    response = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    answer = response.choices[0].message.content
    return answer


def main():
    conn = sqlite3.connect(DB_PATH)
    print("GTM Intelligence RAG — type your question, or 'exit' to quit.\n")

    while True:
        print("-" * 60)
        try:
            question = input("Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            print("Goodbye.")
            break

        keywords = extract_keywords(question)
        rows = search_posts(conn, keywords)

        if not rows:
            print("No enriched posts found. Run the ingestor and enricher first.\n")
            continue

        blocks = [format_block(i + 1, row) for i, row in enumerate(rows)]
        answer = ask_claude(question, blocks)

        print(f"\n{answer}\n")
        print(f"Sources: {len(rows)} posts analyzed from r/gtmengineering and r/ClaudeGTM")

    conn.close()


if __name__ == "__main__":
    main()
