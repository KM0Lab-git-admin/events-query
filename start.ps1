# start.ps1 - Arranque único de Events Query (MySQL + API + Frontend)
# Uso: .\start.ps1   (desde la raíz del proyecto)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = Get-Location.Path }

Set-Location $root

Write-Host "Events Query - Iniciando servicios..." -ForegroundColor Cyan

# 1. MySQL con Docker (si está disponible)
$dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    # Comprobar si el daemon de Docker está corriendo
    $dockerOk = $false
    $ErrorActionPreference = "Continue"
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
    $ErrorActionPreference = "Stop"

    if (-not $dockerOk) {
        if (Test-Path $dockerExe) {
            Write-Host "Arrancando Docker Desktop..." -ForegroundColor Yellow
            Start-Process -FilePath $dockerExe
            $maxWait = 60
            $waited = 0
            while ($waited -lt $maxWait) {
                Start-Sleep -Seconds 5
                $waited += 5
                docker info 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    $dockerOk = $true
                    Write-Host "Docker Desktop listo." -ForegroundColor Green
                    break
                }
                Write-Host "Esperando a Docker... ($waited s)" -ForegroundColor DarkGray
            }
            if (-not $dockerOk) {
                Write-Host "Docker no respondió a tiempo. Inicia Docker Desktop manualmente y vuelve a ejecutar .\start.ps1" -ForegroundColor Red
            }
        } else {
            Write-Host "Docker no está corriendo y no se encontró Docker Desktop en $dockerExe" -ForegroundColor Red
            Write-Host "Inicia Docker Desktop manualmente o usa MySQL local en localhost:3306" -ForegroundColor DarkYellow
        }
    }

    if ($dockerOk) {
        Write-Host "Levantando MySQL (Docker)..." -ForegroundColor Yellow
        $ErrorActionPreference = "Continue"
        $dockerOut = docker compose up -d mysql 2>&1
        $dockerExit = $LASTEXITCODE
        $ErrorActionPreference = "Stop"

        if ($dockerExit -eq 0) {
            Start-Sleep -Seconds 2
            $psOut = docker compose ps mysql 2>&1
            if ($psOut -match "Up|running") {
                Write-Host "MySQL en marcha (contenedor activo)." -ForegroundColor Green
            } else {
                Write-Host "MySQL arrancado. Si la API falla al conectar, ejecuta: docker compose ps" -ForegroundColor Green
            }
        } else {
            Write-Host "Error al levantar MySQL con Docker:" -ForegroundColor Red
            Write-Host $dockerOut
            Write-Host "Comprueba que Docker Desktop está abierto o usa MySQL local." -ForegroundColor DarkYellow
        }
    }
} else {
    Write-Host "Docker no encontrado. Instálalo o usa MySQL local en localhost:3306" -ForegroundColor DarkYellow
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
