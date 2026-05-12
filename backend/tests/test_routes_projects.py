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


@pytest.mark.asyncio
async def test_create_project_with_playback_speed(app_client):
    r = await app_client.post("/api/admin/projects", json={
        "name": "p_speed",
        "playback_speed": 0.7,
    })
    assert r.status_code == 201
    assert r.json()["playback_speed"] == 0.7


@pytest.mark.asyncio
async def test_create_project_default_playback_speed(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p_default_speed"})
    assert r.status_code == 201
    assert r.json()["playback_speed"] == 1.0


@pytest.mark.asyncio
async def test_create_project_speed_out_of_range(app_client):
    r = await app_client.post("/api/admin/projects", json={
        "name": "p_bad_speed",
        "playback_speed": 3.0,
    })
    assert r.status_code == 422
