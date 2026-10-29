$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
Get-Command python,node,npm,git,psql,pg_config,java,mvn -ErrorAction SilentlyContinue | Select-Object Name,Source
& .\.venv\Scripts\python.exe -c "import json; from app.main import health; print(json.dumps(health(), indent=2))"
Write-Host 'Status shows key presence only. It does not consume Gemini generation quota.'
