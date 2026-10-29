import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.ops.logging import request_id_var

log = logging.getLogger("app.http")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(self), microphone=(self), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_NOT_REQUEST_ID = r"[^A-Za-z0-9_-]"
# What a request contributes to a log line is printable ASCII, cut to a length: a path
# cannot carry a line break or an escape sequence into the log.
_NOT_PRINTABLE = r"[^\x20-\x7e]"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # A client's id is echoed into a response header and the log, so it is taken only
        # when it is plain ASCII word characters; the sub is a no-op after the match.
        raw = request.headers.get("x-request-id") or ""
        if _REQUEST_ID_RE.fullmatch(raw):
            rid = re.sub(_NOT_REQUEST_ID, "", raw)
        else:
            rid = uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        method = re.sub(_NOT_PRINTABLE, "?", request.method)[:16]
        path = re.sub(_NOT_PRINTABLE, "?", request.url.path)[:512]
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            for key, value in SECURITY_HEADERS.items():
                response.headers.setdefault(key, value)
            log.info(
                "%s %s -> %s",
                method,
                path,
                response.status_code,
                extra={
                    "request_id": rid,
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)
