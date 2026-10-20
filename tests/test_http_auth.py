"""API-key authentication of the HTTP transport (served ASGI app, mocked Proxmox)."""
import hashlib
import logging
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from proxmox_mcp.auth.apikey import ENV_HASHES, hash_api_key
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
    with TestClient(server.build_app()) as c:
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
