.PHONY: help setup up down logs logs-backend logs-worker logs-vllm \
        restart-backend restart-worker shell-backend shell-worker \
        test test-backend test-frontend frontend-dev \
        verify build clean db-migrate db-revision

help:
	@echo "VibeVoice-ASR Makefile"
	@echo ""
	@echo "Setup:"
	@echo "  make setup            Run bootstrap.sh (one-time)"
	@echo ""
	@echo "Run:"
	@echo "  make up               Start all services (redis, backend, worker, frontend)"
	@echo "  make down             Stop all services"
	@echo "  make logs             Tail logs of all services"
	@echo "  make logs-backend     Tail backend logs"
	@echo "  make logs-worker      Tail worker logs"
	@echo "  make logs-vllm        Tail vLLM logs"
	@echo ""
	@echo "Dev:"
	@echo "  make restart-backend  Restart backend container"
	@echo "  make restart-worker   Restart worker container"
	@echo "  make shell-backend    Open shell in backend container"
	@echo "  make frontend-dev     Run frontend dev server (npm run dev)"
	@echo ""
	@echo "Test:"
	@echo "  make test             Run all tests"
	@echo "  make test-backend     Run backend tests"
	@echo "  make verify           Run scripts/verify_deployment.sh"
	@echo ""
	@echo "DB:"
	@echo "  make db-migrate       Apply alembic migrations"
	@echo "  make db-revision      Create new migration (M=msg)"
	@echo ""
	@echo "Build:"
	@echo "  make build            Build all docker images"
	@echo "  make clean            Remove all containers and data (DESTRUCTIVE)"

setup:
	@chmod +x scripts/*.sh scripts/*.py 2>/dev/null || true
	bash scripts/bootstrap.sh

up:
	docker compose up -d redis backend worker frontend
	@echo ""
	@echo "Services started. Backend will start vLLM on demand."
	@echo "Frontend: http://localhost:$${FRONTEND_PORT:-5173}"
	@echo "Backend:  http://localhost:$${BACKEND_PORT:-8080}"
	@echo "OpenAPI:  http://localhost:$${BACKEND_PORT:-8080}/api/v1/openapi.json"

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

logs-backend:
	docker compose logs -f --tail=100 backend

logs-worker:
	docker compose logs -f --tail=100 worker

logs-vllm:
	docker logs -f vibevoice-vllm

restart-backend:
	docker compose restart backend

restart-worker:
	docker compose restart worker

shell-backend:
	docker compose exec backend bash

shell-worker:
	docker compose exec worker bash

frontend-dev:
	cd frontend && npm run dev

test: test-backend

test-backend:
	docker compose exec backend pytest -v

verify:
	@chmod +x scripts/*.sh 2>/dev/null || true
	bash scripts/verify_deployment.sh

db-migrate:
	docker compose exec backend alembic upgrade head

db-revision:
	@if [ -z "$(M)" ]; then echo "Usage: make db-revision M='your message'"; exit 1; fi
	docker compose exec backend alembic revision --autogenerate -m "$(M)"

build:
	docker compose build

clean:
	@echo "WARNING: This will remove all containers, volumes, and data."
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker compose down -v; \
		rm -rf data/app.db data/uploads data/datasets data/staging data/loras data/merged data/logs data/redis; \
	fi
