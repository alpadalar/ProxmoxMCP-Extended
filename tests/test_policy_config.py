"""Policy config tests (SEC-01 config surface). Fake values only."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from proxmox_mcp.config.loader import load_config
from proxmox_mcp.config.models import Config, PolicyConfig

POLICY_ENV = [
    "PROXMOX_MCP_READ_ONLY",
    "PROXMOX_MCP_ALLOW_DESTRUCTIVE",
    "PROXMOX_MCP_ALLOW_EXEC",
    "PROXMOX_MCP_EXEC_TIMEOUT",
    "PROXMOX_MCP_EXEC_MAX_OUTPUT",
    "PROXMOX_MCP_EXEC_MAX_CONCURRENT",
]
BASE_ENV = {
    "PROXMOX_HOST": "h.example",
    "PROXMOX_USER": "u@pve",
    "PROXMOX_TOKEN_NAME": "t",
    "PROXMOX_TOKEN_VALUE": "fake-secret",
}


@pytest.fixture
def env(monkeypatch):
    for k in POLICY_ENV:
        monkeypatch.delenv(k, raising=False)
    for k, v in BASE_ENV.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def _minimal(**policy):
    d = {
        "proxmox": {"host": "h.example"},
        "auth": {"user": "u@pve", "token_name": "t", "token_value": "fake"},
    }
    if policy:
        d["policy"] = policy
    return d


def test_defaults_closed():
    p = Config(**_minimal()).policy
    assert (p.read_only, p.allow_destructive, p.allow_exec) == (False, False, False)
    assert p.exec_timeout_seconds == 30.0
    assert p.exec_max_output_bytes == 65536


@pytest.mark.parametrize(
    "raw,expected",
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("true", True),
        ("FALSE", False),
        ("Yes", True),
        ("no", False),
        ("on", True),
        ("OFF", False),
        ("1", True),
        ("0", False),
    ],
)
def test_bool_accepts(raw, expected):
    assert PolicyConfig(allow_exec=raw).allow_exec is expected


@pytest.mark.parametrize("raw", ["ture", "maybe", 2, None])
def test_bool_rejects_without_echo(raw):
    with pytest.raises(ValidationError) as ei:
        PolicyConfig(allow_exec=raw)
    text = str(ei.value)
    assert "allow_exec" in text
    if isinstance(raw, str):
        assert raw not in text.replace("allow_exec", "")


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        PolicyConfig(allow_everything=True)


@pytest.mark.parametrize(
    "kw",
    [
        {"exec_timeout_seconds": 0},
        {"exec_timeout_seconds": 301},
        {"exec_max_output_bytes": 1023},
        {"exec_max_output_bytes": 1_048_577},
    ],
)
def test_ranges_rejected(kw):
    with pytest.raises(ValidationError):
        PolicyConfig(**kw)


@pytest.mark.parametrize(
    "kw",
    [
        {"exec_timeout_seconds": 300},
        {"exec_max_output_bytes": 1024},
        {"exec_max_output_bytes": 1_048_576},
    ],
)
def test_range_edges_accepted(kw):
    PolicyConfig(**kw)


def test_env_beats_file_and_empty_is_unset(env, tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({**_minimal(allow_exec=False)}))
    env.setenv("PROXMOX_MCP_ALLOW_EXEC", "true")
    assert load_config(str(f)).policy.allow_exec is True
    env.setenv("PROXMOX_MCP_ALLOW_EXEC", "")
    assert load_config(str(f)).policy.allow_exec is False


def test_env_typo_is_explicit_error(env):
    env.setenv("PROXMOX_MCP_READ_ONLY", "ture")
    with pytest.raises(ValueError) as ei:
        load_config(None)
    msg = str(ei.value)
    assert msg.startswith("Invalid configuration: policy.read_only: ")
    assert "ture" not in msg


def test_env_numeric_mapping(env):
    env.setenv("PROXMOX_MCP_EXEC_TIMEOUT", "12.5")
    env.setenv("PROXMOX_MCP_EXEC_MAX_OUTPUT", "2048")
    env.setenv("PROXMOX_MCP_EXEC_MAX_CONCURRENT", "4")
    p = load_config(None).policy
    assert (p.exec_timeout_seconds, p.exec_max_output_bytes) == (12.5, 2048)
    assert p.exec_max_concurrent == 4


# ---- CLI flags / entry points / example config (Task 2) ----

ROOT = Path(__file__).resolve().parent.parent


def _write_cfg(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps(_minimal()))
    return str(f)


def _capture_stdio(monkeypatch):
    import proxmox_mcp.server as srv

    seen = {}

    class Fake:
        def __init__(self, config_path, cli_overrides=None):
            seen["overrides"] = cli_overrides

        def start(self):
            pass

    monkeypatch.setattr(srv, "ProxmoxMCPServer", Fake)
    return srv, seen


@pytest.mark.parametrize(
    "flag,key",
    [
        ("--allow-destructive", "allow_destructive"),
        ("--allow-exec", "allow_exec"),
        ("--read-only", "read_only"),
    ],
)
def test_stdio_flags_in_overrides(env, tmp_path, monkeypatch, flag, key):
    srv, seen = _capture_stdio(monkeypatch)
    srv.main(["--config", _write_cfg(tmp_path), flag])
    assert seen["overrides"]["policy"] == {key: "true"}


def test_stdio_no_flags_no_policy_key(env, tmp_path, monkeypatch):
    srv, seen = _capture_stdio(monkeypatch)
    srv.main(["--config", _write_cfg(tmp_path)])
    assert "policy" not in seen["overrides"]


def test_cli_beats_env(env, tmp_path):
    env.setenv("PROXMOX_MCP_ALLOW_EXEC", "false")
    cfg = load_config(_write_cfg(tmp_path), cli_overrides={"policy": {"allow_exec": "true"}})
    assert cfg.policy.allow_exec is True


def test_http_parser_flags_and_server(env):
    from unittest.mock import patch

    from proxmox_mcp.config.loader import policy_cli_overrides
    from proxmox_mcp.server_http import ProxmoxMCPHTTPServer, build_parser

    args = build_parser().parse_args(["--allow-exec", "--allow-destructive", "--read-only"])
    assert policy_cli_overrides(args) == {
        "policy": {"read_only": "true", "allow_destructive": "true", "allow_exec": "true"}
    }
    assert policy_cli_overrides(build_parser().parse_args([])) == {}

    digest = hashlib.sha256(b"k" * 16).hexdigest()
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI"):
        server = ProxmoxMCPHTTPServer(
            api_key_digests=[digest], cli_overrides={"policy": {"allow_exec": "true"}}
        )
    assert server.config.policy.allow_exec is True
    assert server.config.policy.allow_destructive is False


def test_example_config_loads_closed(env):
    cfg = load_config(str(ROOT / "proxmox-config" / "config.example.json"))
    assert (cfg.policy.read_only, cfg.policy.allow_destructive, cfg.policy.allow_exec) == (
        False,
        False,
        False,
    )
