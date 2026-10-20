"""PVE 8.x vs 9.x behavior matrix (TECH-02), run against the pve8 and pve9 harness fixtures."""
import pytest
from fastmcp.exceptions import ToolError
from proxmoxer.core import ResourceException

from tests.helpers import tool_text

UPID_RE_PREFIX = "UPID:pve1:"
MISSING = ResourceException(
    500, "Internal Server Error",
    "Configuration file 'nodes/pve1/qemu-server/999.conf' does not exist",
)

# tool -> (args for vmid 999, expected privilege in a 403 message)
VM_TOOLS = {
    "start_vm": ({}, "VM.PowerMgmt"),
    "stop_vm": ({"confirm": True}, "VM.PowerMgmt"),
    "shutdown_vm": ({}, "VM.PowerMgmt"),
    "reset_vm": ({"confirm": True}, "VM.PowerMgmt"),
    "delete_vm": ({"confirm": True}, "VM.Allocate"),
    "update_vm": ({"memory": 2048}, "VM.Config"),
    "create_snapshot": ({"name": "s1"}, "VM.Snapshot"),
    "rollback_snapshot": ({"name": "s1", "confirm": True}, "VM.Snapshot.Rollback"),
    "list_snapshots": ({}, "VM.Audit"),
    "delete_snapshot": ({"name": "s1", "confirm": True}, "VM.Snapshot"),
}


@pytest.fixture
def app(policy_app):
    return policy_app(allow_destructive=True, allow_exec=True)


def _args(tool, vmid="999"):
    extra, _ = VM_TOOLS[tool]
    return {"node": "pve1", "vmid": vmid, **extra}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", sorted(VM_TOOLS))
async def test_missing_vm_is_not_found_and_mutates_nothing(app, fake_pve, tool):
    fake_pve.fail("GET", "nodes/*/qemu/999/status/current", MISSING)
    fake_pve.reset_calls()
    with pytest.raises(ToolError, match="VM 999 not found on node pve1"):
        await app.mcp.call_tool(tool, _args(tool))
    assert fake_pve.mutating_calls() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", sorted(VM_TOOLS))
async def test_403_names_privilege_and_path(app, fake_pve, tool):
    fake_pve.fail("GET", "nodes/*/qemu/999/status/current",
                  ResourceException(403, "Forbidden", "Permission check failed"))
    fake_pve.reset_calls()
    with pytest.raises(ToolError) as ei:
        await app.mcp.call_tool(tool, _args(tool))
    text = str(ei.value)
    assert "Permission denied" in text
    assert VM_TOOLS[tool][1] in text and "/vms/999" in text
    assert fake_pve.mutating_calls() == []


@pytest.mark.asyncio
async def test_rollback_upid_vs_null_return(app, fake_pve):
    args = {"node": "pve1", "vmid": "100", "name": "snap1", "confirm": True}
    text = tool_text(await app.mcp.call_tool("rollback_snapshot", args))
    assert "Task ID: UPID:pve1:" in text
    # PVE 9.1: rollback returns null
    fake_pve.set("POST", "nodes/*/qemu/*/snapshot/*/rollback", None)
    text = tool_text(await app.mcp.call_tool("rollback_snapshot", args))
    assert "no task id" in text.lower() and "verify" in text.lower()
    assert "None" not in text and "Task ID" not in text


@pytest.mark.asyncio
async def test_update_and_snapshot_never_print_task_id_none(app, fake_pve):
    fake_pve.set("POST", "nodes/*/qemu/*/snapshot", None)
    snap = tool_text(await app.mcp.call_tool(
        "create_snapshot", {"node": "pve1", "vmid": "100", "name": "s2"}))
    upd = tool_text(await app.mcp.call_tool(
        "update_vm", {"node": "pve1", "vmid": "101", "name": "renamed-vm"}))
    for text in (snap, upd):
        assert "Task ID: None" not in text and "None" not in text
        assert "no task id" in text.lower()


def _stop_sequence(fake, final_exit="OK"):
    states = iter([{"status": "running"}, {"status": "stopped", "exitstatus": final_exit}])
    fake.set("GET", "nodes/*/tasks/*/status", lambda p, s: next(states))


@pytest.mark.asyncio
async def test_force_delete_waits_for_stop_task(app, fake_pve):
    app.vm_tools._sleep = lambda s: None
    _stop_sequence(fake_pve)
    cur = iter([{"status": "running", "name": "web-01"}])
    fake_pve.set("GET", "nodes/*/qemu/100/status/current",
                 lambda p, s: next(cur, {"status": "stopped", "name": "web-01"}))
    fake_pve.reset_calls()
    await app.mcp.call_tool(
        "delete_vm", {"node": "pve1", "vmid": "100", "force": True, "confirm": True})
    seq = [(c.method, c.path) for c in fake_pve.calls if c.method != "GET" or "tasks" in c.path]
    assert seq[0] == ("POST", "nodes/pve1/qemu/100/status/stop")
    assert [p for m, p in seq if "tasks" in p] and seq[-1] == ("DELETE", "nodes/pve1/qemu/100")
    assert sum("tasks" in p for _, p in seq) == 2


