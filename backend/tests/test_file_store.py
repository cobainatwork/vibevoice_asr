"""Unit tests for LocalFileStore."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.file_store import LocalFileStore


@pytest.mark.asyncio
async def test_local_file_store_copy(tmp_path: Path):
    store = LocalFileStore(root=tmp_path)
    await store.save_bytes("src/foo.bin", b"hello")
    await store.copy("src/foo.bin", "dst/bar.bin")
    assert (tmp_path / "dst" / "bar.bin").read_bytes() == b"hello"
    # 來源仍存在
    assert (tmp_path / "src" / "foo.bin").exists()


@pytest.mark.asyncio
async def test_local_file_store_copy_creates_parent_dirs(tmp_path: Path):
    store = LocalFileStore(root=tmp_path)
    await store.save_bytes("a.bin", b"x")
    await store.copy("a.bin", "deeply/nested/dir/b.bin")
    assert (tmp_path / "deeply" / "nested" / "dir" / "b.bin").read_bytes() == b"x"
