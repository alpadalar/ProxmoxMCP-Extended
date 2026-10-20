"""App factory: transports, auth policy matrix, /health, served-app identity."""

import hashlib
import json
import logging
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from proxmox_mcp.app import ProxmoxApp, create_app
from proxmox_mcp.auth.apikey import ENV_HASHES
from proxmox_mcp.auth.policy import AuthConfigError, resolve_auth_policy
from proxmox_mcp.config.loader import load_config
from tests.test_tool_schema_snapshot import GOLDEN_PATH, normalize_tool

DIGEST = hashlib.sha256(b"k").hexdigest()
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ENV_HASHES, raising=False)


@pytest.fixture
def config(mock_env_vars):
    return load_config(None)


def test_unknown_transport(config):
    with pytest.raises(ValueError):
        create_app(config, "carrier-pigeon")


def test_defaults_are_loopback(config):
    import inspect

    assert inspect.signature(create_app).parameters["host"].default == "127.0.0.1"


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_snapshot_parity(config, mock_proxmox, transport):
    app = create_app(config, transport, api_key_digests=[DIGEST])
    assert isinstance(app, ProxmoxApp)
    snap = sorted((normalize_tool(t) for t in await app.mcp.list_tools()), key=lambda t: t["name"])
    assert snap == GOLDEN
    if transport == "stdio":
        assert app.asgi is None and app.auth_state == "n/a" and app.mcp.name == "ProxmoxMCP"
    else:
        assert app.asgi is not None and app.auth_state == "api-key"
        assert app.mcp.name == "ProxmoxMCP-HTTP"


def test_policy_matrix(config):
    with pytest.raises(AuthConfigError) as ei:
        resolve_auth_policy(config, host="127.0.0.1", environ={})
    assert ENV_HASHES in str(ei.value) and "http.api_key_digests" in str(ei.value)
    for host in ("0.0.0.0", "10.0.0.1", "example.com"):
        with pytest.raises(AuthConfigError, match="loopback"):
            resolve_auth_policy(config, host=host, insecure_no_auth=True, environ={})
    with pytest.raises(AuthConfigError):
        resolve_auth_policy(config, host="127.0.0.1", explicit_digests=["zz"], environ={})
    on = resolve_auth_policy(
        config, host="0.0.0.0", explicit_digests=[DIGEST], insecure_no_auth=True, environ={}
    )
    assert on.enabled and not on.insecure
    off = resolve_auth_policy(config, host="::1", insecure_no_auth=True, environ={})
    assert not off.enabled and off.insecure and off.state == "disabled"


def test_no_auth_loopback_warns(config, mock_proxmox, caplog):
    with caplog.at_level(logging.WARNING):
        app = create_app(config, "http", insecure_no_auth=True)
    assert app.auth_state == "disabled"
    assert any("AUTHENTICATION DISABLED" in r.getMessage() for r in caplog.records)


def test_health_payload_over_asgi(config, mock_proxmox):
    app = create_app(config, "http", api_key_digests=[DIGEST])
    with TestClient(app.asgi) as c:
        assert c.get("/health").json() == {"status": "ok"}
        body = c.get("/health", headers={"X-API-Key": "k"}).json()
    assert set(body) == {
        "status",
        "server",
        "transport",
        "auth",
        "policy",
        "proxmox",
        "pve",
        "timestamp",
    }
    assert body["pve"] is None
    assert body["auth"] == "api-key" and body["transport"] == "http"
    assert body["proxmox"] == "not_connected"
    mock_proxmox.assert_not_called()
    text = json.dumps(body)
    for secret in (DIGEST, "test_value", "test.proxmox.com"):
        assert secret not in text


def test_build_app_is_served_object(config, mock_proxmox, monkeypatch):
    monkeypatch.setattr("proxmox_mcp.server_http.setup_logging", lambda c: logging.getLogger("x"))
    from proxmox_mcp.server_http import ProxmoxMCPHTTPServer

    server = ProxmoxMCPHTTPServer(api_key_digests=[DIGEST])
    assert server.build_app() is server.app.asgi
    with patch("proxmox_mcp.app.serve_asgi") as serve:
        server.app.run()
    serve.assert_called_once_with(server.app.asgi, "127.0.0.1", 8812)


def test_unreachable_proxmox_does_not_break_create_app(config):
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", side_effect=ConnectionError("down")):
        app = create_app(config, "http", api_key_digests=[DIGEST])
        assert app.manager.connection_state() == "not_connected"


def test_plaintext_non_loopback_warns(config, mock_proxmox, caplog):
    with caplog.at_level(logging.WARNING):
        create_app(config, "http", host="0.0.0.0", api_key_digests=[DIGEST])
    assert any("plaintext HTTP" in r.getMessage() for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        create_app(config, "http", host="127.0.0.1", api_key_digests=[DIGEST])
    assert not any("plaintext HTTP" in r.getMessage() for r in caplog.records)
