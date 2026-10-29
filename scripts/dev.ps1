$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run scripts/setup.ps1 first' }
New-Item -ItemType Directory -Path (Join-Path $projectRoot '.data') -Force | Out-Null
$backend = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot '.data/backend.log') -RedirectStandardError (Join-Path $projectRoot '.data/backend-error.log')
try {
    Write-Host 'Dashboard http://127.0.0.1:3000 | API http://127.0.0.1:8000/docs | Ctrl+C stops both'
    Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
    try { npm run dev } finally { Pop-Location }
} finally { if (!$backend.HasExited) { Stop-Process -Id $backend.Id } }
