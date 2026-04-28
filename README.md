# GTM Community Pulse

Pulls posts and comments from r/gtmengineering and r/ClaudeGTM, runs them through an LLM to extract signals, and lets you query the results from a CLI.

## What it does

The ingestor fetches posts and top comments from two GTM engineering subreddits using Reddit's public JSON API. It stores everything in a local SQLite database. On the first run it pulls the full post history. On later runs it only fetches posts newer than what is already stored.

The enricher reads each unenriched post, combines the title, body, and comments into a single text block, and sends it to the LLM. It returns structured JSON with tools mentioned, skills, project ideas, job signals, a category, a one sentence insight, and a relevance score from 1 to 10. All of that goes into a separate enriched table and the post is marked as done.

The query interface is a CLI loop. You type a question and it searches the enriched database for matching posts, builds a compact context block from the extracted signals, and sends everything to Claude Sonnet. You get a direct answer with citations to the specific posts it drew from.

## Architecture

```
Reddit API → Ingestor → SQLite → Enricher (LLM) → Enriched DB → RAG Query CLI → LLM → Answer
```

## Stack

- Python
- SQLite
- Docker
- OpenAI API (gpt-5.4-mini)
- Reddit Public JSON API

## Project Structure

```
gtm-community-pulse/
├── README.md
├── .gitignore
├── .env.example
├── docker-compose.yml
├── ingestor/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ingestor.py
├── enricher/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── enricher.py
├── rag/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── query.py
├── schema/
│   └── init.sql
└── data/
    └── .gitkeep
```

## Setup

1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your OpenAI API key
3. Run: `docker-compose up --build`
4. To ask questions: `docker-compose run rag`

## Requirements

Docker and an OpenAI API key.

## Example Queries

```
What projects are people building with Clay right now?
What skills keep showing up in GTM engineer job posts?
What tools do people pair with Apollo for outbound?
What would be a good project to build to get hired as a GTM engineer?
What is the community saying about AI SDRs?
```

## How it Works

The ingestor hits Reddit's public JSON API with a custom user agent and no authentication required. It paginates through posts using the `after` token and fetches the top 10 comments for each post. It sleeps one second between every API call. Each run checks the latest stored timestamp and only pulls what is new.

The enricher reads posts where `enriched = 0`, builds a text block from the title, body, and comments, and sends it to the LLM with a prompt that requires raw JSON back. It extracts tools mentioned with context, skill names, project ideas with complexity and replicability flags, job signals by type, a post category, a one sentence key insight, and a GTM relevance score. Results go into the enriched table and the post is flagged as done.

The query CLI extracts keywords from the question, filters out stop words, and runs a SQL search across post titles, bodies, key insights, tools, skills, and project ideas. It takes the top 15 results ordered by relevance score, formats each into a compact block, and sends the full context to the LLM. It answers the question directly and names the posts that support its answer.

## Why I Built This

Built to understand what GTM engineers are actually working on and what companies are hiring for. Also demonstrates building a working data pipeline with LLM enrichment from scratch.
