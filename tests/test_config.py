"""Config hardening tests (CONF-01, CONF-04). Fake values only; tmp_path for files."""
import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from proxmox_mcp.config.models import AuthConfig, Config, LoggingConfig, ProxmoxConfig

ROOT = Path(__file__).resolve().parent.parent
SENTINEL = "SENTINEL-token-value-xyz"

ENV_KEYS = [
    "PROXMOX_HOST", "PROXMOX_PORT", "PROXMOX_USER", "PROXMOX_TOKEN_NAME",
    "PROXMOX_TOKEN_VALUE", "PROXMOX_VERIFY_SSL", "PROXMOX_CA_BUNDLE",
    "PROXMOX_SERVICE", "LOG_LEVEL", "LOG_FILE",
]


@pytest.fixture
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def _auth(**kw):
    base = dict(user="u@pve", token_name="t", token_value=SENTINEL)
    base.update(kw)
    return base


def _data(**over):
    d = {
        "proxmox": {"host": "h.example"},
        "auth": _auth(),
        "logging": {"level": "INFO"},
    }
    for k, v in over.items():
        d[k] = {**d.get(k, {}), **v}
    return d


# ---- Task 1: models ----

def test_extra_keys_forbidden():
    with pytest.raises(ValidationError):
        ProxmoxConfig(host="h", bogus=1)
    with pytest.raises(ValidationError):
        AuthConfig(**_auth(bogus=1))
    with pytest.raises(ValidationError):
        LoggingConfig(bogus=1)
    with pytest.raises(ValidationError):
        Config(**_data(), bogus=1)


@pytest.mark.parametrize("val,exp", [
    (True, True), (False, False), ("1", True), (" TRUE ", True), ("yes", True),
    ("on", True), ("0", False), ("False", False), ("no", False), ("OFF", False),
])
def test_verify_ssl_accepts(val, exp):
    assert ProxmoxConfig(host="h", verify_ssl=val).verify_ssl is exp


@pytest.mark.parametrize("val", ["ture", "", "2", None, "maybe"])
def test_verify_ssl_rejects(val):
    with pytest.raises(ValidationError):
        ProxmoxConfig(host="h", verify_ssl=val)


def test_verify_ssl_default_true():
    assert ProxmoxConfig(host="h").verify_ssl is True


def test_token_not_in_text_sinks():
    a = AuthConfig(**_auth())
    for text in (repr(a), str(a), str(a.model_dump()), a.model_dump_json()):
        assert SENTINEL not in text
    assert a.token_value.get_secret_value() == SENTINEL
    c = Config(**_data())
    assert SENTINEL not in repr(c) + str(c.model_dump()) + c.model_dump_json()


def test_ca_bundle(tmp_path):
    f = tmp_path / "ca.pem"
    f.write_text("x")
    assert ProxmoxConfig(host="h", ca_bundle=str(f)).ca_bundle == str(f)
    with pytest.raises(ValidationError):
        ProxmoxConfig(host="h", ca_bundle=str(tmp_path / "missing.pem"))
    with pytest.raises(ValidationError):
        ProxmoxConfig(host="h", ca_bundle=str(f), verify_ssl=False)


def test_validation_error_hides_token():
    with pytest.raises(ValidationError) as ei:
        AuthConfig(user="bad user", token_name="t", token_value=SENTINEL)
    assert SENTINEL not in str(ei.value)
    with pytest.raises(ValidationError) as ei:
        Config(**_data(), bogus=SENTINEL)
    assert SENTINEL not in str(ei.value)


@pytest.mark.parametrize("kw", [
    {"port": 0}, {"port": 70000}, {"host": ""}, {"host": "a b"},
    {"host": "a/b"}, {"host": "https://h"}, {"host": "evil.com#@pve"}, {"host": "u@h"}, {"host": "h?x"}, {"service": "XYZ"},
])
def test_proxmox_field_validation(kw):
    with pytest.raises(ValidationError):
        ProxmoxConfig(**{"host": "h", **kw})


def test_logging_level_normalized():
    assert LoggingConfig(level="warning").level == "WARNING"
    with pytest.raises(ValidationError):
        LoggingConfig(level="LOUD")


def test_proxmox_manager_passes_secret_and_verify(tmp_path, caplog):
    from proxmox_mcp.core.proxmox import ProxmoxManager

    f = tmp_path / "ca.pem"
    f.write_text("x")
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as m:
        ProxmoxManager(ProxmoxConfig(host="h"), AuthConfig(**_auth()))
        kw = m.call_args.kwargs
        assert kw["token_value"] == SENTINEL and kw["verify_ssl"] is True
        ProxmoxManager(ProxmoxConfig(host="h", ca_bundle=str(f)), AuthConfig(**_auth()))
        assert m.call_args.kwargs["verify_ssl"] == str(f)
        with caplog.at_level(logging.WARNING, logger="proxmox-mcp.proxmox"):
            ProxmoxManager(ProxmoxConfig(host="h", verify_ssl=False), AuthConfig(**_auth()))
        assert any(
            r.levelno == logging.WARNING and r.name == "proxmox-mcp.proxmox"
            and SENTINEL not in r.getMessage()
            for r in caplog.records
        )


