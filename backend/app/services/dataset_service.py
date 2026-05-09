"""
Dataset service — CRUD + from_job + audio 複製。

See SPEC.md §7.3.6 / §9.
M3.5 milestone。本檔含 list / get / update / delete；
create_from_import / create_from_job 留 Task 8 / 9。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError, ErrorCode
from app.models import DatasetItem
from app.schemas import DatasetItemPatch
from app.services import dataset_importer
from app.services.file_store import get_store

logger = logging.getLogger(__name__)


async def list_items(db: AsyncSession, project_id: int) -> list[DatasetItem]:
    """依 project 過濾，最新建立優先。"""
    stmt = (
        select(DatasetItem)
        .where(DatasetItem.project_id == project_id)
        .order_by(DatasetItem.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_item(db: AsyncSession, item_id: int) -> DatasetItem:
    """找不到 raise DATASET_NOT_FOUND。"""
    item = await db.get(DatasetItem, item_id)
    if item is None:
        raise AppError(ErrorCode.DATASET_NOT_FOUND, f"Dataset item {item_id} not found")
    return item


async def update_item(
    db: AsyncSession,
    *,
    item_id: int,
    patch: DatasetItemPatch,
) -> DatasetItem:
    """部分更新 label / notes；label 走 dataset_importer.validate_segments。"""
    item = await get_item(db, item_id)
    if patch.label is not None:
        segs = patch.label.get("segments")
        if not isinstance(segs, list):
            raise AppError(ErrorCode.IMPORT_PARSE_FAILED, "label.segments must be list")
        dataset_importer.validate_segments(segs, item.duration_sec)
        item.label = patch.label
    if patch.notes is not None:
        item.notes = patch.notes
    await db.commit()
    await db.refresh(item)
    return item


async def delete_item(db: AsyncSession, item_id: int) -> None:
    """idempotent：找不到視為成功；刪 audio 失敗只 warning，不擋 DB delete。"""
    item = await db.get(DatasetItem, item_id)
    if item is None:
        return
    store = get_store()
    target_dir = f"datasets/{item_id}"
    try:
        await store.delete(target_dir)
    except Exception as e:  # noqa: BLE001
        logger.warning("delete_item: failed to remove %s: %s", target_dir, e)
    await db.delete(item)
    await db.commit()
