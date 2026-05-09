"""
Admin: System health, vLLM status, GPU info, queue depth.

See SPEC.md §7.3.10。
M2 milestone（basic）→ M7（full GPU info via pynvml）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.schemas import GpuInfo, HealthOut, QueueInfo, VllmStatusOut
from app.services.deployment import make_strategy
from app.services.queue import get_pool, queue_depth
from app.services.vllm_client import VllmClient

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/system/health", response_model=HealthOut)
async def health(db: AsyncSession = Depends(get_db)):
    """
    Aggregate health：DB / Redis / vLLM 各自 best-effort，失敗不互相影響。
    """
    settings = get_settings()

    # DB ping
    try:
        await db.execute(sql_text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.warning("db ping failed: %s", e)
        db_status = f"down: {e}"

    # Redis ping
    try:
        pool = await get_pool()
        await pool.ping()
        redis_status = "ok"
    except Exception as e:
        logger.warning("redis ping failed: %s", e)
        redis_status = f"down: {e}"

    # vLLM ping
    if settings.mock_vllm:
        vllm_status = "mock"
    else:
        client = VllmClient(settings.vllm_base_url)
        try:
            vllm_status = "ready" if await client.health() else "down"
        except Exception as e:
            logger.warning("vllm ping failed: %s", e)
            vllm_status = f"down: {e}"

    return HealthOut(
        ok=(db_status == "ok" and redis_status == "ok"),
        vllm_status=vllm_status,
        redis_status=redis_status,
        db_status=db_status,
    )


@router.get("/system/vllm_status", response_model=VllmStatusOut)
async def vllm_status_endpoint():
    settings = get_settings()
    if settings.mock_vllm:
        return VllmStatusOut(
            status="mock",
            model=settings.vllm_default_model,
            uptime_sec=None,
        )
    client = VllmClient(settings.vllm_base_url)
    try:
        if not await client.health():
            return VllmStatusOut(status="down", model=None, uptime_sec=None)
        model = await client.get_loaded_model()
    except Exception as e:
        logger.warning("vllm_status failed: %s", e)
        return VllmStatusOut(status="down", model=None, uptime_sec=None)
    return VllmStatusOut(status="ready", model=model, uptime_sec=None)


@router.get("/system/profile")
async def get_profile():
    settings = get_settings()
    strategy = make_strategy()
    return {
        "profile": strategy.profile,
        "gpu_inference_devices": settings.gpu_inference_devices,
        "gpu_training_devices": settings.gpu_training_devices,
        "tensor_parallel": settings.vllm_tensor_parallel,
        "data_parallel": settings.vllm_data_parallel,
        "max_concurrent_requests": strategy.vllm_max_concurrent_requests(),
        "can_concurrent_train": strategy.can_concurrent_train(),
        "mock_vllm": settings.mock_vllm,
    }


@router.get("/system/gpu", response_model=list[GpuInfo])
async def gpu_info():
    """nvidia-smi / pynvml 在 M7 才接；目前回空 list。"""
    return []


@router.get("/system/queue", response_model=QueueInfo)
async def queue_info():
    stats = await queue_depth()
    return QueueInfo(**stats)
