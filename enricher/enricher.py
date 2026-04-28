import json
import os
import sqlite3
import time
from datetime import datetime, timezone

from openai import OpenAI

DB_PATH = os.environ.get("DB_PATH", "/data/gtm.db")
MODEL = "gpt-5.4-mini"
BATCH_SIZE = 10

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

PROMPT = """\
You are a GTM (Go-To-Market) engineering intelligence analyst. Analyze the Reddit post below and extract structured signals.

Return ONLY valid JSON with exactly these keys. No markdown, no backticks, no explanation — raw JSON only.

{
  "tools_mentioned": [
    {"name": "tool name", "context": "how it was used or mentioned"}
  ],
  "skills_mentioned": ["skill1", "skill2"],
  "project_ideas": [
    {
      "title": "project title",
      "tools_used": ["tool1"],
      "problem_solved": "what problem this solves",
      "complexity": "beginner|intermediate|advanced",
      "replicable": true
    }
  ],
  "job_signals": [
    {"signal_type": "requirement|salary|title|culture", "detail": "specific detail"}
  ],
  "post_category": "Tools|Skills|Career|Project|Discussion|Job",
  "key_insight": "one sentence capturing the single most valuable takeaway",
  "gtm_relevance": 7
}

Post:
"""


def get_unenriched_posts(conn):
    conn.execute(
        """
        UPDATE posts SET enriched = 1
        WHERE enriched = 0
          AND COALESCE(selftext, '') = ''
          AND num_comments = 0
        """
    )
    conn.commit()
    return conn.execute(
        """
        SELECT id, title, selftext, subreddit, score, num_comments
        FROM posts
        WHERE enriched = 0
        """
    ).fetchall()


def get_comments(conn, post_id):
    return conn.execute(
        """
        SELECT author, body, score
        FROM comments
        WHERE post_id = ?
        ORDER BY score DESC
        """,
        (post_id,),
    ).fetchall()


def build_text_block(title, selftext, comments):
    lines = [f"Title: {title}"]
    if selftext:
        lines.append(f"Body: {selftext}")
    if comments:
        lines.append("Comments:")
        for author, body, score in comments:
            lines.append(f"  [{score}] {author}: {body}")
    return "\n".join(lines)


def call_claude(text_block):
    prompt = PROMPT + text_block
    response = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.choices[0].message.content
    return raw


def insert_enriched(conn, post_id, data):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT OR REPLACE INTO enriched
            (post_id, tools_mentioned, skills_mentioned, project_ideas, job_signals,
             post_category, key_insight, gtm_relevance, enriched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            post_id,
            json.dumps(data.get("tools_mentioned", [])),
            json.dumps(data.get("skills_mentioned", [])),
            json.dumps(data.get("project_ideas", [])),
            json.dumps(data.get("job_signals", [])),
            data.get("post_category"),
            data.get("key_insight"),
            data.get("gtm_relevance"),
            now,
        ),
    )
    conn.execute("UPDATE posts SET enriched = 1 WHERE id = ?", (post_id,))
    conn.commit()


def process_post(conn, post):
    post_id, title, selftext, subreddit, score, num_comments = post
    label = (title or "")[:60]

    try:
        comments = get_comments(conn, post_id)
        text_block = build_text_block(title, selftext, comments)
        raw = call_claude(text_block)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()
        data = json.loads(raw)
        insert_enriched(conn, post_id, data)
        print(f"[{subreddit}] OK   {label}")
    except Exception as e:
        print(f"[{subreddit}] FAIL {label} — {e}")


def main():
    conn = sqlite3.connect(DB_PATH)
    posts = get_unenriched_posts(conn)
    total = len(posts)
    print(f"Found {total} unenriched posts.")

    for batch_start in range(0, total, BATCH_SIZE):
        batch = posts[batch_start : batch_start + BATCH_SIZE]
        for post in batch:
            process_post(conn, post)
        if batch_start + BATCH_SIZE < total:
            print("Batch complete. Sleeping 2 seconds...")
            time.sleep(2)

    conn.close()
    print("Enrichment complete.")


if __name__ == "__main__":
    main()
