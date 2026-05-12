"""PATCH /api/admin/jobs/{id} — partial update Job(目前只 is_corrected)。"""
from __future__ import annotations

import pytest

from app import models  # noqa: F401
from app.db import db_session
from app.models import Job, JobSource, JobStatus, Project


async def _seed_project_and_job(status: JobStatus = JobStatus.DONE) -> str:
    """建一個 project + done job，回 job_id。"""
    async with db_session() as db:
        project = Project(name="p1", hotwords=[])
        db.add(project)
        await db.flush()
        job = Job(
            id="job-1",
            project_id=project.id,
            source=JobSource.ADMIN_UPLOAD,
            filename="a.mp3",
            audio_path="/tmp/a.mp3",
            duration_sec=10.0,
            status=status,
            used_hotwords=[],
        )
        db.add(job)
        await db.commit()
        return job.id


@pytest.mark.asyncio
async def test_patch_job_set_is_corrected_true(app_client):
    job_id = await _seed_project_and_job()
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}",
        json={"is_corrected": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_corrected"] is True


@pytest.mark.asyncio
async def test_patch_job_set_is_corrected_false(app_client):
    job_id = await _seed_project_and_job()
    # 先設 True
    await app_client.patch(f"/api/admin/jobs/{job_id}", json={"is_corrected": True})
    # 再設 False
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}",
        json={"is_corrected": False},
    )
    assert r.status_code == 200
    assert r.json()["is_corrected"] is False


@pytest.mark.asyncio
async def test_patch_job_missing_field_no_op(app_client):
    """body 空(無 is_corrected) → 不改、回原 Job。"""
    job_id = await _seed_project_and_job()
    r = await app_client.patch(f"/api/admin/jobs/{job_id}", json={})
    assert r.status_code == 200
    assert r.json()["is_corrected"] is False


@pytest.mark.asyncio
async def test_patch_job_not_found(app_client):
    r = await app_client.patch(
        "/api/admin/jobs/nonexistent",
        json={"is_corrected": True},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "job_not_found"


@pytest.mark.asyncio
async def test_list_jobs_filter_is_corrected_true(app_client):
    """GET /jobs?is_corrected=true 只回勾過的 Jobs。"""
    job_id = await _seed_project_and_job()
    # 先確認 unmarked job(預設 False)不被列入
    r = await app_client.get("/api/admin/jobs?is_corrected=true")
    assert r.status_code == 200
    assert len(r.json()) == 0

    # 勾它
    await app_client.patch(f"/api/admin/jobs/{job_id}", json={"is_corrected": True})

    r = await app_client.get("/api/admin/jobs?is_corrected=true")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["is_corrected"] is True


@pytest.mark.asyncio
async def test_list_jobs_filter_is_corrected_false(app_client):
    job_id = await _seed_project_and_job()
    r = await app_client.get("/api/admin/jobs?is_corrected=false")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["is_corrected"] is False
