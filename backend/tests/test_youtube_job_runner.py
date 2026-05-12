"""youtube_fetch_job 流程整合:probe → fetch → parse → enqueue transcribe。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# 確保 ORM models 在 app_client fixture 的 create_all 之前已 register 到 Base.metadata
from app import models  # noqa: F401
from app.db import db_session
from app.models import Job, JobSource, JobStatus, Project
from app.services.youtube_fetcher import FetchResult, VideoInfo
from app.services.youtube_job_runner import run_youtube_fetch_job


@pytest.mark.asyncio
async def test_youtube_fetch_job_success_with_subtitle(
    app_client, tmp_path,
):
    """完整成功路徑:有字幕 → reference_subtitles 寫入 → enqueue transcribe。"""
    # arrange:project + job(source=YOUTUBE_FETCH, status=QUEUED)
    async with db_session() as db:
        project = Project(name="p1")
        db.add(project)
        await db.flush()

        job = Job(
            id="job-yt-1",
            project_id=project.id,
            source=JobSource.YOUTUBE_FETCH,
            source_url="https://youtu.be/abc",
            filename="placeholder.mp3",
            audio_path="",
            duration_sec=120.0,
            status=JobStatus.QUEUED,
        )
        db.add(job)
        await db.commit()

    # mock fetcher + enqueue
    sub_file = tmp_path / "yt.zh-Hant.vtt"
    sub_file.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n你好\n",
        encoding="utf-8",
    )
    fake_fetch = FetchResult(
        audio_path=tmp_path / "yt.mp3",
        subtitle_path=sub_file,
        subtitle_lang="zh-Hant",
    )

    with patch(
        "app.services.youtube_job_runner.youtube_fetcher.fetch_audio_and_subtitle",
        AsyncMock(return_value=fake_fetch),
    ), patch(
        "app.services.youtube_job_runner.enqueue_transcribe",
        AsyncMock(return_value="job-yt-1"),
    ) as mock_enqueue:
        await run_youtube_fetch_job("job-yt-1")

    # assert
    async with db_session() as db:
        job = await db.get(Job, "job-yt-1")
        assert job.audio_path == str(tmp_path / "yt.mp3")
        assert job.reference_subtitle_lang == "zh-Hant"
        assert job.reference_subtitles is not None
        assert len(job.reference_subtitles) == 1
        assert job.reference_subtitles[0]["text"] == "你好"
        assert job.status == JobStatus.QUEUED
    mock_enqueue.assert_awaited_once_with("job-yt-1")


@pytest.mark.asyncio
async def test_youtube_fetch_job_no_subtitle(app_client, tmp_path):
    """無字幕 → reference_subtitles 為 None、仍 enqueue transcribe。"""
    async with db_session() as db:
        project = Project(name="p2")
        db.add(project)
        await db.flush()

        job = Job(
            id="job-yt-2",
            project_id=project.id,
            source=JobSource.YOUTUBE_FETCH,
            source_url="https://youtu.be/no-sub",
            filename="placeholder.mp3",
            audio_path="",
            duration_sec=60.0,
            status=JobStatus.QUEUED,
        )
        db.add(job)
        await db.commit()

    fake_fetch = FetchResult(
        audio_path=tmp_path / "yt.mp3",
        subtitle_path=None,
        subtitle_lang=None,
    )
    with patch(
        "app.services.youtube_job_runner.youtube_fetcher.fetch_audio_and_subtitle",
        AsyncMock(return_value=fake_fetch),
    ), patch(
        "app.services.youtube_job_runner.enqueue_transcribe",
        AsyncMock(return_value="job-yt-2"),
    ):
        await run_youtube_fetch_job("job-yt-2")

    async with db_session() as db:
        job = await db.get(Job, "job-yt-2")
        assert job.reference_subtitles is None
        assert job.reference_subtitle_lang is None
        assert job.audio_path == str(tmp_path / "yt.mp3")


@pytest.mark.asyncio
async def test_youtube_fetch_job_fetch_failed(app_client):
    """fetch_audio_and_subtitle raise AppError → Job.status=FAILED + error_code 記錄。"""
    from app.errors import AppError, ErrorCode

    async with db_session() as db:
        project = Project(name="p3")
        db.add(project)
        await db.flush()

        job = Job(
            id="job-yt-3",
            project_id=project.id,
            source=JobSource.YOUTUBE_FETCH,
            source_url="https://youtu.be/dead",
            filename="placeholder.mp3",
            audio_path="",
            duration_sec=60.0,
            status=JobStatus.QUEUED,
        )
        db.add(job)
        await db.commit()

    with patch(
        "app.services.youtube_job_runner.youtube_fetcher.fetch_audio_and_subtitle",
        AsyncMock(side_effect=AppError(
            ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE,
            "Video unavailable",
        )),
    ):
        await run_youtube_fetch_job("job-yt-3")

    async with db_session() as db:
        job = await db.get(Job, "job-yt-3")
        assert job.status == JobStatus.FAILED
        assert job.error is not None
        assert "youtube_video_unavailable" in job.error


@pytest.mark.asyncio
async def test_youtube_fetch_job_missing_job_id(app_client):
    """job_id 不存在 → 靜默 return(視為 cancelled / deleted)。"""
    await run_youtube_fetch_job("nonexistent-job-id")
    # 不 raise 即可
