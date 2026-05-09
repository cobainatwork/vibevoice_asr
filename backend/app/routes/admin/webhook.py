"""
Admin: Webhook configuration + test.

See SPEC.md §7.3.4 and §17.6.
M6 milestone.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import (
    WebhookSecretCreatedOut,
    WebhookSettingsIn,
    WebhookSettingsOut,
    WebhookTestResult,
)

router = APIRouter()


@router.get("/projects/{project_id}/webhook", response_model=WebhookSettingsOut)
async def get_webhook(project_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M6)
    raise NotImplementedError


@router.put("/projects/{project_id}/webhook", response_model=WebhookSettingsOut)
async def set_webhook(
    project_id: int,
    payload: WebhookSettingsIn,
    db: AsyncSession = Depends(get_db),
):
    """Set/update webhook URL. If no secret yet, auto-generate one."""
    # TODO(M6)
    raise NotImplementedError


@router.post("/projects/{project_id}/webhook/rotate_secret", response_model=WebhookSecretCreatedOut)
async def rotate_secret(project_id: int, db: AsyncSession = Depends(get_db)):
    """Generate new secret, return plain (only this time)."""
    # TODO(M6)
    raise NotImplementedError


@router.post("/projects/{project_id}/webhook/test", response_model=WebhookTestResult)
async def test_webhook(project_id: int, db: AsyncSession = Depends(get_db)):
    """
    Send a test event to the configured webhook URL with HMAC sig.
    Useful for QC team to verify their endpoint accepts our format.
    """
    # TODO(M6): see app/services/webhook.py
    raise NotImplementedError
