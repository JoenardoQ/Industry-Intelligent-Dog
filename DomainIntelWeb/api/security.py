"""Local desktop HTTP trust boundary.

Localhost is a transport choice, not authorization: arbitrary websites can try
to submit requests to loopback services. The launcher capability grants mutation
authority only to the SPA opened for that desktop session.
"""

from __future__ import annotations

import hmac
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}
CAPABILITY_HEADER = "X-IntDog-Session"


def _local_origin(value: str) -> bool:
    if not value:
        return True
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in ALLOWED_HOSTS


def evaluate_request(*, method: str, host: str, origin: str,
                     supplied: str, capability: str) -> tuple[int, str] | None:
    """Pure policy function shared by middleware and deterministic tests."""
    if host.casefold() not in ALLOWED_HOSTS:
        return 421, "Host 不受信任"
    if origin and not _local_origin(origin):
        return 403, "Origin 不受信任"
    if capability and method.upper() not in SAFE_METHODS:
        if not supplied or not hmac.compare_digest(supplied, capability):
            return 401, "桌面会话凭证缺失或已失效"
    return None


def install_security(app, capability: str) -> None:
    required = bool(capability)

    @app.middleware("http")
    async def desktop_boundary(request: Request, call_next):
        host = (request.url.hostname or "").casefold()
        origin = request.headers.get("origin", "")
        denial = evaluate_request(
            method=request.method, host=host, origin=origin,
            supplied=request.headers.get(CAPABILITY_HEADER, ""),
            capability=capability if required else "")
        if denial:
            return JSONResponse({"detail": denial[1]}, status_code=denial[0])
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response
