"""
Admin: Transcribe & Job management.

See SPEC.md §7.3.5.
M2 milestone — implement first.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import JobCreatedOut, JobOut

router = APIRouter()


@router.post("/transcribe", response_model=JobCreatedOut, status_code=202)
async def transcribe_admin(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin upload — multipart file. Creates Job and enqueues to Arq.
    Source = JobSource.ADMIN_UPLOAD.
    """
    # TODO(M2):
    # 1. Validate project exists
    # 2. Save file to data/uploads/{job_id}/
    # 3. ffprobe duration; reject if > MAX_AUDIO_DURATION_SEC
    # 4. Create Job (status=PENDING, source=ADMIN_UPLOAD, used_hotwords=project.hotwords)
    # 5. Enqueue: await services.queue.enqueue_transcribe(job_id)
    # 6. Return {job_id}
    raise NotImplementedError


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(
    project_id: int | None = None,
    source: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    # TODO(M2)
    raise NotImplementedError


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    # TODO(M2)
    raise NotImplementedError


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    # TODO(M2)
    raise NotImplementedError


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    # TODO(M2)
    raise NotImplementedError


@router.get("/jobs/{job_id}/audio")
async def stream_audio(job_id: str, db: AsyncSession = Depends(get_db)):
    """Stream the original audio file (for waveform display in editor)."""
    # TODO(M3): StreamingResponse with appropriate Content-Type from job.filename
    raise NotImplementedError
