"""
Web Scraper + Semantic Search
Scrapes URLs on demand, extracts clean content with pydantic-ai,
and stores it in a searchable JSON index with keyword + semantic matching.

Endpoints:
  POST /scrape          — Scrape a URL and add to index
  GET  /search?q=...    — Keyword search across indexed content
  POST /search/semantic — AI-powered semantic search with ranked results
  GET  /index           — List all indexed pages
  DELETE /index/{id}    — Remove a page from index
"""
import os, json, uuid, re
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pydantic_ai import Agent
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
INDEX_FILE        = Path(os.getenv("INDEX_FILE", "scraped_index.json"))

if not ANTHROPIC_API_KEY:
    raise RuntimeError("Missing ANTHROPIC_API_KEY")


# ── Pydantic models ───────────────────────────────────────────────────────────
class ScrapedContent(BaseModel):
    title: str
    summary: str         # 2-3 sentence summary of the page
    key_points: list[str]  # up to 6 bullet points
    category: str        # article | docs | product | blog | news | other
    topics: list[str]    # up to 5 topic tags
    language: str        # en | es | fr | de | zh | etc.


class ScrapeRequest(BaseModel):
    url: str
    notes: str = ""  # optional user notes about why this was saved


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class SearchResult(BaseModel):
    id: str
    url: str
    title: str
    summary: str
    score: float
    category: str
    topics: list[str]


# ── pydantic-ai extractor ─────────────────────────────────────────────────────
extractor = Agent(
    "anthropic:claude-haiku-4-5",
    result_type=ScrapedContent,
    system_prompt=(
        "Extract structured information from web page content. "
        "Write a neutral, factual summary. "
        "Key points should be the most important actionable or informational items. "
        "Topics should be specific (not generic like 'technology'): e.g., 'pydantic-ai', 'async python', 'rate limiting'. "
        "Detect the primary language of the content."
    ),
)

semantic_ranker = Agent(
    "anthropic:claude-haiku-4-5",
    result_type=list[str],  # ordered list of IDs, most relevant first
    system_prompt=(
        "You are a semantic search engine. Given a user query and a list of page summaries, "
        "return the IDs of the most relevant pages in order from most to least relevant. "
        "Consider topic overlap, intent match, and content depth. "
        "Return only IDs that are actually relevant — omit irrelevant ones."
    ),
)


# ── Index helpers ─────────────────────────────────────────────────────────────
def load_index() -> dict:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return {}


def save_index(index: dict):
    INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:8000]  # cap at 8k chars


def keyword_score(query: str, entry: dict) -> float:
    """Simple TF-style keyword score for fast pre-filtering."""
    terms = re.findall(r"\w+", query.lower())
    text  = " ".join([
        entry.get("title", ""),
        entry.get("summary", ""),
        " ".join(entry.get("topics", [])),
        " ".join(entry.get("key_points", [])),
    ]).lower()
    hits = sum(term in text for term in terms)
    return hits / max(len(terms), 1)


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Web Scraper + Semantic Search", version="1.0.0")


@app.post("/scrape")
async def scrape(req: ScrapeRequest):
    # Fetch URL
    async with httpx.AsyncClient(
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"},
        follow_redirects=True,
    ) as client:
        try:
            r = await client.get(req.url)
            r.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Fetch failed: {e}")

    raw_text = clean_html(r.text)
    if len(raw_text) < 100:
        raise HTTPException(status_code=422, detail="Page content too short to index")

    # Extract structured content
    result  = await extractor.run(f"URL: {req.url}\n\nContent:\n{raw_text}")
    content = result.data

    # Store in index
    index = load_index()
    entry_id = str(uuid.uuid4())[:8]
    index[entry_id] = {
        "id":         entry_id,
        "url":        req.url,
        "title":      content.title,
        "summary":    content.summary,
        "key_points": content.key_points,
        "category":   content.category,
        "topics":     content.topics,
        "language":   content.language,
        "notes":      req.notes,
    }
    save_index(index)

    return {"id": entry_id, "title": content.title, "topics": content.topics}


@app.get("/search")
def search_keyword(q: str, limit: int = 10):
    index  = load_index()
    scored = [(keyword_score(q, e), e) for e in index.values()]
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [
        SearchResult(
            id=e["id"],
            url=e["url"],
            title=e["title"],
            summary=e["summary"],
            score=round(s, 3),
            category=e["category"],
            topics=e["topics"],
        )
        for s, e in scored[:limit]
        if s > 0
    ]
    return {"query": q, "results": results}


@app.post("/search/semantic", response_model=list[SearchResult])
async def search_semantic(req: SearchRequest):
    index = load_index()
    if not index:
        return []

    # Pre-filter with keyword score to limit Claude context
    scored = sorted(
        [(keyword_score(req.query, e), e) for e in index.values()],
        key=lambda x: x[0], reverse=True
    )
    candidates = [e for _, e in scored[:20]]  # top 20 by keyword

    summaries = "\n\n".join(
        f"ID: {e['id']}\nTitle: {e['title']}\nSummary: {e['summary']}\nTopics: {', '.join(e['topics'])}"
        for e in candidates
    )

    ranked_ids = (await semantic_ranker.run(
        f"Query: {req.query}\n\nPages:\n{summaries}"
    )).data

    id_to_entry = {e["id"]: e for e in candidates}
    results = []
    for rank, eid in enumerate(ranked_ids[: req.top_k]):
        if eid in id_to_entry:
            e = id_to_entry[eid]
            results.append(SearchResult(
                id=e["id"],
                url=e["url"],
                title=e["title"],
                summary=e["summary"],
                score=round(1.0 - rank * 0.1, 2),
                category=e["category"],
                topics=e["topics"],
            ))
    return results


@app.get("/index")
def list_index():
    index = load_index()
    return {
        "count": len(index),
        "pages": [
            {"id": e["id"], "title": e["title"], "url": e["url"], "category": e["category"]}
            for e in index.values()
        ],
    }


@app.delete("/index/{entry_id}")
def delete_entry(entry_id: str):
    index = load_index()
    if entry_id not in index:
        raise HTTPException(status_code=404, detail="Entry not found")
    del index[entry_id]
    save_index(index)
    return {"deleted": entry_id}


@app.get("/health")
def health():
    return {"status": "ok", "indexed": len(load_index())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003, reload=True)
