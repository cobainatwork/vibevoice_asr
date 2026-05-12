"""
yt-dlp 包裝層:probe(取 metadata、不下載)+ fetch(下載 audio + subtitle)。

一律 subprocess、不用 yt-dlp 的 python API(版本 API 易破)。
失敗對應 ErrorCode.YOUTUBE_* 系列。

⚠ SECURITY: 只傳已驗證過的 URL 進來、subprocess 不過 shell。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

DEFAULT_SUB_LANGS = "zh-Hant,zh-Hans,zh,zh-TW,en"
PROBE_TIMEOUT_SEC = 30
FETCH_TIMEOUT_SEC = 300  # 5 min


@dataclass
class VideoInfo:
    title: str
    duration_sec: float
    available: bool


@dataclass
class FetchResult:
    audio_path: Path
    subtitle_path: Path | None
    subtitle_lang: str | None


async def probe(url: str) -> VideoInfo:
    """
    取影片 metadata,不下載。

    yt-dlp `--print "%(title)s|%(duration)s|%(availability)s" --skip-download <url>`
    輸出單行 "Title|125.5|public"。
    """
    cmd = [
        "yt-dlp",
        "--print", "%(title)s|%(duration)s|%(availability)s",
        "--skip-download",
        "--no-warnings",
        url,
    ]
    stdout, stderr, rc = await _run_subprocess(cmd, PROBE_TIMEOUT_SEC)

    if rc != 0:
        _raise_for_yt_dlp_error(stderr)

    line = stdout.decode("utf-8", errors="replace").strip()
    parts = line.split("|")
    if len(parts) < 3:
        raise AppError(
            ErrorCode.YOUTUBE_FETCH_FAILED,
            f"unexpected probe output: {line[:200]}",
        )
    title, dur_str, avail = parts[0], parts[1], parts[2]
    try:
        duration = float(dur_str)
    except ValueError as e:
        raise AppError(
            ErrorCode.YOUTUBE_FETCH_FAILED,
            f"bad duration in probe: {dur_str}",
        ) from e

    return VideoInfo(
        title=title,
        duration_sec=duration,
        available=avail.lower() in ("public", "unlisted", "needs_auth"),
    )


async def fetch_audio_and_subtitle(
    url: str,
    job_dir: Path,
    sub_langs: str = DEFAULT_SUB_LANGS,
) -> FetchResult:
    """
    下載 audio(MP3)+ 字幕(VTT,人工上傳優先)。

    輸出檔案命名:`yt.mp3` / `yt.<lang>.vtt`。
    無字幕時 subtitle_path / subtitle_lang 為 None。
    """
    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3", "--audio-quality", "4",
        "--write-subs",
        "--no-write-auto-subs",
        "--sub-langs", sub_langs,
        "--sub-format", "vtt",
        "-o", str(job_dir / "yt.%(ext)s"),
        "--no-warnings",
        url,
    ]
    _, stderr, rc = await _run_subprocess(cmd, FETCH_TIMEOUT_SEC)

    if rc != 0:
        _raise_for_yt_dlp_error(stderr)

    audio_path = job_dir / "yt.mp3"
    if not audio_path.exists():
        raise AppError(
            ErrorCode.YOUTUBE_NO_AUDIO,
            "yt-dlp succeeded but mp3 not produced",
        )

    subtitle_path, subtitle_lang = _find_subtitle(job_dir, sub_langs)
    return FetchResult(
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        subtitle_lang=subtitle_lang,
    )


# === Helpers ===


async def _run_subprocess(
    cmd: list[str], timeout_sec: int,
) -> tuple[bytes, bytes, int]:
    """執行 subprocess、timeout、回 (stdout, stderr, returncode)。"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_sec,
        )
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise AppError(
            ErrorCode.YOUTUBE_FETCH_FAILED,
            f"yt-dlp timeout after {timeout_sec}s",
        ) from e
    return stdout, stderr, proc.returncode or 0


def _raise_for_yt_dlp_error(stderr: bytes) -> None:
    """把 yt-dlp stderr 分類成對應 ErrorCode、同時印到 backend log 方便排查。"""
    detail = stderr.decode("utf-8", errors="replace")[:500]
    msg = detail.lower()
    logger.warning("yt-dlp failure: %s", detail)
    if "video unavailable" in msg or "private video" in msg or "removed" in msg:
        raise AppError(ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE, detail)
    if "age" in msg and "restricted" in msg:
        raise AppError(ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE, detail)
    raise AppError(ErrorCode.YOUTUBE_FETCH_FAILED, detail)


def _find_subtitle(
    job_dir: Path, sub_langs: str,
) -> tuple[Path | None, str | None]:
    """依語言優先序找命中字幕檔。"""
    for lang in sub_langs.split(","):
        candidate = job_dir / f"yt.{lang.strip()}.vtt"
        if candidate.exists():
            return candidate, lang.strip()
    return None, None
