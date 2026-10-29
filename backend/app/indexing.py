import hashlib
import re
import threading
from functools import lru_cache

from sqlalchemy import delete, func, literal_column, select

from app.config import settings
from app.db import Chunk, Record, Repository, RepositoryFile, session, uid
from app.safety import REPOS, eligible, git, safe_path, secret_content

_embedding_lock = threading.Lock()
_index_lock = threading.Lock()


def fts_document(path, content):
    # Expose camelCase/PascalCase identifiers and give source paths more lexical weight.
    def split(value):
        return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ")

    return func.setweight(func.to_tsvector("english", split(path)), literal_column("'A'")).op("||")(
        func.setweight(func.to_tsvector("english", split(content)), literal_column("'B'"))
    )


@lru_cache
def embedding_model():
    import torch
    from huggingface_hub import try_to_load_from_cache
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(2)
    name = settings().embedding_model
    cached = all(
        isinstance(try_to_load_from_cache(name, file), str) for file in ("modules.json", "config.json")
    )
    cached = cached and any(
        isinstance(try_to_load_from_cache(name, file), str)
        for file in ("model.safetensors", "pytorch_model.bin")
    )
    model = SentenceTransformer(name, device="cpu", trust_remote_code=False, local_files_only=cached)
    if model.get_sentence_embedding_dimension() != 384:
        raise ValueError(
            "Schema requires 384-dimensional embeddings; migrate and reindex for a different model"
        )
    return model


def embed(texts):
    with _embedding_lock:
        return (
            embedding_model()
            .encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
            .tolist()
        )


def chunk_source(path, content):
    """Java syntax-tree declaration boundaries; line windows for other languages/large declarations."""
    lines = content.splitlines()
    boundaries = {0, len(lines)}
    if path.endswith(".java"):
        import tree_sitter_java
        from tree_sitter import Language, Parser

        tree = Parser(Language(tree_sitter_java.language())).parse(content.encode())

        def walk(node):
            if node.type in {
                "method_declaration",
                "constructor_declaration",
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
            }:
                boundaries.add(node.start_point.row)
                boundaries.add(min(len(lines), node.end_point.row + 1))
            for child in node.children:
                walk(child)

        walk(tree.root_node)
    edges = sorted(boundaries)
    for start, end in zip(edges, edges[1:]):
        for offset in range(start, end, 64):
            stop = min(offset + 80, end)
            text = "\n".join(lines[offset:stop])
            if text.strip():
                yield {
                    "start_line": offset + 1,
                    "end_line": stop,
                    "content": text,
                    "symbol": lines[start][:160],
                }


def repo_root(repository_id):
    with session() as db:
        repo = db.get(Repository, repository_id)
        if not repo:
            raise ValueError("Repository not found")
        if repo.meta.get("fixture"):
            return REPOS / repository_id
        return REPOS / repository_id


def index_repository(repository_id):
    if not _index_lock.acquire(blocking=False):
        with session() as db:
            pending = db.get(Repository, repository_id)
            if pending:
                pending.status = "error"
                pending.error = "Another indexing job is running; retry after it finishes"
        raise ValueError("Another indexing job is running; retry shortly")
    job_id = uid()
    try:
        with session() as db:
            repo = db.get(Repository, repository_id)
            if not repo:
                raise ValueError("Repository not found")
            repo.status, repo.error = "cloning", None
            url, meta = repo.url, repo.meta
            db.add(
                Record(id=job_id, kind="ingestion", repository_id=repository_id, status="running", data={})
            )
        root = repo_root(repository_id)
        root.parent.mkdir(parents=True, exist_ok=True)
        if not root.exists():
            git(["clone", "--depth", "1", "--", url, str(root)])
        elif not meta.get("fixture"):
            git(["fetch", "--depth", "1", "origin", "HEAD"], root)
            git(["checkout", "--detach", "FETCH_HEAD"], root)
        sha = git(["rev-parse", "HEAD"], root)
        tracked = git(["ls-files"], root).splitlines()
        with session() as db:
            db.get(Repository, repository_id).status = "embedding"
        entries, skipped = [], 0
        for path in tracked[:10000]:
            if not eligible(path):
                skipped += 1
                continue
            target = safe_path(root, path)
            if not target.is_file() or target.is_symlink() or target.stat().st_size > 250000:
                skipped += 1
                continue
            try:
                content = target.read_text(encoding="utf-8")
            except (UnicodeError, OSError):
                skipped += 1
                continue
            if "\x00" in content or secret_content(content):
                skipped += 1
                continue
            entries.append((path, content, list(chunk_source(path, content))))
        texts = [path + "\n" + chunk["content"] for path, _, chunks in entries for chunk in chunks]
        if not texts:
            raise ValueError("No eligible source code found")
        vectors = iter(embed(texts))
        with session() as db:
            # Atomic replacement: existing revision remains queryable until this commit.
            db.execute(delete(Chunk).where(Chunk.repository_id == repository_id))
            db.execute(delete(RepositoryFile).where(RepositoryFile.repository_id == repository_id))
            for path, content, chunks in entries:
                file = RepositoryFile(
                    repository_id=repository_id,
                    path=path,
                    sha=sha,
                    language=path.rsplit(".", 1)[-1],
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                )
                db.add(file)
                db.flush()
                for chunk in chunks:
                    db.add(
                        Chunk(
                            repository_id=repository_id,
                            file_id=file.id,
                            path=path,
                            sha=sha,
                            **chunk,
                            embedding=next(vectors),
                            search=fts_document(path, chunk["content"]),
                        )
                    )
            repo = db.get(Repository, repository_id)
            repo.sha, repo.status, repo.files, repo.chunks = sha, "ready", len(entries), len(texts)
            repo.meta = meta | {
                "embedding_model": settings().embedding_model,
                "skipped": skipped,
                "chunking": "Java tree-sitter declarations; overlapping 80-line windows",
            }
            job = db.get(Record, job_id)
            job.status, job.data = "completed", {"files": len(entries), "chunks": len(texts), "sha": sha}
        return job_id
    except Exception as exc:
        from app.config import redact

        with session() as db:
            repo = db.get(Repository, repository_id)
            if repo:
                repo.status, repo.error = "error", redact(str(exc))
            job = db.get(Record, job_id)
            if job:
                job.status, job.data = "failed", {"error": redact(str(exc))}
        raise
    finally:
        _index_lock.release()


def source_context(repository_id, path, start=1, end=80):
    if not 1 <= start <= end <= start + 199:
        raise ValueError("Choose 1–200 lines")
    with session() as db:
        repo = db.get(Repository, repository_id)
        found = db.scalar(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository_id, RepositoryFile.path == path
            )
        )
        if not repo or not found:
            raise ValueError("File is not in this indexed repository")
        root = repo_root(repository_id)
        content = git(["show", f"{repo.sha}:{path}"], root, preserve_output=True)
        lines = content.splitlines()
        if start > len(lines):
            raise ValueError("Line outside indexed file")
        return {
            "path": path,
            "sha": repo.sha,
            "start_line": start,
            "end_line": min(end, len(lines)),
            "content": "\n".join(lines[start - 1 : end]),
        }
