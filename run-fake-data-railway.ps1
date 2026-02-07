# Carga variables desde .env.railway y ejecuta el generador de datos contra la BD de Railway.
# No modifica .env (Docker sigue usando tu configuración local).
# Uso: .\run-fake-data-railway.ps1
#      .\run-fake-data-railway.ps1 --no-clear

$envFile = Join-Path $PSScriptRoot ".env.railway"
if (-not (Test-Path $envFile)) {
    Write-Host "No existe .env.railway. Copia .env.railway.example a .env.railway y rellena los valores de Railway." -ForegroundColor Red
    exit 1
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

& python scripts/generate_fake_data.py @args
