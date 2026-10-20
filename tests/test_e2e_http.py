"""End-to-end tests of the served HTTP app over a real 127.0.0.1 socket."""
import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest
import requests

from proxmox_mcp.app import build_uvicorn_server
from proxmox_mcp.auth.apikey import ENV_HASHES
from proxmox_mcp.server_http import ProxmoxMCPHTTPServer, build_parser

KEY = "e2e-secret-key"
DIGEST = hashlib.sha256(KEY.encode()).hexdigest()
PATH = "/proxmox-mcp"
HEADERS = {"Accept": "application/json, text/event-stream"}
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "e2e", "version": "0"},
    },
}


@contextmanager
def _serve(server: ProxmoxMCPHTTPServer):
    """Run the production uvicorn construction on an ephemeral loopback port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    uv = build_uvicorn_server(server.build_app(), "127.0.0.1", port)
    thread = threading.Thread(target=uv.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not uv.started and time.time() < deadline:
        time.sleep(0.02)
    assert uv.started, "uvicorn did not start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        uv.should_exit = True
        thread.join(timeout=15)
        sock.close()
        assert not thread.is_alive()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv(ENV_HASHES, raising=False)
    monkeypatch.setattr(
        "proxmox_mcp.server_http.setup_logging", lambda cfg: logging.getLogger("proxmox-mcp")
    )


@pytest.fixture
def served(mock_env_vars, fake_pve):
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", return_value=fake_pve):
        server = ProxmoxMCPHTTPServer(api_key_digests=[DIGEST])
        with _serve(server) as url:
            yield url, server


def _post(url, body=INIT, **headers):
    return requests.post(url + PATH, json=body, headers={**HEADERS, **headers}, timeout=10)


def _data(resp):
    text = resp.text
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(text)


def test_auth_over_real_socket(served):
    url, _ = served
    r = _post(url)
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized", "message": "Valid API key required"}
    assert r.headers["www-authenticate"] == "Bearer"
    assert _post(url, Authorization="Bearer wrong").status_code == 401
    assert _post(url, Authorization=f"Bearer {KEY}").status_code == 200
    assert _post(url, **{"X-API-Key": KEY}).status_code == 200


AUTH_HDR = {"Authorization": f"Bearer {KEY}"}


def test_health_unauthenticated_is_liveness_only(served):
    url, _ = served
    r = requests.get(url + "/health", timeout=10)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_authenticated_is_truthful(served):
    url, _ = served
    r = requests.get(url + "/health", headers=AUTH_HDR, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["auth"] == "api-key"
    assert body["proxmox"] == "not_connected"
    text = r.text
    for secret in (DIGEST, KEY, "test_value", "test.proxmox.com"):
        assert secret not in text


def _tool_call(url, name, arguments):
    auth = {"Authorization": f"Bearer {KEY}"}
    init = _post(url, **auth)
    assert init.status_code == 200
    sid = init.headers.get("mcp-session-id")
    sess = {**auth, **({"mcp-session-id": sid} if sid else {})}
    requests.post(
        url + PATH,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={**HEADERS, **sess},
        timeout=10,
    )
    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    return requests.post(url + PATH, json=body, headers={**HEADERS, **sess}, timeout=20)


def test_health_connected_after_tool_call(served):
    url, _ = served
    r = _tool_call(url, "get_nodes", {})
    assert r.status_code == 200, r.text
    assert "error" not in _data(r) or not _data(r)["error"]
    assert requests.get(url + "/health", headers=AUTH_HDR, timeout=10).json()["proxmox"] == "connected"


def test_health_unreachable(mock_env_vars):
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", side_effect=ConnectionError("down")):
        server = ProxmoxMCPHTTPServer(api_key_digests=[DIGEST])
        with _serve(server) as url:
            assert requests.get(url + "/health", headers=AUTH_HDR, timeout=10).json()["proxmox"] == "not_connected"
            _tool_call(url, "get_nodes", {})
            body = requests.get(url + "/health", headers=AUTH_HDR, timeout=10).json()
            assert body["proxmox"] == "unreachable"
            assert "down" not in json.dumps(body)


def test_ports_released_between_runs(mock_env_vars, fake_pve):
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", return_value=fake_pve):
        for _ in range(2):
            server = ProxmoxMCPHTTPServer(api_key_digests=[DIGEST])
            with _serve(server) as url:
                assert requests.get(url + "/health", timeout=10).status_code == 200


def test_default_bind_is_loopback():
    assert build_parser().parse_args([]).host == "127.0.0.1"


def _cli(tmp_path, *args):
    cfg = {
        "proxmox": {"host": "pve.invalid"},
        "auth": {"user": "u@pve", "token_name": "t", "token_value": "fake-value"},
    }
    path = tmp_path / "c.json"
    path.write_text(json.dumps(cfg))
    env = {
        k: v for k, v in os.environ.items()
        if k != ENV_HASHES and not k.startswith("PROXMOX_")
    }
    return subprocess.run(
        [sys.executable, "-I", "-m", "proxmox_mcp.server_http", "--config", str(path), *args],
        env=env, capture_output=True, text=True, timeout=60,
    )


def test_fail_closed_without_digests(tmp_path):
    out = _cli(tmp_path)
    assert out.returncode != 0
    assert ENV_HASHES in out.stdout + out.stderr


def test_no_auth_refused_off_loopback(tmp_path):
    out = _cli(tmp_path, "--no-auth", "--host", "0.0.0.0")
    assert out.returncode != 0
    assert "loopback" in out.stdout + out.stderr
