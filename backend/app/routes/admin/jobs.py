"""
Admin: Transcribe & Job management.

See SPEC.md §7.3.5。
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.constants import guess_mime
from app.db import get_db
from app.errors import AppError, ErrorCode, http_error
from app.models import Job, JobSource, JobStatus, Project
from app.schemas import JobCreatedOut, JobOut, Segment, SegmentsPatchIn, YoutubeImportIn
from app.services import youtube_fetcher
from app.services.queue import enqueue_transcribe, enqueue_youtube_fetch
from app.utils.audio import get_duration_sec

YOUTUBE_URL_RE = re.compile(
    r"^https?://(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)",
    re.IGNORECASE,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# === Endpoints ===


@router.post("/transcribe", response_model=JobCreatedOut, status_code=202)
async def transcribe_admin(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Admin upload。建 Job、enqueue。Source = JobSource.ADMIN_UPLOAD。"""
    settings = get_settings()
    project = await _ensure_project(db, project_id)
    contents = await _read_with_size_limit(file, settings)
    job_id, audio_path, filename = _persist_upload(file.filename, contents, settings)
    duration = _probe_or_cleanup(audio_path)
    _validate_duration(duration, settings)
    job = await _create_job_row(
        db, job_id=job_id, project=project,
        filename=filename, audio_path=audio_path, duration=duration,
    )
    await _enqueue_and_mark(db, job, job_id)
    logger.info(
        "admin transcribe enqueued: job_id=%s project_id=%d duration=%.2f",
        job_id, project_id, duration,
    )
    return JobCreatedOut(job_id=job_id)


