import json
import time
from datetime import datetime, timezone

from app.config import ROOT, settings
from app.db import save_record
from app.indexing import source_context
from app.retrieval import search


def evaluate(repository_id):
    cases = json.loads((ROOT / "evaluation/gold_queries.json").read_text())
    started = time.perf_counter()
    results = {}
    for mode in ("vector", "keyword", "hybrid"):
        rows = []
        for case in cases:
            result = search(repository_id, case["query"], mode, 5)
            relevant = [
                i + 1 for i, item in enumerate(result["evidence"]) if item["path"] in case["relevant_files"]
            ]
            valid = []
            for item in result["evidence"]:
                source = source_context(repository_id, item["path"], item["start_line"], item["end_line"])
                valid.append(source["content"] == item["content"])
            rows.append(
                {
                    "query": case["query"],
                    "hit_at_5": bool(relevant),
                    "reciprocal_rank": 1 / min(relevant) if relevant else 0,
                    "citation_validity": all(valid),
                    "latency_ms": result["latency_ms"],
                    "retrieved_files": [e["path"] for e in result["evidence"]],
                }
            )
        results[mode] = {
            "recall_at_5": sum(r["hit_at_5"] for r in rows) / len(rows),
            "mrr": sum(r["reciprocal_rank"] for r in rows) / len(rows),
            "cases": rows,
        }
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repository_id": repository_id,
        "embedding_model": settings().embedding_model,
        "cases": len(cases),
        "results": results,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "methodology": "File-level hit Recall@5 and first-relevant-chunk MRR; 10 hand-labeled banking questions. "
        "Small development set, not a held-out generalization benchmark. No Gemini calls.",
    }
    record_id = save_record("evaluation", data, repository_id=repository_id)
    folder = ROOT / "evaluation/results"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{record_id}.json").write_text(json.dumps(data, indent=2))
    return {"id": record_id, **data}
