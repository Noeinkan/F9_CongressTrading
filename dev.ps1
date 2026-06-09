<#
.SYNOPSIS
    Avvia la dashboard in locale (FastAPI + Vite) con un solo comando.

.DESCRIPTION
    Lancia il backend FastAPI (.venv\Scripts\python.exe -m src.api) e il
    frontend Vite (frontend/npm run dev) in processi paralleli, colorandone
    l'output e propagando Ctrl+C ad entrambi.

    Requisiti:
      - venv Python creato in .venv\ (vedi README.md)
      - Node.js + npm (per il frontend)
      - dipendenze frontend installate (cd frontend; npm install)
        -> al primo avvio lo script le installa automaticamente se mancanti.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\dev.ps1
#>

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$repoRoot    = (Get-Location).Path
$venvPy      = Join-Path $repoRoot ".venv\Scripts\python.exe"
$frontendDir = Join-Path $repoRoot "frontend"
$apiPort     = if ($env:API_SERVER_PORT) { $env:API_SERVER_PORT } else { "9001" }
$webPort     = "5173"

function Write-Section($msg) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

Write-Section "Congress Trading - Local Dashboard"
Write-Host "  Repo:    $repoRoot"
Write-Host "  API:     http://127.0.0.1:$apiPort"
Write-Host "  Web:     http://127.0.0.1:$webPort"
Write-Host "  Premi Ctrl+C per fermare entrambi."
Write-Host ""

# --- Preflight checks -------------------------------------------------------

if (-not (Test-Path $venvPy)) {
    Write-Error "Virtualenv non trovato in .venv\. Crealo prima: py -m venv .venv"
    exit 1
}

if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "[setup] node_modules mancante in frontend\: installo..." -ForegroundColor Yellow
    Push-Location $frontendDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install fallito" }
    } finally {
        Pop-Location
    }
}

# --- Start backend -----------------------------------------------------------

Write-Section "Avvio backend (FastAPI su :$apiPort)"

$apiProc = Start-Process `
    -FilePath $venvPy `
    -ArgumentList @("-m", "src.api") `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput ".\.dev-api.out.log" `
    -RedirectStandardError  ".\.dev-api.err.log" `
    -NoNewWindow -PassThru

Write-Host "[api] pid=$($apiProc.Id) - log: .dev-api.{out,err}.log" -ForegroundColor Blue

# --- Start frontend ----------------------------------------------------------

Write-Section "Avvio frontend (Vite su :$webPort)"

$webProc = Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev") `
    -WorkingDirectory $frontendDir `
    -RedirectStandardOutput ".\.dev-web.out.log" `
    -RedirectStandardError  ".\.dev-web.err.log" `
    -NoNewWindow -PassThru

Write-Host "[web] pid=$($webProc.Id) - log: .dev-web.{out,err}.log" -ForegroundColor Green

# --- Tail logs + handle shutdown --------------------------------------------

Write-Section "Log live (tail -f equivalente). Ctrl+C per uscire."
Write-Host "  [api]  .\.dev-api.out.log  /  .\.dev-api.err.log" -ForegroundColor Blue
Write-Host "  [web]  .\.dev-web.out.log  /  .\.dev-web.err.log" -ForegroundColor Green
Write-Host ""

# Tail dei log in job background.
$apiTail = Start-Job -ScriptBlock {
    Get-Content -Path ".\.dev-api.out.log", ".\.dev-api.err.log" -Tail 0 -Wait |
        ForEach-Object { "[api] $_" }
}
$webTail = Start-Job -ScriptBlock {
    Get-Content -Path ".\.dev-web.out.log", ".\.dev-web.err.log" -Tail 0 -Wait |
        ForEach-Object { "[web] $_" }
}

# Apri il browser dopo qualche secondo.
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 5
    Start-Process "http://127.0.0.1:$using:webPort"
} | Out-Null

try {
    # Attendi indefinitamente, ma esci se uno dei due muore.
    while ($true) {
        if ($apiProc.HasExited) {
            Write-Host "[api] processo terminato (exit=$($apiProc.ExitCode))." -ForegroundColor Red
            break
        }
        if ($webProc.HasExited) {
            Write-Host "[web] processo terminato (exit=$($webProc.ExitCode))." -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host ""
    Write-Section "Cleanup: termino processi figli..."
    foreach ($p in @($apiProc, $webProc)) {
        if ($p -and -not $p.HasExited) {
            try {
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
                # taskkill /T per killare eventuali figli (es. uvicorn workers)
                Start-Process "taskkill.exe" -ArgumentList @("/PID", $p.Id, "/T", "/F") `
                    -NoNewWindow -Wait -ErrorAction SilentlyContinue | Out-Null
            } catch {}
        }
    }
    Stop-Job $apiTail, $webTail -ErrorAction SilentlyContinue
    Remove-Job $apiTail, $webTail -ErrorAction SilentlyContinue
    Write-Host "Fatto." -ForegroundColor Cyan
}
