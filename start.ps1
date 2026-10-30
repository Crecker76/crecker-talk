# CreckerTalk — one-command start (Windows PowerShell).
# Prereqs (one-time): Docker Desktop (WSL2) + Ollama for Windows must be installed.
# Usage:  .\start.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. .env from the prod preset if missing
if (-not (Test-Path ".env")) {
    Copy-Item ".env.prod.example" ".env"
    Write-Host "[CreckerTalk] created .env from .env.prod.example" -ForegroundColor Green
}

# 2. pull the model named in .env
$line = Get-Content .env | Where-Object { $_ -match '^\s*OLLAMA_MODEL\s*=' } | Select-Object -First 1
$model = if ($line) { ($line -replace '^\s*OLLAMA_MODEL\s*=', '').Trim() } else { "dolphin3:8b" }
Write-Host "[CreckerTalk] pulling model: $model  (first run can take a while)" -ForegroundColor Cyan
ollama pull $model

# 3. build & start the container
Write-Host "[CreckerTalk] building and starting the container..." -ForegroundColor Cyan
docker compose up -d --build

# 4. open the app
Start-Sleep -Seconds 3
Start-Process "http://localhost:8000"
Write-Host "[CreckerTalk] running at http://localhost:8000  — hold Space to talk" -ForegroundColor Green
