"""Shared pytest fixtures."""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio


# 自訂 event_loop 已被 pytest-asyncio 棄用；asyncio_mode=auto 已內建處理
# event loop 生命週期，無須在此覆寫。


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch):
    """Each test gets its own temp data dir."""
    monkeypatch.setenv("BACKEND_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKEND_DB_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")  # test DB
    yield


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator:
    """FastAPI app with isolated DB schema (tables created per test)."""
    # 清掉 cached settings 確保讀到 monkeypatched env
    from app.config import get_settings
    get_settings.cache_clear()

    # 重 import 以套用新 env
    from app.db import Base, engine
    from httpx import ASGITransport, AsyncClient

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
