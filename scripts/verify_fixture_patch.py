"""Exercise a reviewed live fixture proposal through real approval APIs and native tests.

Execution is enabled only in this verification process, only for the labeled trusted fixture.
The user's .env and normal application's disabled-by-default policy are not changed.
"""

import json
import re
import sys
from unittest.mock import patch

from app.config import ROOT, settings
from app.db import Repository, load_record, session
from app.main import app
from fastapi.testclient import TestClient

run_id = sys.argv[1]
run = load_record(run_id, "agent")
with session() as db:
    repo = db.get(Repository, run.repository_id)
    if not repo or not repo.meta.get("fixture") or repo.name != "demo-fixture/rounding":
        raise SystemExit("This developer verification is restricted to the known seeded rounding fixture")
if run.status != "awaiting_review":
    raise SystemExit("Inspect a proposal at its actual review checkpoint before invoking verification")
if not set(run.data["patch"]["affected_paths"]) <= {"money.py", "test_money.py"}:
    raise SystemExit("This verification only accepts reviewed changes to the rounding fixture source/tests")

with TestClient(app) as client:
    response = client.post(f"/api/agents/runs/{run_id}/approve", json={"action": "review"})
    assert response.status_code == 200, response.text
    assert client.get(f"/api/agents/runs/{run_id}").json()["status"] == "approved"
    gate = client.post(
        f"/api/agents/runs/{run_id}/approve", json={"action": "test", "profile": "fixture_python"}
    )
    assert gate.status_code == 200, gate.text
    with patch(
        "app.patches.settings",
        return_value=settings().model_copy(update={"local_test_execution_enabled": True}),
    ):
        result = client.post(
            "/api/tests/run",
            json={"run_id": run_id, "profile": "fixture_python", "approval_id": gate.json()["approval_id"]},
        )
    assert result.status_code == 200, result.text
    output = result.json()
    assert output["exit_code"] == 0 and re.search(r"Ran \d+ tests?", output["stderr"]), output
    print(json.dumps(output, indent=2))
    (ROOT / "evaluation/results/live-fixture-test.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
