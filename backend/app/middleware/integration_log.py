"""
Middleware: log every /api/v1/* call to integration_calls table.

Captures: endpoint, method, status_code, duration_ms, source_ip, user_agent.

See SPEC.md §7.2 IntegrationCall model.
M6 milestone.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class IntegrationLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # TODO(M6):
        # 1. Skip if not /api/v1/*
        # 2. Capture start time, source_ip, user_agent
        # 3. Call next, capture response
        # 4. Insert IntegrationCall row (project_id from authenticated key in request.state)
        return await call_next(request)
