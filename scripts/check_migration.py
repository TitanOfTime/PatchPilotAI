"""Verify migrations in a newly created, disposable dedicated database; never reuse an existing DB."""

import json
import os
import subprocess
import sys
import uuid

import psycopg
from app.config import ROOT, redact, settings
from psycopg import sql

cfg = settings()
name = "patchpilot_migration_" + uuid.uuid4().hex[:10]
created = False
with psycopg.connect(
    host=cfg.database_host,
    port=cfg.database_port,
    user="postgres",
    dbname="postgres",
    connect_timeout=5,
    autocommit=True,
) as admin:
    if admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
        raise SystemExit("Refusing to reuse an existing migration-test database")
    admin.execute(
        sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(cfg.database_user))
    )
    created = True
    try:
        with psycopg.connect(
            host=cfg.database_host, port=cfg.database_port, user="postgres", dbname=name, autocommit=True
        ) as connection:
            connection.execute("CREATE EXTENSION vector")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ROOT / "backend/alembic.ini"), "upgrade", "head"],
            env=os.environ | {"DATABASE_NAME": name},
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            raise RuntimeError(redact(result.stderr))
        with psycopg.connect(
            host=cfg.database_host, port=cfg.database_port, user="postgres", dbname=name
        ) as connection:
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            datatype = connection.execute(
                "SELECT format_type(atttypid,atttypmod) FROM pg_attribute "
                "WHERE attrelid='code_chunks'::regclass AND attname='embedding'"
            ).fetchone()[0]
            assert revision == "001" and datatype == "vector(384)"
        evidence = {
            "status": "passed",
            "migration": revision,
            "embedding_column": datatype,
            "fresh_database": True,
            "extension": "vector",
            "disposable_database_removed": True,
        }
        folder = ROOT / "evaluation/results"
        folder.mkdir(exist_ok=True, parents=True)
        (folder / "migration-check.json").write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence))
    finally:
        if created:
            # Only the unique database successfully created by this invocation is ever dropped.
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
