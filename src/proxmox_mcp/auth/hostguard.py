"""Host/Origin allow-list for the unauthenticated loopback development mode.

Loopback is not a trust boundary for browsers: a web page can reach 127.0.0.1 via DNS
rebinding or cross-origin requests. With auth disabled, only loopback Host headers and
loopback (or absent) Origin headers are served.
"""

import json
from collections.abc import Iterable, MutableMapping
from typing import Any
from urllib.parse import urlsplit

LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def _host_only(value: str) -> str | None:
    """Hostname part of a Host header value (port stripped, IPv6 brackets removed)."""
    value = value.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end > 0 else None
    if value.count(":") > 1:  # bare IPv6
        return value
    return value.split(":", 1)[0]


class LoopbackHostGuardMiddleware:
    """Pure ASGI middleware rejecting non-loopback Host and cross-site Origin headers."""

    def __init__(self, app: Any, allowed: Iterable[str] = LOOPBACK_NAMES) -> None:
        self.app = app
        self.allowed = frozenset(a.lower() for a in allowed)

    def _ok(self, headers: Iterable[tuple[bytes, bytes]]) -> bool:
        host = origin = None
        for k, v in headers:
            if k == b"host":
                host = v.decode("latin-1")
            elif k == b"origin":
                origin = v.decode("latin-1")
        if host is None or _host_only(host) not in self.allowed:
            return False
        if origin is not None:
            try:
                origin_host = urlsplit(origin).hostname
            except ValueError:
                return False
            if origin_host is None or origin_host.lower() not in self.allowed:
                return False
        return True

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket") or self._ok(scope.get("headers", [])):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"error": "forbidden", "message": "Host or Origin not allowed"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
