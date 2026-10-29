import pytest
from app import patches
from app.config import Settings
from app.main import app
from fastapi.testclient import TestClient


def test_execution_disabled_before_any_db_or_process_access(monkeypatch):
    monkeypatch.setattr(
        patches, "settings", lambda: Settings(_env_file=None, local_test_execution_enabled=False)
    )
    with pytest.raises(ValueError, match="disabled"):
        patches.run_tests("invented", "fixture_python", "invented")


def test_cross_origin_and_non_json_post_rejected():
    with TestClient(app) as client:
        result = client.post(
            "/api/repositories",
            json={"url": "https://github.com/a/b"},
            headers={"Origin": "https://attacker.invalid"},
        )
        assert result.status_code == 403
        assert client.post("/api/repositories", data="url=x").status_code == 415


def test_dns_rebinding_host_rejected():
    with TestClient(app) as client:
        assert client.get("/api/health", headers={"host": "evil.invalid"}).status_code == 403


def test_openapi_and_input_validation():
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert (
            client.post("/api/retrieval/search", json={"repository_id": "id", "query": "x"}).status_code
            == 422
        )


def test_config_never_returns_keys():
    with TestClient(app) as client:
        payload = client.get("/api/config/status").json()
        assert "gemini_api_key" not in payload
        assert "github_token" not in payload
        assert "database_password" not in payload