@router.post("/transcribe/from_youtube", response_model=JobCreatedOut, status_code=202)
async def transcribe_from_youtube(
    payload: YoutubeImportIn,
    db: AsyncSession = Depends(get_db),
):
    """從 YouTube URL 建 Job + 下載音訊 + 抓字幕、完成後自動跑 ASR。"""
    settings = get_settings()
    url = str(payload.url)
    if not YOUTUBE_URL_RE.match(url):
        raise http_error(
            ErrorCode.YOUTUBE_INVALID_URL,
            f"not a supported YouTube URL: {url[:200]}",
        )

    project = await _ensure_project(db, payload.project_id)
    info = await youtube_fetcher.probe(url)

    if info.duration_sec > settings.max_audio_duration_sec:
        raise http_error(
            ErrorCode.YOUTUBE_VIDEO_TOO_LONG,
            f"video {info.duration_sec:.1f}s exceeds limit "
            f"{settings.max_audio_duration_sec}s",
        )

    job = Job(
        project_id=project.id,
        source=JobSource.YOUTUBE_FETCH,
        source_url=url,
        filename=f"{info.title}.mp3",
        audio_path="",  # youtube_fetch_job 完成後才填
        duration_sec=info.duration_sec,
        status=JobStatus.PENDING,
        used_hotwords=list(project.hotwords or []),
    )
    db.add(job)
    await db.flush()

    await enqueue_youtube_fetch(job.id)
    job.status = JobStatus.QUEUED
    await db.flush()

    logger.info(
        "youtube fetch enqueued: job_id=%s project_id=%d duration=%.1f url=%s",
        job.id, project.id, info.duration_sec, url[:100],
    )
    return JobCreatedOut(job_id=job.id)


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(
    project_id: int | None = None,
    source: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job).order_by(Job.created_at.desc())
    if project_id is not None:
        stmt = stmt.where(Job.project_id == project_id)
    if source is not None:
        stmt = stmt.where(Job.source == source)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    return await _get_job_or_404(db, job_id)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await _get_job_or_404(db, job_id)
    _cleanup_audio_files(job)
    await db.delete(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    M2：只標 status=CANCELLED；worker 端尚未檢查 cancel flag，
    若 job 已在跑會跑完才看狀態。M5/M7 補真實中斷。
    """
    job = await _get_job_or_404(db, job_id)
    if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
        return job
    job.status = JobStatus.CANCELLED
    job.finished_at = datetime.utcnow()
    await db.flush()
    return job


@router.get("/jobs/{job_id}/audio")
async def stream_audio(job_id: str, db: AsyncSession = Depends(get_db)):
    """Stream original audio file（給 frontend waveform 使用）。"""
    job = await _get_job_or_404(db, job_id)
    audio_path = Path(job.audio_path)
    if not audio_path.exists():
        raise http_error(ErrorCode.AUDIO_UNREADABLE, "audio file missing")
    return FileResponse(
        audio_path,
        media_type=guess_mime(job.filename),
        filename=job.filename,
    )


@router.patch("/jobs/{job_id}/segments", response_model=JobOut)
async def patch_segments(
    job_id: str,
    payload: SegmentsPatchIn,
    db: AsyncSession = Depends(get_db),
):
    """更新 Job.segments（用於 TranscriptEditor 自動儲存）。"""
    job = await _get_job_or_404(db, job_id)
    _validate_segments(payload.segments)
    job.segments = [s.model_dump() for s in payload.segments]
    await db.flush()
    await db.refresh(job)
    return job


# === Helpers — upload pipeline ===


async def _ensure_project(db: AsyncSession, project_id: int) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise http_error(
            ErrorCode.PROJECT_NOT_FOUND,
            f"project {project_id} not found",
        )
    return project


async def _read_with_size_limit(file: UploadFile, settings: Settings) -> bytes:
    contents = await file.read()
    max_bytes = settings.backend_max_upload_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise http_error(
            ErrorCode.UPLOAD_TOO_LARGE,
            f"upload {len(contents)} bytes exceeds {max_bytes}",
        )
    return contents


def _persist_upload(
    original_filename: str | None, contents: bytes, settings: Settings
) -> tuple[str, Path, str]:
    """寫檔到 data/uploads/{job_id}/audio.<ext>，回 (job_id, audio_path, safe_filename)。"""
    job_id = str(uuid.uuid4())
    safe_filename = os.path.basename(original_filename or "audio")
    ext = os.path.splitext(safe_filename)[1].lower() or ".bin"
    job_dir = settings.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    audio_path = job_dir / f"audio{ext}"
    audio_path.write_bytes(contents)
    return job_id, audio_path, safe_filename


def _probe_or_cleanup(audio_path: Path) -> float:
    """ffprobe 失敗時清理已寫檔案，再轉 400 上拋。"""
    try:
        return get_duration_sec(audio_path)
    except AppError as e:
        _silent_remove(audio_path)
        try:
            audio_path.parent.rmdir()
        except OSError:
            pass
        raise http_error(e.code, e.detail) from e


def _validate_duration(duration: float, settings: Settings) -> None:
    if duration > settings.max_audio_duration_sec:
        raise http_error(
            ErrorCode.AUDIO_TOO_LONG,
            f"audio {duration:.1f}s exceeds limit "
            f"{settings.max_audio_duration_sec}s",
        )
    if duration < 0.5:
        raise http_error(
            ErrorCode.AUDIO_TOO_SHORT,
            f"audio {duration:.2f}s shorter than 0.5s",
        )


async def _create_job_row(
    db: AsyncSession,
    *,
    job_id: str,
    project: Project,
    filename: str,
    audio_path: Path,
    duration: float,
) -> Job:
    job = Job(
        id=job_id,
        project_id=project.id,
        source=JobSource.ADMIN_UPLOAD,
        filename=filename,
        audio_path=str(audio_path),
        duration_sec=duration,
        status=JobStatus.PENDING,
        used_hotwords=list(project.hotwords or []),
    )
    db.add(job)
    await db.flush()
    return job


async def _enqueue_and_mark(db: AsyncSession, job: Job, job_id: str) -> None:
    await enqueue_transcribe(job_id)
    job.status = JobStatus.QUEUED
    await db.flush()


# === Helpers — fetch / cleanup ===


async def _get_job_or_404(db: AsyncSession, job_id: str) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise http_error(
            ErrorCode.JOB_NOT_FOUND, f"job {job_id} not found"
        )
    return job


def _validate_segments(segments: list[Segment]) -> None:
    if not segments:
        raise http_error(
            ErrorCode.INVALID_SEGMENTS, "segments must not be empty"
        )
    # 移除 overlap raise：M5 並行切 chunk + merge 後相鄰段在 overlap 區自然會有
    # 時間重疊（譬如 chunk 0 結尾跟 chunk 1 開頭都在 50-55s 區）。Editor 是讓 user
    # 編輯校正、不該因為上游切段機制 byproduct 而擋住 save。dataset 製作（export
    # 訓練 JSON）階段再嚴格 validate 無 overlap。
    for i, s in enumerate(segments):
        if s.start_time >= s.end_time:
            raise http_error(
                ErrorCode.INVALID_SEGMENTS,
                f"segment[{i}] start ({s.start_time}) >= end ({s.end_time})",
            )
        if s.speaker_id < 0:
            raise http_error(
                ErrorCode.INVALID_SEGMENTS,
                f"segment[{i}] speaker_id must be >= 0, got {s.speaker_id}",
            )
        if not s.text.strip():
            raise http_error(
                ErrorCode.INVALID_SEGMENTS, f"segment[{i}] text is empty"
            )


def _cleanup_audio_files(job: Job) -> None:
    audio_path = Path(job.audio_path)
    _silent_remove(audio_path)
    if audio_path.parent.exists() and audio_path.parent.is_dir():
        try:
            audio_path.parent.rmdir()
        except OSError:
            pass  # 目錄非空就留著


def _silent_remove(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError as e:
        logger.warning("file cleanup failed: %s (%s)", path, e)
