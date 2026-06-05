# Sube static/images/ a Railway (HTTPS). Uso: .\run-sync-images-railway.ps1

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
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

$venvActivate = Join-Path $root "venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) { . $venvActivate }

$baseUrl = if ($env:EVENTS_API_BASE_URL) { $env:EVENTS_API_BASE_URL } else { "https://eventquery.km0lab.com" }

Write-Host "Subiendo static/images -> $baseUrl ..." -ForegroundColor Cyan
& python scripts/upload_images_railway.py --base-url $baseUrl @args
exit $LASTEXITCODE
