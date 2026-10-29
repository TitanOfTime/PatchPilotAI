param(
    [string]$PgConfig = (Join-Path $env:USERPROFILE 'scoop\apps\postgresql\current\bin\pg_config.exe'),
    [string]$Source = (Join-Path $PSScriptRoot '..\.data\pgvector')
)

$ErrorActionPreference = 'Stop'
$expectedCommit = '44624c1f8d17327943fbe9a62fa96b3fbd59d2b2'
$pgConfigPath = (Resolve-Path -LiteralPath $PgConfig).Path
if (-not (Test-Path -LiteralPath $Source)) {
    & git clone --no-checkout https://github.com/pgvector/pgvector $Source
    if ($LASTEXITCODE) { throw 'Official pgvector source clone failed.' }
    & git -C $Source checkout --detach $expectedCommit
    if ($LASTEXITCODE) { throw 'Pinned pgvector revision is unavailable.' }
}
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Visual Studio Installer vswhere.exe was not found.' }
$vsPath = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $vsPath) { throw 'Visual Studio C++ x64/x86 build tools were not found.' }
$vcvars = Join-Path ($vsPath | Select-Object -First 1) 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path -LiteralPath $vcvars)) { throw 'vcvars64.bat was not found.' }

$actualCommit = & git -C $sourcePath rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $expectedCommit) { throw "Source must be official pgvector 0.8.7 at commit $expectedCommit." }
& git -C $sourcePath diff --quiet
if ($LASTEXITCODE) { throw 'Tracked pgvector source files differ from the verified revision.' }
$pgVersion = & $pgConfigPath --version
if ($LASTEXITCODE -ne 0 -or $pgVersion -notmatch '^PostgreSQL 18\.') { throw 'This helper requires PostgreSQL 18.' }
$bindir = & $pgConfigPath --bindir
if ($LASTEXITCODE -ne 0) { throw 'pg_config --bindir failed.' }
$pgRoot = Split-Path -Parent $bindir.Trim()
$psql = Join-Path $bindir.Trim() 'psql.exe'
if (-not (Test-Path -LiteralPath (Join-Path $pgRoot 'lib\postgres.lib')) -or -not (Test-Path -LiteralPath $psql)) { throw 'PostgreSQL development files or psql are missing.' }

$previousPgRoot = $env:PGROOT
try {
    $env:PGROOT = $pgRoot
    Push-Location -LiteralPath $sourcePath
    try {
        # Rebuild all objects for this PostgreSQL installation before copying files.
        & cmd.exe /d /s /c "`"`"$vcvars`" && nmake /F Makefile.win clean && nmake /F Makefile.win && nmake /F Makefile.win install`""
        if ($LASTEXITCODE -ne 0) { throw 'pgvector build or installation failed.' }
    } finally { Pop-Location }
} finally { $env:PGROOT = $previousPgRoot }

& $psql -X -w -h 127.0.0.1 -U postgres -d patchpilot_ai -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector' -c "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
if ($LASTEXITCODE -ne 0) { throw 'Could not enable or verify vector in patchpilot_ai.' }
