# mcp_server/auth.py — bearer token middleware for HTTP transport
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Reject requests without a valid Authorization: Bearer <token> header."""

    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth.removeprefix("Bearer ").strip() != self.token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)