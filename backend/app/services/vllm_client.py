"""
vLLM HTTP client.

Handles:
- OpenAI-compatible chat completions request to vLLM
- Streaming SSE response parsing
- Auto-recovery on repetition loops (escalate temperature)
- Round-robin across multiple vLLM URLs (for multi-instance deploys)

See SPEC.md §6 (vLLM layer) and §7.5.1.
M2 milestone — implement first.

Reference: vendor/VibeVoice/vllm_plugin/tests/test_api.py
           vendor/VibeVoice/vllm_plugin/tests/test_api_auto_recover.py
"""
from __future__ import annotations

import base64
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.constants import (
    MAX_VLLM_RETRIES,
    REPETITION_MIN_OCCURRENCES,
    REPETITION_MIN_SUBSTRING_LEN,
    REPETITION_WINDOW_CHARS,
    RETRY_TEMPERATURES,
    SHOW_KEYS,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


class VllmClient:
    """Async client for the upstream vLLM server (OpenAI-compatible API)."""

    def __init__(self, base_url: str | list[str], timeout: float = 600.0):
        """
        Args:
            base_url: Single URL or list of URLs (round-robin).
            timeout: Per-request timeout in seconds.
        """
        self._urls = [base_url] if isinstance(base_url, str) else list(base_url)
        self._idx = 0
        self._timeout = timeout

    def _next_url(self) -> str:
        url = self._urls[self._idx % len(self._urls)]
        self._idx += 1
        return url

    async def health(self, base_url: str | None = None) -> bool:
        """Check if vLLM /v1/models is reachable."""
        url = (base_url or self._next_url()).rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{url}/v1/models")
                return r.status_code == 200
        except Exception:
            return False

    async def get_loaded_model(self, base_url: str | None = None) -> str | None:
        """Return the model id loaded by vLLM (e.g., 'vibevoice')."""
        url = (base_url or self._next_url()).rstrip("/")
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{url}/v1/models")
            r.raise_for_status()
            data = r.json().get("data", [])
            return data[0]["id"] if data else None

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime: str,
        duration_sec: float,
        hotwords: list[str] | None = None,
        on_token: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """
        Send audio to vLLM and return parsed result.

        Returns:
            {
                "raw_text": str,        # accumulated content
                "elapsed_sec": float,
                "attempts": int,        # 1..MAX_VLLM_RETRIES
                "partial": bool,        # True if recovery exhausted
            }

        Note: parsing into segments is done by app.utils.parser separately.
        """
        # TODO(M2): full implementation per test_api.py + test_api_auto_recover.py logic
        # Outline:
        #   for attempt in range(MAX_VLLM_RETRIES):
        #       payload = self._build_payload(audio_bytes, mime, duration_sec, hotwords,
        #                                      temperature=RETRY_TEMPERATURES[attempt])
        #       async with httpx.AsyncClient(timeout=self._timeout) as c:
        #           async with c.stream("POST", url, json=payload) as resp:
        #               for line in resp.aiter_lines():
        #                   ... parse SSE delta.content
        #                   ... append to accumulated
        #                   ... call on_token if present
        #                   ... check for repetition; if found break attempt
        #       if no repetition: return result
        raise NotImplementedError

    @staticmethod
    def _build_payload(
        audio_bytes: bytes,
        mime: str,
        duration_sec: float,
        hotwords: list[str] | None,
        temperature: float = 0.0,
        max_tokens: int = 32768,
    ) -> dict[str, Any]:
        """Build the vLLM chat completions request body."""
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{audio_b64}"
        return {
            "model": "vibevoice",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "audio_url", "audio_url": {"url": data_url}},
                        {"type": "text", "text": build_user_prompt(duration_sec, hotwords)},
                    ],
                },
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 1.0 if temperature == 0.0 else 0.95,
            "stream": True,
        }

    @staticmethod
    def _detect_repetition(buffer: str) -> bool:
        """
        Slide a window of the last N chars; check if any substring of
        length M repeats >=K times.

        Constants from SPEC.md §6.5 / vendor/.../test_api_auto_recover.py
        """
        if len(buffer) < REPETITION_WINDOW_CHARS:
            return False
        window = buffer[-REPETITION_WINDOW_CHARS:]
        # Simple algorithm: for each candidate length, count substrings via Counter.
        # Production should use rolling hash for efficiency.
        # TODO(M2): port test_api_auto_recover detection logic
        return False
