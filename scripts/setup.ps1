param([switch]$BootstrapDatabase)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv }
if ($LASTEXITCODE) { throw 'Python virtual environment failed' }
if (!(Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
& .\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
if ($LASTEXITCODE) { throw 'Python dependency installation failed' }
& .\.venv\Scripts\python.exe -m pip install --no-deps -e backend
if ($BootstrapDatabase) {
    & .\.venv\Scripts\python.exe scripts/bootstrap_db.py
    if ($LASTEXITCODE) { throw 'Dedicated database setup failed; see native pgvector instructions' }
}
& .\.venv\Scripts\alembic.exe -c backend/alembic.ini upgrade head
if ($LASTEXITCODE) { throw 'Migration failed. Check PostgreSQL, pgvector and local .env.' }
Push-Location -LiteralPath frontend
try { npm ci; if ($LASTEXITCODE) { throw 'Node dependency installation failed' } } finally { Pop-Location }
Write-Host 'Setup complete. Add Gemini/GitHub credentials to local .env, then run scripts/dev.ps1.'
