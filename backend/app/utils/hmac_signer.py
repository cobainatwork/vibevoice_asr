"""
HMAC signing utilities — alias to webhook signer for clarity.

Re-exports for use in non-webhook contexts (e.g., admin webhook test).
"""
from app.services.webhook import build_headers, sign_payload

__all__ = ["sign_payload", "build_headers"]
