"""Lazy, timeout-bounded Proxmox connection (SRV-04)."""

import hashlib
import logging
import threading
from unittest.mock import patch

import pytest

from proxmox_mcp.config.models import AuthConfig, ProxmoxConfig
from proxmox_mcp.core.proxmox import LazyProxmoxAPI, ProxmoxManager

TOKEN = "super-secret-token-value"


def _manager():
    return ProxmoxManager(
        ProxmoxConfig(host="h"),
        AuthConfig(user="u@pve", token_name="t", token_value=TOKEN),
    )


def test_construction_does_no_io():
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as api:
        m = _manager()
        assert api.call_count == 0
        assert m.connection_state() == "not_connected"
        assert isinstance(m.get_api(), LazyProxmoxAPI)
        assert api.call_count == 0


def test_first_access_connects_once_with_timeout():
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as api:
        m = _manager()
        proxy = m.get_api()
        _ = proxy.nodes
        _ = proxy.nodes
        _ = proxy.version
        assert api.call_count == 1
        assert api.call_args.kwargs["timeout"] == 30.0
        assert api.call_args.kwargs["verify_ssl"] is True
        api.return_value.version.get.assert_called_once()
        assert m.connection_state() == "connected"


def test_concurrent_first_access_single_connection():
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as api:
        proxy = _manager().get_api()
        barrier = threading.Barrier(8)

        def go():
            barrier.wait()
            _ = proxy.nodes

        ts = [threading.Thread(target=go) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert api.call_count == 1


def test_failure_is_redacted_and_retried():
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as api:
        api.side_effect = ConnectionError(f"boom {TOKEN}")
        m = _manager()
        with pytest.raises(RuntimeError) as ei:
            _ = m.get_api().nodes
        assert "Failed to connect to Proxmox" in str(ei.value)
        assert TOKEN not in str(ei.value)
        assert ei.value.__cause__ is None
        assert m.connection_state() == "unreachable"
        api.side_effect = None
        # Within the negative-cache window the failure is replayed without a new connect.
        with pytest.raises(RuntimeError):
            _ = m.get_api().nodes
        assert api.call_count == 1
        m.get_api()._retry_at = 0.0
        _ = m.get_api().nodes
        assert m.connection_state() == "connected"
        assert api.call_count == 2


def test_version_check_failure_unreachable():
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as api:
        api.return_value.version.get.side_effect = ConnectionError(TOKEN)
        m = _manager()
        with pytest.raises(RuntimeError) as ei:
            _ = m.get_api().nodes
        assert TOKEN not in str(ei.value)
        assert m.connection_state() == "unreachable"


def test_private_names_do_not_connect():
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as api:
        proxy = _manager().get_api()
        for name in ("__wrapped__", "_x"):
            with pytest.raises(AttributeError):
                getattr(proxy, name)
        assert api.call_count == 0


@pytest.fixture
def _quiet_logging(monkeypatch):
    monkeypatch.setattr(
        "proxmox_mcp.server_http.setup_logging", lambda cfg: logging.getLogger("proxmox-mcp")
    )


@pytest.mark.asyncio
async def test_servers_construct_when_proxmox_down(mock_env_vars, _quiet_logging):
    from fastmcp.exceptions import ToolError

    from proxmox_mcp.server import ProxmoxMCPServer
    from proxmox_mcp.server_http import ProxmoxMCPHTTPServer

    digest = hashlib.sha256(b"k").hexdigest()
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", side_effect=ConnectionError("down")):
        stdio = ProxmoxMCPServer()
        http = ProxmoxMCPHTTPServer(api_key_digests=[digest])
        for srv in (stdio, http):
            with pytest.raises(ToolError) as ei:
                await srv.mcp.call_tool("get_nodes", {})
            assert "test_value" not in str(ei.value)


def test_fake_pve_end_to_end_records_timeout(fake_pve):
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", return_value=fake_pve) as api:
        proxy = _manager().get_api()
        assert proxy.nodes.get() is not None
        assert api.call_args.kwargs["timeout"] == 30.0


def test_failed_connect_is_negative_cached_and_single_flight():
    import threading
    import time as _time

    calls = []

    def connect():
        calls.append(1)
        _time.sleep(0.2)
        raise RuntimeError("down")

    lazy = LazyProxmoxAPI(connect)
    errors = []

    def worker():
        try:
            _ = lazy.version
        except RuntimeError as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    start = _time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _time.monotonic() - start < 1.0  # not 8 x 0.2s serialized
    assert len(calls) == 1
    assert errors == ["down"] * 8
    assert lazy.state == "unreachable"

    # Retry allowed once the negative cache expires.
    lazy._retry_at = 0.0
    with pytest.raises(RuntimeError):
        _ = lazy.version
    assert len(calls) == 2
