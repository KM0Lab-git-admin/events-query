# stop.ps1 - Detener todos los servicios de Events Query
# Uso: .\stop.ps1   (desde la raíz del proyecto)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = Get-Location.Path }

Set-Location $root

Write-Host "Events Query - Deteniendo servicios..." -ForegroundColor Cyan

# 1. Detener MySQL (Docker) y Docker Desktop
$dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    $ErrorActionPreference = "Continue"
    docker info 2>&1 | Out-Null
    $dockerRunning = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"

    if ($dockerRunning) {
        Write-Host "Deteniendo MySQL (Docker)..." -ForegroundColor Yellow
        $ErrorActionPreference = "Continue"
        docker compose stop mysql 2>&1 | Out-Null
        $ErrorActionPreference = "Stop"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "MySQL detenido." -ForegroundColor Green
        } else {
            Write-Host "Docker no respondió o MySQL no estaba corriendo." -ForegroundColor DarkYellow
        }
    }

    if (Test-Path $dockerExe) {
        Write-Host "Cerrando Docker Desktop..." -ForegroundColor Yellow
        Start-Process -FilePath $dockerExe -ArgumentList "-Quit" -ErrorAction SilentlyContinue
        Write-Host "Docker Desktop cerrado." -ForegroundColor Green
    }
} else {
    Write-Host "Docker no encontrado. Omitiendo MySQL y Docker." -ForegroundColor DarkYellow
}

# 2. Detener proceso en puerto 8000 (API / uvicorn)
$port8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($port8000) {
    foreach ($procId in $port8000) {
        Write-Host "Deteniendo API (PID $procId, puerto 8000)..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "API detenida." -ForegroundColor Green
    }
} else {
    Write-Host "Nada escuchando en puerto 8000." -ForegroundColor DarkGray
}

# 3. Detener proceso en puerto 3000 (Frontend / Vite)
$port3000 = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($port3000) {
    foreach ($procId in $port3000) {
        Write-Host "Deteniendo frontend (PID $procId, puerto 3000)..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "Frontend detenido." -ForegroundColor Green
    }
} else {
    Write-Host "Nada escuchando en puerto 3000." -ForegroundColor DarkGray
}

Write-Host "Todo detenido. Para arrancar de nuevo: .\start.ps1" -ForegroundColor Cyan
