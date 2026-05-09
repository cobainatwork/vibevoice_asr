"""
Admin: Audit log of v1 API calls (read-only).

See SPEC.md §7.3.9.
M6 milestone — populated by middleware.api_key_auth.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import IntegrationCallOut

router = APIRouter()


@router.get("/integration_calls", response_model=list[IntegrationCallOut])
async def list_calls(
    project_id: int | None = None,
    api_key_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    # TODO(M6): SELECT ... FROM integration_calls ORDER BY created_at DESC LIMIT ...
    raise NotImplementedError
