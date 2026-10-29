param([switch]$Integration, [switch]$Browser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
& .\.venv\Scripts\ruff.exe check --config backend/pyproject.toml backend mcp_server scripts
if ($LASTEXITCODE) { throw 'Python lint failed' }
& .\.venv\Scripts\python.exe -m pytest backend/tests -m 'not integration and not live' -q
if ($LASTEXITCODE) { throw 'Backend tests failed' }
if ($Integration) {
    $env:PATCHPILOT_INTEGRATION = '1'
    & .\.venv\Scripts\python.exe -m pytest backend/tests -m integration -q
    if ($LASTEXITCODE) { throw 'Integration tests failed' }
}
Push-Location -LiteralPath frontend
try {
    npm run typecheck
    if ($LASTEXITCODE) { throw 'TypeScript failed' }
    npm run lint
    if ($LASTEXITCODE) { throw 'Frontend lint failed' }
    npm run build
    if ($LASTEXITCODE) { throw 'Frontend build failed' }
    if ($Browser) {
        npm test
        if ($LASTEXITCODE) { throw 'Browser tests failed (start local frontend/backend first)' }
    }
} finally { Pop-Location }
