# Ejecuta shift_horarios_to_future contra el MySQL de Railway.
# Carga .env y, si defines RAILWAY_DB_* ahi, usa esa BD solo en este proceso.
# Si no hay RAILWAY_DB_*, usa .env.railway (opcional).
# Tu .env con DB_* localhost no se modifica en disco.
#
# Uso: .\run-shift-railway.ps1
#      .\run-shift-railway.ps1 --dry-run

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

try {
    . (Join-Path $root "load-railway-db-env.ps1") -RepoRoot $root
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

$venvActivate = Join-Path $root "venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
} else {
    Write-Host "Aviso: no hay venv\Scripts\Activate.ps1; se usa el python del PATH." -ForegroundColor DarkYellow
}

Write-Host "Railway: actualizando horarios (shift_horarios_to_future)..." -ForegroundColor Cyan
python scripts/shift_horarios_to_future.py @args
exit $LASTEXITCODE
