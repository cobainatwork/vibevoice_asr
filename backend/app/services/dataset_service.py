"""
Dataset service — CRUD + from_job + audio 複製。

See SPEC.md §7.3.6 / §9.
M3.5 milestone。本檔含 list / get / update / delete / create_from_import / create_from_job。
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile
from mutagen import File as MutagenFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError, ErrorCode
from app.models import DatasetItem, DatasetSource, Job, JobStatus, Project
from app.schemas import DatasetItemPatch
from app.services import dataset_importer
from app.services.file_store import get_store

logger = logging.getLogger(__name__)


SUPPORTED_IMPORT_FORMATS = {"json", "xlsx", "srt", "txt"}

# 對應到既有 models.DatasetSource enum（M2 已建 migration，不動 schema）
_SOURCE_BY_FORMAT = {
    "json": DatasetSource.IMPORTED_JSON,
    "xlsx": DatasetSource.IMPORTED_XLSX,
    "srt": DatasetSource.IMPORTED_SRT,
    "txt": DatasetSource.IMPORTED_TXT,
}


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


# ============================================================
# create_from_import — Task 8
# ============================================================


async def create_from_import(
    db: AsyncSession,
    *,
    project_id: int,
    audio_upload: UploadFile,
    label_upload: UploadFile,
    format: str,
) -> DatasetItem:
    """從上傳的音檔 + label 檔建立 DatasetItem。

    流程：
      1. 驗 format / project 存在
      2. 串流上傳檔到 tempfile（避免一次載入記憶體）
      3. probe 音檔秒數
      4. 解析 label → canonical training JSON
      5. INSERT row 取 auto-increment id
      6. shutil.move audio tempfile → datasets/{id}/audio.{ext}
      7. 失敗點分兩種 rollback：
         - duration / import_label fail（row 未建）→ 清 tempfile
         - move audio fail（row 已建）→ db.delete + store.delete + commit
    """
    if format not in SUPPORTED_IMPORT_FORMATS:
        raise AppError(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"Format must be one of {sorted(SUPPORTED_IMPORT_FORMATS)}",
        )
    project = await db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found")

    audio_tmp_path = await _stream_to_tempfile(audio_upload)
    label_tmp_path = await _stream_to_tempfile(label_upload)
    try:
        duration = _probe_audio_duration(audio_tmp_path)
        label = dataset_importer.import_label(
            label_path=label_tmp_path,
            audio_filename="audio." + _ext(audio_upload.filename or ""),
            audio_duration=duration,
            format=format,
            project_hotwords=list(project.hotwords or []),
        )
    except Exception:
        _silent_unlink(audio_tmp_path)
        _silent_unlink(label_tmp_path)
        raise
    finally:
        _silent_unlink(label_tmp_path)

    # Insert row（取 auto-increment id 才知道 audio_path 該放哪）
    item = DatasetItem(
        project_id=project_id,
        audio_path="",
        label=label,
        duration_sec=duration,
        source=_SOURCE_BY_FORMAT[format],
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # Move audio tempfile → final location
    ext = _ext(audio_upload.filename or "")
    audio_key = f"datasets/{item.id}/audio.{ext}"
    store = get_store()
    try:
        dst = store.local_path(audio_key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(audio_tmp_path), str(dst))
        item.audio_path = audio_key
        await db.commit()
        await db.refresh(item)
    except Exception:
        # rollback row + cleanup disk
        await db.delete(item)
        await db.commit()
        try:
            await store.delete(f"datasets/{item.id}")
        except Exception as e:  # noqa: BLE001
            logger.warning("create_from_import: cleanup store failed: %s", e)
        _silent_unlink(audio_tmp_path)
        raise
    return item


async def _stream_to_tempfile(upload: UploadFile) -> Path:
    """Stream UploadFile 到臨時檔，回傳 path。caller 負責 unlink。

    持有單一 file handle（與 LocalFileStore.save_stream 相同 pattern），
    避免大檔（>100 MB）每 chunk 重 open 造成 syscall 倍數放大。
    """
    fd, name = tempfile.mkstemp(suffix=Path(upload.filename or "").suffix)
    p = Path(name)
    with os.fdopen(fd, "wb") as f:  # noqa: ASYNC101
        while chunk := await upload.read(65536):
            f.write(chunk)
    return p


def _ext(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower() or "bin"


def _silent_unlink(p: Path) -> None:
    try:
        p.unlink()
    except (FileNotFoundError, OSError):
        pass


def _probe_audio_duration(path: Path) -> float:
    """用 mutagen 取秒數。失敗 → AUDIO_DURATION_FAILED。"""
    try:
        f = MutagenFile(str(path))
        if f is None or not getattr(f, "info", None) or not getattr(f.info, "length", None):
            raise ValueError("no info")
        return float(f.info.length)
    except Exception as e:
        raise AppError(
            ErrorCode.AUDIO_DURATION_FAILED,
            f"Cannot extract duration from {path.name}: {e}",
        ) from None


# ============================================================
# create_from_job — Task 9
# ============================================================


async def create_from_job(
    db: AsyncSession, *, job_id: str, notes: str | None,
) -> DatasetItem:
    """從已完成的 Job 建立 DatasetItem（複製 audio + segments → 0-indexed speaker）。

    流程：
      1. 找 job；不存在 → JOB_NOT_FOUND
      2. status 必須為 DONE；否則 INVALID_JOB_STATE
      3. 讀 job.segments JSON 欄位（內部 1-indexed），轉 0-indexed training JSON
      4. INSERT row 取 auto-increment id
      5. file_store.copy(job.audio_path → datasets/{id}/audio.{ext})
      6. copy 失敗 → rollback row + 清 store
    """
    job = await db.get(Job, job_id)
    if job is None:
        raise AppError(ErrorCode.JOB_NOT_FOUND, f"Job {job_id} not found")
    if job.status != JobStatus.DONE:
        raise AppError(
            ErrorCode.INVALID_JOB_STATE,
            f"Job {job_id} is in {job.status.value}, expected done",
        )

    project = await db.get(Project, job.project_id)
    project_hotwords = list(project.hotwords or []) if project else []

    # job.segments 為內部 1-indexed dict list（admin TranscriptEditor 格式）
    raw_segments = list(job.segments or [])
    ext = _ext(job.audio_path)
    label = {
        "audio_duration": job.duration_sec,
        "audio_path": f"audio.{ext}",
        "segments": [
            {
                "speaker": max(0, int(s["speaker_id"]) - 1),  # 1-indexed → 0-indexed
                "text": s["text"],
                "start": s["start_time"],
                "end": s["end_time"],
            }
            for s in raw_segments
        ],
        "customized_context": project_hotwords,
    }

    item = DatasetItem(
        project_id=job.project_id,
        audio_path="",
        label=label,
        duration_sec=job.duration_sec or 0.0,
        source=DatasetSource.FROM_TRANSCRIPTION,
        source_job_id=job.id,
        notes=notes,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    audio_key = f"datasets/{item.id}/audio.{ext}"
    store = get_store()
    try:
        await store.copy(job.audio_path, audio_key)
        item.audio_path = audio_key
        await db.commit()
        await db.refresh(item)
    except Exception:
        await db.delete(item)
        await db.commit()
        try:
            await store.delete(f"datasets/{item.id}")
        except Exception as e:  # noqa: BLE001
            logger.warning("create_from_job: cleanup store failed: %s", e)
        raise
    return item
