"""Tests for hotwords import / export endpoints."""
from __future__ import annotations

import pytest

from app.db import db_session
from app.models import Project


async def _seed_project(name: str = "p", hotwords: list[str] | None = None) -> int:
    async with db_session() as db:
        p = Project(name=name, hotwords=hotwords or [])
        db.add(p)
        await db.commit()
        return p.id


@pytest.mark.asyncio
async def test_export_basic(app_client):
    pid = await _seed_project("export-1", ["alpha", "beta", "gamma"])
    r = await app_client.get(f"/api/admin/projects/{pid}/hotwords/export?format=txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "attachment" in r.headers["content-disposition"]
    assert r.text == "alpha\nbeta\ngamma\n"


@pytest.mark.asyncio
async def test_export_chinese(app_client):
    pid = await _seed_project("export-2", ["糖尿病", "胰島素"])
    r = await app_client.get(f"/api/admin/projects/{pid}/hotwords/export?format=txt")
    assert r.status_code == 200
    assert r.text == "糖尿病\n胰島素\n"


@pytest.mark.asyncio
async def test_export_empty(app_client):
    pid = await _seed_project("export-3", [])
    r = await app_client.get(f"/api/admin/projects/{pid}/hotwords/export?format=txt")
    assert r.status_code == 200
    assert r.text == ""


@pytest.mark.asyncio
async def test_export_404(app_client):
    r = await app_client.get("/api/admin/projects/9999/hotwords/export?format=txt")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_export_unsupported_format(app_client):
    pid = await _seed_project("export-4", ["x"])
    r = await app_client.get(f"/api/admin/projects/{pid}/hotwords/export?format=csv")
    assert r.status_code == 400
    assert "format" in r.json()["detail"]["detail"].lower()
