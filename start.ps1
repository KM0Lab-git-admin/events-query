# start.ps1 - Arranque único de Events Query (MySQL + API + Frontend)
# Uso: .\start.ps1   (desde la raíz del proyecto)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = Get-Location.Path }

Set-Location $root

Write-Host "Events Query - Iniciando servicios..." -ForegroundColor Cyan

# 1. MySQL con Docker (si está disponible)
if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "Levantando MySQL (Docker)..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    docker compose up -d mysql 2>&1 | Out-Null
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "MySQL en marcha." -ForegroundColor Green
        Start-Sleep -Seconds 2
    } else {
        Write-Host "Docker no disponible o fallo. Usa MySQL local si lo tienes." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "Docker no encontrado. Asegúrate de tener MySQL corriendo." -ForegroundColor DarkYellow
}

# 2. Backend (uvicorn) en ventana nueva
$venvActivate = Join-Path $root "venv\Scripts\Activate.ps1"
$uvicornCmd = "uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

if (Test-Path $venvActivate) {
    Write-Host "Arrancando API (ventana nueva)..." -ForegroundColor Yellow
    $backendScript = "Set-Location '$root'; & '$venvActivate'; $uvicornCmd"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendScript
    Start-Sleep -Seconds 2
} else {
    Write-Host "No se encontró venv. Crea uno: python -m venv venv; .\venv\Scripts\Activate.ps1; pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

# 3. Frontend en esta terminal
$frontendPath = Join-Path $root "frontend"
if (-not (Test-Path (Join-Path $frontendPath "package.json"))) {
    Write-Host "No se encontró frontend/package.json." -ForegroundColor Red
    exit 1
}

Write-Host "Arrancando frontend (esta ventana)..." -ForegroundColor Yellow
Set-Location $frontendPath
npm run dev
