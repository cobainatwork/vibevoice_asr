"""
Admin: Model Version listing + active model switching.

See SPEC.md §7.3.8 and §6.6.
M4 milestone.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import ModelVersionOut, ProjectOut, SetActiveModelIn

router = APIRouter()


@router.get("/projects/{project_id}/models", response_model=list[ModelVersionOut])
async def list_models(project_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M4)
    raise NotImplementedError


@router.post("/projects/{project_id}/active_model", response_model=ProjectOut)
async def set_active_model(
    project_id: int,
    payload: SetActiveModelIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Switch active model. Triggers vLLM restart if path changed.
    See app/services/docker_ctrl.py:restart_vllm_with_model.
    """
    # TODO(M4)
    raise NotImplementedError


@router.delete("/models/{model_id}", status_code=204)
async def delete_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Delete model files (rm -rf data/merged/{...}). Cannot delete active."""
    # TODO(M4)
    raise NotImplementedError
