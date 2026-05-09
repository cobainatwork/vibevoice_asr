"""
Tests for services.vllm_client（純函式 + mock 模式）。

不打真實 vLLM；HTTP 層由 _stream_attempt 包裝，整合測試另闢。
"""
from __future__ import annotations

import json

import pytest

from app.constants import (
    MAX_VLLM_RETRIES,
    REPETITION_MIN_OCCURRENCES,
    REPETITION_MIN_SUBSTRING_LEN,
    REPETITION_WINDOW_CHARS,
    RETRY_TEMPERATURES,
)
from app.services.vllm_client import VllmClient


# === _next_url：round-robin ===


def test_next_url_single():
    c = VllmClient("http://a")
    assert c._next_url() == "http://a"
    assert c._next_url() == "http://a"


def test_next_url_round_robin():
    c = VllmClient(["http://a", "http://b", "http://c"])
    seq = [c._next_url() for _ in range(7)]
    assert seq == [
        "http://a", "http://b", "http://c",
        "http://a", "http://b", "http://c",
        "http://a",
    ]


# === _temperature_for ===


def test_temperature_for_uses_table_then_clamps():
    # 在表內：直接取
    for i, expected in enumerate(RETRY_TEMPERATURES):
        assert VllmClient._temperature_for(i) == expected
    # 超出表：取最後一個
    assert VllmClient._temperature_for(99) == RETRY_TEMPERATURES[-1]


# === _detect_repetition ===


def test_detect_repetition_short_buffer_false():
    """buffer < window → 不偵測。"""
    assert VllmClient._detect_repetition("a" * 50) is False


def test_detect_repetition_normal_text_false():
    """每段 unique 的文字不應誤判（每段 17 字、彼此不同）。"""
    buffer = "".join(f"{i:08d}-unique " for i in range(20))[:REPETITION_WINDOW_CHARS]
    assert VllmClient._detect_repetition(buffer) is False


def test_detect_repetition_obvious_loop_true():
    """末段大量重複同 substring → True。"""
    pad = "x" * 50
    loop = "ABCDEFGHIJ" * 20  # 10 字 × 20 次 = 200 字
    buffer = pad + loop
    assert VllmClient._detect_repetition(buffer) is True


def test_detect_repetition_exactly_min_occurrences_true():
    """剛好達到 MIN_OCCURRENCES 次重複 → True。"""
    cand = "Z" * REPETITION_MIN_SUBSTRING_LEN
    pad_len = REPETITION_WINDOW_CHARS - len(cand) * REPETITION_MIN_OCCURRENCES
    pad = "_" * max(pad_len, 0)
    buffer = pad + cand * REPETITION_MIN_OCCURRENCES
    assert VllmClient._detect_repetition(buffer) is True


def test_detect_repetition_below_min_occurrences_false():
    """重複次數低於門檻 → False。"""
    cand = "Q" * REPETITION_MIN_SUBSTRING_LEN
    pad = "_" * (REPETITION_WINDOW_CHARS - len(cand) * 2)
    buffer = pad + cand * (REPETITION_MIN_OCCURRENCES - 1)
    assert VllmClient._detect_repetition(buffer) is False


# === _extract_sse_content ===


@pytest.mark.parametrize("line", [
    "",
    "event: foo",
    ":heartbeat",
    "data:",
    "data: [DONE]",
    "data: {not json",
    'data: {"choices": []}',
    'data: {"choices": [{"delta": {}}]}',
    'data: {"choices": [{"delta": {"content": ""}}]}',
    'data: {"choices": [{"delta": {"content": null}}]}',
])
def test_extract_sse_content_returns_none_for_irrelevant(line):
    assert VllmClient._extract_sse_content(line) is None


def test_extract_sse_content_happy_path():
    line = 'data: {"choices": [{"delta": {"content": "hello"}}]}'
    assert VllmClient._extract_sse_content(line) == "hello"


def test_extract_sse_content_handles_chinese():
    line = 'data: {"choices": [{"delta": {"content": "你好"}}]}'
    assert VllmClient._extract_sse_content(line) == "你好"


def test_extract_sse_content_with_extra_whitespace():
    """data: 後可能多個空格。"""
    line = 'data:   {"choices": [{"delta": {"content": "x"}}]}'
    assert VllmClient._extract_sse_content(line) == "x"


# === _build_payload ===


def test_build_payload_structure():
    payload = VllmClient._build_payload(
        b"\x00\x01\x02", "audio/wav", 60.0, ["hot"], temperature=0.0
    )
    assert payload["model"] == "vibevoice"
    assert payload["stream"] is True
    assert payload["temperature"] == 0.0
    assert payload["top_p"] == 1.0
    msgs = payload["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    user_content = msgs[1]["content"]
    assert user_content[0]["type"] == "audio_url"
    assert user_content[0]["audio_url"]["url"].startswith("data:audio/wav;base64,")
    assert user_content[1]["type"] == "text"
    assert "60.00 seconds" in user_content[1]["text"]
    assert "with extra info: hot" in user_content[1]["text"]


def test_build_payload_top_p_drops_when_temperature_nonzero():
    payload = VllmClient._build_payload(
        b"x", "audio/wav", 1.0, None, temperature=0.3
    )
    assert payload["top_p"] == 0.95


# === _build_result ===


def test_build_result_shape():
    import time
    start = time.monotonic() - 0.5
    r = VllmClient._build_result("hello", attempts=2, start_monotonic=start, partial=False)
    assert r["raw_text"] == "hello"
    assert r["attempts"] == 2
    assert r["partial"] is False
    assert r["elapsed_sec"] >= 0.5


# === _mock_transcribe ===


@pytest.mark.asyncio
async def test_mock_transcribe_returns_valid_segments():
    result = await VllmClient._mock_transcribe(17.28, ["foo"], None)
    assert result["partial"] is False
    assert result["attempts"] == 1
    parsed = json.loads(result["raw_text"])
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    for seg in parsed:
        assert {"Start time", "End time", "Speaker ID", "Content"} <= seg.keys()


@pytest.mark.asyncio
async def test_mock_transcribe_invokes_on_token():
    received: list[str] = []

    async def collect(chunk: str) -> None:
        received.append(chunk)

    await VllmClient._mock_transcribe(5.0, None, collect)
    assert len(received) == 1  # mock 一次性吐完整 raw_text


@pytest.mark.asyncio
async def test_mock_transcribe_includes_hotwords_in_text():
    result = await VllmClient._mock_transcribe(5.0, ["糖尿病", "胰島素"], None)
    assert "糖尿病" in result["raw_text"]
    assert "胰島素" in result["raw_text"]
