import io
import json
import wave

import pytest
from openpyxl import Workbook

# 必須在 conftest.app_client fixture 跑 create_all 之前讓 ORM models register 到 Base.metadata。
# 若僅靠 fixture 內 `from app.main import app` 也會 import models，但時序在 create_all 之後，
# 第一個跑的 test 會撞 no-such-table。其他 test 檔（test_admin_hotwords_io、
# test_admin_jobs_segments）也是用 top-level import models 來解。
from app import models  # noqa: F401


def _wav_bytes(duration: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * duration))
    return buf.getvalue()


def _xlsx_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_list_empty(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    pid = r.json()["id"]
    r = await app_client.get(f"/api/admin/datasets?project_id={pid}")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_import_xlsx_happy_path(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    pid = r.json()["id"]
    audio = ("source.wav", _wav_bytes(1.0), "audio/wav")
    label = ("label.xlsx", _xlsx_bytes([
        ["start_time", "end_time", "speaker", "text"],
        [0.0, 0.5, 0, "x"],
        [0.5, 1.0, 1, "y"],
    ]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    r = await app_client.post(
        "/api/admin/datasets/import",
        data={"project_id": pid, "format": "xlsx"},
        files={"audio": audio, "label": label},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "imported_xlsx"
    assert len(body["label"]["segments"]) == 2


@pytest.mark.asyncio
async def test_import_unsupported_format_400(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    pid = r.json()["id"]
    audio = ("source.wav", _wav_bytes(1.0), "audio/wav")
    label = ("label.csv", b"x", "text/csv")
    r = await app_client.post(
        "/api/admin/datasets/import",
        data={"project_id": pid, "format": "csv"},
        files={"audio": audio, "label": label},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "unsupported_format"


@pytest.mark.asyncio
async def test_get_not_found_404(app_client):
    r = await app_client.get("/api/admin/datasets/9999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "dataset_not_found"


@pytest.mark.asyncio
async def test_update_label_validate_fail_400(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    pid = r.json()["id"]
    r = await app_client.post(
        "/api/admin/datasets/import",
        data={"project_id": pid, "format": "xlsx"},
        files={
            "audio": ("source.wav", _wav_bytes(1.0), "audio/wav"),
            "label": ("label.xlsx", _xlsx_bytes([
                ["start_time", "end_time", "speaker", "text"],
                [0.0, 0.5, 0, "x"],
            ]), "application/octet-stream"),
        },
    )
    item_id = r.json()["id"]
    bad_label = {
        "audio_duration": 1.0,
        "audio_path": "audio.wav",
        "segments": [{"speaker": 0, "text": "x", "start": 0.5, "end": 0.0}],  # start > end
        "customized_context": [],
    }
    r = await app_client.put(
        f"/api/admin/datasets/{item_id}", json={"label": bad_label},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_idempotent(app_client):
    r = await app_client.delete("/api/admin/datasets/9999")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_template_json(app_client):
    r = await app_client.get("/api/admin/datasets/templates/json")
    assert r.status_code == 200
    assert "audio_duration" in r.text


@pytest.mark.asyncio
async def test_template_unsupported(app_client):
    r = await app_client.get("/api/admin/datasets/templates/csv")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_export_json(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    pid = r.json()["id"]
    r = await app_client.post(
        "/api/admin/datasets/import",
        data={"project_id": pid, "format": "xlsx"},
        files={
            "audio": ("source.wav", _wav_bytes(1.0), "audio/wav"),
            "label": ("label.xlsx", _xlsx_bytes([
                ["start_time", "end_time", "speaker", "text"],
                [0.0, 0.5, 0, "x"],
            ]), "application/octet-stream"),
        },
    )
    item_id = r.json()["id"]
    r = await app_client.get(f"/api/admin/datasets/{item_id}/export?format=json")
    assert r.status_code == 200
    assert json.loads(r.text)["segments"][0]["speaker"] == 0


@pytest.mark.asyncio
async def test_export_srt_speaker_one_indexed(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    pid = r.json()["id"]
    r = await app_client.post(
        "/api/admin/datasets/import",
        data={"project_id": pid, "format": "xlsx"},
        files={
            "audio": ("source.wav", _wav_bytes(1.0), "audio/wav"),
            "label": ("label.xlsx", _xlsx_bytes([
                ["start_time", "end_time", "speaker", "text"],
                [0.0, 0.5, 0, "x"],
            ]), "application/octet-stream"),
        },
    )
    item_id = r.json()["id"]
    r = await app_client.get(f"/api/admin/datasets/{item_id}/export?format=srt")
    assert r.status_code == 200
    assert "Speaker 1: x" in r.text


@pytest.mark.asyncio
async def test_audio_endpoint_streams_file(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    pid = r.json()["id"]
    audio_bytes = _wav_bytes(1.0)
    r = await app_client.post(
        "/api/admin/datasets/import",
        data={"project_id": pid, "format": "xlsx"},
        files={
            "audio": ("source.wav", audio_bytes, "audio/wav"),
            "label": ("label.xlsx", _xlsx_bytes([
                ["start_time", "end_time", "speaker", "text"],
                [0.0, 0.5, 0, "x"],
            ]), "application/octet-stream"),
        },
    )
    item_id = r.json()["id"]
    r = await app_client.get(f"/api/admin/datasets/{item_id}/audio")
    assert r.status_code == 200
    assert r.content == audio_bytes


@pytest.mark.asyncio
async def test_from_job_invalid_state_400(app_client):
    """from_job 對 PENDING / FAILED job 回 400 INVALID_JOB_STATE。"""
    from app.db import db_session
    from app.models import Job, JobSource, JobStatus, Project

    # 直接 seed PENDING job（避開 enqueue → Redis 依賴）。
    async with db_session() as db:
        proj = Project(name="p-from-job", hotwords=[])
        db.add(proj)
        await db.commit()
        job = Job(
            id="job-pending-1",
            project_id=proj.id,
            source=JobSource.ADMIN_UPLOAD,
            status=JobStatus.PENDING,
            audio_path="data/uploads/job-pending-1/a.wav",
            duration_sec=0.5,
            filename="a.wav",
        )
        db.add(job)
        await db.commit()

    r = await app_client.post(
        "/api/admin/datasets/from_job/job-pending-1", json={"notes": None},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_job_state"
