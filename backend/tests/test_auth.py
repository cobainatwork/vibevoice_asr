"""
Tests for services.auth — API key generation and parsing.
M6 milestone.
"""
from __future__ import annotations

import pytest

from app.errors import AppError, ErrorCode
from app.services.auth import generate_api_key, hash_key, parse_ws_subprotocol


def test_generate_api_key_format():
    plain, key_hash, prefix = generate_api_key()
    assert plain.startswith("vva_")
    assert len(plain) >= 20
    assert prefix == plain[:8]
    assert hash_key(plain) == key_hash
    assert len(key_hash) == 64  # SHA-256 hex


def test_generate_unique():
    keys = {generate_api_key()[0] for _ in range(50)}
    assert len(keys) == 50


def test_parse_ws_subprotocol_ok():
    assert parse_ws_subprotocol(["bearer.vva_xxx"]) == "vva_xxx"
    assert parse_ws_subprotocol(["other", "bearer.vva_yyy"]) == "vva_yyy"


def test_parse_ws_subprotocol_missing():
    with pytest.raises(AppError) as ei:
        parse_ws_subprotocol([])
    assert ei.value.code == ErrorCode.MISSING_AUTH

    with pytest.raises(AppError):
        parse_ws_subprotocol(["wrong.format"])
