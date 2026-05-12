"""
YouTube fetch job orchestration。

流程:
  1. 取 Job 從 DB(status 應為 QUEUED)
  2. 標 RUNNING
  3. youtube_fetcher.fetch_audio_and_subtitle(下載 audio + 字幕)
  4. 字幕解析 + s2tw 正規化 → Job.reference_subtitles
  5. 寫 Job.audio_path / reference_subtitles / reference_subtitle_lang
  6. status 改 QUEUED(交棒給 transcribe_job)
  7. enqueue_transcribe(復用既有 ASR pipeline)

失敗 → Job.status=FAILED + Job.error 記 ErrorCode + detail。
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.config import get_settings
from app.db import db_session
from app.errors import AppError, ErrorCode
from app.models import Job, JobStatus
from app.services import youtube_fetcher
from app.services.queue import enqueue_transcribe
from app.utils.subtitle_parser import normalize_subtitle, parse_vtt

logger = logging.getLogger(__name__)


async def run_youtube_fetch_job(job_id: str) -> None:
    """Entry point — 由 worker.youtube_fetch_job 呼叫。"""
    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            logger.info("youtube_fetch_job %s not found, skip", job_id)
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        await db.flush()
        await db.commit()

    try:
        await _execute_fetch(job_id)
    except AppError as e:
        await _mark_failed(job_id, e.code, e.detail)
    except Exception as e:  # noqa: BLE001
        logger.exception("youtube_fetch_job unexpected error: %s", job_id)
        await _mark_failed(job_id, ErrorCode.YOUTUBE_FETCH_FAILED, str(e)[:500])


# === Helpers ===


async def _execute_fetch(job_id: str) -> None:
    settings = get_settings()
    job_dir = settings.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None or job.source_url is None:
            raise AppError(
                ErrorCode.YOUTUBE_FETCH_FAILED,
                "job source_url missing",
            )
        url = job.source_url

    fetch = await youtube_fetcher.fetch_audio_and_subtitle(url, job_dir)

    ref_subs: list[dict] | None = None
    ref_lang: str | None = None
    if fetch.subtitle_path is not None:
        text = fetch.subtitle_path.read_text(encoding="utf-8")
        parsed = parse_vtt(text)
        ref_subs = normalize_subtitle(parsed)
        ref_lang = fetch.subtitle_lang

    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.audio_path = str(fetch.audio_path)
        job.reference_subtitles = ref_subs
        job.reference_subtitle_lang = ref_lang
        job.status = JobStatus.QUEUED  # 交棒給 transcribe_job
        await db.flush()
        await db.commit()

    await enqueue_transcribe(job_id)


async def _mark_failed(
    job_id: str, code: ErrorCode, detail: str,
) -> None:
    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = f"{code.value}: {detail}"
        job.finished_at = datetime.utcnow()
        await db.flush()
        await db.commit()
