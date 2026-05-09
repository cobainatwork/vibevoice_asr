"""
Tests for services.webhook signing.
M6 milestone.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from app.services.webhook import sign_payload


def test_sign_payload_deterministic_within_same_second():
    """Same payload + secret + timestamp → same signature."""
    payload = {"a": 1, "b": "two"}
    sig1, ts1 = sign_payload(payload, "secret123")
    # If we re-sign immediately, ts may be the same and sig identical
    sig2, ts2 = sign_payload(payload, "secret123")
    if ts1 == ts2:
        assert sig1 == sig2


def test_sign_payload_format():
    sig, ts = sign_payload({"x": 1}, "abc")
    assert sig.startswith("sha256=")
    assert len(sig) == len("sha256=") + 64
    assert ts.isdigit()


def test_sign_payload_can_be_verified():
    """Reproduce the signature using the same algorithm."""
    payload = {"event": "test", "value": 42}
    secret = "supersecret"
    sig, ts = sign_payload(payload, secret)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    expected_sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(),
                            hashlib.sha256).hexdigest()
    assert sig == f"sha256={expected_sig}"
