"""Explicit live check. Uses up to five Gemini requests; never publishes to GitHub.

Run only after native DB migration and indexing. Records real results; exits on failure.
"""

import json
from datetime import datetime, timezone

from app.agent import execute
from app.config import ROOT, settings
from app.db import Repository, load_record, save_record, session
from app.evaluation import evaluate
from app.llm import ask
from app.mcp_client import call_sync
from sqlalchemy import select

with session() as db:
    banking = db.scalar(select(Repository).where(Repository.url == settings().banking_repository_url))
    fixture = db.scalar(select(Repository).where(Repository.name == "demo-fixture/rounding"))
    if not banking or banking.status != "ready" or not fixture or fixture.status != "ready":
        raise SystemExit("Index Banking App and register fixture first")

results = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "model": settings().gemini_model,
    "banking_sha": banking.sha,
    "questions": [],
}
for question in [
    "Where are payment webhooks and idempotency handled?",
    "How are JWT access tokens generated and validated?",
    "How does the transfer saga compensate failed transfers?",
]:
    answer = ask(banking.id, question)
    if answer.get("insufficient_evidence") or not answer.get("evidence_ids"):
        raise SystemExit("Question did not produce a grounded answer: " + question)
    results["questions"].append({"question": question, **answer})
    print("Grounded answer verified:", question)

results["github_mcp"] = call_sync(
    "github", "get_file_contents", {"owner": "TitanOfTime", "repo": "TestBankingApp", "path": "README.md"}
)
results["custom_mcp"] = call_sync(
    "custom",
    "get_source_context",
    {
        "repository_id": banking.id,
        "file_path": "backend/gateway-service/src/main/java/com/fintech/gateway/filter/IdempotencyFilter.java",
        "start_line": 35,
        "end_line": 65,
    },
)
results["evaluation"] = evaluate(banking.id)

for repo, issue in [
    (
        fixture,
        'Manual demo fixture bug: cents("1.005") returns 100 instead of 101. '
        "Use explicit Decimal ROUND_HALF_UP for positive and negative half-cent ties. "
        "Keep or add regression tests for these edge cases.",
    ),
    (
        banking,
        'Manual bug report: In gateway IdempotencyFilter, path.contains("/ws") '
        'and path.contains("/webhook/stripe") exempt unrelated state-changing routes if '
        "those substrings appear anywhere in the URI. Limit exemptions to the actual "
        "WebSocket endpoint/subpaths and the exact Stripe webhook path. "
        "Use a minimal evidence-backed fix and add an appropriate focused regression test.",
    ),
]:
    run_id = save_record("agent", {"issue": issue, "issue_number": None}, "running", repo.id)
    execute(run_id)
    run = load_record(run_id, "agent")
    results.setdefault("agent_runs", []).append(
        {"id": run_id, "repository": repo.name, "status": run.status, "data": run.data}
    )
    print("Live investigation:", repo.name, run.status, run_id)

folder = ROOT / "evaluation/results"
folder.mkdir(exist_ok=True, parents=True)
(folder / "live-demo.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print("Saved actual outputs: evaluation/results/live-demo.json")
if any(run["status"] != "awaiting_review" for run in results.get("agent_runs", [])):
    raise SystemExit("At least one live proposal needs investigation; inspect actual recorded error")
