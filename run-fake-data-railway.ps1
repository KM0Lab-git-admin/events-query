# Generador fake contra MySQL remoto desde tu PC.
# Mismo .env que local: RAILWAY_DB_* apuntan al host/puerto publicos de Railway.
# Uso: .\run-fake-data-railway.ps1
#      .\run-fake-data-railway.ps1 --no-clear

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
}

& python scripts/generate_fake_data.py @args
exit $LASTEXITCODE
