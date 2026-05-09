"""
API key generation, hashing, validation.

See SPEC.md §17.2.
M6 milestone.
"""
from __future__ import annotations

import hashlib
import secrets

from app.config import get_settings
from app.errors import AppError, ErrorCode


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        (plain_key, key_hash, key_prefix)
        plain_key   : "vva_<random>"  — show to user once
        key_hash    : SHA-256 hex     — store in DB
        key_prefix  : first 8 chars   — store + display in UI
    """
    settings = get_settings()
    rand = secrets.token_urlsafe(48)[:settings.api_key_length]
    plain = f"{settings.api_key_prefix}{rand}"
    key_hash = hashlib.sha256(plain.encode()).hexdigest()
    key_prefix = plain[:8]
    return plain, key_hash, key_prefix


def hash_key(plain: str) -> str:
    """Hash a plain key for lookup."""
    return hashlib.sha256(plain.encode()).hexdigest()


async def authenticate(plain_key: str):
    """
    Validate an API key. Raise AppError on failure.

    Returns the ApiKey ORM object on success, also updates last_used_at.
    """
    # TODO(M6):
    # 1. hash the key
    # 2. SELECT FROM api_keys WHERE key_hash = ? AND is_active = TRUE
    # 3. Check expires_at
    # 4. UPDATE last_used_at = NOW()
    # 5. Return ApiKey
    raise NotImplementedError


def parse_ws_subprotocol(subprotocols: list[str]) -> str:
    """
    Extract API key from WS subprotocol list.
    QC client sends: 'bearer.vva_xxx'

    Returns the plain key string. Raises AppError on bad format.
    """
    for proto in subprotocols:
        if proto.startswith("bearer."):
            return proto[len("bearer."):]
    raise AppError(
        ErrorCode.MISSING_AUTH,
        "WebSocket must include 'bearer.<api_key>' as subprotocol",
    )
