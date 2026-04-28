CREATE TABLE IF NOT EXISTS posts (
    id             TEXT PRIMARY KEY,
    subreddit      TEXT,
    title          TEXT,
    selftext       TEXT,
    author         TEXT,
    score          INTEGER,
    num_comments   INTEGER,
    url            TEXT,
    permalink      TEXT,
    flair          TEXT,
    created_utc    REAL,
    created_date   TEXT,
    ingested_at    TEXT,
    enriched       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS comments (
    id           TEXT PRIMARY KEY,
    post_id      TEXT REFERENCES posts(id),
    subreddit    TEXT,
    author       TEXT,
    body         TEXT,
    score        INTEGER,
    created_utc  REAL,
    created_date TEXT,
    ingested_at  TEXT,
    enriched     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS enriched (
    post_id              TEXT PRIMARY KEY REFERENCES posts(id),
    tools_mentioned      TEXT,
    skills_mentioned     TEXT,
    project_ideas        TEXT,
    job_signals          TEXT,
    post_category        TEXT,
    key_insight          TEXT,
    top_comment_insights TEXT,
    gtm_relevance        INTEGER,
    enriched_at          TEXT
);
