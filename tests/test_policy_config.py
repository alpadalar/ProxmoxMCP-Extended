"""Policy config tests (SEC-01 config surface). Fake values only."""
import json

import pytest
from pydantic import ValidationError

from proxmox_mcp.config.loader import load_config
from proxmox_mcp.config.models import Config, PolicyConfig

POLICY_ENV = [
    "PROXMOX_MCP_READ_ONLY", "PROXMOX_MCP_ALLOW_DESTRUCTIVE", "PROXMOX_MCP_ALLOW_EXEC",
    "PROXMOX_MCP_EXEC_TIMEOUT", "PROXMOX_MCP_EXEC_MAX_OUTPUT",
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


@pytest.mark.parametrize("raw,expected", [
    (True, True), (False, False), (1, True), (0, False),
    ("true", True), ("FALSE", False), ("Yes", True), ("no", False),
    ("on", True), ("OFF", False), ("1", True), ("0", False),
])
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


@pytest.mark.parametrize("kw", [
    {"exec_timeout_seconds": 0}, {"exec_timeout_seconds": 301},
    {"exec_max_output_bytes": 1023}, {"exec_max_output_bytes": 1_048_577},
])
def test_ranges_rejected(kw):
    with pytest.raises(ValidationError):
        PolicyConfig(**kw)


@pytest.mark.parametrize("kw", [
    {"exec_timeout_seconds": 300}, {"exec_max_output_bytes": 1024},
    {"exec_max_output_bytes": 1_048_576},
])
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
    p = load_config(None).policy
    assert (p.exec_timeout_seconds, p.exec_max_output_bytes) == (12.5, 2048)
