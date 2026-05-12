"""Project admin routes — denoise settings 欄位驗收。"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_project_with_denoise_settings(app_client):
    r = await app_client.post("/api/admin/projects", json={
        "name": "p_denoise",
        "denoise_enabled": True,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["denoise_enabled"] is True


@pytest.mark.asyncio
async def test_create_project_default_denoise(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p_default"})
    assert r.status_code == 201
    body = r.json()
    assert body["denoise_enabled"] is False


@pytest.mark.asyncio
async def test_patch_project_denoise(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    assert r.status_code == 201
    pid = r.json()["id"]
    r = await app_client.put(f"/api/admin/projects/{pid}", json={
        "denoise_enabled": True,
    })
    assert r.status_code == 200
    assert r.json()["denoise_enabled"] is True
