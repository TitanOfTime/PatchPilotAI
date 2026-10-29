import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from app.config import ROOT

DATA = ROOT / ".data"
REPOS = DATA / "repos"
SUFFIXES = {
    ".java",
    ".kt",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".xml",
    ".yml",
    ".yaml",
    ".properties",
    ".json",
    ".toml",
    ".gradle",
    ".sql",
    ".css",
}
EXCLUDED = {".git", "node_modules", ".venv", "target", "build", "dist", ".next", "vendor", "__pycache__"}


def github_url(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment:
        raise ValueError("Use https://github.com/owner/repository without credentials or query parameters")
    parts = parsed.path.rstrip("/").removesuffix(".git").strip("/").split("/")
    if len(parts) != 2 or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", p) or p in {".", ".."} for p in parts):
        raise ValueError("Invalid GitHub owner/repository")
    return f"https://github.com/{parts[0]}/{parts[1]}", "/".join(parts)


def safe_path(root: Path, relative: str) -> Path:
    if "\\" in relative or ":" in relative or PurePosixPath(relative).is_absolute():
        raise ValueError("Unsafe path")
    if any(p in {"..", ".git", ".env"} or p.startswith(".env.") for p in PurePosixPath(relative).parts):
        raise ValueError("Prohibited path")
    candidate = root.joinpath(relative).resolve()
    if not candidate.is_relative_to(root.resolve()) or candidate == root.resolve():
        raise ValueError("Path escapes workspace")
    return candidate


def eligible(path: str) -> bool:
    p = PurePosixPath(path)
    if any(part in EXCLUDED or part.startswith(".env") for part in p.parts):
        return False
    return (
        p.suffix in SUFFIXES
        and not p.name.endswith((".min.js", ".min.css", "-lock.json"))
        and p.name not in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
    )


def secret_content(content: str) -> bool:
    return bool(
        re.search(
            r"-----BEGIN .*PRIVATE KEY|AIza[\w-]{30,}|gh[pousr]_[\w]{20,}|github_pat_[\w]{20,}", content
        )
    )


def git(args: list[str], cwd: Path | None = None, timeout=120, preserve_output=False):
    # File-backed capture avoids inherited Windows pipe handles hanging a stdio MCP server.
    # stdin is isolated so Git can never consume MCP protocol messages.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(
            ["git", "--no-pager", "-c", "core.hooksPath=NUL", *args],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            timeout=timeout,
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__("sys").platform == "win32" else 0,
            env=__import__("os").environ | {"GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"},
        )
        stdout.seek(0)
        stderr.seek(0)
        output = stdout.read().decode("utf-8", errors="replace").replace("\r\n", "\n")
        if result.returncode:
            raise ValueError(f"Git operation failed: {stderr.read(1500).decode('utf-8', errors='replace')}")
        return output if preserve_output else output.strip()
