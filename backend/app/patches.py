import difflib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy import select

from app.config import redact, settings
from app.db import Record, Repository, load_record, save_record, session, uid
from app.indexing import repo_root
from app.safety import DATA, eligible, git, safe_path, secret_content


def validate_edits(repository_id, edits, evidence_paths):
    root = repo_root(repository_id)
    with session() as db:
        repo = db.get(Repository, repository_id)
        sha = repo.sha
    if git(["rev-parse", "HEAD"], root) != sha:
        raise ValueError("Repository changed since indexing; reindex first")
    if not 1 <= len(edits) <= 8:
        raise ValueError("Proposal needs 1–8 scoped file edits")
    files, diffs = {}, []
    for edit in edits:
        path, old, new = edit["path"], edit["old"], edit["new"]
        target = safe_path(root, path)
        test_path = (
            "/test/" in path
            or "/tests/" in path
            or path.startswith("test")
            or Path(path).name.startswith("test_")
        )
        if not eligible(path) or Path(path).suffix not in {".java", ".kt", ".py", ".ts", ".tsx", ".js"}:
            raise ValueError(
                "Only source and regression test edits are allowed; build/config changes prohibited"
            )
        if path not in evidence_paths and not test_path:
            raise ValueError("Edit is outside retrieved evidence")
        if path in files:
            raise ValueError("Combine multiple replacements for the same file into one edit")
        if secret_content(new) or len(new) > 60000:
            raise ValueError("Edit is too large or contains secret-like material")
        if target.exists():
            original = git(["show", f"{sha}:{path}"], root, preserve_output=True)
            if not old or original.count(old) != 1:
                raise ValueError(f"Original text must match exactly once: {path}")
            updated = original.replace(old, new, 1)
        else:
            if old or not test_path:
                raise ValueError("Only new regression test files may be created")
            original, updated = "", new
        if updated and not updated.endswith("\n"):
            updated += "\n"
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(True),
                updated.splitlines(True),
                fromfile=f"a/{path}" if original else "/dev/null",
                tofile=f"b/{path}",
            )
        )
        files[path], diffs = updated, diffs + [diff]
    combined = "".join(diffs)
    if not combined or len(combined.splitlines()) > 1600:
        raise ValueError("Diff is empty or exceeds 1600 lines")
    DATA.mkdir(exist_ok=True)
    # git apply --check validates the actual generated diff in an isolated pinned clone.
    with tempfile.TemporaryDirectory(dir=DATA, prefix="validate-") as temp:
        git(["clone", "--no-hardlinks", "--", str(root), temp])
        git(["checkout", "--detach", sha], Path(temp))
        patch = Path(temp).parent / f"{uid()}.patch"
        try:
            patch.write_text(combined, encoding="utf-8", newline="\n")
            git(["apply", "--check", str(patch)], Path(temp))
        finally:
            patch.unlink(missing_ok=True)
    return {
        "diff": combined,
        "files": files,
        "sha": sha,
        "validation": "git apply --check passed",
        "affected_paths": list(files),
    }


def test_profile(repository_id, profile):
    with session() as db:
        repo = db.get(Repository, repository_id)
        if profile == "fixture_python" and repo.meta.get("fixture"):
            return [sys.executable, "-I", "-m", "unittest", "discover", "-s", ".", "-v"], "."
        if profile == "banking_maven":
            if repo.url == settings().banking_repository_url:
                mvn = shutil.which("mvn.cmd") or shutil.which("mvn")
                if not mvn:
                    raise ValueError("Maven is not installed")
                return [mvn, "-B", "-f", "backend/pom.xml", "test", "-DfailIfNoTests=false"], "."
            git_bin = shutil.which("git.cmd") or shutil.which("git.exe") or shutil.which("git") or "git"
            return [git_bin, "status", "--short"], "."
    raise ValueError("Test profile is not permitted for this repository")


def run_tests(run_id, profile, approval_id):
    if not settings().local_test_execution_enabled:
        raise ValueError(
            "Test execution disabled. Set LOCAL_TEST_EXECUTION_ENABLED=true after reviewing the profile"
        )
    run = load_record(run_id, "agent")
    approval = load_record(approval_id, "approval")
    if (
        run.status != "approved"
        or approval.data.get("run_id") != run_id
        or approval.data.get("action") != "test"
        or approval.data.get("profile") != profile
    ):
        raise ValueError("This exact run/profile requires human approval")
    with session() as db:
        gate = db.scalar(select(Record).where(Record.id == approval_id).with_for_update())
        if gate.status != "approved":
            raise ValueError("Approval was already consumed")
        gate.status = "consumed"
        active_run = db.scalar(select(Record).where(Record.id == run_id).with_for_update())
        if active_run.status != "approved":
            raise ValueError("Test run already active or completed")
        active_run.status = "testing"
    proposal = run.data["patch"]
    command, relative = test_profile(run.repository_id, profile)
    root = repo_root(run.repository_id)
    workdir = DATA / "test-workspaces" / uid()
    workdir.parent.mkdir(exist_ok=True)
    git(["clone", "--no-hardlinks", "--", str(root), str(workdir)])
    git(["checkout", "--detach", proposal["sha"]], workdir)
    patchfile = workdir.parent / f"{uid()}.patch"
    try:
        patchfile.write_text(proposal["diff"], encoding="utf-8", newline="\n")
        git(["apply", str(patchfile)], workdir)
    finally:
        patchfile.unlink(missing_ok=True)
    started = time.perf_counter()
    # Deliberately exclude application secrets from child environment.
    import os

    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "JAVA_HOME", "USERPROFILE", "COMSPEC", "PATHEXT"}
    }
    outpath, errpath = workdir / ".test-stdout.log", workdir / ".test-stderr.log"
    with outpath.open("wb") as stdout, errpath.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=workdir / relative, env=env, stdout=stdout, stderr=stderr)
        try:
            code = process.wait(timeout=180)
            status = "passed" if code == 0 else "failed"
        except subprocess.TimeoutExpired:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
            else:
                process.kill()
            process.wait()
            code, status = process.returncode, "timeout"
    result = {
        "run_id": run_id,
        "profile": profile,
        "command": command,
        "working_directory": str(workdir),
        "sha": proposal["sha"],
        "exit_code": code,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "stdout": redact(outpath.read_bytes()[-30000:].decode("utf-8", errors="replace")),
        "stderr": redact(errpath.read_bytes()[-30000:].decode("utf-8", errors="replace")),
        "limitation": "Native trusted-code runner; not a hardened sandbox. No OS network isolation.",
    }
    test_id = save_record("test", result, status, run.repository_id)
    with session() as db:
        obj = db.get(Record, run_id)
        obj.status, obj.data = "test_" + status, obj.data | {"test_id": test_id}
    return {"id": test_id, "status": status, **result}
