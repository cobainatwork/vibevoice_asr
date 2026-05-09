"""
Admin: Dataset CRUD + multi-format import + templates + export.

See SPEC.md §7.3.6 and §9.
M3.5 milestone.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import DatasetFromJobIn, DatasetItemOut, DatasetItemPatch

router = APIRouter()


@router.get("/datasets", response_model=list[DatasetItemOut])
async def list_datasets(project_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M3.5)
    raise NotImplementedError


@router.get("/datasets/{item_id}", response_model=DatasetItemOut)
async def get_dataset(item_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M3.5)
    raise NotImplementedError


@router.post("/datasets/import", response_model=DatasetItemOut, status_code=201)
async def import_dataset(
    audio: UploadFile = File(...),
    label: UploadFile = File(...),
    project_id: int = Form(...),
    format: str = Form(...),  # xlsx | csv | srt | vtt | json | txt
    db: AsyncSession = Depends(get_db),
):
    """
    Import a dataset item. Backend converts label to canonical training JSON
    using services.dataset_importer.

    See SPEC.md §9.2.
    """
    # TODO(M3.5)
    raise NotImplementedError


@router.post("/datasets/from_job/{job_id}", response_model=DatasetItemOut, status_code=201)
async def from_job(
    job_id: str,
    payload: DatasetFromJobIn,
    db: AsyncSession = Depends(get_db),
):
    """Convert a completed Job's segments into a DatasetItem (starting point for editing)."""
    # TODO(M3.5)
    raise NotImplementedError


@router.put("/datasets/{item_id}", response_model=DatasetItemOut)
async def update_dataset(
    item_id: int,
    payload: DatasetItemPatch,
    db: AsyncSession = Depends(get_db),
):
    """Save edits to label (used by TranscriptEditor auto-save)."""
    # TODO(M3.5)
    raise NotImplementedError


@router.delete("/datasets/{item_id}", status_code=204)
async def delete_dataset(item_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M3.5)
    raise NotImplementedError


@router.get("/datasets/{item_id}/audio")
async def stream_dataset_audio(item_id: int, db: AsyncSession = Depends(get_db)):
    # TODO(M3)
    raise NotImplementedError


@router.get("/datasets/templates/{format}")
async def download_template(format: str):
    """Serve a pre-built template file from backend/templates/."""
    # TODO(M3.5): FileResponse("templates/dataset_template.{format}")
    raise NotImplementedError


@router.get("/datasets/{item_id}/export")
async def export_dataset(item_id: int, format: str = "json", db: AsyncSession = Depends(get_db)):
    # TODO(M3.5): convert internal label → requested format
    raise NotImplementedError
