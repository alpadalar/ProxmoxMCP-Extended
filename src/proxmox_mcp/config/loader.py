"""
Configuration loading utilities for the Proxmox MCP server.

This module handles loading and validation of server configuration:
- JSON configuration file loading
- Environment variable handling
- Configuration validation using Pydantic models
- Error handling for invalid configurations

The module ensures that all required configuration is present
and valid before the server starts operation.
"""
import json
import os
from typing import Optional
from .models import Config

def load_config(config_path: Optional[str] = None) -> Config:
    """Load and validate configuration from JSON file.

    Performs the following steps:
    1. Verifies config path is provided
    2. Loads JSON configuration file
    3. Validates required fields are present
    4. Converts to typed Config object using Pydantic
    
    Configuration must include:
    - Proxmox connection settings (host, port, etc.)
    - Authentication credentials (user, token)
    - Logging configuration
    
    Args:
        config_path: Path to the JSON configuration file
                    If not provided, raises ValueError

    Returns:
        Config object containing validated configuration:
        {
            "proxmox": {
                "host": "proxmox-host",
                "port": 8006,
                ...
            },
            "auth": {
                "user": "username",
                "token_name": "token-name",
                ...
            },
            "logging": {
                "level": "INFO",
                ...
            }
        }

    Raises:
        ValueError: If:
                 - Config path is not provided
                 - JSON is invalid
                 - Required fields are missing
                 - Field values are invalid
    """
    # If a config path is provided, load from JSON file
    if config_path:
        try:
            with open(config_path) as f:
                config_data = json.load(f)
                if not config_data.get('proxmox', {}).get('host'):
                    raise ValueError("Proxmox host cannot be empty")
                return Config(**config_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load config: {e}")

    # Otherwise, build config from environment variables (test-friendly path)
    proxmox_host = os.getenv("PROXMOX_HOST")
    proxmox_user = os.getenv("PROXMOX_USER")
    token_name = os.getenv("PROXMOX_TOKEN_NAME")
    token_value = os.getenv("PROXMOX_TOKEN_VALUE")
    log_level = os.getenv("LOG_LEVEL", "INFO")

    if not all([proxmox_host, proxmox_user, token_name, token_value]):
        raise ValueError("PROXMOX_MCP_CONFIG environment variable must be set")

    # Optional overrides
    port_str = os.getenv("PROXMOX_PORT")
    verify_ssl_str = os.getenv("PROXMOX_VERIFY_SSL")
    service = os.getenv("PROXMOX_SERVICE", "PVE")

    try:
        port = int(port_str) if port_str else 8006
    except ValueError:
        raise ValueError("Invalid PROXMOX_PORT value; must be integer")

    if verify_ssl_str is None:
        verify_ssl = True
    else:
        verify_ssl = verify_ssl_str.lower() in ("1", "true", "yes", "on")

    config_data = {
        "proxmox": {
            "host": proxmox_host,
            "port": port,
            "verify_ssl": verify_ssl,
            "service": service,
        },
        "auth": {
            "user": proxmox_user,
            "token_name": token_name,
            "token_value": token_value,
        },
        "logging": {
            "level": log_level,
        },
    }

    return Config(**config_data)
