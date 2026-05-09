"""
Admin: Project CRUD + hotwords shortcut.

See SPEC.md §7.3.1, §7.3.2.
M2 milestone — implement first.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import AppError, ErrorCode
from app.schemas import ProjectIn, ProjectOut, ProjectPatch

router = APIRouter()


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all projects."""
    # TODO(M2): SELECT * FROM projects ORDER BY created_at DESC
    raise NotImplementedError


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(payload: ProjectIn, db: AsyncSession = Depends(get_db)):
    """Create a new project. Name must be unique."""
    # TODO(M2): INSERT, return ProjectOut
    raise NotImplementedError


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M2)
    raise NotImplementedError


@router.put("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, payload: ProjectPatch, db: AsyncSession = Depends(get_db)):
    # TODO(M2)
    raise NotImplementedError


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M2)
    raise NotImplementedError


# === Hotwords shortcut ===


@router.get("/projects/{project_id}/hotwords", response_model=list[str])
async def get_hotwords(project_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M2)
    raise NotImplementedError


@router.put("/projects/{project_id}/hotwords", response_model=list[str])
async def set_hotwords(project_id: int, hotwords: list[str], db: AsyncSession = Depends(get_db)):
    # TODO(M2)
    raise NotImplementedError
