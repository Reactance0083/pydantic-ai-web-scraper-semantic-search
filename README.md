> **Commercial status:** Deferred code reference. This repository is not the current flagship and should not be promoted as commercially ready until its package, listing, README, and download flow are re-verified.


## Current Status

This repository is a deferred code reference, not the current Stage 1 flagship. It may be useful for learning, but it should not be promoted as commercially ready until its package, listing, README, and download flow are re-verified.

# Web Scraper + Semantic Search (pydantic-ai + FastAPI)

Scrapes any URL, extracts structured content with `pydantic-ai`, and stores it in a searchable local index. Supports both keyword search and AI-powered semantic search with ranked results.

## What It Does

1. Fetches and cleans HTML (strips nav, scripts, headers, footers)
2. Extracts structured content: title, summary, key points, topics, category, language
3. Stores to a local JSON index (swap for Postgres/Redis in production)
4. Exposes keyword search (instant) and semantic search (AI-ranked)

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in ANTHROPIC_API_KEY
uvicorn main:app --reload --port 8003
```

## API Usage

### Scrape a URL

```bash
curl -X POST http://localhost:8003/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://docs.pydantic.dev/latest/concepts/pydantic_ai/", "notes": "pydantic-ai docs"}'
```

Response:
```json
{"id": "a3f8c2d1", "title": "Pydantic AI — Getting Started", "topics": ["pydantic-ai", "llm", "structured-outputs"]}
```

### Keyword Search

```bash
curl "http://localhost:8003/search?q=async+python+agents"
```

### Semantic Search (AI-ranked)

```bash
curl -X POST http://localhost:8003/search/semantic \
  -H "Content-Type: application/json" \
  -d '{"query": "how to handle rate limits in production", "top_k": 5}'
```

### List Index

```bash
curl http://localhost:8003/index
```

### Delete Entry

```bash
curl -X DELETE http://localhost:8003/index/a3f8c2d1
```

## Structured Extraction (pydantic-ai)

```python
class ScrapedContent(BaseModel):
    title: str
    summary: str            # 2-3 sentence summary
    key_points: list[str]   # up to 6 bullet points
    category: str           # article | docs | product | blog | news | other
    topics: list[str]       # up to 5 specific topic tags
    language: str           # en | es | fr | de | zh | etc.
```

## Search Architecture

**Keyword search** uses TF-style term frequency scoring — instant, no API calls.

**Semantic search** uses a two-step pipeline:
1. Pre-filter top 20 candidates by keyword score (avoids token waste)
2. Claude re-ranks by semantic relevance to the query

```
POST /search/semantic
  → keyword pre-filter (top 20)
  → semantic_ranker agent (claude-haiku-4-5)
  → ranked SearchResult list
```

## Customization

- Replace JSON file index with Postgres: swap `load_index()`/`save_index()` with SQLAlchemy
- Add vector embeddings with `pgvector` for true vector search
- Extend `ScrapedContent` with `author`, `published_date`, `reading_time`
- Add pagination to `/search` with `offset` and `limit` params

## Requirements

- Python 3.11+
- Anthropic API key (uses claude-haiku-4-5, ~$0.001/10 pages scraped)
- `beautifulsoup4` for HTML parsing

---
