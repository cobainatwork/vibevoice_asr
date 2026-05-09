<#
.SYNOPSIS
    Day 0 environment setup (Windows version of bootstrap.sh).

.DESCRIPTION
    Verifies host prerequisites, clones vendor/VibeVoice if missing,
    copies .env.example → .env, and builds Docker images.

    Idempotent: safe to re-run.

    Run from project root:
        .\make.ps1 setup
    or directly:
        powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
#>
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

function Info($msg)  { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Err($msg)   { Write-Host "[ERR] $msg" -ForegroundColor Red }

# ============================================================
# 1. Host prerequisites
# ============================================================

Write-Host "=== Checking host prerequisites ==="

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Err "Docker not found. Install Docker Desktop and ensure it's running."
    Err "  Download: https://www.docker.com/products/docker-desktop/"
    exit 1
}
$dockerVer = (docker --version) -replace "^Docker version ", ""
Info "docker: $dockerVer"

# Docker Compose v2
$composeOK = $false
try {
    docker compose version --short 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $composeOK = $true }
} catch {}
if (-not $composeOK) {
    Err "Docker Compose v2 not found. Update Docker Desktop."
    exit 1
}
Info "docker compose: v2"

# NVIDIA — only relevant if GPU profile chosen later. Dev-on-Windows often has no GPU.
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpuName = (nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Select-Object -First 1)
    Info "nvidia-smi: $gpuName"
    Warn "GPU passthrough on Windows requires Docker Desktop + WSL2 backend + NVIDIA WSL toolkit."
    Warn "  See SPEC.md §5 'Windows dev'  if production target is Linux, dev host needs no GPU."
} else {
    Warn "nvidia-smi not found. CPU-only dev host (vLLM container will not start here)."
    Warn "  This is OK for scenario (c): dev on Windows, prod on Linux."
}

# ============================================================
# 2. Vendor: clone upstream if missing
# ============================================================

Write-Host ""
Write-Host "=== Checking vendor/VibeVoice ==="
if (-not (Test-Path "vendor\VibeVoice")) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Err "git not found and vendor/VibeVoice missing. Install Git for Windows."
        exit 1
    }
    Info "Cloning microsoft/VibeVoice..."
    New-Item -ItemType Directory -Force -Path "vendor" | Out-Null
    git clone --depth 1 https://github.com/microsoft/VibeVoice.git vendor\VibeVoice
} else {
    Info "vendor/VibeVoice exists (skipping clone)"
}

# ============================================================
# 3. .env file
# ============================================================

Write-Host ""
Write-Host "=== Checking .env ==="
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Info "Created .env from .env.example. Edit it to customize DEPLOYMENT_PROFILE etc."
} else {
    Info ".env exists (skipping)"
}

# ============================================================
# 4. Build images
# ============================================================

Write-Host ""
Write-Host "=== Building Docker images ==="
docker compose build backend frontend
if ($LASTEXITCODE -ne 0) {
    Err "Failed to build backend / frontend images."
    exit 1
}

# Training image (optional — only needed for M4)
try {
    docker build -f docker\train.Dockerfile -t vibevoice-train:latest .
    Info "Built vibevoice-train:latest"
} catch {
    Warn "vibevoice-train build failed (only needed for M4 training)"
}

# ============================================================
# 5. Pre-create data directories
# ============================================================

Write-Host ""
Write-Host "=== Pre-creating data directories ==="
@("uploads", "datasets", "staging", "loras", "merged", "logs", "redis", "hf_cache") | ForEach-Object {
    New-Item -ItemType Directory -Force -Path "data\$_" | Out-Null
}
Info "data\ ready"

# ============================================================
# Summary
# ============================================================

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit .env if needed (DEPLOYMENT_PROFILE, GPU_*, etc.)"
Write-Host "  2. .\make.ps1 up                 # start services"
Write-Host "  3. open http://localhost:5173"
Write-Host ""
Write-Host "Note: vLLM container will not start on dev Windows host without GPU."
Write-Host "      Production deployment target is Linux per SPEC.md §5."
Write-Host ""
