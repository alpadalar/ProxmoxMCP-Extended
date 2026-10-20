"""pytest fixtures exposing the FakeProxmox harness (registered via conftest pytest_plugins)."""
import hashlib
from unittest.mock import patch

import pytest

from .fake_proxmox import FakeProxmox, load_fixture


@pytest.fixture(params=["pve8", "pve9"], ids=["pve8", "pve9"])
def fake_pve(request):
    """A fresh FakeProxmox loaded with the PVE 8 / PVE 9 canned data."""
    return FakeProxmox(load_fixture(request.param))


@pytest.fixture
def fake_pve_server(mock_env_vars, fake_pve):
    """ProxmoxMCPServer (stdio) wired to ``fake_pve``."""
    from proxmox_mcp.server import ProxmoxMCPServer

    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", return_value=fake_pve):
        yield ProxmoxMCPServer()


@pytest.fixture
def fake_pve_http_server(mock_env_vars, fake_pve):
    """ProxmoxMCPHTTPServer wired to ``fake_pve`` (API-key auth enabled)."""
    from proxmox_mcp.server_http import ProxmoxMCPHTTPServer

    digest = hashlib.sha256(b"test-api-key").hexdigest()
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", return_value=fake_pve):
        yield ProxmoxMCPHTTPServer(api_key_digests=[digest])


@pytest.fixture
def policy_app(mock_env_vars, fake_pve):
    """Factory ``build(transport, read_only, allow_destructive, allow_exec)`` -> ProxmoxApp.

    Policy values are passed as CLI overrides (highest precedence), so the permissive
    test baseline in ``mock_env_vars`` never leaks into policy tests. ``ProxmoxAPI`` is
    patched to return ``fake_pve``; the patch mock is exposed as ``build.api_ctor``.
    """
    from proxmox_mcp.app import create_app
    from proxmox_mcp.config.loader import load_config

    def build(transport="stdio", read_only=False, allow_destructive=False, allow_exec=False):
        config = load_config(None, cli_overrides={"policy": {
            "read_only": str(read_only).lower(),
            "allow_destructive": str(allow_destructive).lower(),
            "allow_exec": str(allow_exec).lower(),
        }})
        kwargs = {}
        if transport == "http":
            kwargs["api_key_digests"] = [hashlib.sha256(b"test-api-key").hexdigest()]
        return create_app(config, transport, **kwargs)

    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", return_value=fake_pve) as ctor:
        build.api_ctor = ctor
        yield build
