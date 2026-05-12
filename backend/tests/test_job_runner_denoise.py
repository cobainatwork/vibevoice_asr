"""run_transcribe 整合 denoise pipeline。

測試策略：
- mock maybe_denoise / cleanup_denoised / split_long_audio / _transcribe_all_chunks
- 驗證 was_denoised=False 時 cleanup 不呼叫、was_denoised=True 時 cleanup 以正確 path 呼叫
"""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.db import db_session
from app.models import Job, JobSource, JobStatus, Project


# === seed helper ===


async def _seed_job_with_denoise(denoise_enabled: bool) -> tuple[int, str]:
    """在 test engine（app_client scope 已替換 SessionLocal）建 Project + Job。"""
    job_id = str(uuid.uuid4())
    async with db_session() as db:
        project = Project(
            name=f"p_denoise_{uuid.uuid4().hex[:6]}",
            denoise_enabled=denoise_enabled,
            denoise_model="gtcrn",
        )
        db.add(project)
        await db.flush()
        job = Job(
            id=job_id,
            project_id=project.id,
            source=JobSource.ADMIN_UPLOAD,
            filename="a.mp3",
            audio_path="/tmp/a.mp3",
            duration_sec=10.0,
            status=JobStatus.QUEUED,
        )
        db.add(job)
        await db.commit()
        return project.id, job_id


# === 最小合法 outcome dict（_persist_success 需要的 keys）===

_FAKE_OUTCOME = {
    "raw_text": "",
    "segments": [],
    "parser_debug": {"validation_warnings": []},
    "duration": 10.0,
    "attempts": 1,
    "partial": False,
    "chunks_total": 1,
}


# === tests ===


@pytest.mark.asyncio
async def test_run_transcribe_denoise_disabled_skips(app_client):
    """denoise_enabled=False → maybe_denoise 以 False 呼叫、cleanup 不呼叫。"""
    _, job_id = await _seed_job_with_denoise(denoise_enabled=False)

    with patch(
        "app.services.job_runner.maybe_denoise",
        return_value=(Path("/tmp/a.mp3"), False),
    ) as mock_denoise, patch(
        "app.services.job_runner.cleanup_denoised",
    ) as mock_cleanup, patch(
        "app.services.job_runner.split_long_audio",
        return_value=[],
    ), patch(
        "app.services.job_runner._transcribe_all_chunks",
        new_callable=AsyncMock,
        return_value=_FAKE_OUTCOME,
    ):
        from app.services.job_runner import run_transcribe

        await run_transcribe(job_id)

    # maybe_denoise 應以 denoise_enabled=False 呼叫
    mock_denoise.assert_called_once()
    call_kwargs = mock_denoise.call_args.kwargs
    assert call_kwargs["denoise_enabled"] is False

    # was_denoised=False → cleanup 不呼叫
    mock_cleanup.assert_not_called()


@pytest.mark.asyncio
async def test_run_transcribe_denoise_enabled_temp_cleanup(app_client, tmp_path):
    """denoise_enabled=True → 假設 maybe_denoise 回 (temp_path, True)，job 完後 cleanup 呼叫。"""
    _, job_id = await _seed_job_with_denoise(denoise_enabled=True)

    temp_denoised = tmp_path / "denoised_x.mp3"
    temp_denoised.write_bytes(b"fake denoised audio")

    with patch(
        "app.services.job_runner.maybe_denoise",
        return_value=(temp_denoised, True),
    ), patch(
        "app.services.job_runner.cleanup_denoised",
    ) as mock_cleanup, patch(
        "app.services.job_runner.split_long_audio",
        return_value=[],
    ), patch(
        "app.services.job_runner._transcribe_all_chunks",
        new_callable=AsyncMock,
        return_value=_FAKE_OUTCOME,
    ):
        from app.services.job_runner import run_transcribe

        await run_transcribe(job_id)

    # was_denoised=True → cleanup 必須以 temp path 呼叫
    mock_cleanup.assert_called_once_with(temp_denoised)
