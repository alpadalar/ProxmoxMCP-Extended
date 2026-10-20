"""Mock-based tests for mutating and exec tools, called through ``server.mcp.call_tool``.

These document current behavior (no gating yet); error paths must not reach the mutation.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError, ValidationError

from tests.helpers import tool_text

NODE_ARGS = {"node": "node1", "vmid": "100"}


@pytest.fixture
def vm(api):
    """The ``qemu(vmid)`` mock node, with a running VM by default."""
    vm = api.nodes.return_value.qemu.return_value
    vm.status.current.get.return_value = {"status": "running", "name": "web01"}
    return vm


def _set_status(vm, status):
    vm.status.current.get.return_value = {"status": status, "name": "web01"}


@pytest.mark.asyncio
async def test_create_vm_calls_qemu_create(server, api):
    """create_vm creates the VM with vmid/name/cores/memory on the node."""
    node = api.nodes.return_value
    node.qemu.return_value.config.get.side_effect = Exception("does not exist")
    node.storage.get.return_value = [
        {"storage": "local-lvm", "type": "lvmthin", "content": "images,rootdir"},
    ]
    node.qemu.create.return_value = "UPID:task"
    args = {"node": "node1", "vmid": "200", "name": "new-vm", "cpus": 2,
            "memory": 2048, "disk_size": 10}
    text = tool_text(await server.mcp.call_tool("create_vm", args))
    node.qemu.create.assert_called_once()
    kwargs = node.qemu.create.call_args.kwargs
    assert kwargs["vmid"] == "200" and kwargs["name"] == "new-vm"
    assert kwargs["cores"] == 2 and kwargs["memory"] == 2048
    assert "200" in text


@pytest.mark.asyncio
async def test_create_vm_rejects_out_of_range_cpus(server, api):
    """cpus=64 is rejected by parameter validation before any API call."""
    args = {"node": "node1", "vmid": "200", "name": "new-vm", "cpus": 64,
            "memory": 2048, "disk_size": 10}
    with pytest.raises((ToolError, ValidationError)):
        await server.mcp.call_tool("create_vm", args)
    api.nodes.return_value.qemu.create.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,action,state", [
    ("start_vm", "start", "stopped"),
    ("stop_vm", "stop", "running"),
    ("shutdown_vm", "shutdown", "running"),
    ("reset_vm", "reset", "running"),
])
async def test_power_tools_post_once(server, vm, tool, action, state):
    """Each power tool posts to the matching status endpoint exactly once."""
    _set_status(vm, state)
    vm.status.__getattr__(action).post.return_value = "UPID:task"
    text = tool_text(await server.mcp.call_tool(tool, NODE_ARGS))
    getattr(vm.status, action).post.assert_called_once_with()
    assert "UPID:task" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,action", [
    ("start_vm", "start"), ("stop_vm", "stop"),
    ("shutdown_vm", "shutdown"), ("reset_vm", "reset"),
])
async def test_power_tools_missing_vm_does_not_post(server, vm, tool, action):
    """A nonexistent VM yields an error and never posts the action."""
    vm.status.current.get.side_effect = Exception("VM 100 does not exist")
    with pytest.raises(ToolError, match="not found"):
        await server.mcp.call_tool(tool, NODE_ARGS)
    getattr(vm.status, action).post.assert_not_called()


@pytest.mark.asyncio
async def test_delete_vm_stopped(server, vm):
    """Deleting a stopped VM calls qemu(vmid).delete without stopping first."""
    _set_status(vm, "stopped")
    vm.delete.return_value = "UPID:del"
    text = tool_text(await server.mcp.call_tool("delete_vm", NODE_ARGS))
    vm.delete.assert_called_once_with()
    vm.status.stop.post.assert_not_called()
    assert "UPID:del" in text


@pytest.mark.asyncio
async def test_delete_vm_running_without_force_refused(server, vm):
    """A running VM is not deleted without force."""
    with pytest.raises(ToolError, match="running"):
        await server.mcp.call_tool("delete_vm", NODE_ARGS)
    vm.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_vm_force_stops_then_deletes(server, vm):
    """force=True on a running VM stops it first, then deletes (call order)."""
    manager = MagicMock()
    manager.attach_mock(vm.status.stop.post, "stop_post")
    manager.attach_mock(vm.delete, "delete")
    await server.mcp.call_tool("delete_vm", {**NODE_ARGS, "force": True})
    names = [c[0] for c in manager.mock_calls if c[0] in ("stop_post", "delete")]
    assert names == ["stop_post", "delete"]


@pytest.mark.asyncio
async def test_update_vm_applies_config(server, vm):
    """update_vm maps memory/cpus/name to a single config.put on a stopped VM."""
    _set_status(vm, "stopped")
    vm.config.get.return_value = {"memory": 1024, "cores": 1}
    vm.config.put.return_value = "UPID:cfg"
    await server.mcp.call_tool("update_vm", {**NODE_ARGS, "memory": 2048, "cpus": 4, "name": "renamed"})
    vm.config.put.assert_called_once_with(memory=2048, cores=4, name="renamed")


@pytest.mark.asyncio
async def test_update_vm_without_fields_posts_nothing(server, vm):
    """update_vm with no fields reports no changes and writes nothing."""
    _set_status(vm, "stopped")
    vm.config.get.return_value = {"memory": 1024, "cores": 1}
    text = tool_text(await server.mcp.call_tool("update_vm", NODE_ARGS))
    vm.config.put.assert_not_called()
    assert "No changes" in text


@pytest.mark.asyncio
async def test_create_snapshot_posts_snapname(server, vm):
    """create_snapshot posts snapname plus description and vmstate when supplied."""
    vm.snapshot.post.return_value = "UPID:snap"
    await server.mcp.call_tool(
        "create_snapshot", {**NODE_ARGS, "name": "pre", "description": "d", "vmstate": True})
    vm.snapshot.post.assert_called_once_with(snapname="pre", description="d", vmstate=1)


@pytest.mark.asyncio
async def test_create_snapshot_minimal(server, vm):
    """Without optional fields only snapname is posted."""
    await server.mcp.call_tool("create_snapshot", {**NODE_ARGS, "name": "pre"})
    vm.snapshot.post.assert_called_once_with(snapname="pre")


@pytest.mark.asyncio
async def test_rollback_snapshot_posts_rollback(server, vm):
    """rollback_snapshot posts snapshot(name).rollback."""
    vm.snapshot.return_value.rollback.post.return_value = "UPID:rb"
    text = tool_text(await server.mcp.call_tool("rollback_snapshot", {**NODE_ARGS, "name": "pre"}))
    vm.snapshot.assert_called_with("pre")
    vm.snapshot.return_value.rollback.post.assert_called_once_with()
    assert "UPID:rb" in text


def _agent(vm, output="hello"):
    exec_ep = MagicMock()
    exec_ep.post.return_value = {"pid": 7}
    status_ep = MagicMock()
    status_ep.get.return_value = {"out-data": output, "err-data": "", "exitcode": 0, "exited": 1}
    vm.agent = MagicMock(side_effect=lambda p: exec_ep if p == "exec" else status_ep)
    return exec_ep, status_ep


@pytest.mark.asyncio
async def test_execute_vm_command_returns_output(server, vm):
    """execute_vm_command starts exec on the guest agent and returns its output."""
    exec_ep, status_ep = _agent(vm, "hello-from-guest")
    with patch("asyncio.sleep", new=AsyncMock()):
        text = tool_text(await server.mcp.call_tool(
            "execute_vm_command", {**NODE_ARGS, "command": "echo hi"}))
    exec_ep.post.assert_called_once_with(command="echo hi")
    status_ep.get.assert_called_once_with(pid=7)
    assert "hello-from-guest" in text


@pytest.mark.asyncio
async def test_execute_vm_command_stopped_vm(server, vm):
    """A stopped VM raises 'not running' and never starts exec."""
    _set_status(vm, "stopped")
    exec_ep, _ = _agent(vm)
    with pytest.raises(ToolError, match="not running"):
        await server.mcp.call_tool("execute_vm_command", {**NODE_ARGS, "command": "ls"})
    exec_ep.post.assert_not_called()


def test_every_tool_has_a_mock_test():
    """Each golden tool name appears as a string literal in a mock test module."""
    here = Path(__file__).parent
    golden = json.loads((here / "golden" / "tools.json").read_text(encoding="utf-8"))
    corpus = (here / "test_tools_read.py").read_text() + (here / "test_tools_mutating.py").read_text()
    missing = [t["name"] for t in golden if f'"{t["name"]}"' not in corpus]
    assert not missing, f"tools without a mock test: {missing}"
