import os
import sqlite3
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DB_PATH = os.environ.get("DB_PATH", "/data/gtm.db")
SCHEMA_PATH = os.environ.get("SCHEMA_PATH", "/schema/init.sql")
SUBREDDITS = [s.strip() for s in os.environ.get("SUBREDDITS", "gtmengineering,ClaudeGTM").split(",")]
MODE = os.environ.get("MODE", "posts")

REDDIT_BASE = "https://www.reddit.com/r"

retry_strategy = Retry(
    total=5,
    backoff_factor=3,
    status_forcelist=[429, 500, 502, 503, 504],
    respect_retry_after_header=True,
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session = requests.Session()
session.mount("https://", adapter)
session.headers.update({"User-Agent": "GTMIntelligence/1.0"})


def init_db(conn):
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()


def get_post_count(conn, subreddit):
    row = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE subreddit = ?", (subreddit,)
    ).fetchone()
    return row[0]


def fetch_posts_page(subreddit, after):
    params = {"limit": 100}
    if after:
        params["after"] = after

    resp = session.get(f"{REDDIT_BASE}/{subreddit}.json", params=params)
    resp.raise_for_status()
    data = resp.json()["data"]

    posts = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for child in data["children"]:
        p = child["data"]
        utc = p["created_utc"]

        posts.append({
            "id": p["id"],
            "subreddit": subreddit,
            "title": p.get("title"),
            "selftext": p.get("selftext"),
            "author": p.get("author"),
            "score": p.get("score"),
            "num_comments": p.get("num_comments"),
            "url": p.get("url"),
            "permalink": p.get("permalink"),
            "flair": p.get("link_flair_text"),
            "created_utc": utc,
            "created_date": datetime.fromtimestamp(utc, timezone.utc).strftime("%Y-%m-%d"),
            "ingested_at": now,
        })

    return posts, data["after"]


def get_posts_without_comments(conn):
    return conn.execute(
        """
        SELECT p.id, p.subreddit
        FROM posts p
        WHERE p.num_comments > 0
          AND NOT EXISTS (SELECT 1 FROM comments c WHERE c.post_id = p.id)
        """
    ).fetchall()


def ingest_all_comments(conn):
    posts = get_posts_without_comments(conn)
    print(f"Found {len(posts)} posts needing comments.")
    total_stored = 0
    total_skipped = 0
    ua = {"User-Agent": "GTMIntelligence/1.0"}

    for post_id, subreddit in posts:
        url = f"{REDDIT_BASE}/{subreddit}/comments/{post_id}.json"
        params = {"limit": 10, "sort": "top"}

        resp = requests.get(url, headers=ua, params=params)
        if resp.status_code == 429:
            print(f"[{subreddit}] Rate limited, sleeping 60s...")
            time.sleep(60)
            resp = requests.get(url, headers=ua, params=params)
            if resp.status_code == 429:
                print(f"[{subreddit}] Still rate limited, skipping post {post_id}")
                time.sleep(5)
                continue

        try:
            resp.raise_for_status()
        except Exception as e:
            print(f"[{subreddit}] Error fetching comments for {post_id}: {e}")
            time.sleep(5)
            continue

        children = resp.json()[1]["data"]["children"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        comments = []
        skipped = 0

        for child in children:
            if child["kind"] != "t1":
                continue
            c = child["data"]
            body = c.get("body", "")
            if not body or body in ("[removed]", "[deleted]"):
                skipped += 1
                continue
            utc = c.get("created_utc", 0)
            comments.append({
                "id": c["id"],
                "post_id": post_id,
                "subreddit": subreddit,
                "author": c.get("author"),
                "body": body,
                "score": c.get("score"),
                "created_utc": utc,
                "created_date": datetime.fromtimestamp(utc, timezone.utc).strftime("%Y-%m-%d"),
                "ingested_at": now,
            })

        insert_comments(conn, comments)
        total_stored += len(comments)
        total_skipped += skipped
        print(f"[{subreddit}] Post {post_id}: {len(comments)} comments stored, {skipped} skipped")
        time.sleep(5)

    print(f"Done. Comments stored: {total_stored} | Skipped: {total_skipped}")


def insert_posts(conn, posts):
    conn.executemany(
        """
        INSERT OR IGNORE INTO posts
            (id, subreddit, title, selftext, author, score, num_comments, url,
             permalink, flair, created_utc, created_date, ingested_at)
        VALUES
            (:id, :subreddit, :title, :selftext, :author, :score, :num_comments,
             :url, :permalink, :flair, :created_utc, :created_date, :ingested_at)
        """,
        posts,
    )
    conn.commit()


def insert_comments(conn, comments):
    conn.executemany(
        """
        INSERT OR IGNORE INTO comments
            (id, post_id, subreddit, author, body, score, created_utc, created_date, ingested_at)
        VALUES
            (:id, :post_id, :subreddit, :author, :body, :score, :created_utc, :created_date, :ingested_at)
        """,
        comments,
    )
    conn.commit()


def ingest_subreddit(conn, subreddit):
    post_count = get_post_count(conn, subreddit)
    if post_count == 0:
        print(f"[{subreddit}] First run: fetching all posts.")
    else:
        print(f"[{subreddit}] {post_count} posts already stored. Paginating to completion, duplicates skipped.")

    total_posts = 0
    after = None
    page = 1

    while True:
        print(f"[{subreddit}] Fetching page {page}...")
        posts, after = fetch_posts_page(subreddit, after)
        time.sleep(3)

        if not posts:
            print(f"[{subreddit}] No new posts found on this page.")
            break

        insert_posts(conn, posts)
        total_posts += len(posts)
        print(f"[{subreddit}]   Stored {len(posts)} posts (running total: {total_posts})")

        if not after:
            break

        page += 1

    print(f"[{subreddit}] Done. Posts: {total_posts}")


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    if MODE == "comments":
        ingest_all_comments(conn)
    else:
        print(f"Subreddits: {', '.join(SUBREDDITS)}")
        for subreddit in SUBREDDITS:
            ingest_subreddit(conn, subreddit)

    conn.close()


if __name__ == "__main__":
    main()
