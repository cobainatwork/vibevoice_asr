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
    """
    FastAPI app with isolated DB schema (tables created per test).

    重要：建立獨立 test engine + session 並 monkey-patch app.db 模組層
    指向；test 結束 dispose 後還原。**不可**直接用 `from app.db import engine`
    然後 drop_all：那個 engine 是 module 載入時用 prod BACKEND_DB_URL
    建立的，drop_all 會抹掉 production /data/app.db 的業務 tables。
    """
    from app.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()

    from app.db import Base, _make_async_url
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    test_engine = create_async_engine(_make_async_url(settings.backend_db_url))
    test_session_local = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # 替換 app.db 的 module-level engine / SessionLocal，
    # 讓 endpoint 中的 Depends(get_db) 拿到 test session
    import app.db as db_module
    original_engine = db_module.engine
    original_sessionlocal = db_module.SessionLocal
    db_module.engine = test_engine
    db_module.SessionLocal = test_session_local

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.main import app
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await test_engine.dispose()
        db_module.engine = original_engine
        db_module.SessionLocal = original_sessionlocal