@pytest.mark.asyncio
async def test_force_delete_aborts_when_stop_task_failed(app, fake_pve):
    app.vm_tools._sleep = lambda s: None
    _stop_sequence(fake_pve, final_exit="some error")
    fake_pve.reset_calls()
    with pytest.raises(ToolError, match="some error"):
        await app.mcp.call_tool(
            "delete_vm", {"node": "pve1", "vmid": "100", "force": True, "confirm": True})
    assert [c for c in fake_pve.mutating_calls() if c.method == "DELETE"] == []


@pytest.mark.asyncio
async def test_force_delete_null_stop_polls_status_current(app, fake_pve):
    app.vm_tools._sleep = lambda s: None
    fake_pve.set("POST", "nodes/*/qemu/*/status/stop", None)
    states = iter([
        {"status": "running", "name": "web-01"},  # lookup
        {"status": "running"},
        {"status": "stopped"},
        {"status": "stopped"},  # re-check right before delete
    ])
    fake_pve.set("GET", "nodes/*/qemu/100/status/current", lambda p, s: next(states))
    fake_pve.reset_calls()
    await app.mcp.call_tool(
        "delete_vm", {"node": "pve1", "vmid": "100", "force": True, "confirm": True})
    methods = [(c.method, c.path) for c in fake_pve.calls]
    assert methods[-1] == ("DELETE", "nodes/pve1/qemu/100")
    assert not any("tasks" in p for _, p in methods)


@pytest.mark.asyncio
async def test_force_delete_null_stop_times_out_without_delete(app, fake_pve):
    app.vm_tools._sleep = lambda s: None
    fake_pve.set("POST", "nodes/*/qemu/*/status/stop", None)  # status.current stays running
    fake_pve.reset_calls()
    with pytest.raises(ToolError, match="did not stop"):
        await app.mcp.call_tool(
            "delete_vm", {"node": "pve1", "vmid": "100", "force": True, "confirm": True})
    assert [c for c in fake_pve.calls if c.method == "DELETE"] == []


@pytest.mark.asyncio
async def test_delete_running_without_force_refused_and_stopped_only_deletes(app, fake_pve):
    fake_pve.reset_calls()
    with pytest.raises(ToolError, match="currently running"):
        await app.mcp.call_tool("delete_vm", {"node": "pve1", "vmid": "100", "confirm": True})
    assert fake_pve.mutating_calls() == []
    await app.mcp.call_tool("delete_vm", {"node": "pve1", "vmid": "101", "confirm": True})
    assert [(c.method, c.path) for c in fake_pve.mutating_calls()] == [
        ("DELETE", "nodes/pve1/qemu/101")]


@pytest.mark.asyncio
async def test_create_vm_existence_uses_listing(app, fake_pve):
    base = {"node": "pve1", "name": "new-vm", "cpus": 2, "memory": 1024, "disk_size": 10}
    fake_pve.reset_calls()
    with pytest.raises(ToolError, match="already exists"):
        await app.mcp.call_tool("create_vm", {**base, "vmid": "100"})
    assert fake_pve.mutating_calls() == []
    # a config probe error whose text says "does not exist" must not matter any more
    text = tool_text(await app.mcp.call_tool("create_vm", {**base, "vmid": "200"}))
    assert "creation queued" in text
    assert [c.path for c in fake_pve.mutating_calls()] == ["nodes/pve1/qemu"]


# --------------------------------------------------------------------------
# Version capture, health reporting, version-aware guest-agent hints
# --------------------------------------------------------------------------
import json  # noqa: E402
import logging  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from starlette.testclient import TestClient  # noqa: E402

from tests.test_harness import SMOKE_ARGS_CONFIRMED  # noqa: E402

EXPECTED_VERSION = {"pve8": ("8.4.1", "8"), "pve9": ("9.0.3", "9")}


def _expected(fake_pve):
    """(version, major) the fixture reports."""
    version = fake_pve.version.get()["version"]
    fake_pve.reset_calls()
    return version, int(version.split(".")[0])


def test_version_info_none_before_connect_and_set_after(app, fake_pve):
    version, major = _expected(fake_pve)
    assert app.manager.version_info() is None and app.manager.pve_major() is None
    assert fake_pve.calls == []
    app.manager.get_api().nodes.get()
    info = app.manager.version_info()
    assert info.version == version and info.major == major == app.manager.pve_major()
    n = len(fake_pve.calls)
    app.manager.version_info(), app.manager.pve_major()
    assert len(fake_pve.calls) == n  # no network I/O


