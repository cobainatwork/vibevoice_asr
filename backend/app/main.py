"""
FastAPI application entry point.

Wires:
- /api/admin/* — internal UI routes
- /api/v1/*    — external (QC) routes with API key auth
- /metrics     — Prometheus
- /api/v1/openapi.json — exposed for QC client SDK generation

Lifespan: startup creates data dirs, validates Redis & DB connectivity.

See SPEC.md §7 for the full backend layer specification.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import ensure_data_dirs, get_settings
from app.errors import AppError

# 讓 app.* logger 印 INFO log。
# basicConfig(force=True) 重設 root handler level、確保 INFO 不被擋。
# uvicorn 自己的 access log handler 獨立、不受影響。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logging.getLogger("app").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup/shutdown hooks."""
    settings = get_settings()
    ensure_data_dirs(settings)
    logger.info(
        "Backend starting profile=%s mock_vllm=%s",
        settings.deployment_profile, settings.mock_vllm,
    )

    # Best-effort connectivity checks（warn but don't block startup）
    try:
        from sqlalchemy import text as _sql_text

        from app.db import engine
        async with engine.begin() as conn:
            await conn.execute(_sql_text("SELECT 1"))
        logger.info("DB connectivity OK")
    except Exception as e:
        logger.warning("DB connectivity check failed: %s", e)

    try:
        from app.services.queue import get_pool
        pool = await get_pool()
        await pool.ping()
        logger.info("Redis connectivity OK")
    except Exception as e:
        logger.warning("Redis connectivity check failed: %s", e)

    yield

    # Shutdown
    try:
        from app.db import engine
        await engine.dispose()
    except Exception as e:
        logger.warning("DB engine dispose failed: %s", e)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="VibeVoice ASR Internal Platform",
        version="0.1.0",
        description="Internal ASR platform with QC integration. See SPEC.md §17 for v1 API.",
        lifespan=lifespan,
    )

    # CORS — internal use, permissive
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # === Error handler ===
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    # === Routes ===
    # NOTE: Routers will be wired in M2-M6. Imports are lazy to avoid breaking
    # the skeleton when individual route modules are still TODO.
    _wire_routes(app)

    # === Metrics ===
    if settings.metrics_enabled:
        try:
            from prometheus_client import make_asgi_app
            app.mount("/metrics", make_asgi_app())
        except ImportError:
            logger.warning("prometheus_client not installed; /metrics disabled")

    # === Health (minimal, always available) ===
    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


def _wire_routes(app: FastAPI) -> None:
    """
    Register all routers. Each router lives in its own module under app/routes/.
    During scaffold phase, routers may not exist yet — wrap in try/except so
    main.py still imports cleanly.
    """
    # Admin routes
    try:
        from app.routes.admin import projects as admin_projects
        app.include_router(admin_projects.router, prefix="/api/admin", tags=["admin:projects"])
    except ImportError as e:
        logger.warning("admin.projects router not wired: %s", e)

    try:
        from app.routes.admin import jobs as admin_jobs
        app.include_router(admin_jobs.router, prefix="/api/admin", tags=["admin:jobs"])
    except ImportError as e:
        logger.warning("admin.jobs router not wired: %s", e)

    try:
        from app.routes.admin import datasets as admin_datasets
        app.include_router(admin_datasets.router, prefix="/api/admin", tags=["admin:datasets"])
    except ImportError as e:
        logger.warning("admin.datasets router not wired: %s", e)

    try:
        from app.routes.admin import training as admin_training
        app.include_router(admin_training.router, prefix="/api/admin", tags=["admin:training"])
    except ImportError as e:
        logger.warning("admin.training router not wired: %s", e)

    try:
        from app.routes.admin import models as admin_models
        app.include_router(admin_models.router, prefix="/api/admin", tags=["admin:models"])
    except ImportError as e:
        logger.warning("admin.models router not wired: %s", e)

    try:
        from app.routes.admin import api_keys as admin_api_keys
        app.include_router(admin_api_keys.router, prefix="/api/admin", tags=["admin:api_keys"])
    except ImportError as e:
        logger.warning("admin.api_keys router not wired: %s", e)

    try:
        from app.routes.admin import webhook as admin_webhook
        app.include_router(admin_webhook.router, prefix="/api/admin", tags=["admin:webhook"])
    except ImportError as e:
        logger.warning("admin.webhook router not wired: %s", e)

    try:
        from app.routes.admin import integration_calls as admin_calls
        app.include_router(admin_calls.router, prefix="/api/admin", tags=["admin:integration_calls"])
    except ImportError as e:
        logger.warning("admin.integration_calls router not wired: %s", e)

    try:
        from app.routes.admin import system as admin_system
        app.include_router(admin_system.router, prefix="/api/admin", tags=["admin:system"])
    except ImportError as e:
        logger.warning("admin.system router not wired: %s", e)

    # v1 (external) routes
    try:
        from app.routes.v1 import transcribe_ws
        app.include_router(transcribe_ws.router, prefix="/api/v1", tags=["v1"])
    except ImportError as e:
        logger.warning("v1.transcribe_ws router not wired: %s", e)

    try:
        from app.routes.v1 import transcribe_sync
        app.include_router(transcribe_sync.router, prefix="/api/v1", tags=["v1"])
    except ImportError as e:
        logger.warning("v1.transcribe_sync router not wired: %s", e)

    try:
        from app.routes.v1 import jobs as v1_jobs
        app.include_router(v1_jobs.router, prefix="/api/v1", tags=["v1"])
    except ImportError as e:
        logger.warning("v1.jobs router not wired: %s", e)


app = create_app()
