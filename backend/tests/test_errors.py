"""
Tests for app.errors — AppError、ErrorCode 對應、http_error helper。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.errors import HTTP_STATUS_FOR_CODE, AppError, ErrorCode, http_error


# === ErrorCode ↔ HTTP status mapping 完整性 ===


def test_every_error_code_has_http_status_mapping():
    """新增 ErrorCode 必須同步在 HTTP_STATUS_FOR_CODE 加 mapping。"""
    missing = [c for c in ErrorCode if c not in HTTP_STATUS_FOR_CODE]
    assert not missing, f"ErrorCode 缺 HTTP status mapping: {missing}"


def test_project_not_found_maps_404():
    assert HTTP_STATUS_FOR_CODE[ErrorCode.PROJECT_NOT_FOUND] == 404


def test_project_name_conflict_maps_409():
    assert HTTP_STATUS_FOR_CODE[ErrorCode.PROJECT_NAME_CONFLICT] == 409


def test_idempotency_replay_maps_409():
    assert HTTP_STATUS_FOR_CODE[ErrorCode.IDEMPOTENCY_REPLAY] == 409


def test_quota_exceeded_maps_429():
    assert HTTP_STATUS_FOR_CODE[ErrorCode.QUOTA_EXCEEDED] == 429


# === AppError ===


def test_app_error_to_dict_basic():
    e = AppError(ErrorCode.JOB_NOT_FOUND, "job xyz missing")
    assert e.to_dict() == {
        "code": "job_not_found",
        "detail": "job xyz missing",
    }


def test_app_error_to_dict_with_extra():
    e = AppError(ErrorCode.AUDIO_TOO_LONG, "too long", limit=4800, actual=5500)
    d = e.to_dict()
    assert d["code"] == "audio_too_long"
    assert d["detail"] == "too long"
    assert d["limit"] == 4800
    assert d["actual"] == 5500


def test_app_error_default_detail_uses_code_value():
    e = AppError(ErrorCode.INTERNAL_ERROR)
    assert e.detail == "internal_error"


def test_app_error_http_status_property():
    assert AppError(ErrorCode.JOB_NOT_FOUND).http_status == 404
    assert AppError(ErrorCode.UPLOAD_TOO_LARGE).http_status == 413
    assert AppError(ErrorCode.VLLM_UNAVAILABLE).http_status == 503


# === http_error helper ===


def test_http_error_returns_http_exception():
    exc = http_error(ErrorCode.JOB_NOT_FOUND, "missing")
    assert isinstance(exc, HTTPException)


def test_http_error_uses_default_status_for_code():
    assert http_error(ErrorCode.JOB_NOT_FOUND, "x").status_code == 404
    assert http_error(ErrorCode.UPLOAD_TOO_LARGE, "x").status_code == 413
    assert http_error(ErrorCode.AUDIO_TOO_LONG, "x").status_code == 400


def test_http_error_detail_body_shape():
    exc = http_error(ErrorCode.PROJECT_NOT_FOUND, "project 1 not found")
    assert exc.detail == {
        "code": "project_not_found",
        "detail": "project 1 not found",
    }


def test_http_error_explicit_status_override():
    """明確傳 status 應覆寫 ErrorCode 對應的預設值。"""
    exc = http_error(ErrorCode.INTERNAL_ERROR, "boom", status=502)
    assert exc.status_code == 502
    assert exc.detail["code"] == "internal_error"
