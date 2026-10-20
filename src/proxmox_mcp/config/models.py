"""
Configuration models for the Proxmox MCP server.

This module defines Pydantic models for configuration validation:
- Proxmox connection settings
- Authentication credentials
- Logging configuration
- Tool-specific parameter models

The models provide:
- Type validation
- Default values
- Field descriptions
- Required vs optional field handling
"""
import os
import re
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_STRICT = ConfigDict(extra="forbid", hide_input_in_errors=True)


def _strict_bool(v: Any, field_name: str) -> bool:
    """Parse a boolean strictly; typos raise (fail closed) and never echo input."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    if isinstance(v, str):
        norm = v.strip().lower()
        if norm in _TRUE_VALUES:
            return True
        if norm in _FALSE_VALUES:
            return False
    raise ValueError(
        f"invalid {field_name} value; accepted: true/false, 1/0, yes/no, on/off"
    )


class NodeStatus(BaseModel):
    """Model for node status query parameters.
    
    Validates and documents the required parameters for
    querying a specific node's status in the cluster.
    """
    node: Annotated[
        str, Field(description="Name/ID of node to query (e.g. 'pve1', 'proxmox-node2')")
    ]

class VMCommand(BaseModel):
    """Model for VM command execution parameters.
    
    Validates and documents the required parameters for
    executing commands within a VM via QEMU guest agent.
    """
    node: Annotated[str, Field(description="Host node name (e.g. 'pve1', 'proxmox-node2')")]
    vmid: Annotated[str, Field(description="VM ID number (e.g. '100', '101')")]
    command: Annotated[
        str,
        Field(description="Shell command to run (e.g. 'uname -a', 'systemctl status nginx')"),
    ]

class ProxmoxConfig(BaseModel):
    """Model for Proxmox connection configuration.

    Strict: unknown keys are rejected. ``verify_ssl`` defaults to True and is
    parsed strictly (typos raise instead of silently disabling TLS).
    """
    model_config = _STRICT

    host: str  # Required: Proxmox host address
    port: int = Field(default=8006, ge=1, le=65535)  # API port
    verify_ssl: bool = True  # SSL verification (default: True)
    ca_bundle: str | None = None  # Optional CA bundle file for private CAs
    service: str = Field(default="PVE", pattern=r"^(PVE|PMG|PBS)$")
    timeout: float = Field(default=30.0, gt=0, le=300)  # request timeout in seconds

    @field_validator("host")
    @classmethod
    def _check_host(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Proxmox host cannot be empty")
        if re.search(r"\s", v) or "/" in v or "://" in v:
            raise ValueError("host must be a bare hostname or IP (no scheme, path or spaces)")
        if any(ch in v for ch in "@?#\\"):
            raise ValueError("host must not contain URL-significant characters (@ ? # \\)")
        return v

    @field_validator("verify_ssl", mode="before")
    @classmethod
    def _parse_verify_ssl(cls, v: Any) -> bool:
        return _strict_bool(v, "verify_ssl")

    @field_validator("ca_bundle")
    @classmethod
    def _check_ca_bundle(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not os.path.isfile(v):
            raise ValueError("ca_bundle must be an existing file")
        return v

    @model_validator(mode="after")
    def _ca_bundle_requires_verify(self) -> "ProxmoxConfig":
        if self.ca_bundle and not self.verify_ssl:
            raise ValueError("ca_bundle cannot be combined with verify_ssl=false")
        return self

class AuthConfig(BaseModel):
    """Model for Proxmox authentication configuration.

    ``token_value`` is a SecretStr so it never appears in repr/dumps/errors.
    """
    model_config = _STRICT

    user: str = Field(pattern=r"^[^@\s]+@[A-Za-z0-9._-]+$")  # e.g. 'monitor@pve'
    token_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    token_value: SecretStr = Field(min_length=1)

class LoggingConfig(BaseModel):
    """Model for logging configuration."""
    model_config = _STRICT

    level: str = "INFO"  # Optional: Log level (default: INFO)
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"  # Optional: Log format
    file: str | None = None  # Optional: Log file path (default: None for console logging)

    @field_validator("level")
    @classmethod
    def _check_level(cls, v: str) -> str:
        norm = v.strip().upper()
        if norm not in _LOG_LEVELS:
            raise ValueError("level must be one of " + ", ".join(sorted(_LOG_LEVELS)))
        return norm

class HttpConfig(BaseModel):
    """HTTP transport settings.

    ``api_key_digests`` holds SHA-256 hex digests of accepted API keys (never
    the keys themselves). Env ``PROXMOX_MCP_API_KEY_HASHES`` replaces this list.
    """
    model_config = _STRICT

    api_key_digests: list[str] = Field(default_factory=list)

    @field_validator("api_key_digests", mode="before")
    @classmethod
    def _check_digests(cls, v: Any) -> Any:
        from ..auth.apikey import normalize_digests  # lazy: avoid import cycle

        if not isinstance(v, (list, tuple)) or not all(isinstance(i, str) for i in v):
            raise ValueError("api_key_digests must be a list of digest strings")
        try:
            return normalize_digests(v)
        except ValueError:
            raise ValueError(
                "api_key_digests must be sha256 hex digests "
                "(64 hex chars, optional 'sha256:' prefix)"
            ) from None

class PolicyConfig(BaseModel):
    """Tool-layer safety policy. All dangerous gates default to closed.

    ``read_only=true`` overrides both ``allow_*`` gates and blocks every
    write, destructive and exec tool. The gates are enforced at call time
    (tools stay registered so the MCP surface is stable).
    """
    model_config = _STRICT

    read_only: bool = False
    allow_destructive: bool = False
    allow_exec: bool = False
    exec_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    exec_max_output_bytes: int = Field(default=65536, ge=1024, le=1_048_576)
    exec_max_concurrent: int = Field(default=2, ge=1, le=16)

    @field_validator("read_only", "allow_destructive", "allow_exec", mode="before")
    @classmethod
    def _parse_gates(cls, v: Any, info: Any) -> bool:
        return _strict_bool(v, info.field_name)

class Config(BaseModel):
    """Root configuration model (proxmox and auth required, logging defaulted)."""
    model_config = _STRICT

    proxmox: ProxmoxConfig  # Required: Proxmox connection settings
    auth: AuthConfig  # Required: Authentication credentials
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
