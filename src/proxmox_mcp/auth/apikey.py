"""Self-contained API-key authentication for the HTTP transport.

Clients send ``Authorization: Bearer <key>`` or ``X-API-Key: <key>``.  Only
SHA-256 hex digests of the keys are configured (env ``PROXMOX_MCP_API_KEY_HASHES``,
comma-separated; an optional ``sha256:`` prefix is accepted) and compared with
:func:`hmac.compare_digest`.  Keys are never logged.

Digests may also come from the config file (``http.api_key_digests``) or an
explicit argument. Precedence: explicit > env > config. Sources replace each
other (never merged), so a rotated env key cannot leave a stale config digest
alive; see :func:`resolve_digests`.

Generate a digest::

    echo -n 'my-secret-key' | python -m proxmox_mcp.auth.apikey
"""

import hashlib
import hmac
import json
import logging
import os
import re
import sys
from collections.abc import Iterable, Mapping

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("proxmox-mcp.auth.apikey")

ENV_HASHES = "PROXMOX_MCP_API_KEY_HASHES"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def hash_api_key(key: str) -> str:
    """Return the SHA-256 hex digest of an API key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def normalize_digests(values: Iterable[str], source: str = "API key digests") -> list[str]:
    """Validate digests (optional ``sha256:`` prefix) and return lowercase hex.

    ``source`` names where the values came from, for the error message.
    """
    result: list[str] = []
    for raw in values:
        item = raw.strip().lower()
        if not item:
            continue
        item = item.removeprefix("sha256:")
        if not _HEX64.match(item):
            raise ValueError(
                f"Invalid API key digest in {source}: expected 64 hex characters "
                "(sha256), optionally prefixed with 'sha256:'"
            )
        result.append(item)
    return result


def digests_from_env(environ: Mapping[str, str] | None = None) -> list[str]:
    """Read digests from ``PROXMOX_MCP_API_KEY_HASHES`` (comma-separated)."""
    env = os.environ if environ is None else environ
    return normalize_digests(env.get(ENV_HASHES, "").split(","), ENV_HASHES)


def resolve_digests(
    explicit: Iterable[str] | None,
    config_digests: Iterable[str] = (),
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Resolve API key digests: explicit > env > config (replacement, not union).

    An explicit value (even an empty list) wins outright; the caller then fails
    closed on an empty result. A non-empty env list replaces the config list.
    """
    if explicit is not None:
        return normalize_digests(explicit, "the explicit api_key_digests argument")
    env_digests = digests_from_env(environ)
    if env_digests:
        return env_digests
    return normalize_digests(config_digests, "http.api_key_digests")


def is_authorized(headers: list[tuple], digests: Iterable[str]) -> bool:
    """True if the raw ASGI ``headers`` carry a key matching one of ``digests``."""
    key = APIKeyAuthMiddleware._extract_key(headers)
    if key is None:
        return False
    candidate = hash_api_key(key)
    ok = False
    for digest in digests:  # no early exit: constant work per configured key
        ok |= hmac.compare_digest(candidate, digest)
    return ok


class APIKeyAuthMiddleware:
    """Pure ASGI middleware enforcing API-key auth on HTTP requests."""

    def __init__(
        self,
        app: ASGIApp,
        digests: Iterable[str],
        exempt_paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self._digests = normalize_digests(digests)
        if not self._digests:
            raise ValueError("APIKeyAuthMiddleware requires at least one key digest")
        self.exempt_paths = set(exempt_paths) if exempt_paths is not None else {"/health"}

    @staticmethod
    def _extract_key(headers: list[tuple]) -> str | None:
        bearer = None
        x_key = None
        for name, value in headers:
            lname = name.lower()
            if lname == b"authorization":
                text = value.decode("latin-1")
                if text[:7].lower() == "bearer ":
                    bearer = text[7:].strip()
            elif lname == b"x-api-key":
                x_key = value.decode("latin-1").strip()
        return bearer or x_key or None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # Fail closed: no websocket route is served, and none may bypass the key check.
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            return
        if scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        if is_authorized(scope.get("headers", []), self._digests):
            await self.app(scope, receive, send)
            return

        # %r escapes control characters so a crafted path/method cannot forge log lines.
        logger.warning(
            "Rejected unauthenticated request: %r %r",
            str(scope.get("method"))[:16],
            str(scope.get("path"))[:200],
        )
        body = json.dumps({"error": "unauthorized", "message": "Valid API key required"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def main() -> None:
    """Read a key from stdin and print its digest."""
    key = sys.stdin.readline().rstrip("\r\n")
    if not key:
        print("No key provided on stdin", file=sys.stderr)
        sys.exit(1)
    print(hash_api_key(key))
    print(f"# export {ENV_HASHES}=<digest>", file=sys.stderr)


if __name__ == "__main__":
    main()
