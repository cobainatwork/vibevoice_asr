"""
Admin: System health, vLLM status, GPU info, queue depth.

See SPEC.md §7.3.10.
M2 milestone (basic) → M7 (full).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import GpuInfo, HealthOut, QueueInfo, VllmStatusOut

router = APIRouter()


@router.get("/system/health", response_model=HealthOut)
async def health(db: AsyncSession = Depends(get_db)):
    """
    Aggregate health check: DB + Redis + vLLM (best-effort, non-blocking).
    """
    # TODO(M2)
    raise NotImplementedError


@router.get("/system/vllm_status", response_model=VllmStatusOut)
async def vllm_status():
    """Current vLLM container status + loaded model + uptime."""
    # TODO(M2): docker_ctrl.get_container_info("vibevoice-vllm")
    raise NotImplementedError


@router.get("/system/profile")
async def get_profile():
    """Return current deployment profile + GPU mapping."""
    # TODO(M2): from app.services.deployment.make_strategy()
    raise NotImplementedError


@router.get("/system/gpu", response_model=list[GpuInfo])
async def gpu_info():
    """Query nvidia-smi (or pynvml) for GPU state."""
    # TODO(M7)
    raise NotImplementedError


@router.get("/system/queue", response_model=QueueInfo)
async def queue_info():
    """Query Arq queue: pending count, running count, oldest job age."""
    # TODO(M2)
    raise NotImplementedError
