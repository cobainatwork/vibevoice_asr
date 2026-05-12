"""POST /api/admin/transcribe/from_youtube 端點。"""
from unittest.mock import AsyncMock, patch

import pytest

from app import models  # noqa: F401 — 確保 ORM models 在 Base.metadata.create_all 前已 register
from app.services.youtube_fetcher import VideoInfo


@pytest.mark.asyncio
async def test_transcribe_from_youtube_success(app_client):
    """成功：probe pass → 建 Job + enqueue。"""
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    with patch(
        "app.routes.admin.jobs.youtube_fetcher.probe",
        AsyncMock(return_value=VideoInfo(
            title="Test Video", duration_sec=120.0, available=True,
        )),
    ), patch(
        "app.routes.admin.jobs.enqueue_youtube_fetch",
        AsyncMock(return_value="fake-job-id"),
    ):
        resp = await app_client.post(
            "/api/admin/transcribe/from_youtube",
            json={"url": "https://www.youtube.com/watch?v=abc", "project_id": project_id},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body

    # 透過 GET /jobs API 確認 DB 內有對應 Job
    jobs_resp = await app_client.get(f"/api/admin/jobs?project_id={project_id}")
    assert jobs_resp.status_code == 200
    jobs = jobs_resp.json()
    assert len(jobs) == 1
    assert jobs[0]["source"] == "youtube_fetch"
    assert jobs[0]["source_url"] == "https://www.youtube.com/watch?v=abc"
    assert jobs[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_transcribe_from_youtube_invalid_url(app_client):
    """非 YouTube URL → 400 YOUTUBE_INVALID_URL。"""
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    resp = await app_client.post(
        "/api/admin/transcribe/from_youtube",
        json={"url": "https://vimeo.com/12345", "project_id": project_id},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "youtube_invalid_url"


@pytest.mark.asyncio
async def test_transcribe_from_youtube_project_not_found(app_client):
    """project_id 不存在 → 404。"""
    resp = await app_client.post(
        "/api/admin/transcribe/from_youtube",
        json={"url": "https://www.youtube.com/watch?v=abc", "project_id": 9999},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "project_not_found"


@pytest.mark.asyncio
async def test_transcribe_from_youtube_video_too_long(app_client):
    """probe 回 duration 超過 max_audio_duration_sec → 400。"""
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    with patch(
        "app.routes.admin.jobs.youtube_fetcher.probe",
        AsyncMock(return_value=VideoInfo(
            title="Long", duration_sec=99999.0, available=True,
        )),
    ):
        resp = await app_client.post(
            "/api/admin/transcribe/from_youtube",
            json={"url": "https://www.youtube.com/watch?v=long", "project_id": project_id},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "youtube_video_too_long"


@pytest.mark.asyncio
async def test_transcribe_from_youtube_video_unavailable(app_client):
    """probe raise YOUTUBE_VIDEO_UNAVAILABLE → 404。"""
    from app.errors import AppError, ErrorCode

    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    assert r.status_code == 201
    project_id = r.json()["id"]

    with patch(
        "app.routes.admin.jobs.youtube_fetcher.probe",
        AsyncMock(side_effect=AppError(
            ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE, "Video unavailable",
        )),
    ):
        resp = await app_client.post(
            "/api/admin/transcribe/from_youtube",
            json={"url": "https://www.youtube.com/watch?v=dead", "project_id": project_id},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "youtube_video_unavailable"
