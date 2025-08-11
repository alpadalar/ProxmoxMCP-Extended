"""
Tests for the Proxmox MCP server.
"""

import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from proxmox_mcp.server import ProxmoxMCPServer

@pytest.fixture
def mock_env_vars():
    """Fixture to set up test environment variables."""
    env_vars = {
        "PROXMOX_HOST": "test.proxmox.com",
        "PROXMOX_USER": "test@pve",
        "PROXMOX_TOKEN_NAME": "test_token",
        "PROXMOX_TOKEN_VALUE": "test_value",
        "LOG_LEVEL": "DEBUG"
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars

@pytest.fixture
def mock_proxmox():
    """Fixture to mock ProxmoxAPI."""
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as mock:
        mock.return_value.nodes.get.return_value = [
            {"node": "node1", "status": "online"},
            {"node": "node2", "status": "online"}
        ]
        yield mock

@pytest.fixture
def server(mock_env_vars, mock_proxmox):
    """Fixture to create a ProxmoxMCPServer instance."""
    return ProxmoxMCPServer()

def test_server_initialization(server, mock_proxmox):
    """Test server initialization with environment variables."""
    assert server.config.proxmox.host == "test.proxmox.com"
    assert server.config.auth.user == "test@pve"
    assert server.config.auth.token_name == "test_token"
    assert server.config.auth.token_value == "test_value"
    assert server.config.logging.level == "DEBUG"

    mock_proxmox.assert_called_once()

@pytest.mark.asyncio
async def test_list_tools(server):
    """Test listing available tools."""
    tools = await server.mcp.list_tools()

    assert len(tools) > 0
    tool_names = [tool.name for tool in tools]
    assert "get_nodes" in tool_names
    assert "get_vms" in tool_names
    assert "get_containers" in tool_names
    assert "create_snapshot" in tool_names
    assert "rollback_snapshot" in tool_names
    assert "get_vm_usage" in tool_names
    assert "execute_vm_command" in tool_names

@pytest.mark.asyncio
async def test_get_nodes(server, mock_proxmox):
    """Test get_nodes tool."""
    mock_proxmox.return_value.nodes.get.return_value = [
        {"node": "node1", "status": "online"},
        {"node": "node2", "status": "online"}
    ]
    # Mock detailed node status to avoid MagicMock arithmetic in formatter
    mock_proxmox.return_value.nodes.return_value.status.get.side_effect = [
        {"uptime": 1000, "cpuinfo": {"cpus": 4}, "memory": {"used": 1024*1024*1024, "total": 2*1024*1024*1024}},
        {"uptime": 2000, "cpuinfo": {"cpus": 8}, "memory": {"used": 2*1024*1024*1024, "total": 4*1024*1024*1024}},
    ]
    response = await server.mcp.call_tool("get_nodes", {})
    text = response[0].text
    # Response is pre-formatted text; ensure it contains our mocked node names
    assert "node1" in text
    assert "node2" in text

    # The response is formatted text now; length checks on raw list are not applicable

@pytest.mark.asyncio
async def test_get_node_status_missing_parameter(server):
    """Test get_node_status tool with missing parameter."""
    with pytest.raises(ToolError):
        await server.mcp.call_tool("get_node_status", {})

@pytest.mark.asyncio
async def test_get_node_status(server, mock_proxmox):
    """Test get_node_status tool with valid parameter."""
    mock_proxmox.return_value.nodes.return_value.status.get.return_value = {
        "status": "running",
        "uptime": 123456
    }

    response = await server.mcp.call_tool("get_node_status", {"node": "node1"})
    # Verify formatted content contains expected fields
    assert "Status: RUNNING" in response[0].text
    assert "Uptime:" in response[0].text

@pytest.mark.asyncio
async def test_get_vms(server, mock_proxmox):
    """Test get_vms tool."""
    mock_proxmox.return_value.nodes.get.return_value = [{"node": "node1", "status": "online"}]
    mock_proxmox.return_value.nodes.return_value.qemu.get.return_value = [
        {"vmid": "100", "name": "vm1", "status": "running"},
        {"vmid": "101", "name": "vm2", "status": "stopped"}
    ]

    response = await server.mcp.call_tool("get_vms", {})
    text = response[0].text
    assert "vm1" in text and "vm2" in text

@pytest.mark.asyncio
async def test_get_containers(server, mock_proxmox):
    """Test get_containers tool."""
    mock_proxmox.return_value.nodes.get.return_value = [{"node": "node1", "status": "online"}]
    mock_proxmox.return_value.nodes.return_value.lxc.get.return_value = [
        {"vmid": "200", "name": "container1", "status": "running"},
        {"vmid": "201", "name": "container2", "status": "stopped"}
    ]

    response = await server.mcp.call_tool("get_containers", {})
    text = response[0].text
    assert "container1" in text and "container2" in text

@pytest.mark.asyncio
async def test_get_storage(server, mock_proxmox):
    """Test get_storage tool."""
    mock_proxmox.return_value.storage.get.return_value = [
        {"storage": "local", "type": "dir"},
        {"storage": "ceph", "type": "rbd"}
    ]

    # Mock storage status metrics for formatters
    mock_proxmox.return_value.nodes.return_value.storage.return_value.status.get.side_effect = [
        {"used": 10*1024*1024*1024, "total": 100*1024*1024*1024, "avail": 90*1024*1024*1024},
        {"used": 50*1024*1024*1024, "total": 500*1024*1024*1024, "avail": 450*1024*1024*1024},
    ]
    response = await server.mcp.call_tool("get_storage", {})
    text = response[0].text
    assert "local" in text and "ceph" in text

@pytest.mark.asyncio
async def test_get_vm_usage(server, mock_proxmox):
    """Test get_vm_usage tool output formatting."""
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "cpu": 0.235,
        "mem": 1200 * 1024 * 1024,
        "maxmem": 4 * 1024 * 1024 * 1024,
        "disk": 10 * 1024 * 1024 * 1024,
        "maxdisk": 50 * 1024 * 1024 * 1024,
    }
    response = await server.mcp.call_tool("get_vm_usage", {"node": "node1", "vmid": "100"})
    text = response[0].text
    assert "CPU:" in text and "%" in text
    assert "Memory:" in text
    assert "Disk:" in text

