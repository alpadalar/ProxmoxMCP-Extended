"""API-key authentication of the HTTP transport (served ASGI app, mocked Proxmox)."""
import hashlib
import logging
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from proxmox_mcp.auth.apikey import ENV_HASHES, hash_api_key, resolve_digests
from proxmox_mcp.server_http import AuthConfigError, ProxmoxMCPHTTPServer

KEY = "test-secret-key-123"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ENV_HASHES, raising=False)


@pytest.fixture(autouse=True)
def _keep_caplog(monkeypatch):
    """setup_logging() strips root handlers (incl. caplog's); make it a no-op here."""
    monkeypatch.setattr(
        "proxmox_mcp.server_http.setup_logging", lambda cfg: logging.getLogger("proxmox-mcp")
    )


@pytest.fixture
def client(mock_env_vars, mock_proxmox):
    server = ProxmoxMCPHTTPServer(api_key_digests=[hash_api_key(KEY)])
    with TestClient(server.build_app()) as c:
        yield c


def _post(client, **headers):
    return client.post("/proxmox-mcp", json=INIT, headers={**MCP_HEADERS, **headers})


def test_hash_helper_is_sha256():
    assert hash_api_key("abc") == hashlib.sha256(b"abc").hexdigest()


def test_no_key_401(client):
    r = _post(client)
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_wrong_key_401(client):
    assert _post(client, Authorization="Bearer nope").status_code == 401
    assert _post(client, **{"X-API-Key": "nope"}).status_code == 401


def test_valid_bearer_200(client):
    assert _post(client, Authorization=f"Bearer {KEY}").status_code == 200


def test_valid_x_api_key_200(client):
    assert _post(client, **{"X-API-Key": KEY}).status_code == 200


def test_health_open_and_truthful(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["auth"] == "api-key"


def test_only_health_exempt(client):
    assert client.get("/health/extra").status_code == 401
    assert client.get("/other").status_code == 401


def test_digests_from_env(mock_env_vars, mock_proxmox, monkeypatch):
    monkeypatch.setenv(ENV_HASHES, f"{hash_api_key('x')}, sha256:{hash_api_key(KEY)}")
    server = ProxmoxMCPHTTPServer()
    with TestClient(server.build_app()) as c:
        assert _post(c, Authorization=f"Bearer {KEY}").status_code == 200


def test_invalid_env_digest_rejected(mock_env_vars, mock_proxmox, monkeypatch):
    monkeypatch.setenv(ENV_HASHES, "not-a-digest")
    with pytest.raises(AuthConfigError):
        ProxmoxMCPHTTPServer()


def test_startup_fails_without_keys(mock_env_vars, mock_proxmox):
    with pytest.raises(AuthConfigError, match=ENV_HASHES):
        ProxmoxMCPHTTPServer()


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com"])
def test_no_auth_refused_off_loopback(mock_env_vars, mock_proxmox, host):
    with pytest.raises(AuthConfigError, match="loopback"):
        ProxmoxMCPHTTPServer(host=host, insecure_no_auth=True)


def test_default_host_is_loopback(mock_env_vars, mock_proxmox):
    assert ProxmoxMCPHTTPServer(insecure_no_auth=True).host == "127.0.0.1"


def test_no_auth_on_loopback_warns_and_reports_disabled(mock_env_vars, mock_proxmox, caplog):
    with caplog.at_level(logging.WARNING):
        server = ProxmoxMCPHTTPServer(host="localhost", insecure_no_auth=True)
    assert any("AUTHENTICATION DISABLED" in r.getMessage() for r in caplog.records)
    with TestClient(server.build_app(), base_url="http://localhost") as c:
        assert c.get("/health").json()["auth"] == "disabled"
        assert _post(c).status_code == 200


def test_deprecated_django_flag_is_noop(mock_env_vars, mock_proxmox):
    with pytest.warns(DeprecationWarning):
        with pytest.raises(AuthConfigError):
            ProxmoxMCPHTTPServer(use_django_auth=False)


def test_key_never_logged(mock_env_vars, mock_proxmox, caplog):
    server = ProxmoxMCPHTTPServer(api_key_digests=[hash_api_key(KEY)])
    with caplog.at_level(logging.DEBUG):
        with TestClient(server.build_app()) as c:
            _post(c, Authorization="Bearer wrong-key-xyz")
            _post(c, Authorization=f"Bearer {KEY}")
    text = caplog.text
    assert KEY not in text and "wrong-key-xyz" not in text


def test_cli_prints_digest():
    out = subprocess.run(
        [sys.executable, "-m", "proxmox_mcp.auth.apikey"],
        input="abc\n", capture_output=True, text=True, timeout=60,
    )
    assert out.stdout.strip() == hashlib.sha256(b"abc").hexdigest()


def test_rejected_log_cannot_be_forged(client, caplog):
    with caplog.at_level(logging.WARNING):
        client.post("/proxmox-mcp/%0aFORGED%0dline", json=INIT, headers=MCP_HEADERS)
    msgs = [r.getMessage() for r in caplog.records if "Rejected" in r.getMessage()]
    assert msgs
    for m in msgs:
        assert "\n" not in m and "\r" not in m


def test_websocket_is_not_let_through(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/proxmox-mcp"):
            pass


def test_run_installs_no_signal_handlers(mock_env_vars, mock_proxmox, monkeypatch):
    import signal
    from unittest.mock import MagicMock

    server = ProxmoxMCPHTTPServer(api_key_digests=[hash_api_key(KEY)])
    monkeypatch.setattr(server.mcp, "run", MagicMock())
    before = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
    server.run()
    assert (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)) == before


@pytest.fixture
def noauth_app(mock_env_vars, mock_proxmox):
    return ProxmoxMCPHTTPServer(host="127.0.0.1", insecure_no_auth=True).build_app()


@pytest.mark.parametrize("base", ["http://localhost", "http://127.0.0.1:8812", "http://[::1]:8812"])
def test_noauth_allows_loopback_hosts(noauth_app, base):
    with TestClient(noauth_app, base_url=base) as c:
        assert _post(c).status_code == 200


@pytest.mark.parametrize("base", ["http://evil.example.com", "http://rebind.test:8812"])
def test_noauth_rejects_unknown_host(noauth_app, base):
    with TestClient(noauth_app, base_url=base) as c:
        assert _post(c).status_code == 403
        assert c.get("/health").status_code == 403


@pytest.mark.parametrize("origin", ["http://evil.example.com", "null", "https://localhost.evil.com"])
def test_noauth_rejects_foreign_origin(noauth_app, origin):
    with TestClient(noauth_app, base_url="http://localhost") as c:
        assert _post(c, Origin=origin).status_code == 403


def test_noauth_allows_loopback_origin(noauth_app):
    with TestClient(noauth_app, base_url="http://localhost") as c:
        assert _post(c, Origin="http://localhost:3000").status_code == 200


def test_resolve_digests_precedence():
    a, b, c = "a" * 64, "b" * 64, "c" * 64
    assert resolve_digests(None, [a], {}) == [a]
    assert resolve_digests(None, [a], {ENV_HASHES: b}) == [b]
    assert resolve_digests([c], [a], {ENV_HASHES: b}) == [c]
    assert resolve_digests([], [a], {ENV_HASHES: b}) == []
    assert resolve_digests(None, [], {}) == []
