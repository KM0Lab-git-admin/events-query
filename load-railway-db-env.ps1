# Carga variables para scripts que apuntan al MySQL de Railway desde tu PC.
# Orden:
#   1) Lee .env (OPENAI_API_KEY, opcional base)
#   2) Si existen RAILWAY_DB_HOST (y resto), copia a DB_* solo en este proceso
#   3) Si no, si existe .env.railway, lo carga (compatibilidad)
#
# Uso (desde la raiz del repo):
#   . .\load-railway-db-env.ps1 -RepoRoot $PSScriptRoot

param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot
)

function Import-DotEnv {
    param([string]$FilePath)
    if (-not (Test-Path $FilePath)) { return }
    Get-Content $FilePath | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

Import-DotEnv (Join-Path $RepoRoot ".env")

if ($env:RAILWAY_DB_HOST) {
    [Environment]::SetEnvironmentVariable("DB_HOST", $env:RAILWAY_DB_HOST, "Process")
    if ($env:RAILWAY_DB_PORT) {
        [Environment]::SetEnvironmentVariable("DB_PORT", $env:RAILWAY_DB_PORT, "Process")
    }
    if ($env:RAILWAY_DB_USER) {
        [Environment]::SetEnvironmentVariable("DB_USER", $env:RAILWAY_DB_USER, "Process")
    }
    if ($env:RAILWAY_DB_PASSWORD) {
        [Environment]::SetEnvironmentVariable("DB_PASSWORD", $env:RAILWAY_DB_PASSWORD, "Process")
    }
    if ($env:RAILWAY_DB_NAME) {
        [Environment]::SetEnvironmentVariable("DB_NAME", $env:RAILWAY_DB_NAME, "Process")
    }
    Write-Host "BD destino: RAILWAY (RAILWAY_DB_* -> DB_* en este proceso)." -ForegroundColor DarkGray
}
elseif (Test-Path (Join-Path $RepoRoot ".env.railway")) {
    Import-DotEnv (Join-Path $RepoRoot ".env.railway")
    Write-Host "BD destino: variables desde .env.railway" -ForegroundColor DarkGray
}
else {
    Write-Host "Falta configuracion Railway en el proceso actual." -ForegroundColor Red
    Write-Host "Opcion A: en tu .env (junto a DB_* local) anade:" -ForegroundColor Yellow
    Write-Host "  RAILWAY_DB_HOST=caboose.proxy.rlwy.net"
    Write-Host "  RAILWAY_DB_PORT=55339"
    Write-Host "  RAILWAY_DB_USER=root"
    Write-Host "  RAILWAY_DB_PASSWORD=..."
    Write-Host "  RAILWAY_DB_NAME=railway"
    Write-Host "Opcion B: archivo .env.railway con DB_* apuntando a Railway."
    throw "Falta RAILWAY_DB_* o .env.railway."
}

if (-not $env:OPENAI_API_KEY) {
    throw "OPENAI_API_KEY no definida tras cargar .env."
}
