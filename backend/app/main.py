import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app import agent
from app.config import redact, settings
from app.db import Record, Repository, asdict, engine, load_record, save_record, session
from app.indexing import index_repository
from app.llm import ask, models
from app.mcp_client import call, issues
from app.patches import run_tests
from app.retrieval import recorded_search
from app.safety import github_url

log = logging.getLogger("patchpilot")


@asynccontextmanager
async def lifespan(app):
    # A process restart must not leave abandoned in-process jobs permanently 'running'.
    try:
        with session() as db:
            for repo in db.scalars(
                select(Repository).where(Repository.status.in_(["queued", "cloning", "embedding"]))
            ):
                repo.status, repo.error = "error", "Indexing was interrupted by restart; retry indexing"
            for run in db.scalars(
                select(Record).where(
                    Record.kind == "agent", Record.status.in_(["running", "resuming", "testing"])
                )
            ):
                run.status, run.data = (
                    "interrupted",
                    run.data
                    | {
                        "error": "Process restarted during operation; inspect trace and start a new investigation"
                    },
                )
    except Exception:
        log.warning("Database schema not ready; run setup/migrations before using the workspace")
    yield
    engine().dispose()


app = FastAPI(title="PatchPilot AI", version="0.1.0", lifespan=lifespan)
origins = settings().cors_allowed_origins.split(",") + ["http://127.0.0.1:3000"]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
)
recent = defaultdict(deque)


@app.middleware("http")
async def local_guard(request: Request, call_next):
    if request.headers.get("host", "").split(":")[0] not in {"localhost", "127.0.0.1", "testserver"}:
        return JSONResponse({"detail": "Localhost only"}, status_code=403)
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and origin not in origins:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        if "application/json" not in request.headers.get("content-type", ""):
            return JSONResponse({"detail": "Use application/json"}, status_code=415)
        if int(request.headers.get("content-length", "0")) > 64000:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        key = request.client.host if request.client else "local"
        bucket = recent[key]
        while bucket and time.monotonic() - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= 40:
            return JSONResponse({"detail": "Too many operations; wait a minute"}, status_code=429)
        bucket.append(time.monotonic())
    return await call_next(request)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({"detail": redact(str(exc))}, status_code=400)


@app.exception_handler(Exception)
async def unexpected(request, exc):
    log.error("Operation failed: %s", redact(str(exc)))
    return JSONResponse(
        {"detail": "Service unavailable. Check Settings diagnostics and local configuration."},
        status_code=503,
    )


class RepoInput(BaseModel):
    url: str = Field(max_length=300)


class Query(BaseModel):
    repository_id: str
    query: str = Field(min_length=2, max_length=2000)
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"
    limit: int = Field(default=5, ge=1, le=20)


class RunInput(BaseModel):
    repository_id: str
    issue: str = Field(min_length=8, max_length=10000)
    issue_number: int | None = Field(default=None, ge=1)


class Decision(BaseModel):
    action: Literal["review", "test", "draft_pr"] = "review"
    profile: Literal["fixture_python", "banking_maven"] | None = None


class TestInput(BaseModel):
    run_id: str
    approval_id: str
    profile: Literal["fixture_python", "banking_maven"]


class DraftInput(BaseModel):
    run_id: str
    approval_id: str


def background_index(repo_id):
    try:
        index_repository(repo_id)
    except Exception as exc:
        log.error("Indexing failed: %s", redact(str(exc)))


@app.get("/api/health")
@app.get("/api/config/status")
def health():
    cfg = settings()
    status = {
        "backend": "ok",
        "database": "unavailable",
        "pgvector": None,
        "gemini_configured": bool(cfg.gemini_api_key.get_secret_value()),
        "gemini_model": cfg.gemini_model,
        "github_configured": bool(cfg.github_token.get_secret_value()),
        "github_remote_write_enabled": cfg.github_remote_write_enabled,
        "local_test_execution_enabled": cfg.local_test_execution_enabled,
        "embedding_model": cfg.embedding_model,
        "version": "0.1.0",
    }
    try:
        with engine().connect() as conn:
            status["pgvector"] = conn.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            )
            status["database"] = "connected"
    except Exception:
        status["database"] = "unavailable: check local PostgreSQL and .env"
    return status


@app.get("/api/config/models")
def available_models():
    return {"models": models()}


@app.get("/api/repositories")
def repositories():
    with session() as db:
        return [asdict(r) for r in db.scalars(select(Repository).order_by(Repository.created_at.desc()))]


@app.post("/api/repositories")
def add_repo(body: RepoInput):
    url, name = github_url(body.url)
    with session() as db:
        existing = db.scalar(select(Repository).where(Repository.url == url))
        if existing:
            return asdict(existing)
        repo = Repository(url=url, name=name)
        db.add(repo)
        db.flush()
        return asdict(repo)


@app.post("/api/repositories/{repo_id}/index")
def start_index(repo_id: str, background: BackgroundTasks):
    with session() as db:
        repo = db.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, "Repository not found")
        if repo.status in {"queued", "cloning", "embedding"}:
            raise ValueError("Repository indexing is already active")
        repo.status = "queued"
    background.add_task(background_index, repo_id)
    return {"status": "queued"}


@app.get("/api/repositories/{repo_id}/index-status")
def index_status(repo_id: str):
    with session() as db:
        repo = db.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, "Repository not found")
        return asdict(repo)


@app.post("/api/retrieval/search")
def retrieve(body: Query):
    return recorded_search(body.repository_id, body.query, body.mode, body.limit)


