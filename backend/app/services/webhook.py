"""
Webhook signing + delivery.

See SPEC.md §17.6.
M6 milestone.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import get_settings
from app.constants import (
    WEBHOOK_DELIVERY_HEADER,
    WEBHOOK_EVENT_HEADER,
    WEBHOOK_RETRY_DELAYS_SEC,
    WEBHOOK_SIG_HEADER,
    WEBHOOK_TS_HEADER,
)

logger = logging.getLogger(__name__)


def sign_payload(payload: dict, secret: str) -> tuple[str, str]:
    """
    Sign a webhook payload with HMAC-SHA256.

    Returns:
        (signature_header_value, timestamp)
        signature_header_value: "sha256=<hex>"
        timestamp: unix seconds (str)
    """
    timestamp = str(int(time.time()))
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    msg = f"{timestamp}.{body}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"sha256={sig}", timestamp


def build_headers(
    payload: dict, secret: str, event: str, delivery_id: str
) -> dict[str, str]:
    """Build the full set of headers for a webhook POST."""
    sig, ts = sign_payload(payload, secret)
    return {
        "Content-Type": "application/json",
        WEBHOOK_SIG_HEADER: sig,
        WEBHOOK_TS_HEADER: ts,
        WEBHOOK_EVENT_HEADER: event,
        WEBHOOK_DELIVERY_HEADER: delivery_id,
        "User-Agent": "VibeVoice-ASR/1.0",
    }


async def deliver_once(
    url: str, payload: dict, secret: str, event: str, delivery_id: str
) -> dict[str, Any]:
    """
    Single delivery attempt. Returns dict with response_code / response_body / error.

    Does NOT update DB — caller owns persistence.
    """
    settings = get_settings()
    headers = build_headers(payload, secret, event, delivery_id)
    result: dict[str, Any] = {
        "response_code": None,
        "response_body": None,
        "error": None,
        "elapsed_ms": 0,
    }
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=settings.webhook_timeout_sec) as c:
            r = await c.post(url, content=json.dumps(payload), headers=headers)
        result["response_code"] = r.status_code
        result["response_body"] = r.text[:1000]
    except Exception as e:
        result["error"] = str(e)
    result["elapsed_ms"] = int((time.time() - start) * 1000)
    return result


def next_retry_delay(attempts: int) -> int | None:
    """
    Get delay for next retry given current attempt count (0-indexed).

    Returns None if max attempts reached (caller should mark GIVEN_UP).
    """
    if attempts >= len(WEBHOOK_RETRY_DELAYS_SEC):
        return None
    return WEBHOOK_RETRY_DELAYS_SEC[attempts]


# === Worker job entry point ===


async def deliver(delivery_id: int) -> str:
    """
    Worker job: deliver a single WebhookDelivery row, with retry scheduling.

    Behavior:
      - Load delivery + project (for secret) from DB
      - Call deliver_once
      - On 2xx → status=SUCCEEDED
      - On non-2xx or exception → schedule next retry OR mark GIVEN_UP
    """
    # TODO(M6): full implementation
    raise NotImplementedError
