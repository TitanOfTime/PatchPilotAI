import re
import time
from functools import lru_cache
from urllib.parse import quote

from sqlalchemy import func, select

from app.db import Chunk, Repository, save_record, session
from app.indexing import embed


@lru_cache(maxsize=128)
def query_embedding(model, query):
    return embed([query])[0]


def search(repository_id, query, mode="hybrid", limit=5):
    if mode not in {"hybrid", "vector", "keyword"} or not 1 <= limit <= 20:
        raise ValueError("Invalid retrieval mode or limit")
    started = time.perf_counter()
    with session() as db:
        repo = db.get(Repository, repository_id)
        if not repo or not repo.sha:
            raise ValueError("Index this repository first")
        if (
            repo.meta.get("embedding_model")
            != __import__("app.config", fromlist=["settings"]).settings().embedding_model
        ):
            raise ValueError("Embedding model changed; reindex repository")
        base = select(Chunk).where(Chunk.repository_id == repository_id, Chunk.sha == repo.sha)
        vectors, lexical = [], []
        distances = {}
        if mode != "keyword":
            vector = query_embedding(repo.meta["embedding_model"], query)
            rows = db.execute(
                base.add_columns(Chunk.embedding.cosine_distance(vector).label("distance"))
                .order_by("distance")
                .limit(30)
            ).all()
            vectors = [r[0] for r in rows]
            distances = {r[0].id: float(r[1]) for r in rows}
        if mode != "vector":
            tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]{1,}", query)[:32]
            # OR terms avoids natural-language stop words forcing every word to occur.
            tsquery = func.to_tsquery("english", " | ".join(tokens) or "emptyquery")
            lexical = list(
                db.scalars(
                    base.where(Chunk.search.op("@@")(tsquery))
                    .order_by(func.ts_rank_cd(Chunk.search, tsquery).desc())
                    .limit(30)
                )
            )
        scores, chunks, ranks = {}, {}, {}
        for name, results in [("vector", vectors), ("keyword", lexical)]:
            for rank, chunk in enumerate(results, 1):
                chunks[chunk.id] = chunk
                scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (60 + rank)
                ranks.setdefault(chunk.id, {})[name] = rank
        selected = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
        evidence = []
        for key in selected:
            chunk = chunks[key]
            evidence.append(
                {
                    "id": key,
                    "path": chunk.path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "sha": chunk.sha,
                    "content": chunk.content,
                    "score": scores[key],
                    "ranks": ranks[key],
                    "cosine_similarity": 1 - distances[key] if key in distances else None,
                    "url": f"{repo.url}/blob/{chunk.sha}/{quote(chunk.path)}#L{chunk.start_line}-L{chunk.end_line}",
                }
            )
    return {
        "evidence": evidence,
        "mode": mode,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def recorded_search(repository_id, query, mode="hybrid", limit=5):
    result = search(repository_id, query, mode, limit)
    result["record_id"] = save_record("retrieval", {"query": query, **result}, repository_id=repository_id)
    return result
