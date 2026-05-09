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

import asyncio
import base64
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import get_settings
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
        Send audio to vLLM and return {raw_text, elapsed_sec, attempts, partial}。

        Repetition recovery：偵測迴圈時升 temperature 重試（上限 MAX_VLLM_RETRIES）；
        全部耗盡仍 repetition → 回 partial=True 與已生成內容。
        Parsing 由 app.utils.parser 另外處理。
        """
        if get_settings().mock_vllm:
            return await self._mock_transcribe(duration_sec, hotwords, on_token)

        start = time.monotonic()
        last_buffer = ""

        for attempt in range(MAX_VLLM_RETRIES):
            payload = self._build_payload(
                audio_bytes, mime, duration_sec, hotwords,
                temperature=self._temperature_for(attempt),
            )
            buffer, repeated = await self._stream_attempt(payload, on_token, attempt)
            if not repeated:
                return self._build_result(buffer, attempt + 1, start, partial=False)
            last_buffer = buffer

        return self._build_result(last_buffer, MAX_VLLM_RETRIES, start, partial=True)

    @staticmethod
    def _temperature_for(attempt: int) -> float:
        return RETRY_TEMPERATURES[min(attempt, len(RETRY_TEMPERATURES) - 1)]

    async def _stream_attempt(
        self,
        payload: dict[str, Any],
        on_token: Callable[[str], Awaitable[None]] | None,
        attempt: int,
    ) -> tuple[str, bool]:
        """單次 SSE 串流 attempt；若觸發 repetition 提早回傳 (buffer, True)。"""
        url = self._next_url().rstrip("/") + "/v1/chat/completions"
        buffer = ""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    self._raise_for_bad_status(resp)
                    async for line in resp.aiter_lines():
                        content = self._extract_sse_content(line)
                        if content is None:
                            continue
                        buffer += content
                        if on_token is not None:
                            await on_token(content)
                        if self._detect_repetition(buffer):
                            logger.warning(
                                "Repetition detected attempt=%d len=%d",
                                attempt + 1, len(buffer),
                            )
                            return buffer, True
        except httpx.HTTPError as e:
            raise AppError(
                ErrorCode.VLLM_UNAVAILABLE, f"vLLM connection failed: {e}"
            ) from e
        return buffer, False

    @staticmethod
    async def _raise_for_bad_status(resp: httpx.Response) -> None:
        if resp.status_code == 200:
            return
        body = (await resp.aread())[:200]
        raise AppError(
            ErrorCode.VLLM_UNAVAILABLE,
            f"vLLM HTTP {resp.status_code}: {body!r}",
        )

    @staticmethod
    def _extract_sse_content(line: str) -> str | None:
        """從一行 SSE 抽 delta.content；非 data 行 / [DONE] / 空 content 回 None。"""
        if not line or not line.startswith("data:"):
            return None
        data = line[5:].strip()
        if data == "[DONE]":
            return None
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return None
        choices = chunk.get("choices") or []
        if not choices:
            return None
        return (choices[0].get("delta") or {}).get("content") or None

    @staticmethod
    def _build_result(
        buffer: str, attempts: int, start_monotonic: float, partial: bool
    ) -> dict[str, Any]:
        return {
            "raw_text": buffer,
            "elapsed_sec": time.monotonic() - start_monotonic,
            "attempts": attempts,
            "partial": partial,
        }

    @staticmethod
    async def _mock_transcribe(
        duration_sec: float,
        hotwords: list[str] | None,
        on_token: Callable[[str], Awaitable[None]] | None,
    ) -> dict[str, Any]:
        """Return fake but valid raw_text for Windows dev (no GPU)."""
        await asyncio.sleep(0.3)
        mid = min(duration_sec / 2, 3.0)
        fake_segments = [
            {
                "Start time": "0.00",
                "End time": f"{mid:.2f}",
                "Speaker ID": "1",
                "Content": "（mock）這是模擬轉錄第一段，hotwords="
                + ",".join(hotwords or []),
            },
            {
                "Start time": f"{mid:.2f}",
                "End time": f"{duration_sec:.2f}",
                "Speaker ID": "2",
                "Content": "（mock）這是模擬轉錄第二段。",
            },
        ]
        raw_text = json.dumps(fake_segments, ensure_ascii=False)
        if on_token is not None:
            await on_token(raw_text)
        return {
            "raw_text": raw_text,
            "elapsed_sec": 0.3,
            "attempts": 1,
            "partial": False,
        }

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
        Detect a runaway repetition loop: any substring of length
        ≥REPETITION_MIN_SUBSTRING_LEN that occurs ≥REPETITION_MIN_OCCURRENCES
        times within the trailing window.

        Strategy: probe the tail of the window — if the last K chars repeat
        ≥N times in the window, we are looping.
        """
        if len(buffer) < REPETITION_WINDOW_CHARS:
            return False
        window = buffer[-REPETITION_WINDOW_CHARS:]
        max_cand_len = len(window) // REPETITION_MIN_OCCURRENCES
        for cand_len in range(REPETITION_MIN_SUBSTRING_LEN, max_cand_len + 1):
            candidate = window[-cand_len:]
            if window.count(candidate) >= REPETITION_MIN_OCCURRENCES:
                return True
        return False
