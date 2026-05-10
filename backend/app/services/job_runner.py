"""
Offline transcribe job orchestration (called from worker).

Pipeline:
  Job(PENDING)
    → _begin_running：load Job + Project → status=RUNNING
    → _do_transcribe：read file → split（如需）→ 各 chunk vllm_client → parser → merge
    → _persist_success：寫回 segments / status=DONE
  失敗 → _mark_failed：status=FAILED + error 欄位

長音檔處理（M5 minimal viable）：duration > AUTO_SPLIT_THRESHOLD_SEC（預設 60s）
時切成多 chunk file，序列推論後 merge_chunk_results 合併時間軸。每 chunk 完成
更新 chunks_done / progress，前端 polling 拿到中段進度。Webhook 觸發在 M6 加入。

See SPEC.md §3.4.2、§6.4、§14.2 (M2 acceptance).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.constants import guess_mime
from app.db import db_session
from app.errors import AppError, ErrorCode
from app.models import Job, JobStatus, Project
from app.services.audio_splitter import Chunk, merge_chunk_results, split_long_audio
from app.services.vllm_client import VllmClient
from app.utils.audio import extract_audio_to_mp3, get_duration_sec, is_video_file
from app.utils.parser import parse_transcription

logger = logging.getLogger(__name__)


@dataclass
class ChunkOutcome:
    """單一 chunk（含 retry 後）的轉錄結果。

    fields:
      segments: 該 chunk（已加 offset）的 segment list
      raw_text: vLLM 原始輸出（多次 retry 時用 separator 串接）
      partial: 達 retry 上限仍 partial 為 True
      depth_reached: 實際遞迴到的最深深度（0 = 不 retry、N = retry N 次）
      attempts: 該 chunk 累計 vLLM 呼叫次數（含所有 retry sub-chunks）
    """

    segments: list[dict] = field(default_factory=list)
    raw_text: str = ""
    partial: bool = False
    depth_reached: int = 0
    attempts: int = 0


async def run_transcribe(job_id: str) -> None:
    """執行單一離線轉錄 Job。Caller：worker.transcribe_job。"""
    state = await _begin_running(job_id)
    if state is None:
        return

    try:
        outcome = await _do_transcribe(get_settings(), state)
        await _persist_success(job_id, state, outcome)
        logger.info(
            "transcribe_job DONE id=%s segments=%d attempts=%d partial=%s chunks=%d",
            job_id, len(outcome["segments"]),
            outcome["attempts"], outcome["partial"],
            outcome.get("chunks_total", 1),
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
            "job_id": job_id,
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
    """讀檔 → 視需要切段 → 各 chunk 推論 → merge；回 outcome dict。"""
    audio_path = Path(state["audio_path"])
    if not audio_path.exists():
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"audio file missing: {audio_path}",
        )

    duration = state["duration_initial"] or get_duration_sec(audio_path)

    chunks_dir = audio_path.parent / "chunks"
    chunks = await asyncio.to_thread(split_long_audio, audio_path, chunks_dir)
    try:
        return await _transcribe_all_chunks(settings, state, duration, chunks)
    finally:
        if chunks and chunks[0].is_split:
            shutil.rmtree(chunks_dir, ignore_errors=True)


async def _transcribe_all_chunks(
    settings: Settings,
    state: dict[str, Any],
    duration: float,
    chunks: list[Chunk],
) -> dict[str, Any]:
    """逐 chunk 呼 vLLM、parse、merge；單 chunk 路徑兼容（n=1 時走 _load_audio_for_vllm）。"""
    is_multi = len(chunks) > 1
    job_id = state["job_id"]

    if is_multi:
        await _update_progress(job_id, chunks_total=len(chunks), chunks_done=0)

    client = VllmClient(settings.vllm_base_url)
    chunk_segments_lists: list[list[dict]] = []
    chunk_raw_texts: list[str] = []
    parser_warnings: list[str] = []
    total_attempts = 0
    any_partial = False

    for i, chunk in enumerate(chunks):
        audio_bytes, mime = await _load_chunk_audio(chunk)
        chunk_duration = chunk.end_offset_sec - chunk.start_offset_sec
        result = await client.transcribe(
            audio_bytes, mime, chunk_duration, state["hotwords"]
        )
        segs, debug = parse_transcription(result["raw_text"])
        chunk_segments_lists.append(segs)
        chunk_raw_texts.append(result["raw_text"])
        if debug.get("validation_warnings"):
            parser_warnings.extend(debug["validation_warnings"])
        total_attempts += result["attempts"]
        if result.get("partial"):
            any_partial = True

        if is_multi:
            await _update_progress(
                job_id, chunks_total=len(chunks), chunks_done=i + 1
            )

    merged_segments = merge_chunk_results(chunks, chunk_segments_lists)

    return {
        "raw_text": _join_chunk_raw_texts(chunk_raw_texts),
        "segments": merged_segments,
        "parser_debug": {"validation_warnings": parser_warnings},
        "duration": duration,
        "attempts": total_attempts,
        "partial": any_partial,
        "chunks_total": len(chunks),
    }


async def _load_chunk_audio(chunk: Chunk) -> tuple[bytes, str]:
    """讀 chunk audio bytes 與對應 MIME。

    is_split=True（splitter 切出來的 mp3 chunk）→ 直接讀 + audio/mpeg。
    is_split=False（單 chunk、duration <= threshold）→ 走 _load_audio_for_vllm
    保留 video → audio 提取路徑。
    """
    if chunk.is_split:
        return chunk.path.read_bytes(), "audio/mpeg"
    return await _load_audio_for_vllm(chunk.path)


async def _load_audio_for_vllm(audio_path: Path) -> tuple[bytes, str]:
    """讀 audio bytes 與對應 MIME；video container 先抽 audio 規避 vLLM 端 demux bug。

    純音訊檔（MP3 / WAV / M4A 等）→ 直接讀 + guess_mime。
    Video 容器（MP4 / MOV / WebM 等）→ ffmpeg demux 成 16kHz mono MP3，
    mime 統一回 audio/mpeg。
    """
    if is_video_file(audio_path.name):
        logger.info("Video container detected, extracting audio: %s", audio_path.name)
        audio_bytes = await asyncio.to_thread(extract_audio_to_mp3, audio_path)
        return audio_bytes, "audio/mpeg"
    return audio_path.read_bytes(), guess_mime(audio_path.name)


def _join_chunk_raw_texts(chunk_raw_texts: list[str]) -> str:
    """合併多 chunk raw_text 為單一字串，保留分段標記方便事後 debug。"""
    if len(chunk_raw_texts) == 1:
        return chunk_raw_texts[0]
    return "\n\n--- chunk separator ---\n\n".join(chunk_raw_texts)


async def _update_progress(
    job_id: str, chunks_total: int, chunks_done: int,
) -> None:
    """中段進度更新。caller 控制呼叫節奏（每 chunk 結束一次）。"""
    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.chunks_total = chunks_total
        job.chunks_done = chunks_done
        job.progress = chunks_done / chunks_total if chunks_total > 0 else 0.0
        await db.commit()


async def _persist_success(
    job_id: str, state: dict[str, Any], outcome: dict[str, Any]
) -> None:
    async with db_session() as db:
        job = await db.get(Job, job_id)
        if job is None:
            logger.warning("Job %s vanished mid-run; skip persist", job_id)
            return
        chunks_total = outcome.get("chunks_total", 1)
        job.duration_sec = outcome["duration"]
        job.raw_text = outcome["raw_text"]
        job.segments = outcome["segments"]
        job.chunks_total = chunks_total
        job.chunks_done = chunks_total
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
