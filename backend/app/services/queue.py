"""
Arq queue helpers.

See SPEC.md §7.5.2.
"""
from __future__ import annotations

import logging
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings

logger = logging.getLogger(__name__)


_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    """Lazily create a singleton Arq pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue_transcribe(job_id: str) -> str:
    """Enqueue a transcribe_job. Returns job_id."""
    pool = await get_pool()
    await pool.enqueue_job("transcribe_job", job_id, _job_id=f"transcribe:{job_id}")
    return job_id


async def enqueue_training(run_id: str) -> str:
    pool = await get_pool()
    await pool.enqueue_job("training_job", run_id, _job_id=f"training:{run_id}")
    return run_id


async def enqueue_webhook(delivery_id: int, delay_sec: int = 0) -> int:
    """Enqueue a webhook delivery, optionally delayed (for retries)."""
    from datetime import timedelta
    pool = await get_pool()
    await pool.enqueue_job(
        "webhook_delivery_job",
        delivery_id,
        _job_id=f"webhook:{delivery_id}:{delay_sec}",
        _defer_by=timedelta(seconds=delay_sec) if delay_sec > 0 else None,
    )
    return delivery_id


async def queue_depth() -> dict[str, int]:
    """Return rough queue stats for /api/admin/system/queue."""
    pool = await get_pool()
    # TODO: arq exposes .queued_jobs etc. — wire properly in M2
    return {"pending": 0, "running": 0, "workers": 0, "oldest_age_sec": 0}