@app.post("/api/retrieval/ask")
def rag_answer(body: Query):
    return ask(body.repository_id, body.query)


@app.get("/api/github/issues")
async def github_issues(repository_id: str):
    with session() as db:
        repo = db.get(Repository, repository_id)
        if not repo:
            raise ValueError("Repository not found")
        name = repo.name
    return await issues(name)


@app.post("/api/config/mcp-check")
async def mcp_check(body: Query):
    return await call(
        "custom", "get_retrieval_evidence", {"repository_id": body.repository_id, "query": body.query}
    )


@app.get("/api/agents/runs")
def runs():
    with session() as db:
        return [
            asdict(r)
            for r in db.scalars(
                select(Record).where(Record.kind == "agent").order_by(Record.created_at.desc()).limit(30)
            )
        ]


@app.post("/api/agents/runs")
def create_run(body: RunInput, background: BackgroundTasks):
    with session() as db:
        repo = db.get(Repository, body.repository_id)
        if not repo or repo.status != "ready":
            raise ValueError("Repository must be indexed and ready")
        active = db.scalar(select(Record).where(Record.kind == "agent", Record.status == "running"))
        if active:
            raise ValueError("An analysis is already running")
    run_id = save_record("agent", body.model_dump(), "running", body.repository_id)
    background.add_task(agent.execute, run_id)
    return {"id": run_id, "status": "running"}


@app.get("/api/agents/runs/{run_id}")
def get_run(run_id: str):
    run = load_record(run_id, "agent")
    with session() as db:
        steps = [
            asdict(s)
            for s in db.scalars(
                select(Record)
                .where(Record.kind == "step", Record.data["run_id"].astext == run_id)
                .order_by(Record.created_at)
            )
        ]
    test = asdict(load_record(run.data["test_id"], "test")) if run.data.get("test_id") else None
    return asdict(run) | {"steps": steps, "test": test}


@app.get("/api/agents/runs/{run_id}/events")
def events(run_id: str):
    # Bounded polling contract: returns persisted stages only. UI polls while running.
    return get_run(run_id)


@app.post("/api/agents/runs/{run_id}/approve")
def approve(run_id: str, body: Decision, background: BackgroundTasks):
    with session() as db:
        run = db.scalar(select(Record).where(Record.id == run_id, Record.kind == "agent").with_for_update())
        if not run:
            raise ValueError("Run not found")
        required = {"review": "awaiting_review", "test": "approved", "draft_pr": "test_passed"}[body.action]
        if run.status != required:
            raise ValueError(f"Action requires state {required}; current state is {run.status}")
        if body.action == "test" and not body.profile:
            raise ValueError("Choose the exact test profile")
        if body.action == "review":
            run.status = "resuming"
    approval_id = save_record(
        "approval",
        {"run_id": run_id, "action": body.action, "profile": body.profile, "actor": "localhost_user"},
        "approved",
    )
    save_record("audit", {"run_id": run_id, "action": "approve_" + body.action, "approval_id": approval_id})
    if body.action == "review":
        background.add_task(agent.execute, run_id, "approve")
    return {"approval_id": approval_id}


@app.post("/api/agents/runs/{run_id}/reject")
def reject(run_id: str, background: BackgroundTasks):
    with session() as db:
        run = db.scalar(select(Record).where(Record.id == run_id).with_for_update())
        if not run or run.kind != "agent" or run.status != "awaiting_review":
            raise ValueError("Run is not awaiting review")
        run.status = "resuming"
    save_record("audit", {"run_id": run_id, "action": "reject"})
    background.add_task(agent.execute, run_id, "reject")
    return {"status": "resuming"}


@app.post("/api/agents/runs/{run_id}/cancel")
def cancel(run_id: str):
    with session() as db:
        run = db.scalar(select(Record).where(Record.id == run_id, Record.kind == "agent").with_for_update())
        if not run or run.status not in {"running", "awaiting_review"}:
            raise ValueError("Only running or waiting investigations may be cancelled")
        run.status = "cancelled"
    save_record("audit", {"run_id": run_id, "action": "cancel"})
    return {"status": "cancelled", "detail": "Cancellation takes effect at the next stage boundary"}


@app.post("/api/tests/run")
def test_run(body: TestInput):
    return run_tests(body.run_id, body.profile, body.approval_id)


@app.post("/api/pull-requests/draft")
def draft(body: DraftInput):
    from app.publishing import publish_draft

    return publish_draft(body.run_id, body.approval_id)


class EvalInput(BaseModel):
    repository_id: str


@app.post("/api/evaluations/run")
def run_evaluation(body: EvalInput):
    from app.evaluation import evaluate

    return evaluate(body.repository_id)


@app.get("/api/evaluations/latest")
def latest_evaluation():
    with session() as db:
        row = db.scalar(select(Record).where(Record.kind == "evaluation").order_by(Record.created_at.desc()))
        return asdict(row) if row else None


@app.get("/api/metrics")
def metrics():
    with session() as db:
        counts = dict(db.execute(select(Record.kind, func.count()).group_by(Record.kind)).all())
        outcomes = dict(
            db.execute(
                select(Record.status, func.count()).where(Record.kind == "agent").group_by(Record.status)
            ).all()
        )
        today = db.scalar(
            select(func.count())
            .select_from(Record)
            .where(
                Record.kind == "llm_call",
                Record.created_at
                >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
            )
        )
    return {
        "counts": counts,
        "agent_outcomes": outcomes,
        "gemini_requests_today": today,
        "gemini_daily_budget": settings().gemini_daily_request_budget,
    }
