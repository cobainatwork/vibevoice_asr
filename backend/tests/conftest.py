"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest


# 自訂 event_loop 已被 pytest-asyncio 棄用；asyncio_mode=auto 已內建處理
# event loop 生命週期，無須在此覆寫。


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch):
    """Each test gets its own temp data dir."""
    monkeypatch.setenv("BACKEND_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKEND_DB_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")  # test DB
    yield
