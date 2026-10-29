"""Create only the dedicated app DB/role; never change existing DBs or authentication rules."""

import secrets

import psycopg
from app.config import ROOT
from dotenv import dotenv_values, set_key
from psycopg import sql

values = dotenv_values(ROOT / ".env")
name = values.get("DATABASE_NAME", "patchpilot_ai")
user = values.get("DATABASE_USER", "patchpilot_user")
if name != "patchpilot_ai" or user != "patchpilot_user":
    raise SystemExit("Bootstrap is intentionally restricted to patchpilot_ai/patchpilot_user")
password = values.get("DATABASE_PASSWORD") or secrets.token_urlsafe(32)
with psycopg.connect(
    host=values.get("DATABASE_HOST", "127.0.0.1"),
    port=values.get("DATABASE_PORT", 5432),
    user="postgres",
    dbname="postgres",
    connect_timeout=5,
    autocommit=True,
) as conn:
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (user,)).fetchone():
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(user), sql.Literal(password))
        )
    elif not values.get("DATABASE_PASSWORD"):
        raise SystemExit("Existing role found; provide its password locally rather than resetting it")
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
        conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(user))
        )
set_key(str(ROOT / ".env"), "DATABASE_PASSWORD", password)
if not values.get("GEMINI_MODEL"):
    set_key(str(ROOT / ".env"), "GEMINI_MODEL", "gemini-3.5-flash-lite")
with psycopg.connect(
    host=values.get("DATABASE_HOST", "127.0.0.1"),
    port=values.get("DATABASE_PORT", 5432),
    user="postgres",
    dbname=name,
    connect_timeout=5,
    autocommit=True,
) as conn:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    print(
        "Dedicated database ready. pgvector:",
        conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0],
    )
print("App password saved to ignored .env; not displayed.")
