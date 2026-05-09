# Desplaza fechas en EVENTO_HORARIOS en el MySQL remoto.
# Usa tu .env: define RAILWAY_DB_* con host/puerto PUBLICOS (MYSQL_PUBLIC_URL), no MYSQLHOST.
# En disco no se modifica DB_* local; solo en este proceso se copian RAILWAY_DB_* -> DB_*.
#
# Uso: .\run-shift-railway.ps1
#      .\run-shift-railway.ps1 --dry-run

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Normalize-EnvValue {
    param([string]$Raw)
    if ([string]::IsNullOrWhiteSpace($Raw)) { return $Raw }
    $v = $Raw.Trim()
    if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
        $v = $v.Substring(1, $v.Length - 2).Trim()
    }
    return $v
}

function Import-DotEnvFile {
    param([string]$FilePath)
    Get-Content $FilePath | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = Normalize-EnvValue $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
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
    $rh = Normalize-EnvValue $env:RAILWAY_DB_HOST
    if ($rh -match '\.railway\.internal$' -or $rh -ieq 'mysql.railway.internal' -or $rh -ieq 'mysql') {
        throw "RAILWAY_DB_HOST no puede ser mysql.railway.internal (solo existe dentro de Railway). Copia el HOST de MYSQL_PUBLIC_URL (ej. algo.proxy.rlwy.net)."
    }
    if ($rh -like 'mysql://*') {
        throw "RAILWAY_DB_HOST debe ser solo el hostname, no la URL mysql://... (separado en RAILWAY_DB_USER, PASSWORD, PORT, NAME)."
    }

    [Environment]::SetEnvironmentVariable("DB_HOST", $rh, "Process")
    if ($env:RAILWAY_DB_PORT) {
        [Environment]::SetEnvironmentVariable("DB_PORT", (Normalize-EnvValue $env:RAILWAY_DB_PORT), "Process")
    }
    if ($env:RAILWAY_DB_USER) {
        [Environment]::SetEnvironmentVariable("DB_USER", (Normalize-EnvValue $env:RAILWAY_DB_USER), "Process")
    }
    if ($env:RAILWAY_DB_PASSWORD) {
        [Environment]::SetEnvironmentVariable("DB_PASSWORD", (Normalize-EnvValue $env:RAILWAY_DB_PASSWORD), "Process")
    }
    if ($env:RAILWAY_DB_NAME) {
        [Environment]::SetEnvironmentVariable("DB_NAME", (Normalize-EnvValue $env:RAILWAY_DB_NAME), "Process")
    }

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

Write-Host "Conectando a DB_HOST=$env:DB_HOST puerto DB_PORT=$env:DB_PORT ..." -ForegroundColor DarkGray
Write-Host "MySQL remoto (RAILWAY_DB_*): actualizando horarios..." -ForegroundColor Cyan
python scripts/shift_horarios_to_future.py @args
exit $LASTEXITCODE
