"""
Offline transcribe job orchestration (called from worker).

Pipeline (M2，無切段):
  Job(PENDING)
    → _begin_running：load Job + Project → status=RUNNING
    → _do_transcribe：read file → vllm_client → parser
    → _persist_success：寫回 segments / status=DONE
  失敗 → _mark_failed：status=FAILED + error 欄位

長音檔切段在 M5 加入。Webhook 觸發在 M6 加入。
See SPEC.md §3.4.2、§14.2 (M2 acceptance).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.constants import guess_mime
from app.db import db_session
from app.errors import AppError, ErrorCode
from app.models import Job, JobStatus, Project
from app.services.vllm_client import VllmClient
from app.utils.audio import extract_audio_to_mp3, get_duration_sec, is_video_file
from app.utils.parser import parse_transcription

logger = logging.getLogger(__name__)


async def run_transcribe(job_id: str) -> None:
    """執行單一離線轉錄 Job。Caller：worker.transcribe_job。"""
    state = await _begin_running(job_id)
    if state is None:
        return

    try:
        outcome = await _do_transcribe(get_settings(), state)
        await _persist_success(job_id, state, outcome)
        logger.info(
            "transcribe_job DONE id=%s segments=%d attempts=%d partial=%s",
            job_id, len(outcome["segments"]),
            outcome["attempts"], outcome["partial"],
        )
    except AppError as e:
        await _mark_failed(job_id, f"{e.code.value}: {e.detail}")
        logger.warning("transcribe_job FAILED id=%s: %s", job_id, e)
    except Exception as e:
        await _mark_failed(job_id, f"{ErrorCode.INTERNAL_ERROR.value}: {e}")
        logger.exception("transcribe_job CRASHED id=%s", job_id)
        raise  # 讓 arq retry / DLQ 機制接手


# === Stage helpers ===


async def _begin_running(job_id: str) -> dict[str, Any] | None:
    """Load Job + Project，標 RUNNING；回轉錄需要的 state（None 代表 Job 不存在）。"""
    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            logger.error("transcribe_job: Job %s not found", job_id)
            return None
        project = await db.get(Project, job.project_id)
        state: dict[str, Any] = {
            "audio_path": job.audio_path,
            "duration_initial": job.duration_sec,
            "hotwords": list(project.hotwords) if project else [],
        }
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        await db.commit()
    return state


async def _do_transcribe(
    settings: Settings, state: dict[str, Any]
) -> dict[str, Any]:
    """讀檔 → 視需要抽 audio → vllm_client → parser；回 outcome dict。"""
    audio_path = Path(state["audio_path"])
    if not audio_path.exists():
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"audio file missing: {audio_path}",
        )

    audio_bytes, mime = await _load_audio_for_vllm(audio_path)
    duration = state["duration_initial"] or get_duration_sec(audio_path)

    client = VllmClient(settings.vllm_base_url)
    result = await client.transcribe(
        audio_bytes, mime, duration, state["hotwords"]
    )
    segments, parser_debug = parse_transcription(result["raw_text"])

    return {
        "raw_text": result["raw_text"],
        "segments": segments,
        "parser_debug": parser_debug,
        "duration": duration,
        "attempts": result["attempts"],
        "partial": result.get("partial", False),
    }


async def _load_audio_for_vllm(audio_path: Path) -> tuple[bytes, str]:
    """讀 audio bytes 與對應 MIME；video container 先抽 audio 規避 vLLM 端 demux bug。

    純音訊檔（MP3 / WAV / M4A 等）→ 直接讀 + guess_mime。
    Video 容器（MP4 / MOV / WebM 等）→ ffmpeg demux 成 16kHz mono MP3，
    mime 統一回 audio/mpeg（vLLM 已實證可讀）。

    extract_audio_to_mp3 是 subprocess.run blocking call，用 to_thread 卸到
    thread pool 不擋 event loop（worker 同時處理多個 job 時尤其重要）。
    """
    if is_video_file(audio_path.name):
        logger.info("Video container detected, extracting audio: %s", audio_path.name)
        audio_bytes = await asyncio.to_thread(extract_audio_to_mp3, audio_path)
        return audio_bytes, "audio/mpeg"
    return audio_path.read_bytes(), guess_mime(audio_path.name)


async def _persist_success(
    job_id: str, state: dict[str, Any], outcome: dict[str, Any]
) -> None:
    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            logger.warning("Job %s vanished mid-run; skip persist", job_id)
            return
        job.duration_sec = outcome["duration"]
        job.raw_text = outcome["raw_text"]
        job.segments = outcome["segments"]
        job.chunks_total = 1
        job.chunks_done = 1
        job.progress = 1.0
        job.used_hotwords = state["hotwords"]
        job.status = JobStatus.DONE
        job.finished_at = datetime.utcnow()
        job.error = _summarize_warnings(outcome)
        await db.commit()


async def _mark_failed(job_id: str, error_message: str) -> None:
    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = error_message
        job.finished_at = datetime.utcnow()
        await db.commit()


def _summarize_warnings(outcome: dict[str, Any]) -> str | None:
    """成功 Job 的 error 欄位用於記錄非致命警告（partial / parse warnings）。"""
    if outcome["partial"]:
        return (
            f"{ErrorCode.REPETITION_LOOP.value}: partial result "
            f"after {outcome['attempts']} attempts"
        )
    warnings = outcome["parser_debug"].get("validation_warnings") or []
    if warnings:
        return f"parse_warnings: {','.join(warnings[:3])}"
    return None
