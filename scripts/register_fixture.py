"""Explicit, labeled deterministic fixture. Separate from Banking App evidence."""

import shutil

from app.config import ROOT
from app.db import Repository, session
from app.indexing import index_repository
from app.safety import REPOS, git
from sqlalchemy import select

with session() as db:
    repo = db.scalar(select(Repository).where(Repository.name == "demo-fixture/rounding"))
    if not repo:
        repo = Repository(name="demo-fixture/rounding", url="fixture://rounding", meta={"fixture": True})
        db.add(repo)
        db.flush()
    repo_id = repo.id
root = REPOS / repo_id
if not root.exists():
    shutil.copytree(ROOT / "demo_fixtures/rounding", root)
    git(["init"], root)
    git(["add", "."], root)
    git(
        [
            "-c",
            "user.name=PatchPilot Fixture",
            "-c",
            "user.email=fixture@localhost",
            "commit",
            "-m",
            "Seed rounding defect",
        ],
        root,
    )
index_repository(repo_id)
print("Demo fixture indexed:", repo_id)
