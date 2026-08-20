from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional

import chromadb
from chromadb.config import Settings
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.documents import Document

from src.config import APPROVED_DOCUMENT_IDS, COLLECTION_NAME, DB_DIR, EMBEDDING_MODEL


def get_embeddings():
    return FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)


def _get_client():
    return chromadb.PersistentClient(
        path=str(DB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def collection_name(config_name: str = "B_850_150") -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", config_name)
    return f"{COLLECTION_NAME}_{safe}"


def build_vector_store(chunks: List[Dict], config_name: str = "B_850_150"):
    DB_DIR.mkdir(parents=True, exist_ok=True)
    embeddings = get_embeddings()
    client = _get_client()
    name = collection_name(config_name)

    try:
        client.delete_collection(name)
    except Exception:
        pass

    collection = client.create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "config_name": config_name},
    )

    documents = [Document(page_content=x["text"], metadata=x["metadata"]) for x in chunks]
    texts = [d.page_content for d in documents]
    vectors = embeddings.embed_documents(texts)

    collection.add(
        ids=[x["id"] for x in chunks],
        documents=texts,
        embeddings=vectors,
        metadatas=[x["metadata"] for x in chunks],
    )
    return collection


def build_experiment_indexes(chunks_by_config: Dict[str, List[Dict]]):
    return {name: build_vector_store(chunks, name) for name, chunks in chunks_by_config.items()}


def open_collection(config_name: str = "B_850_150"):
    client = _get_client()
    name = collection_name(config_name)
    try:
        return client.get_collection(name)
    except Exception as exc:
        raise RuntimeError(
            f"The Chroma vector database for {config_name} is not ready. Run `python -m src.main index-day2`."
        ) from exc


def index_ready(config_name: str = "B_850_150") -> bool:
    if not DB_DIR.exists():
        return False
    try:
        collection = _get_client().get_collection(collection_name(config_name))
        return collection.count() > 0
    except Exception:
        return False


def _approved_where():
    return {"document_id": {"$in": sorted(APPROVED_DOCUMENT_IDS)}}


def _safe_rows(result) -> List[Dict]:
    rows = []
    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for i in range(len(ids)):
        md = metas[i] or {}
        if md.get("document_id") not in APPROVED_DOCUMENT_IDS:
            continue
        distance = float(distances[i]) if distances else 0.0
        rows.append({
            "rank": len(rows) + 1,
            "similarity": max(-1.0, min(1.0, 1.0 - distance)),
            "distance": distance,
            "text": docs[i],
            "metadata": md,
            "retrieval_method": "semantic",
        })
    return rows


def semantic_retrieve(query: str, top_k: int = 5, config_name: str = "B_850_150") -> List[Dict]:
    if not query.strip():
        return []
    collection = open_collection(config_name)
    q_vector = get_embeddings().embed_query(query)
    result = collection.query(
        query_embeddings=[q_vector],
        n_results=top_k,
        where=_approved_where(),
        include=["documents", "metadatas", "distances"],
    )
    return _safe_rows(result)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _bm25_scores(query: str, docs: List[str]) -> List[float]:
    q_tokens = set(_tokenize(query))
    if not q_tokens or not docs:
        return [0.0] * len(docs)
    tokenized = [_tokenize(d) for d in docs]
    df = Counter()
    for tokens in tokenized:
        for token in set(tokens):
            df[token] += 1
    n = len(docs)
    avgdl = sum(len(t) for t in tokenized) / max(n, 1)
    k1, b = 1.5, 0.75
    scores = []
    for tokens in tokenized:
        counts = Counter(tokens)
        dl = len(tokens)
        score = 0.0
        for term in q_tokens:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avgdl, 1))))
        scores.append(score)
    return scores


def keyword_retrieve(query: str, top_k: int = 5, config_name: str = "B_850_150") -> List[Dict]:
    collection = open_collection(config_name)
    data = collection.get(where=_approved_where(), include=["documents", "metadatas"])
    docs = data.get("documents", [])
    metas = data.get("metadatas", [])
    ids = data.get("ids", [])
    scores = _bm25_scores(query, docs)
    ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:top_k]
    max_score = max((scores[i] for i in ranked), default=1.0) or 1.0
    rows = []
    for rank, i in enumerate(ranked, start=1):
        rows.append({
            "rank": rank,
            "similarity": round(scores[i] / max_score, 6),
            "keyword_score": scores[i],
            "distance": None,
            "text": docs[i],
            "metadata": metas[i],
            "retrieval_method": "keyword",
        })
    return rows


def _merge_by_id(*groups: Iterable[Dict]) -> Dict[str, Dict]:
    merged = {}
    for group in groups:
        for row in group:
            merged[row["metadata"]["chunk_id"]] = row
    return merged


def hybrid_retrieve(query: str, top_k: int = 5, config_name: str = "B_850_150") -> List[Dict]:
    candidate_k = min(10, max(top_k * 2, 6))
    semantic = semantic_retrieve(query, candidate_k, config_name)
    keyword = keyword_retrieve(query, candidate_k, config_name)
    merged = _merge_by_id(semantic, keyword)

    sem_scores = {r["metadata"]["chunk_id"]: r["similarity"] for r in semantic}
    key_scores = {r["metadata"]["chunk_id"]: r["similarity"] for r in keyword}
    ranked = []
    for cid, row in merged.items():
        hybrid_score = 0.70 * sem_scores.get(cid, 0.0) + 0.30 * key_scores.get(cid, 0.0)
        copy = dict(row)
        copy["similarity"] = round(hybrid_score, 6)
        copy["retrieval_method"] = "hybrid"
        ranked.append(copy)
    ranked.sort(key=lambda x: x["similarity"], reverse=True)
    for idx, row in enumerate(ranked[:top_k], start=1):
        row["rank"] = idx
    return ranked[:top_k]


def heuristic_rerank(query: str, rows: List[Dict], top_k: int = 5) -> List[Dict]:
    q_terms = set(_tokenize(query))
    rescored = []
    for row in rows:
        text_terms = set(_tokenize(row["text"]))
        overlap = len(q_terms & text_terms) / max(len(q_terms), 1)
        section_bonus = 0.05 if any(t in row["metadata"].get("section", "").lower() for t in list(q_terms)[:4]) else 0.0
        score = 0.85 * float(row.get("similarity", 0.0)) + 0.10 * overlap + section_bonus
        copy = dict(row)
        copy["rerank_score"] = round(score, 6)
        copy["retrieval_method"] = f"{row.get('retrieval_method', 'semantic')}+heuristic_rerank"
        rescored.append(copy)
    rescored.sort(key=lambda x: x["rerank_score"], reverse=True)
    for idx, row in enumerate(rescored[:top_k], start=1):
        row["rank"] = idx
    return rescored[:top_k]


def retrieve(query: str, top_k: int = 5, config_name: str = "B_850_150", strategy: str = "semantic", rerank: bool = False):
    if strategy == "semantic":
        rows = semantic_retrieve(query, top_k, config_name)
    elif strategy == "keyword":
        rows = keyword_retrieve(query, top_k, config_name)
    elif strategy == "hybrid":
        rows = hybrid_retrieve(query, top_k, config_name)
    else:
        raise ValueError("strategy must be semantic, keyword, or hybrid")
    if rerank:
        rows = heuristic_rerank(query, rows, top_k)
    return rows