@pytest.mark.asyncio
async def test_create_snapshot(server, mock_proxmox):
    """Test create_snapshot tool."""
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.status.current.get.return_value = {}
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.snapshot.post.return_value = "UPID:taskid"
    response = await server.mcp.call_tool(
        "create_snapshot",
        {"node": "node1", "vmid": "100", "name": "pre-upgrade", "description": "test", "vmstate": False},
    )
    text = response[0].text
    assert "Snapshot 'pre-upgrade'" in text
    assert "Task ID" in text

@pytest.mark.asyncio
async def test_rollback_snapshot(server, mock_proxmox):
    """Test rollback_snapshot tool."""
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.status.current.get.return_value = {}
    snap_resource = MagicMock()
    snap_resource.rollback.post.return_value = "UPID:taskid"
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.snapshot.return_value = snap_resource
    response = await server.mcp.call_tool(
        "rollback_snapshot",
        {"node": "node1", "vmid": "100", "name": "pre-upgrade"},
    )
    text = response[0].text
    assert "Rollback to snapshot 'pre-upgrade'" in text
    assert "Task ID" in text

@pytest.mark.asyncio
async def test_get_cluster_status(server, mock_proxmox):
    """Test get_cluster_status tool."""
    mock_proxmox.return_value.cluster.status.get.return_value = {
        "quorate": True,
        "nodes": 2
    }

    # Cluster.status.get returns a list in our implementation; adapt mock accordingly
    mock_proxmox.return_value.cluster.status.get.return_value = [
        {"name": "proxmox", "quorate": True, "type": "cluster"},
        {"type": "node"},
        {"type": "node"},
    ]
    response = await server.mcp.call_tool("get_cluster_status", {})
    text = response[0].text
    assert "Quorum: OK" in text
    assert "Nodes: 2" in text

@pytest.mark.asyncio
async def test_execute_vm_command_success(server, mock_proxmox):
    """Test successful VM command execution."""
    # Mock VM status check
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "running"
    }
    # Mock command execution
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.agent.exec.post.return_value = {
        "out": "command output",
        "err": "",
        "exitcode": 0
    }

    # Adjust mocks for new two-step exec flow
    agent_mock = MagicMock()
    exec_endpoint = MagicMock(); exec_endpoint.post.return_value = {"pid": 123}
    status_endpoint = MagicMock(); status_endpoint.get.return_value = {"out-data": "command output", "err-data": "", "exitcode": 0, "exited": 1}
    def agent_call(path):
        return exec_endpoint if path == "exec" else status_endpoint
    agent_mock.side_effect = agent_call
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.agent = agent_mock
    response = await server.mcp.call_tool("execute_vm_command", {
        "node": "node1",
        "vmid": "100",
        "command": "ls -l"
    })
    text = response[0].text
    assert "Status: SUCCESS" in text
    assert "Output:" in text and "command output" in text

@pytest.mark.asyncio
async def test_execute_vm_command_missing_parameters(server):
    """Test VM command execution with missing parameters."""
    with pytest.raises(ToolError):
        await server.mcp.call_tool("execute_vm_command", {})

@pytest.mark.asyncio
async def test_execute_vm_command_vm_not_running(server, mock_proxmox):
    """Test VM command execution when VM is not running."""
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "stopped"
    }

    with pytest.raises(ToolError, match="not running"):
        await server.mcp.call_tool("execute_vm_command", {
            "node": "node1",
            "vmid": "100",
            "command": "ls -l"
        })

@pytest.mark.asyncio
async def test_execute_vm_command_with_error(server, mock_proxmox):
    """Test VM command execution with command error."""
    # Mock VM status check
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "running"
    }
    # Mock command execution with error via two-step flow
    agent_mock = MagicMock()
    exec_endpoint = MagicMock(); exec_endpoint.post.return_value = {"pid": 456}
    status_endpoint = MagicMock(); status_endpoint.get.return_value = {"out-data": "", "err-data": "command not found", "exitcode": 1, "exited": 1}
    def agent_call_err(path):
        return exec_endpoint if path == "exec" else status_endpoint
    agent_mock.side_effect = agent_call_err
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.agent = agent_mock

    response = await server.mcp.call_tool("execute_vm_command", {
        "node": "node1",
        "vmid": "100",
        "command": "invalid-command"
    })
    text = response[0].text
    assert "Status: SUCCESS" in text
    assert "Error:" in text and "command not found" in text

@pytest.mark.asyncio
async def test_start_vm(server, mock_proxmox):
    """Test start_vm tool."""
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "stopped"
    }
    mock_proxmox.return_value.nodes.return_value.qemu.return_value.status.start.post.return_value = "UPID:taskid"

    response = await server.mcp.call_tool("start_vm", {"node": "node1", "vmid": "100"})
    assert "start initiated successfully" in response[0].text
