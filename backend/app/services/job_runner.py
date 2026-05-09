"""
Offline transcribe job orchestration (called from worker).

Pipeline:
  Job(PENDING)
    → load audio, ffprobe
    → split if long
    → parallel inference per chunk (vllm_client)
    → parse segments per chunk (parser)
    → merge_chunk_results
    → save to DB; status=DONE
    → fire webhook if configured

See SPEC.md §3.4.
M2 milestone (basic, no split) → M5 (with split).
"""
from __future__ import annotations

import logging

from app.db import db_session

logger = logging.getLogger(__name__)


async def run_transcribe(job_id: str) -> None:
    """
    Run a single offline transcribe job to completion.

    Caller: worker.py:transcribe_job
    """
    # TODO(M2):
    # async with db_session() as db:
    #     job = await db.get(Job, job_id)
    #     job.status = RUNNING
    #     job.started_at = utcnow()
    #
    #     chunks = audio_splitter.split_long_audio(Path(job.audio_path), ...)
    #     job.chunks_total = len(chunks)
    #
    #     all_segments = []
    #     for i, chunk in enumerate(chunks):
    #         result = await vllm_client.transcribe(chunk_bytes, mime, duration, hotwords)
    #         segs = parser.parse_transcription(result["raw_text"])
    #         all_segments.append(segs)
    #         job.chunks_done = i + 1
    #         job.progress = (i + 1) / len(chunks)
    #         await db.commit()
    #
    #     merged = audio_splitter.merge_chunk_results(chunks, all_segments)
    #     job.segments = merged
    #     job.status = DONE
    #     job.finished_at = utcnow()
    #     await db.commit()
    #
    #     # Fire webhook
    #     if job.callback_url or project.webhook_url:
    #         await create_and_enqueue_webhook(job)
    raise NotImplementedError
