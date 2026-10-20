"""start_container / stop_container / shutdown_container (FEAT-04) on PVE 8 and PVE 9 fixtures."""

import json

import pytest
from fastmcp.exceptions import ToolError

from tests.helpers import tool_text

STATUS = "nodes/*/lxc/*/status/current"
TOOLS = {"start_container": "start", "stop_container": "stop", "shutdown_container": "shutdown"}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def app(policy_app):
    built = policy_app(allow_destructive=True)
    clock = Clock()
    built.container_tools._sleep, built.container_tools._clock = clock.sleep, clock
    return built


def _args(name, **extra):
    base = {"vmid": "200"}
    if name == "stop_container":
        base["confirm"] = True
    return {**base, **extra}


def _posts(fake):
    return [(c.path, c.params) for c in fake.mutating_calls()]


@pytest.mark.asyncio
async def test_start_posts_when_stopped_and_returns_upid(app, fake_pve):
    fake_pve.set("GET", STATUS, {"status": "stopped"})
    text = tool_text(await app.mcp.call_tool("start_container", {"vmid": "200"}))
    assert "Container 200 start initiated" in text and "Task ID: UPID:pve1:" in text
    assert _posts(fake_pve) == [("nodes/pve1/lxc/200/status/start", {})]


@pytest.mark.asyncio
async def test_start_running_is_noop(app, fake_pve):
    text = tool_text(await app.mcp.call_tool("start_container", {"vmid": "200"}))
    assert "already running" in text and fake_pve.mutating_calls() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["shutdown_container", "stop_container"])
async def test_stopped_container_is_noop(app, fake_pve, name):
    fake_pve.set("GET", STATUS, {"status": "stopped"})
    text = tool_text(await app.mcp.call_tool(name, _args(name)))
    assert "already stopped" in text and fake_pve.mutating_calls() == []


@pytest.mark.asyncio
async def test_shutdown_sends_no_pve_timeout(app, fake_pve):
    text = tool_text(await app.mcp.call_tool("shutdown_container", {"vmid": "200", "timeout": 120}))
    assert "Task ID: UPID:pve1:" in text
    assert _posts(fake_pve) == [("nodes/pve1/lxc/200/status/shutdown", {})]


@pytest.mark.asyncio
async def test_stop_without_confirm_is_static_preview(app, fake_pve):
    fake_pve.reset_calls()
    out = json.loads(tool_text(await app.mcp.call_tool("stop_container", {"vmid": "200"})))
    assert out["preview"] is True and out["executed"] is False
    assert out["tool"] == "stop_container"
    assert out["target"] == {"node": None, "vmid": "200"}
    assert fake_pve.calls == []
    out = json.loads(
        tool_text(
            await app.mcp.call_tool(
                "stop_container", {"vmid": "200", "node": "pve1", "confirm": False}
            )
        )
    )
    assert out["target"]["node"] == "pve1" and fake_pve.calls == []


@pytest.mark.asyncio
async def test_stop_confirm_resolves_and_posts(app, fake_pve):
    text = tool_text(await app.mcp.call_tool("stop_container", _args("stop_container")))
    assert "stop initiated" in text
    assert [c.path for c in fake_pve.calls if c.path != "version"] == [
        "cluster/resources",
        "nodes/pve1/lxc/200/status/current",
        "nodes/pve1/lxc/200/status/stop",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(TOOLS))
async def test_qemu_vmid_refused_without_post(app, fake_pve, name):
    with pytest.raises(ToolError, match="qemu VM, not an LXC container.*start_vm"):
        await app.mcp.call_tool(name, _args(name, vmid="100"))
    assert fake_pve.mutating_calls() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(TOOLS))
async def test_missing_template_and_node_mismatch_refused(app, fake_pve, name):
    for vmid, node, pattern in (
        ("999", None, "VM.Audit"),
        ("201", None, "template"),
        ("200", "pve2", "pve1"),
    ):
        extra = {"node": node} if node else {}
        with pytest.raises(ToolError, match=pattern):
            await app.mcp.call_tool(name, _args(name, vmid=vmid, **extra))
    assert fake_pve.mutating_calls() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(TOOLS))
async def test_wait_ok_running_failed(app, fake_pve, name):
    fake_pve.set("GET", STATUS, {"status": "stopped" if name == "start_container" else "running"})
    text = tool_text(await app.mcp.call_tool(name, _args(name, wait=True)))
    assert "Task finished: OK" in text
    fake_pve.set("GET", "nodes/*/tasks/*/status", {"status": "running"})
    text = tool_text(await app.mcp.call_tool(name, _args(name, wait=True, timeout=2)))
    assert "still running" in text
    fake_pve.set("GET", "nodes/*/tasks/*/status", {"status": "stopped", "exitstatus": "boom"})
    with pytest.raises(ToolError, match="failed"):
        await app.mcp.call_tool(name, _args(name, wait=True))


@pytest.mark.asyncio
async def test_migrated_container_uses_current_node(app, fake_pve):
    fake_pve.set(
        "GET",
        "cluster/resources",
        [{"type": "lxc", "vmid": 200, "node": "pve2", "status": "running", "name": "ct-01"}],
    )
    await app.mcp.call_tool("shutdown_container", {"vmid": "200"})
    assert _posts(fake_pve) == [("nodes/pve2/lxc/200/status/shutdown", {})]


@pytest.mark.asyncio
async def test_policy_matrix_for_container_tools(policy_app, fake_pve):
    ro = policy_app(read_only=True, allow_destructive=True)
    for name in sorted(TOOLS):
        fake_pve.reset_calls()
        with pytest.raises(ToolError, match="policy_denied"):
            await ro.mcp.call_tool(name, _args(name))
        assert fake_pve.calls == []
    default = policy_app()
    for name in ("start_container", "shutdown_container"):
        assert tool_text(await default.mcp.call_tool(name, {"vmid": "200"}))
    fake_pve.reset_calls()
    for confirm in (True, False):
        with pytest.raises(ToolError, match="policy_denied"):
            await default.mcp.call_tool("stop_container", {"vmid": "200", "confirm": confirm})
    assert fake_pve.calls == []
