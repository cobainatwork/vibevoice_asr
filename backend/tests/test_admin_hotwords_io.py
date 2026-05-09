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


@pytest.mark.asyncio
async def test_import_replace(app_client):
    pid = await _seed_project("imp-1", ["old1", "old2"])
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", b"newA\nnewB\nnewC\n", "text/plain")},
        data={"mode": "replace"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["hotwords"] == ["newA", "newB", "newC"]
    assert body["replaced"] == 2
    assert body["added"] == 3
    assert body["skipped_duplicates"] == 0


@pytest.mark.asyncio
async def test_import_append_dedupe(app_client):
    pid = await _seed_project("imp-2", ["alpha", "beta"])
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", b"beta\ngamma\nalpha\ndelta\n", "text/plain")},
        data={"mode": "append"},
    )
    assert r.status_code == 200
    body = r.json()
    # 順序：原 list 先、新詞接尾、重複略過
    assert body["hotwords"] == ["alpha", "beta", "gamma", "delta"]
    assert body["added"] == 2
    assert body["skipped_duplicates"] == 2


@pytest.mark.asyncio
async def test_import_strips_blank_lines(app_client):
    pid = await _seed_project("imp-3", [])
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", b"  word1  \n\n   \nword2\n\n", "text/plain")},
        data={"mode": "replace"},
    )
    assert r.status_code == 200
    assert r.json()["hotwords"] == ["word1", "word2"]


@pytest.mark.asyncio
async def test_import_utf8_chinese(app_client):
    pid = await _seed_project("imp-4", [])
    body = "糖尿病\n胰島素\n".encode("utf-8")
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", body, "text/plain")},
        data={"mode": "replace"},
    )
    assert r.status_code == 200
    assert r.json()["hotwords"] == ["糖尿病", "胰島素"]


@pytest.mark.asyncio
async def test_import_too_large(app_client):
    pid = await _seed_project("imp-5", [])
    big = b"x" * (1024 * 1024 + 1)  # 1 MB + 1
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", big, "text/plain")},
        data={"mode": "replace"},
    )
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "upload_too_large"


@pytest.mark.asyncio
async def test_import_bad_mode(app_client):
    pid = await _seed_project("imp-6", [])
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", b"x\n", "text/plain")},
        data={"mode": "merge"},
    )
    assert r.status_code == 400
