param([string]$Url = 'https://github.com/TitanOfTime/TestBankingApp')
$ErrorActionPreference = 'Stop'
$repo = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/repositories -Method Post -ContentType application/json -Body (@{url=$Url} | ConvertTo-Json)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/repositories/$($repo.id)/index" -Method Post -ContentType application/json -Body '{}'
Write-Host "Index queued: $($repo.id). Follow real progress in the dashboard."
