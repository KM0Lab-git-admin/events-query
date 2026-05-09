# Desplaza fechas en EVENTO_HORARIOS en el MySQL remoto.
# Usa tu .env: define RAILWAY_DB_* (host/puerto publicos). OPENAI_API_KEY del mismo .env.
# En disco no se modifica DB_* local; solo en este proceso se copian RAILWAY_DB_* -> DB_*.
#
# Uso: .\run-shift-railway.ps1
#      .\run-shift-railway.ps1 --dry-run

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Import-DotEnvFile {
    param([string]$FilePath)
    Get-Content $FilePath | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
        }
    }
}

try {
    $envMain = Join-Path $root ".env"
    if (-not (Test-Path $envMain)) { throw "No existe .env en la raiz del repo." }
    Import-DotEnvFile $envMain

    if (-not $env:RAILWAY_DB_HOST) {
        throw "En .env define RAILWAY_DB_HOST, RAILWAY_DB_PORT, RAILWAY_DB_USER, RAILWAY_DB_PASSWORD, RAILWAY_DB_NAME (MySQL publico remoto)."
    }
    [Environment]::SetEnvironmentVariable("DB_HOST", $env:RAILWAY_DB_HOST, "Process")
    if ($env:RAILWAY_DB_PORT) { [Environment]::SetEnvironmentVariable("DB_PORT", $env:RAILWAY_DB_PORT, "Process") }
    if ($env:RAILWAY_DB_USER) { [Environment]::SetEnvironmentVariable("DB_USER", $env:RAILWAY_DB_USER, "Process") }
    if ($env:RAILWAY_DB_PASSWORD) { [Environment]::SetEnvironmentVariable("DB_PASSWORD", $env:RAILWAY_DB_PASSWORD, "Process") }
    if ($env:RAILWAY_DB_NAME) { [Environment]::SetEnvironmentVariable("DB_NAME", $env:RAILWAY_DB_NAME, "Process") }

    if (-not $env:OPENAI_API_KEY) { throw "OPENAI_API_KEY requerida en .env" }
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

Write-Host "MySQL remoto (RAILWAY_DB_*): actualizando horarios..." -ForegroundColor Cyan
python scripts/shift_horarios_to_future.py @args
exit $LASTEXITCODE
