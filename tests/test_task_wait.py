"""wait/timeout on the seven task-returning mutators (FEAT-02), on PVE 8 and PVE 9 fixtures."""

import json

import pytest
from fastmcp.exceptions import ToolError, ValidationError

from proxmox_mcp.utils.redaction import register_secret
from tests.test_harness import SMOKE_ARGS, SMOKE_ARGS_CONFIRMED

OTHER_NODE_UPID = "UPID:pve2:0000ABCD:00123456:65A1B2C3:qmstart:100:monitor@pve!mcp:"
STATUS = "nodes/*/tasks/*/status"

# tool -> (method, route of the mutating call in the fixtures)
MUTATORS = {
    "start_vm": ("POST", "nodes/*/qemu/*/status/start"),
    "stop_vm": ("POST", "nodes/*/qemu/*/status/stop"),
    "shutdown_vm": ("POST", "nodes/*/qemu/*/status/shutdown"),
    "reset_vm": ("POST", "nodes/*/qemu/*/status/reset"),
    "delete_vm": ("DELETE", "nodes/*/qemu/*"),
    "create_snapshot": ("POST", "nodes/*/qemu/*/snapshot"),
    "rollback_snapshot": ("POST", "nodes/*/qemu/*/snapshot/*/rollback"),
}
DESTRUCTIVE = {"stop_vm", "reset_vm", "delete_vm", "rollback_snapshot"}
names = pytest.mark.parametrize("name", sorted(MUTATORS))


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def app(policy_app):
    built = policy_app(allow_destructive=True)
    clock = Clock()
    built.vm_tools._sleep, built.vm_tools._clock = clock.sleep, clock
    built.clock = clock
    return built


def _args(name, **extra):
    return {**SMOKE_ARGS_CONFIRMED[name], **extra}


def _text(result):
    return result.content[0].text


def _task_calls(fake):
    return [c for c in fake.calls if "/tasks/" in c.path]


@names
@pytest.mark.asyncio
async def test_wait_omitted_keeps_text_and_makes_no_task_calls(app, fake_pve, name):
    text = _text(await app.mcp.call_tool(name, _args(name)))
    assert "Task ID: UPID:pve1:" in text
    assert "Task finished" not in text and "Wait skipped" not in text
    assert _task_calls(fake_pve) == []
    text = _text(await app.mcp.call_tool(name, _args(name, wait=False, timeout=10)))
    assert "Task ID: UPID:pve1:" in text and _task_calls(fake_pve) == []


@names
@pytest.mark.asyncio
async def test_wait_true_ok_polls_upid_node(app, fake_pve, name):
    method, route = MUTATORS[name]
    fake_pve.set(method, route, OTHER_NODE_UPID)
    text = _text(await app.mcp.call_tool(name, _args(name, wait=True)))
    assert "Task finished: OK" in text and OTHER_NODE_UPID in text
    assert [c.path for c in _task_calls(fake_pve)] == [f"nodes/pve2/tasks/{OTHER_NODE_UPID}/status"]


@names
@pytest.mark.asyncio
async def test_wait_true_still_running_reports_not_raises(app, fake_pve, name):
    fake_pve.set("GET", STATUS, {"status": "running"})
    text = _text(await app.mcp.call_tool(name, _args(name, wait=True, timeout=6)))
    assert "UPID:pve1:" in text and "still running" in text
    assert app.clock.sleeps and sum(app.clock.sleeps) == 6  # bounded by the deadline


@names
@pytest.mark.asyncio
async def test_wait_true_failed_task_raises_with_upid_and_exitstatus(app, fake_pve, name):
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "command failed"})
    with pytest.raises(ToolError) as exc:
        await app.mcp.call_tool(name, _args(name, wait=True))
    msg = str(exc.value)
    assert "UPID:pve1:" in msg and "command failed" in msg and "finished: OK" not in msg


@names
@pytest.mark.asyncio
async def test_wait_true_warnings_is_not_success(app, fake_pve, name):
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "WARNINGS: 3"})
    text = _text(await app.mcp.call_tool(name, _args(name, wait=True)))
    assert "finished with warnings" in text and "Task finished: OK" not in text


@names
@pytest.mark.asyncio
async def test_wait_true_null_return_is_skipped(app, fake_pve, name):
    method, route = MUTATORS[name]
    fake_pve.set(method, route, None)
    text = _text(await app.mcp.call_tool(name, _args(name, wait=True)))
    assert "Wait skipped" in text
    assert _task_calls(fake_pve) == []


@names
@pytest.mark.asyncio
async def test_failed_task_log_secret_is_redacted(app, fake_pve, name):
    secret = "sentinel-secret-for-task-wait"
    register_secret(secret)
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "failed"})
    fake_pve.set("GET", "nodes/*/tasks/*/log", [{"n": 1, "t": f"password={secret}"}])
    with pytest.raises(ToolError) as exc:
        await app.mcp.call_tool(name, _args(name, wait=True))
    assert secret not in str(exc.value) and "[REDACTED]" in str(exc.value)


@names
@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, 301, -5])
async def test_bad_timeout_rejected_before_any_call(app, fake_pve, name, timeout):
    fake_pve.reset_calls()
    with pytest.raises((ToolError, ValidationError)):
        await app.mcp.call_tool(name, _args(name, wait=True, timeout=timeout))
    assert fake_pve.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(DESTRUCTIVE))
async def test_missing_confirm_with_wait_is_preview_with_zero_calls(app, fake_pve, name):
    fake_pve.reset_calls()
    result = await app.mcp.call_tool(name, {**SMOKE_ARGS[name], "wait": True, "timeout": 60})
    assert '"preview": true' in _text(result)
    assert fake_pve.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(DESTRUCTIVE))
async def test_policy_denial_wins_over_wait(policy_app, fake_pve, name):
    denied = policy_app(allow_destructive=False)
    with pytest.raises(ToolError, match="policy_denied"):
        await denied.mcp.call_tool(name, _args(name, wait=True, timeout=60))
    assert fake_pve.calls == []
    read_only = policy_app(read_only=True, allow_destructive=True)
    with pytest.raises(ToolError, match="policy_denied"):
        await read_only.mcp.call_tool(name, _args(name, wait=True, timeout=60))
    assert fake_pve.calls == []


@pytest.mark.asyncio
async def test_wait_for_task_after_mutator_returns_same_upid(app, fake_pve):
    """The UPID printed by a mutator is directly usable with wait_for_task."""
    text = _text(await app.mcp.call_tool("start_vm", _args("start_vm")))
    upid = text.split("Task ID: ")[1].split()[0]
    data = json.loads(_text(await app.mcp.call_tool("wait_for_task", {"upid": upid})))
    assert data["success"] is True
