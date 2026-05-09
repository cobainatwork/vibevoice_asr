"""
File storage abstraction.

Default: LocalFileStore (data/ on local volume).
Future: S3FileStore, NfsFileStore (interface ready, no implementation).

See SPEC.md §3.3.
"""
from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class FileStore(Protocol):
    async def save_stream(self, key: str, source: AsyncIterator[bytes]) -> str: ...
    async def save_bytes(self, key: str, data: bytes) -> str: ...
    async def open_stream(self, key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    def local_path(self, key: str) -> Path: ...


class LocalFileStore:
    """Store files under BACKEND_DATA_DIR."""

    def __init__(self, root: Path | None = None):
        self._root = root or get_settings().backend_data_dir

    def _path(self, key: str) -> Path:
        # Resolve and ensure key stays under root (path-traversal guard)
        p = (self._root / key).resolve()
        if not str(p).startswith(str(self._root.resolve())):
            raise ValueError(f"Path traversal attempt: {key!r}")
        return p

    def local_path(self, key: str) -> Path:
        return self._path(key)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def save_bytes(self, key: str, data: bytes) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    async def save_stream(self, key: str, source: AsyncIterator[bytes]) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            async for chunk in source:
                f.write(chunk)
        return key

    async def open_stream(self, key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        p = self._path(key)
        with open(p, "rb") as f:
            while data := f.read(chunk_size):
                yield data

    async def delete(self, key: str) -> None:
        p = self._path(key)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()


# Singleton
_store: FileStore | None = None


def get_store() -> FileStore:
    global _store
    if _store is None:
        _store = LocalFileStore()
    return _store
