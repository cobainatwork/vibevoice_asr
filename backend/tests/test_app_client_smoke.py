"""Smoke test for app_client fixture."""
import pytest


@pytest.mark.asyncio
async def test_app_client_healthz(app_client):
    r = await app_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
