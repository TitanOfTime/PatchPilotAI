# PatchPilot AI

**Engineering, with evidence.** A local software engineering assistant that indexes a real GitHub repository, answers source-grounded questions, and carries bug investigations through a persisted human review checkpoint.

The primary repository is [TitanOfTime/TestBankingApp](https://github.com/TitanOfTime/TestBankingApp), a Java Spring Boot banking application. A separately labeled `demo-fixture/rounding` repository contains a deliberate decimal rounding defect for reproducible regression testing.

## Stack and responsibilities

| Technology | Actual implementation |
| --- | --- |
| FastAPI, Pydantic, SQLAlchemy, psycopg | Validated REST APIs, local configuration, durable data and audit records |
| Next.js, React, TypeScript, Tailwind | Responsive dashboard, code citations, diff viewer, real progress and review controls |
| Sentence Transformers + PyTorch CPU | Pretrained `all-MiniLM-L6-v2` inference, 384-dimensional embeddings; **no training or fine-tuning** |
| PostgreSQL + pgvector | Source metadata, vectors, native full-text search, reciprocal rank fusion |
| Gemini 3.5 Flash Lite + LangChain | Structured grounded answers and constrained patch proposals |
| LangGraph | Bounded investigation graph, PostgreSQL checkpoints, actual interrupt/resume for approval |
| MCP Python SDK | Separate development evidence server and official GitHub remote MCP client |
A configured credential is not treated as a successful live integration.

## Native Windows setup

Requirements: Windows x64, Python 3.11+, Node 24, Git, the existing local PostgreSQL 18 installation with a matching **server-side pgvector extension**. Java/Maven are needed only for the Banking App test profile. Approximately 16 GB RAM is sufficient for CPU embeddings; large repositories are bounded to 10,000 tracked entries and 250 KB per file.

Open PowerShell in the project root directory:

```powershell
if (!(Test-Path -LiteralPath '.env')) { Copy-Item .env.example .env }
.\scripts\setup.ps1 -BootstrapDatabase
.\scripts\dev.ps1
```

`setup.ps1` creates a virtual environment, installs pinned Python and Node packages, and applies Alembic migrations. `-BootstrapDatabase` creates only `patchpilot_ai` and `patchpilot_user`; it never resets another role/password or modifies existing application databases. It requires local PostgreSQL administration permission. If PostgreSQL administrator authentication is required, set `PGPASSWORD` temporarily in your terminal rather than placing it in source code or command history. The app password is generated and written directly to ignored `.env`.

The pgvector **Python** package does not install the PostgreSQL extension. Ensure the matching server-side pgvector extension is installed for your local PostgreSQL version. Do not use a binary for another PostgreSQL major version.

Fill the ignored `.env`:

- `GEMINI_API_KEY`: your Google AI Studio key.
- `GEMINI_MODEL=gemini-3.5-flash-lite`: verified against the key's model listing.
- `GITHUB_TOKEN`: token for the official remote GitHub MCP server. Read access is enough for investigations; draft PR publishing additionally needs repository Contents/Pull Requests write permissions and an owner token.
- The generated app database password and detected local host/port.
- Leave `GITHUB_REMOTE_WRITE_ENABLED=false`. Leave `LOCAL_TEST_EXECUTION_ENABLED=false` until you review the trusted test profiles.

Never put credentials in `.env.example`, source files, screenshots or Git. Restart the backend after configuration changes.

Open [dashboard](http://127.0.0.1:3000) and [API documentation](http://127.0.0.1:8000/docs). Both processes bind to loopback. No Docker, WSL, Redis or cloud database is used.

Two-terminal alternative:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
npm run dev
```

## First run

1. Repositories → connect the Banking App URL → watch actual cloning/embedding progress.
2. Code intelligence → choose Search only for quota-free hybrid retrieval, or Grounded answer for Gemini. Example: “Where are payment webhooks and idempotency handled?” Expand evidence cards to inspect exact lines and source commit links.
3. Agent workspace → enter a real GitHub issue number or a **manual bug report**. The agent reads GitHub through MCP, retrieves source, reads exact evidence through the custom MCP server, and generates a constrained structured proposal.
4. Inspect the diagnosis, evidence, plan, diff and limitations. `git apply --check` validates the exact patch in an isolated pinned clone. No source is automatically changed in your original repository.
5. Approve or reject the patch. Separately enable trusted local execution in `.env`, restart, and approve the exact test profile. Inspect true stdout/stderr, duration and exit code.
6. Optionally enable remote writes and approve a draft PR after a passing test. Publishing is limited to the authorized Banking App and an owner token. It creates a new branch and **draft** PR; it never merges.
7. Evaluations → run the 10-query Banking App benchmark. All metrics come from actual retrieval and source verification.

Register the deterministic fixture after migrations:

```powershell
.\.venv\Scripts\python.exe scripts/register_fixture.py
```

In Agent workspace select `demo-fixture/rounding` and describe: `cents("1.005") returns 100 instead of 101. Use explicit ROUND_HALF_UP for positive and negative half-cent ties and keep regression tests.` Fixture evidence and test output remain labeled separately from the Banking App.

## Verification

```powershell
.\scripts\doctor.ps1
.\scripts\test.ps1
.\scripts\test.ps1 -Integration
```

Offline tests fake only external dependencies when needed; the custom MCP transport test launches a genuine separate subprocess. Integration tests require the dedicated migrated database and indexed Banking App/fixture. The graph fixture test substitutes the Gemini proposal to conserve quota while exercising real retrieval, MCP, PostgreSQL persistence, diff validation and execution. Live Gemini results must be verified separately and are counted against the local daily budget.

The local quota counter reserves each generation attempt transactionally, including failed calls, with no automatic model retries. The default is 20 requests per UTC day and four calls per investigation; these are application safeguards, **not Google's account quota**. The current graph normally uses one generation request per investigation. Model listing, embeddings, indexing, evaluation and page refreshes do not generate Gemini responses.

Verified on the supplied Banking App: **159 files / 859 chunks**, hybrid file-hit Recall@5 **80%**, MRR **0.620**, three live cited Gemini answers and a correct absent-feature abstention. The live seeded-fixture repair included a newly generated regression test and passed **three real tests**.
This is a single-user localhost portfolio application. Native execution runs trusted code with the user's OS permissions and is not a hardened sandbox. Repository code and third-party tool responses remain untrusted input. Proposed fixes are hypotheses until their relevant regression tests and human review support them.
