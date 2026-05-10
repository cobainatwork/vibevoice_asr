"""Tests for app.config Settings defaults (especially ASR pipeline knobs)."""
from __future__ import annotations


def test_chunk_concurrency_default_is_8():
    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.chunk_concurrency == 8


def test_chunk_retry_max_depth_default_is_2():
    from app.config import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.chunk_retry_max_depth == 2
