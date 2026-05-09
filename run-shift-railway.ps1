# Carga .env.railway y ejecuta el desplazamiento de fechas en EVENTO_HORARIOS
# contra el MySQL de Railway (conexion publica DB_HOST / DB_PORT).
# No modifica tu .env local (Docker).
#
# Uso (desde la raiz del repo):
#   .\run-shift-railway.ps1
#   .\run-shift-railway.ps1 --dry-run

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$envFile = Join-Path $root ".env.railway"
if (-not (Test-Path $envFile)) {
    Write-Host "No existe .env.railway." -ForegroundColor Red
    Write-Host "Copia .env.railway.example a .env.railway y rellena DB_* y OPENAI_API_KEY." -ForegroundColor Yellow
    exit 1
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
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
