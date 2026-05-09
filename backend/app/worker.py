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
    Process an offline transcription job.

    Steps:
      1. Load Job from DB
      2. ffprobe duration; split if > AUTO_SPLIT_THRESHOLD_SEC
      3. For each chunk: vllm_client.transcribe()
      4. merge_chunk_results
      5. Save segments to DB; status=DONE
      6. If Job.callback_url or project.webhook_url: enqueue webhook_delivery_job

    See app/services/job_runner.py for actual implementation.
    """
    # TODO(M2): implement
    logger.info("transcribe_job started: %s", job_id)
    raise NotImplementedError("transcribe_job — implement in M2 (see SPEC.md §14)")


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
