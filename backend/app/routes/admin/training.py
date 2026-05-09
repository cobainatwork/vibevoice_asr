"""
Admin: Training run management + SSE log streaming.

See SPEC.md §7.3.7 and §10.
M4 milestone.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import TrainingRunIn, TrainingRunOut

router = APIRouter()


@router.get("/training", response_model=list[TrainingRunOut])
async def list_runs(project_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M4)
    raise NotImplementedError


@router.post("/training", response_model=TrainingRunOut, status_code=201)
async def start_training(payload: TrainingRunIn, db: AsyncSession = Depends(get_db)):
    """
    Create a TrainingRun and enqueue training_job.
    See app/services/training_runner.py for actual logic.
    """
    # TODO(M4)
    raise NotImplementedError


@router.get("/training/{run_id}", response_model=TrainingRunOut)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    # TODO(M4)
    raise NotImplementedError


@router.get("/training/{run_id}/log")
async def stream_log(run_id: str):
    """SSE log tailing. Reads data/logs/training_{run_id}.log."""
    # TODO(M4): yield SSE events as new log lines arrive
    raise NotImplementedError


@router.post("/training/{run_id}/cancel", response_model=TrainingRunOut)
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    # TODO(M4): docker stop + status=CANCELLED
    raise NotImplementedError
