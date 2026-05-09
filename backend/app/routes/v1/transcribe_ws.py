"""
v1 External API: WebSocket-based audio upload.

🌟 Main path for QC integration.
See SPEC.md §17.3 for the full protocol specification.

Auth: Subprotocol "bearer.<API_KEY>"
Flow:
  client → start metadata → ack
  client → binary chunks ... → eof
  server → queued → running → progress* → done
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.constants import (
    WS_CLOSE_AUTH_FAILED,
    WS_CLOSE_BAD_REQUEST,
    WS_CLOSE_INTERNAL_ERROR,
    WS_CLOSE_UPLOAD_TIMEOUT,
    WsClientMsg,
    WsServerMsg,
)
from app.errors import ErrorCode

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/transcribe")
async def transcribe_ws(ws: WebSocket):
    """
    WebSocket endpoint for QC audio upload.

    Implementation outline (M6):

    1. Accept connection with subprotocol echo
    2. Parse subprotocol → API key → authenticate
       - On fail: close with WS_CLOSE_AUTH_FAILED
    3. Send 'ready' frame
    4. Wait for 'start' text frame → validate metadata → check idempotency
       - If duplicate idempotency: send 'queued' with existing job_id, close
    5. Send 'ack', open uploads/{job_id}/audio.{ext} for streaming write
    6. Loop: receive frames with timeout=ws_idle_timeout_sec
       - binary: append to file, optionally send 'progress'
       - text 'eof': break loop
       - text 'cancel': cleanup + close
    7. Validate audio (ffprobe duration; reject if too long)
    8. Create Job (source=V1_API_WS), enqueue
    9. Send 'queued' with job_id
    10. Watch job status (or subscribe to Redis pub/sub):
        - on RUNNING: send 'running'
        - on DONE: send 'done' with full segments
        - on FAILED: send 'error' with code
    11. Close normally
    """
    # TODO(M6): full implementation
    await ws.close(code=WS_CLOSE_INTERNAL_ERROR, reason="not_implemented")
    raise NotImplementedError
