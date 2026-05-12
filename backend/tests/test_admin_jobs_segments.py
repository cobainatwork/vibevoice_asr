"""Tests for PATCH /api/admin/jobs/{id}/segments."""
from __future__ import annotations

import pytest

from app.db import db_session
from app.models import Job, JobSource, JobStatus, Project


async def _seed_project_and_job(*, segments=None):
    async with db_session() as db:
        p = Project(name="proj", hotwords=[])
        db.add(p)
        await db.flush()
        j = Job(
            id="job-1",
            project_id=p.id,
            source=JobSource.ADMIN_UPLOAD,
            filename="a.wav",
            audio_path="/tmp/a.wav",
            duration_sec=10.0,
            status=JobStatus.DONE,
            segments=segments,
            used_hotwords=[],
        )
        db.add(j)
        await db.commit()
        return p.id, j.id


@pytest.mark.asyncio
async def test_patch_segments_replaces_segments(app_client):
    _, job_id = await _seed_project_and_job(
        segments=[{"start_time": 0.0, "end_time": 3.0, "speaker_id": 1, "text": "old"}]
    )
    new_segs = [
        {"start_time": 0.0, "end_time": 3.0, "speaker_id": 1, "text": "fixed"},
        {"start_time": 3.0, "end_time": 6.0, "speaker_id": 2, "text": "new"},
    ]
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}/segments",
        json={"segments": new_segs},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["segments"]) == 2
    assert body["segments"][0]["text"] == "fixed"
    assert body["segments"][1]["speaker_id"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("segs,expected_msg", [
    # empty
    ([], "must not be empty"),
    # start >= end
    ([{"start_time": 5.0, "end_time": 3.0, "speaker_id": 1, "text": "x"}],
     "start"),
    # overlap 已移除（M5 並行切段後相鄰 chunk 在 overlap 區自然有時間重疊、
    # editor 不該為了上游 byproduct 擋 save。見 c811fed）。
    # speaker_id < 0
    ([{"start_time": 0.0, "end_time": 1.0, "speaker_id": -1, "text": "x"}],
     "speaker_id"),
    # empty text
    ([{"start_time": 0.0, "end_time": 1.0, "speaker_id": 1, "text": "  "}],
     "text is empty"),
])
async def test_patch_segments_invalid(app_client, segs, expected_msg):
    _, job_id = await _seed_project_and_job(segments=[])
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}/segments", json={"segments": segs}
    )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "invalid_segments"
    assert expected_msg in body["detail"]["detail"]


@pytest.mark.asyncio
async def test_patch_segments_404(app_client):
    r = await app_client.patch(
        "/api/admin/jobs/nonexistent/segments", json={"segments": []}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "job_not_found"
