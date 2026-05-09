"""Service 層 unit test：dataset_service list/get/update/delete。

from_import / from_job 留 Task 8 / 9。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError, ErrorCode
from app.models import DatasetItem, DatasetSource, Project
from app.schemas import DatasetItemPatch
from app.services import dataset_service


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    p = Project(name="t", hotwords=[])
    db_session.add(p)
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def existing_item(db_session: AsyncSession, project: Project) -> DatasetItem:
    item = DatasetItem(
        project_id=project.id,
        audio_path="datasets/1/audio.wav",
        label={
            "audio_duration": 5.0,
            "audio_path": "audio.wav",
            "segments": [{"speaker": 0, "text": "x", "start": 0.0, "end": 5.0}],
            "customized_context": [],
        },
        duration_sec=5.0,
        source=DatasetSource.IMPORTED_JSON,
    )
    db_session.add(item)
    await db_session.commit()
    return item


@pytest.mark.asyncio
async def test_list_items_filters_by_project(db_session, project, existing_item):
    items = await dataset_service.list_items(db_session, project_id=project.id)
    assert len(items) == 1
    assert items[0].id == existing_item.id


@pytest.mark.asyncio
async def test_list_items_other_project_empty(db_session, project, existing_item):
    items = await dataset_service.list_items(db_session, project_id=999)
    assert items == []


@pytest.mark.asyncio
async def test_get_item_found(db_session, existing_item):
    got = await dataset_service.get_item(db_session, existing_item.id)
    assert got.id == existing_item.id


@pytest.mark.asyncio
async def test_get_item_not_found_raises(db_session):
    with pytest.raises(AppError) as ei:
        await dataset_service.get_item(db_session, 9999)
    assert ei.value.code == ErrorCode.DATASET_NOT_FOUND


@pytest.mark.asyncio
async def test_update_item_label_validates(db_session, existing_item):
    bad = {
        "audio_duration": 5.0,
        "audio_path": "audio.wav",
        "segments": [{"speaker": 0, "text": "x", "start": 5.0, "end": 3.0}],  # start > end
        "customized_context": [],
    }
    with pytest.raises(AppError) as ei:
        await dataset_service.update_item(
            db_session,
            item_id=existing_item.id,
            patch=DatasetItemPatch(label=bad),
        )
    assert ei.value.code == ErrorCode.IMPORT_PARSE_FAILED


@pytest.mark.asyncio
async def test_delete_item_idempotent(db_session):
    # 不存在 → 視為成功
    await dataset_service.delete_item(db_session, 9999)
