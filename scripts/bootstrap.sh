#!/usr/bin/env bash
# Day 0 environment setup.
#
# Run once after cloning the repo:
#   make setup
#
# Tasks:
#   1. Verify host prereqs (Docker, NVIDIA toolkit, ffmpeg)
#   2. Clone vendor/VibeVoice if missing
#   3. Copy .env.example → .env if missing
#   4. Build all docker images
#   5. Pre-create data directories
#
# Idempotent: safe to re-run.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

info()  { printf "${GREEN}[OK]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC} %s\n" "$*"; }
error() { printf "${RED}[ERR]${NC} %s\n" "$*" >&2; }

# === 1. Check host prereqs ===

echo "=== Checking host prerequisites ==="

if ! command -v docker &>/dev/null; then
    error "docker not found. Install Docker 24+ and rerun."
    exit 1
fi
info "docker: $(docker --version)"

if ! docker compose version &>/dev/null; then
    error "docker compose v2 not found. Update Docker Desktop or install plugin."
    exit 1
fi
info "docker compose: $(docker compose version --short 2>/dev/null || echo 'v2')"

# NVIDIA toolkit (best-effort; only fail if requesting GPU profile)
if command -v nvidia-smi &>/dev/null; then
    info "nvidia-smi: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
    if ! docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi &>/dev/null; then
        warn "NVIDIA Container Toolkit not configured. GPU containers will fail."
        warn "  See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/"
    else
        info "NVIDIA Container Toolkit: working"
    fi
else
    warn "nvidia-smi not found. CPU-only mode (vLLM container will not work)."
fi

if ! command -v ffmpeg &>/dev/null; then
    warn "ffmpeg not on host (only needed for local dev scripts; backend container has it)."
fi

# === 2. Vendor: clone upstream if missing ===

echo "=== Checking vendor/VibeVoice ==="
if [ ! -d "vendor/VibeVoice" ]; then
    info "Cloning microsoft/VibeVoice..."
    mkdir -p vendor
    git clone --depth 1 https://github.com/microsoft/VibeVoice.git vendor/VibeVoice
else
    info "vendor/VibeVoice exists (skipping clone)"
fi

# === 3. .env ===

echo "=== Checking .env ==="
if [ ! -f .env ]; then
    cp .env.example .env
    info "Created .env from .env.example. Edit it to customize DEPLOYMENT_PROFILE etc."
else
    info ".env exists (skipping)"
fi

# === 4. Build images ===

echo "=== Building Docker images ==="
docker compose build backend frontend
docker build -f docker/train.Dockerfile -t vibevoice-train:latest . || \
    warn "vibevoice-train build failed (only needed for M4 training)"

# === 5. Data dirs ===

echo "=== Pre-creating data directories ==="
mkdir -p data/{uploads,datasets,staging,loras,merged,logs,redis,hf_cache}
info "data/ ready"

# === Summary ===

cat <<EOF

${GREEN}=== Setup complete ===${NC}

Next steps:
  1. Edit .env (DEPLOYMENT_PROFILE, GPU_*, etc.)
  2. make up                 # start services
  3. open http://localhost:5173

For first run, vLLM will download ~14 GB of model weights on first transcribe.

To run M1 verification (vLLM only):
  docker compose --profile manual up -d vllm
  docker logs -f vibevoice-vllm    # wait for "Application startup complete"

EOF
