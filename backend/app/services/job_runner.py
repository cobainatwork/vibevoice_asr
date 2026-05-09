"""
Offline transcribe job orchestration (called from worker).

Pipeline (M2，無切段):
  Job(PENDING)
    → load Job + Project
    → status=RUNNING
    → ffprobe duration（若 Job 未帶）
    → vllm_client.transcribe（mock 或真實）
    → parser.parse_transcription
    → save segments、status=DONE
    → (M6) 觸發 webhook
  失敗 → status=FAILED + error 欄位

長音檔切段在 M5 加入。Webhook 觸發在 M6 加入。
See SPEC.md §3.4.2、§14.2 (M2 acceptance).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.constants import guess_mime
from app.db import db_session
from app.errors import AppError, ErrorCode
from app.models import Job, JobStatus, Project
from app.services.vllm_client import VllmClient
from app.utils.audio import get_duration_sec
from app.utils.parser import parse_transcription

logger = logging.getLogger(__name__)


async def run_transcribe(job_id: str) -> None:
    """
    Run a single offline transcribe job to completion.

    Caller: worker.transcribe_job
    """
    settings = get_settings()

    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            logger.error("transcribe_job: Job %s not found", job_id)
            return
        project = await db.get(Project, job.project_id)
        hotwords = list(project.hotwords) if project else []
        audio_path_str = job.audio_path
        existing_duration = job.duration_sec

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        await db.commit()

    try:
        audio_path = Path(audio_path_str)
        if not audio_path.exists():
            raise AppError(
                ErrorCode.AUDIO_UNREADABLE,
                f"audio file missing: {audio_path}",
            )

        audio_bytes = audio_path.read_bytes()
        mime = guess_mime(audio_path.name)
        duration = existing_duration or get_duration_sec(audio_path)

        client = VllmClient(settings.vllm_base_url)
        result = await client.transcribe(audio_bytes, mime, duration, hotwords)

        segments, parser_debug = parse_transcription(result["raw_text"])

        async with db_session() as db:
            job_db = await db.get(Job, job_id)
            if job_db is None:
                logger.warning("Job %s vanished mid-run; skipping persist", job_id)
                return
            job_db.duration_sec = duration
            job_db.raw_text = result["raw_text"]
            job_db.segments = segments
            job_db.chunks_total = 1
            job_db.chunks_done = 1
            job_db.progress = 1.0
            job_db.used_hotwords = hotwords
            job_db.status = JobStatus.DONE
            job_db.finished_at = datetime.utcnow()
            if result.get("partial"):
                # 重複迴圈耗盡重試但仍回傳已生成內容
                job_db.error = (
                    f"{ErrorCode.REPETITION_LOOP.value}: partial result "
                    f"after {result['attempts']} attempts"
                )
            elif parser_debug.get("validation_warnings"):
                # parse 出現 warnings 但仍可用
                job_db.error = (
                    f"parse_warnings: {','.join(parser_debug['validation_warnings'][:3])}"
                )
            await db.commit()

        logger.info(
            "transcribe_job DONE id=%s segments=%d attempts=%d partial=%s",
            job_id,
            len(segments),
            result.get("attempts"),
            result.get("partial"),
        )

    except AppError as e:
        await _mark_failed(job_id, f"{e.code.value}: {e.detail}")
        logger.warning("transcribe_job FAILED id=%s: %s", job_id, e)

    except Exception as e:
        await _mark_failed(job_id, f"{ErrorCode.INTERNAL_ERROR.value}: {e}")
        logger.exception("transcribe_job CRASHED id=%s", job_id)
        raise  # 讓 arq retry / DLQ 機制接手


async def _mark_failed(job_id: str, error_message: str) -> None:
    async with db_session() as db:
        job_db = await db.get(Job, job_id)
        if job_db is None:
            return
        job_db.status = JobStatus.FAILED
        job_db.error = error_message
        job_db.finished_at = datetime.utcnow()
        await db.commit()