def test_failed_connect_leaves_version_none(app, fake_pve):
    fake_pve.fail("GET", "version", ResourceException(401, "Unauthorized", "no ticket"))
    with pytest.raises(RuntimeError):
        app.manager.get_api().nodes.get()
    assert app.manager.version_info() is None and app.manager.pve_major() is None


@pytest.mark.asyncio
async def test_health_tool_reports_pve(app, fake_pve):
    release = fake_pve.version.get()["release"]
    version, major = _expected(fake_pve)
    before = json.loads(tool_text(await app.mcp.call_tool("health", {})))
    assert before["pve"] is None
    await app.mcp.call_tool("get_nodes", {})
    after = json.loads(tool_text(await app.mcp.call_tool("health", {})))
    assert after["pve"] == {"version": version, "release": release, "major": major}


def test_http_health_reports_pve(policy_app, fake_pve):
    version, major = _expected(fake_pve)
    app = policy_app("http")
    headers = {"X-API-Key": "test-api-key"}
    with TestClient(app.asgi) as client:
        body = client.get("/health", headers=headers).json()
        assert "pve" in body and body["pve"] is None
        assert body["proxmox"] == "not_connected"
        app.manager.get_api().nodes.get()
        body = client.get("/health", headers=headers).json()
    assert body["pve"]["version"] == version and body["pve"]["major"] == major
    assert body["proxmox"] == "connected"


# -- guest agent hints ------------------------------------------------------

SENTINEL = "SENTINEL_CMD_91ab"
EXEC = {"node": "pve1", "vmid": "100", "command": SENTINEL}


async def _exec(app):
    with patch("asyncio.sleep", new=AsyncMock()):
        return await app.mcp.call_tool("execute_vm_command", EXEC)


@pytest.mark.asyncio
async def test_exec_403_is_version_aware(app, fake_pve):
    _, major = _expected(fake_pve)
    fake_pve.fail("POST", "nodes/*/qemu/*/agent/exec",
                  ResourceException(403, "Forbidden", "Permission check failed"))
    with pytest.raises(ToolError) as ei:
        await _exec(app)
    text = str(ei.value)
    assert "/vms/100" in text
    if major == 8:
        assert "VM.Monitor" in text and "VM.GuestAgent" not in text
    else:
        assert "VM.Monitor was removed" in text
        assert "VM.GuestAgent.Unrestricted" in text and "unverified" in text
    assert SENTINEL not in text


@pytest.mark.asyncio
async def test_exec_403_unknown_version_names_both(policy_app, fake_pve):
    app = policy_app(allow_exec=True)
    app.vm_tools.console_manager._pve_major = lambda: None
    fake_pve.fail("POST", "nodes/*/qemu/*/agent/exec", ResourceException(403, "Forbidden", "x"))
    with pytest.raises(ToolError) as ei:
        await _exec(app)
    assert "VM.Monitor" in str(ei.value) and "VM.GuestAgent.Unrestricted" in str(ei.value)


@pytest.mark.asyncio
async def test_exec_agent_not_running_and_stopped_vm(app, fake_pve):
    fake_pve.fail("POST", "nodes/*/qemu/*/agent/exec", ResourceException(
        500, "Internal Server Error", "QEMU guest agent is not running"))
    with pytest.raises(ToolError) as ei:
        await _exec(app)
    assert "agent: 1" in str(ei.value) and "qemu-guest-agent" in str(ei.value)
    assert SENTINEL not in str(ei.value)
    with pytest.raises(ToolError, match="is not running"):
        await app.mcp.call_tool("execute_vm_command", {**EXEC, "vmid": "101"})


@pytest.mark.asyncio
async def test_exec_hint_messages_and_logs_have_no_command(app, fake_pve, caplog):
    for name in ("proxmox-mcp", "proxmox-mcp.vm-console"):
        logging.getLogger(name).propagate = True
    fake_pve.fail("POST", "nodes/*/qemu/*/agent/exec", ResourceException(403, "Forbidden", "x"))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ToolError) as ei:
            await _exec(app)
    assert SENTINEL not in str(ei.value) and SENTINEL not in caplog.text


@pytest.mark.asyncio
async def test_exec_missing_vm_uses_listing(app, fake_pve):
    fake_pve.fail("GET", "nodes/*/qemu/999/status/current", MISSING)
    with pytest.raises(ToolError, match="VM 999 not found on node pve1"):
        await _exec_vm(app, "999")


async def _exec_vm(app, vmid):
    with patch("asyncio.sleep", new=AsyncMock()):
        return await app.mcp.call_tool("execute_vm_command", {**EXEC, "vmid": vmid})


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(SMOKE_ARGS_CONFIRMED))
async def test_full_smoke_same_outcome_on_both_versions(app, fake_pve, name):
    """Every tool succeeds on the permissive app against either fixture."""
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await app.mcp.call_tool(name, SMOKE_ARGS_CONFIRMED[name])
    assert tool_text(result).strip()
