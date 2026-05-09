"""
v1 External API: Job status / result polling.

See SPEC.md §17.5.
M6 milestone.

🌟 Schema is STABLE — do NOT modify without API version bump.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from app.schemas import V1JobResultOut, V1JobStatusOut

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=V1JobStatusOut)
async def get_job_status(
    job_id: str,
    authorization: str | None = Header(None),
):
    """
    Get current status of a job.
    Only the API key's project can access its own jobs.
    Other projects' job_ids return 404 (don't leak existence).
    """
    # TODO(M6)
    raise NotImplementedError


@router.get("/jobs/{job_id}/result", response_model=V1JobResultOut)
async def get_job_result(
    job_id: str,
    authorization: str | None = Header(None),
):
    """Get full result. Only valid when status=done."""
    # TODO(M6)
    raise NotImplementedError
