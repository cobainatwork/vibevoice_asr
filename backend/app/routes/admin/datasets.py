"""
Admin: Dataset CRUD + multi-format import + templates + export.

See SPEC.md §7.3.6 / §9.
M3.5 milestone.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import AppError, ErrorCode, http_error
from app.schemas import DatasetFromJobIn, DatasetItemOut, DatasetItemPatch
from app.services import dataset_exporter, dataset_service
from app.services.file_store import get_store

router = APIRouter()

_TEMPLATE_FORMATS = {"json", "xlsx", "srt", "txt"}
_EXPORT_FORMATS = {"json", "srt", "xlsx"}


@router.get("/datasets", response_model=list[DatasetItemOut])
async def list_datasets(project_id: int, db: AsyncSession = Depends(get_db)):
    return await dataset_service.list_items(db, project_id=project_id)


@router.get("/datasets/templates/{format}")
async def download_template(format: str):
    """Serve a pre-built template file from backend/templates/."""
    if format not in _TEMPLATE_FORMATS:
        raise http_error(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"Template format must be one of {sorted(_TEMPLATE_FORMATS)}",
        )
    path = Path("templates") / f"dataset_template.{format}"
    if not path.exists():
        # 範本檔在 image build 時 COPY 進 /app/templates/，prod 不該觸發；
        # 借用 DATASET_NOT_FOUND 是因 errors.py 沒 generic NOT_FOUND。
        raise http_error(ErrorCode.DATASET_NOT_FOUND, f"Template missing: {path.name}")
    return FileResponse(path, filename=path.name)


@router.get("/datasets/{item_id}", response_model=DatasetItemOut)
async def get_dataset(item_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await dataset_service.get_item(db, item_id)
    except AppError as e:
        raise http_error(e.code, e.detail) from e


@router.post("/datasets/import", response_model=DatasetItemOut, status_code=201)
async def import_dataset(
    audio: UploadFile = File(...),
    label: UploadFile = File(...),
    project_id: int = Form(...),
    format: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Import a dataset item. See SPEC.md §9.2."""
    try:
        return await dataset_service.create_from_import(
            db,
            project_id=project_id,
            audio_upload=audio,
            label_upload=label,
            format=format,
        )
    except AppError as e:
        raise http_error(e.code, e.detail) from e


@router.post("/datasets/from_job/{job_id}", response_model=DatasetItemOut, status_code=201)
async def from_job(
    job_id: str,
    payload: DatasetFromJobIn,
    db: AsyncSession = Depends(get_db),
):
    """Convert a completed Job's segments into a DatasetItem (起點，可後續編輯)。"""
    try:
        return await dataset_service.create_from_job(
            db, job_id=job_id, notes=payload.notes,
        )
    except AppError as e:
        raise http_error(e.code, e.detail) from e


@router.put("/datasets/{item_id}", response_model=DatasetItemOut)
async def update_dataset(
    item_id: int,
    payload: DatasetItemPatch,
    db: AsyncSession = Depends(get_db),
):
    """Save edits to label (TranscriptEditor auto-save 用)."""
    try:
        return await dataset_service.update_item(db, item_id=item_id, patch=payload)
    except AppError as e:
        raise http_error(e.code, e.detail) from e


@router.delete("/datasets/{item_id}", status_code=204)
async def delete_dataset(item_id: int, db: AsyncSession = Depends(get_db)):
    await dataset_service.delete_item(db, item_id)
    return Response(status_code=204)


@router.get("/datasets/{item_id}/audio")
async def stream_dataset_audio(item_id: int, db: AsyncSession = Depends(get_db)):
    try:
        item = await dataset_service.get_item(db, item_id)
    except AppError as e:
        raise http_error(e.code, e.detail) from e
    store = get_store()
    path = store.local_path(item.audio_path)
    if not path.exists():
        raise http_error(ErrorCode.DATASET_NOT_FOUND, "Audio file missing on disk")
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@router.get("/datasets/{item_id}/export")
async def export_dataset(
    item_id: int,
    format: str = "json",
    db: AsyncSession = Depends(get_db),
):
    if format not in _EXPORT_FORMATS:
        raise http_error(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"Export format must be one of {sorted(_EXPORT_FORMATS)}",
        )
    try:
        item = await dataset_service.get_item(db, item_id)
    except AppError as e:
        raise http_error(e.code, e.detail) from e
    content, ct, name = dataset_exporter.export_item(item, format)  # type: ignore[arg-type]
    return Response(
        content=content,
        media_type=ct,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
