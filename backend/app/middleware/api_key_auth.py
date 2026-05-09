"""
API key authentication for /api/v1/* routes.

Used as FastAPI dependency. Also writes to integration_calls table for audit.

See SPEC.md §17.2.
M6 milestone.
"""
from __future__ import annotations

from fastapi import Header, Request


async def require_api_key(
    request: Request,
    authorization: str | None = Header(None),
):
    """
    FastAPI dependency. Validate Bearer token, return ApiKey ORM object.
    Side effect: write IntegrationCall record on every authenticated request.
    """
    # TODO(M6):
    # 1. Parse Authorization header
    # 2. Call services.auth.authenticate()
    # 3. Update last_used_at
    # 4. Return ApiKey
    # On failure: raise AppError(ErrorCode.INVALID_API_KEY)
    raise NotImplementedError
