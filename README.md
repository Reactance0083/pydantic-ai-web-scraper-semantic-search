# Web Extraction and Search Reference

A FastAPI reference for extracting structured information from web pages and searching a local JSON index.

**[Portfolio](https://github.com/Reactance0083)** · **Status: experimental implementation**

## Implemented pipeline

Fetch an allowed page → clean HTML with BeautifulSoup → extract a typed summary using PydanticAI → save a JSON record → search by keywords or LLM reranking.

The semantic-search route first selects up to 20 candidates by keyword score and then asks a model to rank their IDs. It does not use a vector database or embedding index.

| Endpoint | Purpose |
| --- | --- |
| `POST /scrape` | Fetch and summarize a URL. |
| `GET /search?q=...` | Keyword matching. |
| `POST /search/semantic` | LLM reranking of keyword-selected candidates. |
| `GET /index` | List stored pages. |
| `DELETE /index/{entry_id}` | Remove a record. |
| `GET /health` | Health and index count. |

## Local setup

```bash
python -m venv .venv
# Activate the environment for your shell.
python -m pip install -r requirements.txt
# Copy .env.example to .env and set ANTHROPIC_API_KEY.
python -m uvicorn main:app --host 127.0.0.1 --port 8003
```

The application is in `main.py`. `INDEX_FILE` selects the local JSON file.

## Design limits

Use only authorized public source pages. URL restrictions, redirect validation, internal-network blocking, authentication, concurrent-write protection, and request limits are not implemented. Keep the service local while evaluating those gaps.

Ranking scores are a display convention based on position, not calibrated probabilities. Current model availability and PydanticAI compatibility require verification; the source uses `result_type` and `result.data`.

Developed with AI assistance. Documentation reviewed against source on November 10, 2026.
