"""Opt in only against the isolated local PatchPilot database: PATCHPILOT_INTEGRATION=1."""

import os

import pytest
from app import agent
from app.config import settings
from app.db import Repository, engine, load_record, save_record, session
from app.indexing import embed, source_context
from app.mcp_client import call
from app.patches import run_tests
from app.retrieval import search
from sqlalchemy import select, text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("PATCHPILOT_INTEGRATION") != "1", reason="Dedicated DB integration opt-in"),
]


def fixture_repo():
    with session() as db:
        repo = db.scalar(select(Repository).where(Repository.name == "demo-fixture/rounding"))
        assert repo and repo.status == "ready", "Run scripts/register_fixture.py first"
        return repo


def test_native_database_vector_and_dimension():
    with engine().connect() as conn:
        assert conn.scalar(text("SELECT current_database()")) == "patchpilot_ai"
        assert conn.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        assert conn.scalar(text("SELECT vector_dims(embedding) FROM code_chunks LIMIT 1")) == 384
    assert len(embed(["genuine local PyTorch inference"])[0]) == 384


def test_banking_three_queries_and_valid_citations():
    with session() as db:
        repo = db.scalar(select(Repository).where(Repository.url == settings().banking_repository_url))
        assert repo and repo.chunks > 0
    for query, expected in [
        ("Stripe webhook payment events", "StripeWebhookController.java"),
        ("Idempotency-Key header duplicate replay", "IdempotencyFilter.java"),
        ("JWT access token generation", "JwtService.java"),
    ]:
        result = search(repo.id, query)
        assert any(e["path"].endswith(expected) for e in result["evidence"])
        for evidence in result["evidence"]:
            source = source_context(repo.id, evidence["path"], evidence["start_line"], evidence["end_line"])
            assert source["content"] == evidence["content"]


async def test_custom_mcp_reads_actual_source():
    repo = fixture_repo()
    result = await call("custom", "get_source_context", {"repository_id": repo.id, "file_path": "money.py"})
    assert "def cents" in result["result"]["content"]


def test_postgres_checkpoint_and_approved_fixture_execution(monkeypatch):
    """Fake only Gemini proposal; real RAG, custom MCP, PostgreSQL checkpoint, diff and native tests."""
    repo = fixture_repo()
    run_id = save_record(
        "agent",
        {"issue": "cents 1.005 returns 100 instead of 101. Fix half cent rounding.", "origin": "integration_test"},
        "running",
        repo.id,
    )
    from app.llm import Proposal

    proposal = Proposal(
        diagnosis="Fixture: Decimal round uses ties-to-even.",
        confidence="fixture",
        plan=["Use explicit ROUND_HALF_UP", "Keep regression tests"],
        evidence_ids=[],
        edits=[
            {
                "path": "money.py",
                "old": "from decimal import Decimal",
                "new": "from decimal import Decimal, ROUND_HALF_UP",
            }
        ],
        test_plan="fixture_python",
    )
    # One exact replacement of the whole file keeps one-edit-per-file invariant.
    original = source_context(repo.id, "money.py")["content"]
    updated = original.replace(
        "from decimal import Decimal", "from decimal import Decimal, ROUND_HALF_UP"
    ).replace(
        "int(round(Decimal(amount) * 100))",
        'int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))',
    )
    proposal.edits[0].old, proposal.edits[0].new = original, updated
    monkeypatch.setattr(agent, "structured", lambda *_: proposal)
    agent.execute(run_id)
    assert load_record(run_id).status == "awaiting_review"
    with pytest.raises(ValueError):
        run_tests(run_id, "fixture_python", "no-approval")
    # New graph object / DB connection resumes actual durable checkpoint.
    agent.execute(run_id, "approve")
    assert load_record(run_id).status == "approved"
    approval_id = save_record(
        "approval", {"run_id": run_id, "action": "test", "profile": "fixture_python"}, "approved"
    )
    monkeypatch.setattr(
        "app.patches.settings", lambda: settings().model_copy(update={"local_test_execution_enabled": True})
    )
    result = run_tests(run_id, "fixture_python", approval_id)
    assert result["exit_code"] == 0
    assert "Ran 2 tests" in result["stderr"]
    with pytest.raises(ValueError):
        run_tests(run_id, "fixture_python", approval_id)
