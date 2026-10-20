"""Fail-closed authentication policy for the HTTP transport."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .apikey import ENV_HASHES, resolve_digests

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class AuthConfigError(ValueError):
    """Raised when the HTTP server's authentication setup is unsafe or missing."""


@dataclass(frozen=True)
class AuthPolicy:
    """Resolved authentication policy."""

    digests: list[str]
    enabled: bool
    insecure: bool

    @property
    def state(self) -> str:
        return "api-key" if self.enabled else "disabled"


def resolve_auth_policy(
    config: Any,
    *,
    host: str,
    explicit_digests: list[str] | None = None,
    insecure_no_auth: bool = False,
    environ: Mapping[str, str] | None = None,
) -> AuthPolicy:
    """Resolve digests (explicit > env > config) and enforce the fail-closed rules.

    Raises:
        AuthConfigError: invalid digest, no digests without ``insecure_no_auth``, or
            ``insecure_no_auth`` on a non-loopback host.
    """
    try:
        digests = resolve_digests(explicit_digests, config.http.api_key_digests, environ)
    except ValueError as e:
        raise AuthConfigError(str(e)) from e
    if digests:
        return AuthPolicy(digests=digests, enabled=True, insecure=False)
    if not insecure_no_auth:
        raise AuthConfigError(
            f"No API key digests configured. Set {ENV_HASHES} or http.api_key_digests "
            "in the config file (comma-separated / list of sha256 hex digests; generate with "
            "`python -m proxmox_mcp.auth.apikey`) "
            "or, for local development only, pass --no-auth on a loopback host."
        )
    if host not in LOOPBACK_HOSTS:
        raise AuthConfigError(
            f"--no-auth is only allowed on loopback (127.0.0.1, ::1, localhost), "
            f"not on {host!r}. Configure {ENV_HASHES} instead."
        )
    return AuthPolicy(digests=[], enabled=False, insecure=True)
