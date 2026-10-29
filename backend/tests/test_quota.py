from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from app import llm
from app.config import Settings
from pydantic import SecretStr


def test_missing_key_never_opens_database(monkeypatch):
    monkeypatch.setattr(llm, "settings", lambda: Settings(_env_file=None, gemini_api_key=""))
    with pytest.raises(ValueError, match="key missing"):
        llm.reserve_call()


def test_daily_budget_fails_before_provider(monkeypatch):
    config = Settings(_env_file=None, gemini_api_key=SecretStr("test-key"), gemini_daily_request_budget=2)
    monkeypatch.setattr(llm, "settings", lambda: config)

    @contextmanager
    def db_session():
        yield SimpleNamespace(execute=lambda *_: None, scalar=lambda *_: 2)

    monkeypatch.setattr(llm, "session", db_session)
    with pytest.raises(ValueError, match="daily.*exhausted"):
        llm.reserve_call()


def test_analysis_budget_fails_before_provider(monkeypatch):
    config = Settings(_env_file=None, gemini_api_key=SecretStr("test-key"), gemini_max_calls_per_analysis=1)
    monkeypatch.setattr(llm, "settings", lambda: config)
    counts = iter([0, 1])

    @contextmanager
    def db_session():
        yield SimpleNamespace(execute=lambda *_: None, scalar=lambda *_: next(counts))

    monkeypatch.setattr(llm, "session", db_session)
    with pytest.raises(ValueError, match="Analysis call budget"):
        llm.reserve_call("test-run")
