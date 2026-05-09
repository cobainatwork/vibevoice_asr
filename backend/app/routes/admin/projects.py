"""
Admin: Project CRUD + hotwords shortcut.

See SPEC.md §7.3.1、§7.3.2.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import ErrorCode, http_error
from app.models import Project
from app.schemas import ProjectIn, ProjectOut, ProjectPatch

router = APIRouter()


# === Endpoints ===


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    return result.scalars().all()


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectIn, db: AsyncSession = Depends(get_db)
):
    project = Project(
        name=payload.name,
        description=payload.description,
        hotwords=payload.hotwords,
        webhook_url=payload.webhook_url,
    )
    db.add(project)
    await _flush_or_409(db, name=payload.name)
    await db.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    return await _get_or_404(db, project_id)


@router.put("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    payload: ProjectPatch,
    db: AsyncSession = Depends(get_db),
):
    project = await _get_or_404(db, project_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(project, k, v)
    await _flush_or_409(db, name=payload.name)
    await db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int, db: AsyncSession = Depends(get_db)
):
    project = await _get_or_404(db, project_id)
    await db.delete(project)


# === Hotwords shortcut（SPEC.md §7.3.2）===


@router.get("/projects/{project_id}/hotwords", response_model=list[str])
async def get_hotwords(
    project_id: int, db: AsyncSession = Depends(get_db)
):
    project = await _get_or_404(db, project_id)
    return project.hotwords or []


@router.put("/projects/{project_id}/hotwords", response_model=list[str])
async def set_hotwords(
    project_id: int,
    hotwords: list[str] = Body(..., embed=False),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_or_404(db, project_id)
    project.hotwords = list(hotwords)
    await db.flush()
    return project.hotwords


@router.get("/projects/{project_id}/hotwords/export")
async def export_hotwords(
    project_id: int,
    format: str = "txt",
    db: AsyncSession = Depends(get_db),
):
    """匯出 project hotwords。M3 階段僅支援 txt（一詞一行 UTF-8）。"""
    if format != "txt":
        raise http_error(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"format {format!r} not supported (only 'txt')",
        )
    project = await _get_or_404(db, project_id)
    body = "\n".join(project.hotwords or []) + ("\n" if project.hotwords else "")
    safe_name = re.sub(r"[^\w\-]+", "-", project.name).strip("-") or "project"
    today = datetime.utcnow().strftime("%Y%m%d")
    filename = f"hotwords-{safe_name}-{today}.txt"
    return PlainTextResponse(
        content=body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="text/plain; charset=utf-8",
    )


@router.post("/projects/{project_id}/hotwords/import")
async def import_hotwords(
    project_id: int,
    file: UploadFile = File(...),
    mode: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """匯入 hotwords。Mode：append（與現有 list 取聯集，保留順序）/ replace（整批換）。"""
    if mode not in ("append", "replace"):
        raise http_error(
            ErrorCode.INVALID_METADATA,
            f"mode must be 'append' or 'replace', got {mode!r}",
        )
    project = await _get_or_404(db, project_id)
    contents = await file.read()
    if len(contents) > 1024 * 1024:
        raise http_error(
            ErrorCode.UPLOAD_TOO_LARGE,
            f"hotwords import upload {len(contents)} bytes exceeds 1 MB limit",
        )
    new_words = _parse_hotwords_txt(contents)

    existing = list(project.hotwords or [])
    if mode == "replace":
        merged = new_words
        added = len(new_words)
        replaced = len(existing)
        skipped = 0
    else:  # append
        seen = set(existing)
        added_words = [w for w in new_words if w not in seen]
        skipped = len(new_words) - len(added_words)
        merged = existing + added_words
        added = len(added_words)
        replaced = 0

    project.hotwords = merged
    await db.flush()
    return {
        "hotwords": merged,
        "added": added,
        "replaced": replaced,
        "skipped_duplicates": skipped,
    }


# === Helpers ===


def _parse_hotwords_txt(contents: bytes) -> list[str]:
    """Decode UTF-8、splitlines、trim、過濾空行。"""
    text = contents.decode("utf-8", errors="replace")
    return [line.strip() for line in text.splitlines() if line.strip()]


async def _get_or_404(db: AsyncSession, project_id: int) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise http_error(
            ErrorCode.PROJECT_NOT_FOUND,
            f"project {project_id} not found",
        )
    return project


async def _flush_or_409(db: AsyncSession, *, name: str | None) -> None:
    """Flush；name 衝突轉 409 PROJECT_NAME_CONFLICT。"""
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise http_error(
            ErrorCode.PROJECT_NAME_CONFLICT,
            f"project name {name!r} already exists" if name else "name conflict",
        )
