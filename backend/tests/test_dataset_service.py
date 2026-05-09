"""Service 層 unit test：dataset_service list/get/update/delete。

from_import / from_job 留 Task 8 / 9。
"""
from __future__ import annotations

import io
import wave

import pytest
import pytest_asyncio
from fastapi import UploadFile
from openpyxl import Workbook
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


# ============================================================
# create_from_import — Task 8
# ============================================================


def _make_wav_bytes(duration_sec: float = 1.0) -> bytes:
    """產生 1 秒 silent WAV in memory（不依賴外部音檔）。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * duration_sec))
    return buf.getvalue()


def _make_xlsx_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_create_from_import_xlsx(db_session, project, tmp_path, monkeypatch):
    # file_store 改用 tmp_path
    from app.services import file_store as fs
    fs._store = fs.LocalFileStore(root=tmp_path)

    audio = _upload("source.wav", _make_wav_bytes(1.0))
    label = _upload("label.xlsx", _make_xlsx_bytes([
        ["start_time", "end_time", "speaker", "text"],
        [0.0, 0.5, 0, "x"],
        [0.5, 1.0, 1, "y"],
    ]))
    item = await dataset_service.create_from_import(
        db_session,
        project_id=project.id,
        audio_upload=audio,
        label_upload=label,
        format="xlsx",
    )
    assert item.id is not None
    assert item.audio_path == f"datasets/{item.id}/audio.wav"
    assert (tmp_path / item.audio_path).read_bytes() == _make_wav_bytes(1.0)
    assert item.label["segments"][0]["speaker"] == 0
    assert item.label["customized_context"] == project.hotwords
    assert item.duration_sec == pytest.approx(1.0, abs=0.05)
    fs._store = None  # cleanup


@pytest.mark.asyncio
async def test_create_from_import_unsupported_format(db_session, project):
    audio = _upload("source.wav", _make_wav_bytes(1.0))
    label = _upload("label.csv", b"x")
    with pytest.raises(AppError) as ei:
        await dataset_service.create_from_import(
            db_session, project_id=project.id,
            audio_upload=audio, label_upload=label, format="csv",
        )
    assert ei.value.code == ErrorCode.UNSUPPORTED_FORMAT


@pytest.mark.asyncio
async def test_create_from_import_audio_duration_failed(db_session, project, tmp_path):
    from app.services import file_store as fs
    fs._store = fs.LocalFileStore(root=tmp_path)

    audio = _upload("garbage.wav", b"not actually a wav file")
    label = _upload("label.xlsx", _make_xlsx_bytes([
        ["start_time", "end_time", "speaker", "text"],
        [0.0, 1.0, 0, "x"],
    ]))
    with pytest.raises(AppError) as ei:
        await dataset_service.create_from_import(
            db_session, project_id=project.id,
            audio_upload=audio, label_upload=label, format="xlsx",
        )
    assert ei.value.code == ErrorCode.AUDIO_DURATION_FAILED
    fs._store = None


@pytest.mark.asyncio
async def test_create_from_import_rollback_on_parse_fail(db_session, project, tmp_path):
    """label 結構壞 → DB 不留 row、disk 不留 audio。"""
    from app.services import file_store as fs
    fs._store = fs.LocalFileStore(root=tmp_path)

    audio = _upload("source.wav", _make_wav_bytes(1.0))
    label = _upload("label.xlsx", _make_xlsx_bytes([
        ["start_time", "end_time", "speaker"],  # 缺 text 欄
        [0.0, 1.0, 0],
    ]))
    with pytest.raises(AppError):
        await dataset_service.create_from_import(
            db_session, project_id=project.id,
            audio_upload=audio, label_upload=label, format="xlsx",
        )
    items = await dataset_service.list_items(db_session, project_id=project.id)
    assert len(items) == 0
    # disk 不應留下任何 datasets/*/
    assert not (tmp_path / "datasets").exists() or not any((tmp_path / "datasets").iterdir())
    fs._store = None
