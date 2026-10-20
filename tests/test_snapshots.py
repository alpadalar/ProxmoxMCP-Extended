"""list_snapshots / delete_snapshot (FEAT-03) on PVE 8 and PVE 9 fixtures."""

import json

import pytest
from fastmcp.exceptions import ToolError

from tests.helpers import tool_text

ARGS = {"node": "pve1", "vmid": "100"}
LISTING = [
    {"name": "current", "description": "You are here!"},
    {
        "name": "snap-b",
        "description": "second",
        "snaptime": 1700000100,
        "vmstate": 1,
        "parent": "snap-a",
    },
    {"name": "currently-x", "description": "keep me"},
    {"name": "snap-a", "description": "first", "snaptime": 1700000000},
]
SNAP_ROUTE = "nodes/*/qemu/*/snapshot"


@pytest.fixture
def app(policy_app):
    return policy_app(allow_destructive=True)


@pytest.mark.asyncio
async def test_list_filters_current_exactly_and_sorts(app, fake_pve):
    fake_pve.set("GET", SNAP_ROUTE, LISTING)
    data = json.loads(tool_text(await app.mcp.call_tool("list_snapshots", ARGS)))
    assert [s["name"] for s in data["snapshots"]] == ["currently-x", "snap-a", "snap-b"]
    assert data["count"] == 3
    b = data["snapshots"][2]
    assert b["snaptime_utc"] == "2023-11-14T22:15:00Z" and b["vmstate"] is True
    assert b["parent"] == "snap-a"
    assert data["snapshots"][0]["snaptime_utc"] is None
    assert fake_pve.mutating_calls() == []


@pytest.mark.asyncio
async def test_list_fixture_and_empty(app, fake_pve):
    data = json.loads(tool_text(await app.mcp.call_tool("list_snapshots", ARGS)))
    assert [s["name"] for s in data["snapshots"]] == ["snap1"]
    fake_pve.set("GET", SNAP_ROUTE, [{"name": "current"}])
    data = json.loads(tool_text(await app.mcp.call_tool("list_snapshots", ARGS)))
    assert data["snapshots"] == [] and data["count"] == 0


@pytest.mark.asyncio
async def test_list_redacts_description(app, fake_pve):
    fake_pve.set("GET", SNAP_ROUTE, [{"name": "s1", "description": "x" * 500}])
    data = json.loads(tool_text(await app.mcp.call_tool("list_snapshots", ARGS)))
    assert len(data["snapshots"][0]["description"]) == 300


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"confirm": False}])
async def test_delete_without_confirm_is_static_preview(app, fake_pve, extra):
    fake_pve.reset_calls()
    out = json.loads(
        tool_text(await app.mcp.call_tool("delete_snapshot", {**ARGS, "name": "snap1", **extra}))
    )
    assert out["preview"] is True and out["executed"] is False
    assert out["tool"] == "delete_snapshot"
    assert out["target"] == {"node": "pve1", "vmid": "100", "name": "snap1"}
    assert fake_pve.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["current", "bad name", "../x", ""])
@pytest.mark.parametrize("confirm", [True, False])
async def test_delete_rejects_bad_names_before_any_call(app, fake_pve, name, confirm):
    fake_pve.reset_calls()
    with pytest.raises(ToolError):
        await app.mcp.call_tool("delete_snapshot", {**ARGS, "name": name, "confirm": confirm})
    assert fake_pve.calls == []


@pytest.mark.asyncio
async def test_delete_confirm_returns_upid(app, fake_pve):
    text = tool_text(
        await app.mcp.call_tool("delete_snapshot", {**ARGS, "name": "snap1", "confirm": True})
    )
    assert "Snapshot 'snap1' deletion initiated for VM 100 on node pve1" in text
    assert "Task ID: UPID:pve1:" in text
    assert [(c.method, c.path) for c in fake_pve.mutating_calls()] == [
        ("DELETE", "nodes/pve1/qemu/100/snapshot/snap1")
    ]


@pytest.mark.asyncio
async def test_delete_unknown_or_current_substring_name_issues_no_delete(app, fake_pve):
    fake_pve.set("GET", SNAP_ROUTE, [{"name": "currently-x", "snaptime": 1}])
    with pytest.raises(ToolError, match="Snapshot 'snap9' not found on VM 100"):
        await app.mcp.call_tool("delete_snapshot", {**ARGS, "name": "snap9", "confirm": True})
    assert fake_pve.mutating_calls() == []
    text = tool_text(
        await app.mcp.call_tool("delete_snapshot", {**ARGS, "name": "currently-x", "confirm": True})
    )
    assert "deletion initiated" in text
    assert len(fake_pve.mutating_calls()) == 1


@pytest.mark.asyncio
async def test_delete_wait_ok_running_failed_null(app, fake_pve):
    args = {**ARGS, "name": "snap1", "confirm": True, "wait": True}
    assert "Task finished: OK" in tool_text(await app.mcp.call_tool("delete_snapshot", args))
    fake_pve.set("GET", "nodes/*/tasks/*/status", {"status": "stopped", "exitstatus": "boom"})
    with pytest.raises(ToolError, match="failed"):
        await app.mcp.call_tool("delete_snapshot", args)
    fake_pve.set(
        "GET", "nodes/*/tasks/*/status", {"status": "stopped", "exitstatus": "WARNINGS: 1"}
    )
    assert "warnings" in tool_text(await app.mcp.call_tool("delete_snapshot", args))
    fake_pve.set("DELETE", "nodes/*/qemu/*/snapshot/*", None)
    assert "Wait skipped" in tool_text(await app.mcp.call_tool("delete_snapshot", args))


@pytest.mark.asyncio
async def test_delete_wait_still_running(app, fake_pve):
    clock = [0.0]

    def sleep(s):
        clock[0] += s

    app.vm_tools._sleep, app.vm_tools._clock = sleep, lambda: clock[0]
    fake_pve.set("GET", "nodes/*/tasks/*/status", {"status": "running"})
    text = tool_text(
        await app.mcp.call_tool(
            "delete_snapshot",
            {**ARGS, "name": "snap1", "confirm": True, "wait": True, "timeout": 2},
        )
    )
    assert "still running" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flags", [{"allow_destructive": False}, {"read_only": True, "allow_destructive": True}]
)
async def test_delete_policy_denied_before_preview(policy_app, fake_pve, flags):
    app = policy_app(**flags)
    fake_pve.reset_calls()
    for confirm in (True, False):
        with pytest.raises(ToolError, match="policy_denied"):
            await app.mcp.call_tool(
                "delete_snapshot", {**ARGS, "name": "snap1", "confirm": confirm}
            )
    assert fake_pve.calls == []


@pytest.mark.asyncio
async def test_list_allowed_under_read_only(policy_app):
    app = policy_app(read_only=True)
    assert tool_text(await app.mcp.call_tool("list_snapshots", ARGS))
