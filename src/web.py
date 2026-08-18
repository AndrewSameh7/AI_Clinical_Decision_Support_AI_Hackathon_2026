from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import (
    CLINICAL_SCOPE,
    MAX_QUERY_LENGTH,
    MAX_TOP_K,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    TOP_K,
)
from src.llm import GROQ_MODEL, generate_grounded_answer
from src.vector_store import index_ready, retrieve

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "web"

app = FastAPI(
    title="AI Clinical Decision Support Lite",
    description="Educational hypertension RAG interface",
    version="2.0.0",
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Short-lived server-side retrieval cache. Evidence is never accepted from the browser
# as authoritative context; /api/answer consumes only a server-issued retrieval ID.
_RETRIEVAL_CACHE: Dict[str, Dict[str, Any]] = {}
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


class RetrieveRequest(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUERY_LENGTH)
    top_k: int = Field(default=TOP_K, ge=1, le=MAX_TOP_K)
    strategy: str = Field(default="hybrid", pattern="^(semantic|keyword|hybrid)$")
    config: str = Field(default="B_850_150", pattern="^[A-Za-z0-9_-]{3,40}$")
    rerank: bool = False


class AnswerRequest(BaseModel):
    retrieval_id: str = Field(min_length=20, max_length=80)
    question: str = Field(min_length=3, max_length=MAX_QUERY_LENGTH)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _RATE_BUCKETS[client_ip]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if request.url.path.startswith("/api/"):
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            return _json_error(429, "Rate limit exceeded. Please wait before trying again.")
        bucket.append(now)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "public, max-age=300"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
    return response


def _json_error(status_code: int, detail: str):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> Dict[str, Any]:
    ready = index_ready("B_850_150")
    return {
        "status": "ok" if ready else "degraded",
        "scope": CLINICAL_SCOPE,
        "model": GROQ_MODEL,
        "index_ready": ready,
        "retrieval_baseline": "B_850_150",
    }


@app.post("/api/retrieve")
def retrieve_evidence(request: RetrieveRequest) -> Dict[str, Any]:
    question = " ".join(request.question.split())
    try:
        rows = retrieve(
            question,
            top_k=request.top_k,
            strategy=request.strategy,
            config_name=request.config,
            rerank=request.rerank,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="Retrieval failed. Check the local index and server logs.")

    retrieval_id = uuid.uuid4().hex
    _RETRIEVAL_CACHE[retrieval_id] = {"created": time.time(), "question": question, "rows": rows}
    # Keep cache bounded.
    if len(_RETRIEVAL_CACHE) > 200:
        oldest = sorted(_RETRIEVAL_CACHE.items(), key=lambda x: x[1]["created"])[:50]
        for key, _ in oldest:
            _RETRIEVAL_CACHE.pop(key, None)

    evidence = [_public_evidence(row) for row in rows]
    return {
        "retrieval_id": retrieval_id,
        "question": question,
        "scope": CLINICAL_SCOPE,
        "strategy": request.strategy,
        "config": request.config,
        "top_k": request.top_k,
        "rerank": request.rerank,
        "evidence": evidence,
    }


@app.post("/api/answer")
def answer(request: AnswerRequest) -> Dict[str, Any]:
    cached = _RETRIEVAL_CACHE.get(request.retrieval_id)
    if not cached or time.time() - cached["created"] > 300:
        raise HTTPException(status_code=410, detail="Retrieval context expired. Please run the search again.")

    question = " ".join(request.question.split())
    if question != cached["question"]:
        raise HTTPException(status_code=400, detail="Question does not match the retrieval context.")

    try:
        answer_text = generate_grounded_answer(question, cached["rows"])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=502, detail="The answer service could not complete the request.")

    return {
        "retrieval_id": request.retrieval_id,
        "question": question,
        "answer": answer_text,
        "scope": CLINICAL_SCOPE,
        "model": GROQ_MODEL,
    }


def _public_evidence(row: Dict[str, Any]) -> Dict[str, Any]:
    metadata = row["metadata"]
    return {
        "rank": row["rank"],
        "similarity": round(float(row.get("similarity", 0.0)), 4),
        "retrieval_method": row.get("retrieval_method"),
        "rerank_score": row.get("rerank_score"),
        "text": row["text"],
        "document_id": metadata.get("document_id"),
        "document_name": metadata.get("document_name"),
        "section": metadata.get("section"),
        "page_number": metadata.get("page_number"),
        "chunk_id": metadata.get("chunk_id"),
        "source": metadata.get("source"),
        "source_url": metadata.get("source_url"),
        "version": metadata.get("version"),
    }
