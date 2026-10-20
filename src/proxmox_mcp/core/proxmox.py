"""
Proxmox API setup and management.

This module handles the core Proxmox API integration, providing:
- Lazy, timeout-bounded API connection (no network I/O at construction)
- Token-based authentication
- Connectivity/auth check on first use
- Redacted error handling for API operations

ProxmoxManager is the central point for Proxmox API access. Constructing it
never touches the network; the connection is established on the first
attribute access of the proxy returned by get_api(). A failed connection is
cached briefly (a few seconds) so bursts fail fast, then the next access retries.
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from proxmoxer import ProxmoxAPI

from ..config.models import AuthConfig, ProxmoxConfig
from ..tools.pve_compat import PveVersion, parse_pve_version
from ..utils.redaction import redact, register_secret

NOT_CONNECTED = "not_connected"
CONNECTED = "connected"
UNREACHABLE = "unreachable"


class LazyProxmoxAPI:
    """Proxy that connects to Proxmox on first attribute access."""

    NEGATIVE_TTL = 5.0  # seconds a failed connect is cached

    def __init__(self, connect: Callable[[], Any]):
        self._connect = connect
        self._lock = threading.Lock()
        self._inflight: threading.Event | None = None
        self._last_error: str | None = None
        self._retry_at = 0.0
        self._api: Any | None = None
        self._state = NOT_CONNECTED

    @property
    def state(self) -> str:
        """Connection state; never performs I/O."""
        return self._state

    def _resolve(self) -> Any:
        """Single-flight connect: the lock is never held across network I/O.

        One caller connects; concurrent callers wait for its outcome. A failure is
        cached for ``NEGATIVE_TTL`` seconds so a burst of calls against a down host
        fails fast instead of serializing N timeouts.
        """
        while True:
            with self._lock:
                if self._api is not None:
                    return self._api
                if self._last_error is not None and time.monotonic() < self._retry_at:
                    raise RuntimeError(self._last_error)
                inflight = self._inflight
                leader = inflight is None
                if leader:
                    inflight = self._inflight = threading.Event()
            if not leader:
                inflight.wait()
                continue
            try:
                api = self._connect()
            except Exception as e:
                with self._lock:
                    self._state = UNREACHABLE
                    self._last_error = str(e)
                    self._retry_at = time.monotonic() + self.NEGATIVE_TTL
                raise
            else:
                with self._lock:
                    self._api = api
                    self._state = CONNECTED
                    self._last_error = None
                return api
            finally:
                with self._lock:
                    self._inflight = None
                inflight.set()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._resolve(), name)


class ProxmoxManager:
    """Manager class for Proxmox API operations (lazy connection)."""

    def __init__(self, proxmox_config: ProxmoxConfig, auth_config: AuthConfig):
        """Initialize the manager without any network I/O.

        Args:
            proxmox_config: Proxmox connection configuration
            auth_config: Authentication configuration
        """
        self.logger = logging.getLogger("proxmox-mcp.proxmox")
        register_secret(auth_config.token_value.get_secret_value())
        self.config = self._create_config(proxmox_config, auth_config)
        self._pve_version: PveVersion | None = None
        self.api = LazyProxmoxAPI(self._connect)

    def _create_config(
        self, proxmox_config: ProxmoxConfig, auth_config: AuthConfig
    ) -> dict[str, Any]:
        """Create a configuration dictionary for ProxmoxAPI.

        Args:
            proxmox_config: Proxmox connection configuration (host, port, SSL, timeout)
            auth_config: Authentication configuration (user, token details)

        Returns:
            Dictionary containing merged configuration ready for API initialization
        """
        if proxmox_config.verify_ssl is False:
            self.logger.warning(
                "TLS certificate verification is DISABLED (verify_ssl=false); "
                "API traffic is vulnerable to interception"
            )
        return {
            "host": proxmox_config.host,
            "port": proxmox_config.port,
            "user": auth_config.user,
            "token_name": auth_config.token_name,
            "token_value": auth_config.token_value.get_secret_value(),
            "verify_ssl": proxmox_config.ca_bundle or proxmox_config.verify_ssl,
            "service": proxmox_config.service,
            "timeout": proxmox_config.timeout,
        }

    def _connect(self) -> ProxmoxAPI:
        """Create the ProxmoxAPI instance and verify connectivity/authentication.

        Raises:
            RuntimeError: with redacted details if the connection or auth check fails.
        """
        try:
            self.logger.info(f"Connecting to Proxmox host: {self.config['host']}")
            api = ProxmoxAPI(**self.config)
            # The connectivity check already fetches /version: remember it (no extra I/O).
            self._pve_version = parse_pve_version(api.version.get())
            self.logger.info("Successfully connected to Proxmox API")
            return api
        except Exception as e:
            safe = redact(str(e))
            self.logger.error(f"Failed to connect to Proxmox: {safe}")
            raise RuntimeError(f"Failed to connect to Proxmox: {safe}") from None

    def get_api(self) -> LazyProxmoxAPI:
        """Get the lazy Proxmox API proxy (connects on first attribute access)."""
        return self.api

    def version_info(self) -> PveVersion | None:
        """PVE version seen by the first successful connect, else None; never performs I/O."""
        return self._pve_version

    def pve_major(self) -> int | None:
        """Major PVE version (8, 9, ...) or None before the first successful connect."""
        info = self._pve_version
        return info.major if info else None

    def connection_state(self) -> str:
        """Return not_connected / connected / unreachable without any I/O."""
        return self.api.state
