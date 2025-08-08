"""
Tests for VM console operations.
"""

import pytest
from unittest.mock import MagicMock

from proxmox_mcp.tools.console import VMConsoleManager

@pytest.fixture
def mock_proxmox():
    """Fixture to create a mock ProxmoxAPI instance."""
    mock = MagicMock()
    # Setup chained mock calls
    mock.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "running"
    }
    # Two-step agent exec/status mocks via callable agent("exec") and agent("exec-status")
    agent_mock = MagicMock()
    exec_endpoint = MagicMock()
    exec_endpoint.post.return_value = {"pid": 123}
    status_endpoint = MagicMock()
    status_endpoint.get.return_value = {
        "out-data": "command output",
        "err-data": "",
        "exitcode": 0,
        "exited": 1
    }
    def agent_call(path):
        return exec_endpoint if path == "exec" else status_endpoint
    agent_mock.side_effect = agent_call
    mock.nodes.return_value.qemu.return_value.agent = agent_mock
    return mock

@pytest.fixture
def vm_console(mock_proxmox):
    """Fixture to create a VMConsoleManager instance."""
    return VMConsoleManager(mock_proxmox)

@pytest.mark.asyncio
async def test_execute_command_success(vm_console, mock_proxmox):
    """Test successful command execution."""
    result = await vm_console.execute_command("node1", "100", "ls -l")

    assert result["success"] is True
    assert result["output"] == "command output"
    assert result["error"] == ""
    assert result["exit_code"] == 0

    # Verify correct API calls
    mock_proxmox.nodes.return_value.qemu.assert_called_with("100")
    # Ensure exec was called (indirect via agent("exec").post)
    exec_endpoint = mock_proxmox.nodes.return_value.qemu.return_value.agent.side_effect("exec")
    exec_endpoint.post.assert_called_with(command="ls -l")

@pytest.mark.asyncio
async def test_execute_command_vm_not_running(vm_console, mock_proxmox):
    """Test command execution on stopped VM."""
    mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "stopped"
    }

    with pytest.raises(ValueError, match="not running"):
        await vm_console.execute_command("node1", "100", "ls -l")

@pytest.mark.asyncio
async def test_execute_command_vm_not_found(vm_console, mock_proxmox):
    """Test command execution on non-existent VM."""
    mock_proxmox.nodes.return_value.qemu.return_value.status.current.get.side_effect = \
        Exception("VM not found")

    with pytest.raises(ValueError, match="not found"):
        await vm_console.execute_command("node1", "100", "ls -l")

@pytest.mark.asyncio
async def test_execute_command_failure(vm_console, mock_proxmox):
    """Test command execution failure."""
    # Simulate failure on exec start
    agent_mock = MagicMock()
    failing_exec = MagicMock()
    failing_exec.post.side_effect = Exception("Command failed")
    status_endpoint = MagicMock()
    def agent_call_fail(path):
        return failing_exec if path == "exec" else status_endpoint
    agent_mock.side_effect = agent_call_fail
    mock_proxmox.nodes.return_value.qemu.return_value.agent = agent_mock

    with pytest.raises(RuntimeError, match="Failed to execute command"):
        await vm_console.execute_command("node1", "100", "ls -l")

@pytest.mark.asyncio
async def test_execute_command_with_error_output(vm_console, mock_proxmox):
    """Test command execution with error output."""
    agent_mock = MagicMock()
    exec_endpoint = MagicMock()
    exec_endpoint.post.return_value = {"pid": 987}
    status_endpoint = MagicMock()
    status_endpoint.get.return_value = {
        "out-data": "",
        "err-data": "command error",
        "exitcode": 1,
        "exited": 1
    }
    def agent_call_err(path):
        return exec_endpoint if path == "exec" else status_endpoint
    agent_mock.side_effect = agent_call_err
    mock_proxmox.nodes.return_value.qemu.return_value.agent = agent_mock

    result = await vm_console.execute_command("node1", "100", "invalid-command")

    assert result["success"] is True  # Success refers to API call, not command
    assert result["output"] == ""
    assert result["error"] == "command error"
    assert result["exit_code"] == 1
