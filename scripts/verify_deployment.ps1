<#
.SYNOPSIS
    Smoke-test a running deployment (Windows version of verify_deployment.sh).

.DESCRIPTION
    Run after `.\make.ps1 up` has settled.
    Exit code 0 = all checks passed, non-zero = at least one failed.
#>
$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

# Load .env if present
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+?)\s*=\s*(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

$BackendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8080" }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "5173" }

$pass = 0
$fail = 0

function Check($name, [scriptblock]$action) {
    try {
        & $action | Out-Null
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
            throw "exit $LASTEXITCODE"
        }
        Write-Host "[PASS] $name" -ForegroundColor Green
        $script:pass++
    } catch {
        Write-Host "[FAIL] $name : $_" -ForegroundColor Red
        $script:fail++
    }
}

function Curl-OK($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return $true }
        throw "HTTP $($r.StatusCode)"
    } catch {
        throw $_
    }
}

Write-Host ""
Write-Host "=== Container health ==="
Check "redis container running"    { docker inspect -f "{{.State.Status}}" vibevoice-redis 2>$null | Select-String -Quiet "running" }
Check "backend container running"  { docker inspect -f "{{.State.Status}}" vibevoice-backend 2>$null | Select-String -Quiet "running" }
Check "worker container running"   { docker compose ps worker 2>$null | Select-String -Quiet "Up" }
Check "frontend container running" { docker inspect -f "{{.State.Status}}" vibevoice-frontend 2>$null | Select-String -Quiet "running" }

Write-Host ""
Write-Host "=== Backend ==="
Check "backend /healthz"           { Curl-OK "http://localhost:$BackendPort/healthz" }
Check "backend OpenAPI"            { Curl-OK "http://localhost:$BackendPort/openapi.json" }
Check "admin/projects reachable"   { Curl-OK "http://localhost:$BackendPort/api/admin/projects" }
Check "v1/openapi reachable"       { Curl-OK "http://localhost:$BackendPort/api/v1/openapi.json" }

Write-Host ""
Write-Host "=== Redis ==="
Check "redis ping" { docker exec vibevoice-redis redis-cli ping 2>$null | Select-String -Quiet "PONG" }

Write-Host ""
Write-Host "=== Frontend ==="
Check "frontend serves index.html" { Curl-OK "http://localhost:$FrontendPort/" }

Write-Host ""
Write-Host "=== vLLM (optional) ==="
$vllmRunning = (docker ps --filter "name=vibevoice-vllm" --filter "status=running" --quiet) -ne $null -and `
               (docker ps --filter "name=vibevoice-vllm" --filter "status=running" --quiet).Length -gt 0
if ($vllmRunning) {
    Check "vLLM /v1/models" { Curl-OK "http://localhost:8000/v1/models" }
} else {
    Write-Host "  (vLLM not running. On dev-Windows host this is expected per scenario c.)"
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "All $pass checks passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host "$fail/$($pass + $fail) checks failed." -ForegroundColor Red
    exit 1
}
