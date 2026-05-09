"""
Admin: Transcribe & Job management.

See SPEC.md §7.3.5。
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.constants import guess_mime
from app.db import get_db
from app.errors import AppError, ErrorCode
from app.models import Job, JobSource, JobStatus, Project
from app.schemas import JobCreatedOut, JobOut
from app.services.queue import enqueue_transcribe
from app.utils.audio import get_duration_sec

router = APIRouter()
logger = logging.getLogger(__name__)


async def _get_job_or_404(db: AsyncSession, job_id: str) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.JOB_NOT_FOUND.value,
                    "detail": f"job {job_id} not found"},
        )
    return job


@router.post("/transcribe", response_model=JobCreatedOut, status_code=202)
async def transcribe_admin(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin upload。建立 Job、enqueue 到 Arq。
    Source = JobSource.ADMIN_UPLOAD。
    """
    settings = get_settings()

    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "project_not_found",
                    "detail": f"project {project_id} not found"},
        )

    # 上傳大小限制
    max_bytes = settings.backend_max_upload_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={"code": ErrorCode.UPLOAD_TOO_LARGE.value,
                    "detail": f"upload {len(contents)} bytes exceeds {max_bytes}"},
        )

    # 產 job_id 並寫檔
    job_id = str(uuid.uuid4())
    safe_filename = os.path.basename(file.filename or "audio")
    ext = os.path.splitext(safe_filename)[1].lower() or ".bin"
    job_dir = settings.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    audio_path = job_dir / f"audio{ext}"
    audio_path.write_bytes(contents)

    # ffprobe 取時長
    try:
        duration = get_duration_sec(audio_path)
    except AppError as e:
        # 清理檔案後上拋
        try:
            audio_path.unlink(missing_ok=True)
            job_dir.rmdir()
        except OSError:
            pass
        raise HTTPException(
            status_code=400,
            detail={"code": e.code.value, "detail": e.detail},
        )

    if duration > settings.max_audio_duration_sec:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.AUDIO_TOO_LONG.value,
                "detail": (
                    f"audio {duration:.1f}s exceeds limit "
                    f"{settings.max_audio_duration_sec}s"
                ),
            },
        )
    if duration < 0.5:
        raise HTTPException(
            status_code=400,
            detail={"code": ErrorCode.AUDIO_TOO_SHORT.value,
                    "detail": f"audio {duration:.2f}s shorter than 0.5s"},
        )

    # 建 Job row
    job = Job(
        id=job_id,
        project_id=project_id,
        source=JobSource.ADMIN_UPLOAD,
        filename=safe_filename,
        audio_path=str(audio_path),
        duration_sec=duration,
        status=JobStatus.PENDING,
        used_hotwords=list(project.hotwords or []),
    )
    db.add(job)
    await db.flush()

    # enqueue
    await enqueue_transcribe(job_id)

    # 標 QUEUED
    job.status = JobStatus.QUEUED
    await db.flush()

    logger.info(
        "admin transcribe enqueued: job_id=%s project_id=%d duration=%.2f",
        job_id, project_id, duration,
    )
    return JobCreatedOut(job_id=job_id)


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
    # 同步刪除上傳檔
    try:
        audio_path = Path(job.audio_path)
        if audio_path.exists():
            audio_path.unlink()
        if audio_path.parent.exists() and audio_path.parent.is_dir():
            try:
                audio_path.parent.rmdir()
            except OSError:
                pass  # 目錄非空就留著
    except OSError as e:
        logger.warning("delete_job %s: file cleanup failed: %s", job_id, e)
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
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.AUDIO_UNREADABLE.value,
                    "detail": "audio file missing"},
        )
    return FileResponse(
        audio_path,
        media_type=guess_mime(job.filename),
        filename=job.filename,
    )
