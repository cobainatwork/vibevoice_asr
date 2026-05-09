<#
.SYNOPSIS
    PowerShell command runner — Windows equivalent of the Makefile.

.DESCRIPTION
    Mirrors the targets in Makefile so Windows devs (without GNU make) can run:
        .\make.ps1 setup
        .\make.ps1 up
        .\make.ps1 down
        ...

    For cmd.exe users: a make.bat wrapper exists that forwards args here.

.EXAMPLE
    .\make.ps1 setup
    .\make.ps1 up
    .\make.ps1 logs-backend
#>
param(
    [Parameter(Position=0)]
    [string]$Target = "help",
    [Parameter(Position=1, ValueFromRemainingArguments=$true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# Read .env if present so $env:* are available to child processes
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+?)\s*=\s*(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

function Show-Help {
    @"
VibeVoice-ASR PowerShell command runner

Setup:
  .\make.ps1 setup            Run bootstrap.ps1 (one-time)

Run:
  .\make.ps1 up               Start all services (redis, backend, worker, frontend)
  .\make.ps1 down             Stop all services
  .\make.ps1 logs             Tail logs of all services
  .\make.ps1 logs-backend     Tail backend logs
  .\make.ps1 logs-worker      Tail worker logs
  .\make.ps1 logs-vllm        Tail vLLM logs

Dev:
  .\make.ps1 restart-backend  Restart backend container
  .\make.ps1 restart-worker   Restart worker container
  .\make.ps1 shell-backend    Open bash in backend container
  .\make.ps1 frontend-dev     Run frontend dev server (npm run dev)

Test:
  .\make.ps1 test             Run backend tests inside container
  .\make.ps1 verify           Run scripts/verify_deployment.ps1

DB:
  .\make.ps1 db-migrate       Apply alembic migrations

Build:
  .\make.ps1 build            Build all docker images
  .\make.ps1 clean            Remove all containers and data (DESTRUCTIVE)
"@ | Write-Host
}

$port_backend = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8080" }
$port_frontend = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "5173" }

switch ($Target) {
    "help"     { Show-Help }
    "setup"    {
        & powershell -NoProfile -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\bootstrap.ps1"
    }
    "up" {
        docker compose up -d redis backend worker frontend
        Write-Host ""
        Write-Host "Services started. Backend will start vLLM on demand." -ForegroundColor Green
        Write-Host "Frontend: http://localhost:$port_frontend"
        Write-Host "Backend:  http://localhost:$port_backend"
        Write-Host "OpenAPI:  http://localhost:$port_backend/api/v1/openapi.json"
    }
    "down"     { docker compose down }
    "logs"             { docker compose logs -f --tail=100 }
    "logs-backend"     { docker compose logs -f --tail=100 backend }
    "logs-worker"      { docker compose logs -f --tail=100 worker }
    "logs-vllm"        { docker logs -f vibevoice-vllm }
    "restart-backend"  { docker compose restart backend }
    "restart-worker"   { docker compose restart worker }
    "shell-backend"    { docker compose exec backend bash }
    "shell-worker"     { docker compose exec worker bash }
    "frontend-dev" {
        Push-Location frontend
        try { npm run dev } finally { Pop-Location }
    }
    "test" {
        docker compose exec backend pytest -v
    }
    "verify" {
        & powershell -NoProfile -ExecutionPolicy Bypass -File "$ProjectRoot\scripts\verify_deployment.ps1"
    }
    "db-migrate" {
        docker compose exec backend alembic upgrade head
    }
    "build" {
        docker compose build
    }
    "clean" {
        Write-Host "WARNING: This will remove all containers, volumes, and data." -ForegroundColor Yellow
        $confirm = Read-Host "Type 'yes' to confirm"
        if ($confirm -eq "yes") {
            docker compose down -v
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
                "data\app.db", "data\uploads", "data\datasets", "data\staging", `
                "data\loras", "data\merged", "data\logs", "data\redis"
        }
    }
    default {
        Write-Host "Unknown target: $Target" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
