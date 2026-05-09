"""
Admin: Project CRUD + hotwords shortcut.

See SPEC.md §7.3.1、§7.3.2.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
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


# === Helpers ===


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
