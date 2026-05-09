"""
v1 External API: synchronous short-audio transcription.

For QC short clips (≤120s). Returns full result in HTTP response.

See SPEC.md §17.4.
M6 milestone.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from app.schemas import V1SyncResultOut

router = APIRouter()


@router.post("/transcribe/sync", response_model=V1SyncResultOut)
async def transcribe_sync(
    file: UploadFile = File(...),
    metadata: str | None = Form(None),  # JSON string
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    authorization: str | None = Header(None),
    # TODO: api_key: ApiKey = Depends(require_api_key)
):
    """
    Synchronous transcription for short audio (≤SYNC_AUDIO_MAX_DURATION_SEC).

    Implementation (M6):
      1. Authenticate via Authorization: Bearer <key>
      2. Save file, ffprobe duration; reject if > sync limit (audio_too_long)
      3. Create Job (source=V1_API_SYNC), but bypass queue and run inline
      4. vllm_client.transcribe → parse → return V1SyncResultOut
      5. Persist Job for audit (status=DONE)
      6. Optional: if project has webhook configured, also fire it
    """
    # TODO(M6)
    raise NotImplementedError