# ---- Task 2: loader ----

def _write(tmp_path, data, name="c.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return str(p)


def test_precedence_matrix(tmp_path, clean_env):
    from proxmox_mcp.config.loader import load_config

    path = _write(tmp_path, _data(proxmox={"port": 9000}, logging={"level": "WARNING"}))
    cfg = load_config(path)
    assert (cfg.logging.level, cfg.proxmox.port) == ("WARNING", 9000)
    clean_env.setenv("LOG_LEVEL", "ERROR")
    cfg = load_config(path)
    assert cfg.logging.level == "ERROR" and cfg.proxmox.port == 9000
    cfg = load_config(path, cli_overrides={"logging": {"level": "DEBUG"}})
    assert cfg.logging.level == "DEBUG" and cfg.proxmox.port == 9000
    assert cfg.proxmox.verify_ssl is True and cfg.proxmox.service == "PVE"


def test_env_only(tmp_path, clean_env):
    from proxmox_mcp.config.loader import load_config

    ca = tmp_path / "ca.pem"
    ca.write_text("x")
    for k, v in {
        "PROXMOX_HOST": "h", "PROXMOX_USER": "u@pve", "PROXMOX_TOKEN_NAME": "t",
        "PROXMOX_TOKEN_VALUE": SENTINEL, "PROXMOX_PORT": "8443", "PROXMOX_SERVICE": "PBS",
        "PROXMOX_CA_BUNDLE": str(ca), "LOG_LEVEL": "warning", "LOG_FILE": "x.log",
    }.items():
        clean_env.setenv(k, v)
    cfg = load_config()
    assert cfg.proxmox.port == 8443 and cfg.proxmox.service == "PBS"
    assert cfg.proxmox.ca_bundle == str(ca)
    assert cfg.logging.level == "WARNING" and cfg.logging.file == "x.log"


def test_env_overrides_file_verify_ssl_and_empty_unset(tmp_path, clean_env):
    from proxmox_mcp.config.loader import load_config

    path = _write(tmp_path, _data(proxmox={"verify_ssl": False}))
    clean_env.setenv("PROXMOX_VERIFY_SSL", "")
    assert load_config(path).proxmox.verify_ssl is False
    clean_env.setenv("PROXMOX_VERIFY_SSL", "true")
    assert load_config(path).proxmox.verify_ssl is True


def test_verify_ssl_typo_raises(tmp_path, clean_env):
    from proxmox_mcp.config.loader import load_config

    path = _write(tmp_path, _data())
    clean_env.setenv("PROXMOX_VERIFY_SSL", "ture")
    with pytest.raises(ValueError):
        load_config(path)
    clean_env.delenv("PROXMOX_VERIFY_SSL")
    with pytest.raises(ValueError) as ei:
        load_config(_write(tmp_path, _data(proxmox={"verify_ssl": "ture"}), "b.json"))
    assert SENTINEL not in str(ei.value)


def test_missing_fields_named(clean_env):
    from proxmox_mcp.config.loader import load_config

    clean_env.setenv("PROXMOX_USER", "u@pve")
    with pytest.raises(ValueError) as ei:
        load_config()
    msg = str(ei.value)
    assert "proxmox.host" in msg and "auth.token_name" in msg
    assert "PROXMOX_MCP_CONFIG" not in msg


def test_typo_key_secret_free(tmp_path, clean_env):
    from proxmox_mcp.config.loader import load_config

    path = _write(tmp_path, _data(proxmox={"verfy_ssl": True}))
    with pytest.raises(ValueError) as ei:
        load_config(path)
    msg = str(ei.value)
    assert "verfy_ssl" in msg and "proxmox" in msg and SENTINEL not in msg
    assert ei.value.__cause__ is None and ei.value.__suppress_context__


def test_invalid_json_message(tmp_path, clean_env):
    from proxmox_mcp.config.loader import load_config

    p = tmp_path / "bad.json"
    p.write_text('{"auth": {"token_value": "' + SENTINEL + '" oops')
    with pytest.raises(ValueError) as ei:
        load_config(str(p))
    assert SENTINEL not in str(ei.value) and "line" in str(ei.value)


def test_missing_file(tmp_path, clean_env):
    from proxmox_mcp.config.loader import load_config

    with pytest.raises(ValueError) as ei:
        load_config(str(tmp_path / "nope.json"))
    assert "nope.json" in str(ei.value)


def test_example_config_loads_safely(clean_env):
    from proxmox_mcp.config.loader import load_config

    path = ROOT / "proxmox-config" / "config.example.json"
    cfg = load_config(str(path))
    assert cfg.proxmox.verify_ssl is True
    assert cfg.logging.level != "DEBUG"
    assert not cfg.auth.user.startswith("root@pam")
    assert cfg.proxmox.ca_bundle is None
