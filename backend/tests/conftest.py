"""Shared pytest fixtures."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch):
    """Each test gets its own temp data dir."""
    monkeypatch.setenv("BACKEND_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKEND_DB_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")  # test DB
    yield
