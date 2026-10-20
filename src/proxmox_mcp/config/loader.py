"""
Configuration loading utilities for the Proxmox MCP server.

A single loader resolves configuration for both the file-path and env-only
cases. Precedence, highest wins:

    CLI overrides > environment variables > JSON file > built-in defaults

Errors raised here are built only from field locations and validation
messages, never from input values, so secrets cannot leak through them.
"""
import json
import os
from typing import Any, Dict, Mapping, Optional

from pydantic import ValidationError

from .models import Config

# env var -> (section, key)
_ENV_MAP = {
    "PROXMOX_HOST": ("proxmox", "host"),
    "PROXMOX_PORT": ("proxmox", "port"),
    "PROXMOX_VERIFY_SSL": ("proxmox", "verify_ssl"),
    "PROXMOX_CA_BUNDLE": ("proxmox", "ca_bundle"),
    "PROXMOX_SERVICE": ("proxmox", "service"),
    "PROXMOX_TIMEOUT": ("proxmox", "timeout"),
    "PROXMOX_USER": ("auth", "user"),
    "PROXMOX_TOKEN_NAME": ("auth", "token_name"),
    "PROXMOX_TOKEN_VALUE": ("auth", "token_value"),
    "LOG_LEVEL": ("logging", "level"),
    "LOG_FILE": ("logging", "file"),
    "PROXMOX_MCP_READ_ONLY": ("policy", "read_only"),
    "PROXMOX_MCP_ALLOW_DESTRUCTIVE": ("policy", "allow_destructive"),
    "PROXMOX_MCP_ALLOW_EXEC": ("policy", "allow_exec"),
    "PROXMOX_MCP_EXEC_TIMEOUT": ("policy", "exec_timeout_seconds"),
    "PROXMOX_MCP_EXEC_MAX_OUTPUT": ("policy", "exec_max_output_bytes"),
}


def _overlay(base: Dict[str, Any], top: Mapping[str, Any]) -> None:
    """Recursively overlay ``top`` onto ``base`` in place."""
    for key, value in top.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _overlay(base[key], value)
        elif isinstance(value, Mapping):
            base[key] = {}
            _overlay(base[key], value)
        else:
            base[key] = value


def _read_json(config_path: str) -> Dict[str, Any]:
    try:
        with open(config_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON in config file: {e.msg} (line {e.lineno}, column {e.colno})"
        ) from None
    except OSError:
        raise ValueError(f"Cannot read config file: {config_path}") from None
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a JSON object")
    return data


def _env_layer() -> Dict[str, Any]:
    layer: Dict[str, Any] = {}
    for name, (section, key) in _ENV_MAP.items():
        value = os.environ.get(name)
        if value is None or value == "":
            continue
        layer.setdefault(section, {})[key] = value
    return layer


def _format_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors(include_input=False, include_url=False):
        loc = ".".join(str(p) for p in err.get("loc", ())) or "config"
        parts.append(f"{loc}: {err.get('msg', 'invalid value')}")
    return "Invalid configuration: " + "; ".join(parts)


def load_config(
    config_path: Optional[str] = None,
    cli_overrides: Optional[Mapping[str, Any]] = None,
) -> Config:
    """Load and validate configuration.

    Layers (highest precedence wins): CLI overrides > environment variables
    > JSON file (if ``config_path``) > model defaults.

    Environment variables: PROXMOX_HOST, PROXMOX_PORT, PROXMOX_USER,
    PROXMOX_TOKEN_NAME, PROXMOX_TOKEN_VALUE, PROXMOX_VERIFY_SSL,
    PROXMOX_CA_BUNDLE, PROXMOX_SERVICE, PROXMOX_TIMEOUT, LOG_LEVEL, LOG_FILE,
    PROXMOX_MCP_READ_ONLY, PROXMOX_MCP_ALLOW_DESTRUCTIVE, PROXMOX_MCP_ALLOW_EXEC,
    PROXMOX_MCP_EXEC_TIMEOUT, PROXMOX_MCP_EXEC_MAX_OUTPUT. An empty
    string is treated as unset.

    Args:
        config_path: Optional path to a JSON config file.
        cli_overrides: Optional nested dict shaped like the JSON file.

    Returns:
        Validated Config.

    Raises:
        ValueError: on unreadable/invalid JSON, unknown keys, missing or
            invalid values. Messages never contain secret values.
    """
    # Seed required sections so missing fields are reported as e.g. "proxmox.host"
    data: Dict[str, Any] = {"proxmox": {}, "auth": {}}
    if config_path:
        _overlay(data, _read_json(config_path))
    _overlay(data, _env_layer())
    if cli_overrides:
        _overlay(data, cli_overrides)

    try:
        return Config(**data)
    except ValidationError as e:
        raise ValueError(_format_errors(e)) from None
