"""yt-dlp probe / fetch wrapper。一律 mock subprocess、不對 YouTube 真連線。"""
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from app.errors import AppError, ErrorCode
from app.services.youtube_fetcher import (
    VideoInfo,
    probe,
    fetch_audio_and_subtitle,
)


@pytest.mark.asyncio
async def test_probe_success():
    """yt-dlp --dump-json 回 JSON → VideoInfo。"""
    fake_stdout = (
        b'{"title": "My Video", "duration": 125.5, "availability": "public"}\n'
    )
    fake_stderr = b""

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(fake_stdout, fake_stderr))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        info = await probe("https://youtu.be/abc")

    assert info.title == "My Video"
    assert info.duration_sec == pytest.approx(125.5)
    assert info.available is True


@pytest.mark.asyncio
async def test_probe_title_with_pipe_char():
    """title 含 '|' 字元(YouTube 常見、頻道名後綴),JSON 解析不會 mis-align。"""
    fake_stdout = (
        b'{"title": "Topic | Channel Name", "duration": 43, "availability": "public"}\n'
    )
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(fake_stdout, b""))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        info = await probe("https://youtu.be/abc")

    assert info.title == "Topic | Channel Name"
    assert info.duration_sec == pytest.approx(43.0)


@pytest.mark.asyncio
async def test_probe_video_unavailable():
    """yt-dlp returncode != 0 + stderr 含 'Video unavailable' → YOUTUBE_VIDEO_UNAVAILABLE。"""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"ERROR: Video unavailable"))
    proc.returncode = 1

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(AppError) as exc:
            await probe("https://youtu.be/dead")

    assert exc.value.code == ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE


@pytest.mark.asyncio
async def test_probe_generic_failure():
    """非 known pattern 的失敗 → YOUTUBE_FETCH_FAILED。"""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"ERROR: some unknown network issue"))
    proc.returncode = 1

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(AppError) as exc:
            await probe("https://youtu.be/xxx")

    assert exc.value.code == ErrorCode.YOUTUBE_FETCH_FAILED


@pytest.mark.asyncio
async def test_fetch_audio_and_subtitle_success(tmp_path: Path):
    """fetch 成功:audio + subtitle 落地。"""
    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    (job_dir / "yt.mp3").write_bytes(b"\x00" * 100)
    (job_dir / "yt.zh-Hant.vtt").write_text("WEBVTT\n\n", encoding="utf-8")

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await fetch_audio_and_subtitle("https://youtu.be/x", job_dir)

    assert result.audio_path == job_dir / "yt.mp3"
    assert result.subtitle_path == job_dir / "yt.zh-Hant.vtt"
    assert result.subtitle_lang == "zh-Hant"


@pytest.mark.asyncio
async def test_fetch_no_subtitle(tmp_path: Path):
    """fetch 成功但無字幕 → subtitle_path / subtitle_lang 為 None。"""
    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    (job_dir / "yt.mp3").write_bytes(b"\x00" * 100)

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await fetch_audio_and_subtitle("https://youtu.be/x", job_dir)

    assert result.audio_path == job_dir / "yt.mp3"
    assert result.subtitle_path is None
    assert result.subtitle_lang is None


@pytest.mark.asyncio
async def test_fetch_no_audio_raises(tmp_path: Path):
    """yt-dlp 成功但找不到 mp3 → YOUTUBE_NO_AUDIO。"""
    job_dir = tmp_path / "job1"
    job_dir.mkdir()

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(AppError) as exc:
            await fetch_audio_and_subtitle("https://youtu.be/x", job_dir)

    assert exc.value.code == ErrorCode.YOUTUBE_NO_AUDIO


@pytest.mark.asyncio
async def test_fetch_subprocess_failure(tmp_path: Path):
    """yt-dlp returncode != 0 → YOUTUBE_FETCH_FAILED。"""
    job_dir = tmp_path / "job1"
    job_dir.mkdir()

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"ERROR: download failed"))
    proc.returncode = 1

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(AppError) as exc:
            await fetch_audio_and_subtitle("https://youtu.be/x", job_dir)

    assert exc.value.code == ErrorCode.YOUTUBE_FETCH_FAILED
