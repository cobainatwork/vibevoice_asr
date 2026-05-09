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

echo "=== Container health ==="
check "redis container running"     docker compose ps redis    --status running --quiet -- with-services
check "backend container running"   docker compose ps backend  --status running --quiet -- with-services
check "worker container running"    docker compose ps worker   --status running --quiet -- with-services
check "frontend container running"  docker compose ps frontend --status running --quiet -- with-services

echo
echo "=== Backend ==="
check "backend /healthz"          curl -fsS "$BACKEND/healthz"
check "backend OpenAPI"           curl -fsS "$BACKEND/openapi.json"
check "admin/projects reachable"  curl -fsS "$BACKEND/api/admin/projects"
check "v1/openapi reachable"      curl -fsS "$BACKEND/api/v1/openapi.json"

echo
echo "=== Redis ==="
check "redis ping"  docker exec vibevoice-redis redis-cli ping

echo
echo "=== Frontend ==="
check "frontend serves index.html"  curl -fsS "$FRONTEND/"

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
