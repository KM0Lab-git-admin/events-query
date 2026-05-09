# Generador fake contra MySQL Railway desde tu PC.
# Preferente: RAILWAY_DB_* en tu .env (mismo archivo que local). Alternativa: .env.railway
# Uso: .\run-fake-data-railway.ps1
#      .\run-fake-data-railway.ps1 --no-clear

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

try {
    . (Join-Path $root "load-railway-db-env.ps1") -RepoRoot $root
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

& python scripts/generate_fake_data.py @args
exit $LASTEXITCODE
