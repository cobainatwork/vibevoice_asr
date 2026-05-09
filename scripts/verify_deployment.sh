#!/usr/bin/env bash
# Verify a running deployment passes basic smoke tests.
# Run after `make up` has settled.
#
# Exit code: 0 if all checks pass, non-zero if any fail.

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

source .env 2>/dev/null || true
BACKEND="http://localhost:${BACKEND_PORT:-8080}"
FRONTEND="http://localhost:${FRONTEND_PORT:-5173}"

GREEN="\033[0;32m"
RED="\033[0;31m"
NC="\033[0m"

PASS=0
FAIL=0
check() {
    local name="$1"; shift
    if "$@" &>/dev/null; then
        printf "${GREEN}✓${NC} %s\n" "$name"
        PASS=$((PASS + 1))
    else
        printf "${RED}✗${NC} %s\n" "$name"
        FAIL=$((FAIL + 1))
    fi
}

# 檢查 docker compose service 是否處於 running 狀態
compose_running() {
    docker compose ps --status running --services 2>/dev/null | grep -qx "$1"
}

echo "=== Container health ==="
check "redis container running"     compose_running redis
check "backend container running"   compose_running backend
check "worker container running"    compose_running worker
check "frontend container running"  compose_running frontend

echo
echo "=== Backend ==="
check "backend /healthz"             curl -fsS "$BACKEND/healthz"
check "backend OpenAPI"              curl -fsS "$BACKEND/openapi.json"
check "admin/system/health"          curl -fsS "$BACKEND/api/admin/system/health"
check "admin/projects reachable"     curl -fsS "$BACKEND/api/admin/projects"

echo
echo "=== Redis ==="
check "redis ping"  docker exec vibevoice-redis redis-cli ping

echo
echo "=== Frontend ==="
check "frontend serves index.html"  curl -fsS "$FRONTEND/"

echo
echo "=== v1 API (optional, M6+) ==="
if curl -fsS "$BACKEND/openapi.json" 2>/dev/null | grep -q '"/api/v1/'; then
    check "v1 routes registered"  bash -c "curl -fsS '$BACKEND/openapi.json' | grep -q '\"/api/v1/'"
else
    echo "  (v1 routes not wired — M6 milestone)"
fi

echo
echo "=== vLLM (optional) ==="
if docker ps --filter "name=vibevoice-vllm" --filter "status=running" -q | grep -q .; then
    check "vLLM /v1/models"  curl -fsS "http://localhost:8000/v1/models"
else
    echo "  (vLLM not running — backend will start it on first transcribe)"
fi

echo
if [ "$FAIL" -eq 0 ]; then
    printf "${GREEN}All %d checks passed.${NC}\n" "$PASS"
    exit 0
else
    printf "${RED}%d/%d checks failed.${NC}\n" "$FAIL" "$((PASS + FAIL))"
    exit 1
fi
