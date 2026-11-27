# Generador fake contra MySQL remoto desde tu PC.
# RAILWAY_DB_HOST = host PUBLICO de MYSQL_PUBLIC_URL (no mysql.railway.internal).
# Uso: .\run-fake-data-railway.ps1
#      .\run-fake-data-railway.ps1 --no-clear

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
    if ($rh -match '\.railway\.internal$' -or $rh -ieq 'mysql') {
        throw "RAILWAY_DB_HOST no puede ser mysql.railway.internal. Usa el host de MYSQL_PUBLIC_URL (proxy publico)."
    }
    if ($rh -like 'mysql://*') {
        throw "RAILWAY_DB_HOST debe ser solo el hostname, no mysql://..."
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
}

Write-Host "Conectando a DB_HOST=$env:DB_HOST ..." -ForegroundColor DarkGray
& python scripts/generate_fake_data.py @args
exit $LASTEXITCODE
