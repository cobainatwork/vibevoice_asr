"""
Admin: API Key management.

See SPEC.md §7.3.3 and §17.2.
M6 milestone.

🌟 Important: plain key only returned ONCE on create/rotate.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import ApiKeyCreatedOut, ApiKeyIn, ApiKeyOut

router = APIRouter()


@router.get("/projects/{project_id}/api_keys", response_model=list[ApiKeyOut])
async def list_keys(project_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M6)
    raise NotImplementedError


@router.post("/projects/{project_id}/api_keys", response_model=ApiKeyCreatedOut, status_code=201)
async def create_key(
    project_id: int,
    payload: ApiKeyIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new API key.
    See app/services/auth.py:generate_api_key.
    """
    # TODO(M6)
    raise NotImplementedError


@router.post("/api_keys/{key_id}/rotate", response_model=ApiKeyCreatedOut)
async def rotate_key(key_id: int, db: AsyncSession = Depends(get_db)):
    """Generate a new key, invalidate old immediately."""
    # TODO(M6)
    raise NotImplementedError


@router.delete("/api_keys/{key_id}", status_code=204)
async def revoke_key(key_id: int, db: AsyncSession = Depends(get_db)):
    """Set is_active=False."""
    # TODO(M6)
    raise NotImplementedError
