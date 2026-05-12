"""
Arq worker entry point.

Run: arq app.worker.WorkerSettings

See SPEC.md §7.5.2 for queue design.
"""
from __future__ import annotations

import logging
from typing import Any

from arq.connections import RedisSettings

from app.config import get_settings

logger = logging.getLogger(__name__)


# ============================================================
# Job functions (registered by name)
# ============================================================


async def transcribe_job(ctx: dict, job_id: str) -> str:
    """
    Process an offline transcription job. Delegates to job_runner.run_transcribe.

    M2：整段直接送，無切段、無 webhook。
    M5：加長音檔切段（audio_splitter）。
    M6：加 webhook 觸發。
    """
    from app.services.job_runner import run_transcribe

    logger.info("transcribe_job started: %s", job_id)
    await run_transcribe(job_id)
    logger.info("transcribe_job finished: %s", job_id)
    return job_id


async def youtube_fetch_job(ctx: dict, job_id: str) -> str:
    """YouTube 下載 + 字幕解析、完成後接力給 transcribe_job。"""
    from app.services.youtube_job_runner import run_youtube_fetch_job

    logger.info("youtube_fetch_job started: %s", job_id)
    await run_youtube_fetch_job(job_id)
    logger.info("youtube_fetch_job finished: %s", job_id)
    return job_id


async def training_job(ctx: dict, run_id: str) -> str:
    """
    Run a LoRA fine-tuning training. See app/services/training_runner.py.
    """
    # TODO(M4): implement
    logger.info("training_job started: %s", run_id)
    raise NotImplementedError("training_job — implement in M4")


async def merge_lora_job(ctx: dict, run_id: str) -> str:
    """Merge LoRA adapter into base model. See app/services/training_runner.py."""
    # TODO(M4)
    raise NotImplementedError("merge_lora_job — implement in M4")


async def webhook_delivery_job(ctx: dict, delivery_id: int) -> str:
    """
    Deliver a single Webhook callback with retry. See app/services/webhook.py.
    """
    # TODO(M6)
    logger.info("webhook_delivery_job started: %s", delivery_id)
    raise NotImplementedError("webhook_delivery_job — implement in M6")


# ============================================================
# Worker settings
# ============================================================


async def startup(ctx: dict) -> None:
    """Worker startup — set up DB, vLLM client, etc."""
    settings = get_settings()
    logger.info("Arq worker starting in profile=%s", settings.deployment_profile)
    # TODO: ctx["db"] = ..., ctx["vllm"] = ..., ctx["docker"] = ...


async def shutdown(ctx: dict) -> None:
    """Worker shutdown."""
    logger.info("Arq worker stopping")


class WorkerSettings:
    """Arq Worker configuration."""
    functions: list[Any] = [
        transcribe_job,
        youtube_fetch_job,
        training_job,
        merge_lora_job,
        webhook_delivery_job,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = get_settings().worker_max_jobs
    keep_result = 300  # seconds
    job_timeout = 3600  # 1 hour default; override per-job for training
