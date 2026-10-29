import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.config import settings


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    url: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    sha: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="registered")
    error: Mapped[str | None] = mapped_column(Text)
    files: Mapped[int] = mapped_column(Integer, default=0)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RepositoryFile(Base):
    __tablename__ = "repository_files"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)
    sha: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String)


class Chunk(Base):
    __tablename__ = "code_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("repository_files.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text)
    sha: Mapped[str] = mapped_column(String)
    embedding: Mapped[list] = mapped_column(Vector(384))
    search: Mapped[str] = mapped_column(TSVECTOR)
    __table_args__ = (Index("chunks_fts", "search", postgresql_using="gin"),)


class Record(Base):
    """Typed durable documents for jobs, traces, proposals, approvals, tests and evaluations."""

    __tablename__ = "records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String, index=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="created")
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


@lru_cache
def engine():
    return create_engine(settings().db_url, pool_pre_ping=True, connect_args={"connect_timeout": 4})


@contextmanager
def session():
    with Session(engine(), expire_on_commit=False) as db:
        with db.begin():
            yield db


def save_record(kind, data, status="completed", repository_id=None, record_id=None):
    with session() as db:
        obj = Record(id=record_id or uid(), kind=kind, status=status, repository_id=repository_id, data=data)
        db.add(obj)
    return obj.id


def load_record(record_id, kind=None):
    with session() as db:
        row = db.get(Record, record_id)
        if row is None or (kind and row.kind != kind):
            raise ValueError("Record not found")
        return row


def asdict(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
