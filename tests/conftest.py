"""Shared fixtures for the ProxmoxMCP test suite."""
import os
from unittest.mock import patch

import pytest

from proxmox_mcp.server import ProxmoxMCPServer


@pytest.fixture
def mock_env_vars():
    """Set fake Proxmox credentials (never real values) in the environment."""
    env_vars = {
        "PROXMOX_HOST": "test.proxmox.com",
        "PROXMOX_USER": "test@pve",
        "PROXMOX_TOKEN_NAME": "test_token",
        "PROXMOX_TOKEN_VALUE": "test_value",
        "LOG_LEVEL": "DEBUG",
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def mock_proxmox():
    """Mock ProxmoxAPI with two online nodes."""
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as mock:
        mock.return_value.nodes.get.return_value = [
            {"node": "node1", "status": "online"},
            {"node": "node2", "status": "online"},
        ]
        yield mock


@pytest.fixture
def api(mock_proxmox):
    """Alias for the mocked API instance, handy for chain-mocking."""
    return mock_proxmox.return_value


@pytest.fixture
def server(mock_env_vars, mock_proxmox):
    """A ProxmoxMCPServer built from the fake environment."""
    return ProxmoxMCPServer()
