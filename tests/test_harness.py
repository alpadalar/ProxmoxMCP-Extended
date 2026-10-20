"""Tests for the FakeProxmox harness itself and an every-tool smoke run through it."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.exceptions import ToolError
from proxmoxer.core import ResourceException

from tests.harness import FakeProxmox, UnmockedCallError, load_fixture
from tests.harness.fake_proxmox import Call
from tests.helpers import tool_text

GOLDEN = Path(__file__).parent / "golden" / "tools.json"


@pytest.fixture
def fake():
    return FakeProxmox(load_fixture("pve8"))


def test_top_level_get(fake):
    assert [n["node"] for n in fake.nodes.get()] == ["pve1", "pve2"]


def test_call_chain_resolves_path(fake):
    status = fake.nodes("pve1").qemu(100).status.current.get()
    assert status["status"] == "running"
    assert fake.calls == [Call("GET", "nodes/pve1/qemu/100/status/current", {})]


def test_agent_exec_call_with_argument(fake):
    assert fake.nodes("pve1").qemu(100).agent("exec").post(command="id") == {"pid": 4242}
    assert fake.calls[0].path == "nodes/pve1/qemu/100/agent/exec"
    assert fake.calls[0].params == {"command": "id"}


def test_exact_route_beats_wildcard():
    f = FakeProxmox({"GET a/*": "wild", "GET a/b": "exact"})
    assert f._dispatch("GET", "a/b", {}) == "exact"
    assert f._dispatch("GET", "a/c", {}) == "wild"


def test_more_literals_win_among_wildcards():
    f = FakeProxmox({"GET a/*/*": "two", "GET a/x/*": "one"})
    assert f._dispatch("GET", "a/x/y", {}) == "one"


def test_callable_route():
    f = FakeProxmox({"GET nodes/*": lambda params, segs: {"seg": segs[1], **params}})
    assert f.nodes("pve1").get(x=1) == {"seg": "pve1", "x": 1}


def test_unmocked_raises_and_records(fake):
    with pytest.raises(UnmockedCallError, match="GET nodes/pve1/nothing"):
        fake.nodes("pve1").nothing.get()
    assert issubclass(UnmockedCallError, AssertionError)
    assert fake.calls[0].path == "nodes/pve1/nothing"


def test_set_override(fake):
    fake.set("POST", "nodes/pve1/qemu/100/status/start", "UPID:custom")
    assert fake.nodes("pve1").qemu(100).status.start.post() == "UPID:custom"


def test_fail_raises_exception(fake):
    fake.fail("DELETE", "nodes/*/qemu/*", ResourceException(500, "Internal Server Error", "boom"))
    with pytest.raises(ResourceException):
        fake.nodes("pve1").qemu(101).delete()
    assert fake.mutating_calls() == [Call("DELETE", "nodes/pve1/qemu/101", {})]


@pytest.mark.parametrize(
    "alias,method", [("create", "POST"), ("set", "PUT"), ("post", "POST"), ("put", "PUT")]
)
def test_method_aliases(alias, method):
    fake = FakeProxmox({f"{method} nodes/*/qemu/*/config": None})
    getattr(fake.nodes("pve1").qemu(100).config, alias)()
    assert fake.calls[-1].method == method


def test_call_bookkeeping(fake):
    fake.assert_no_calls()
    fake.version.get()
    fake.nodes("pve1").qemu(101).status.start.post()
    assert [c.method for c in fake.mutating_calls()] == ["POST"]
    with pytest.raises(AssertionError, match="GET version"):
        fake.assert_no_calls()
    fake.reset_calls()
    fake.assert_no_calls()


def test_private_attribute_not_a_route(fake):
    with pytest.raises(AttributeError):
        fake.nodes._private  # noqa: B018


def test_fixtures_valid_and_differ():
    v8, v9 = load_fixture("pve8"), load_fixture("pve9")
    assert v8["GET version"] != v9["GET version"]
    assert v8["GET version"]["release"].startswith("8.")
    assert v9["GET version"]["release"].startswith("9.")
    assert set(v8) == set(v9)


def test_fixtures_have_no_real_config_reference():
    for name in ("pve8", "pve9"):
        raw = (Path(__file__).parent / "harness" / "data" / f"{name}.json").read_text()
        json.loads(raw)
        assert "config.json" not in raw


# ---- Task 2: pytest fixtures + smoke ----------------------------------------------------

TASK_UPID = "UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:monitor@pve!mcp:"
SMOKE_ARGS = {
    "create_snapshot": {"node": "pve1", "vmid": "100", "name": "snap2"},
    "create_vm": {
        "node": "pve1",
        "vmid": "200",
        "name": "new-vm",
        "cpus": 2,
        "memory": 1024,
        "disk_size": 10,
    },
    "delete_vm": {"node": "pve1", "vmid": "101"},
    "execute_vm_command": {"node": "pve1", "vmid": "100", "command": "echo hello"},
    "get_cluster_status": {},
    "get_containers": {},
    "get_node_status": {"node": "pve1"},
    "get_nodes": {},
    "get_storage": {},
    "get_vm_usage": {"node": "pve1", "vmid": "100"},
    "get_task_status": {"upid": TASK_UPID},
    "get_vms": {},
    "health": {},
    "reset_vm": {"node": "pve1", "vmid": "100"},
    "rollback_snapshot": {"node": "pve1", "vmid": "100", "name": "snap1"},
    "get_ha_status": {},
    "list_backups": {"node": "pve1"},
    "start_container": {"vmid": "200"},
    "stop_container": {"vmid": "200", "node": "pve1"},
    "shutdown_container": {"vmid": "200", "node": "pve1"},
    "list_snapshots": {"node": "pve1", "vmid": "100"},
    "delete_snapshot": {"node": "pve1", "vmid": "100", "name": "snap1"},
    "shutdown_vm": {"node": "pve1", "vmid": "100"},
    "start_vm": {"node": "pve1", "vmid": "101"},
    "stop_vm": {"node": "pve1", "vmid": "100"},
    "update_vm": {"node": "pve1", "vmid": "101", "memory": 2048},
    "wait_for_task": {"upid": TASK_UPID, "timeout": 5},
}


CONFIRM_TOOLS = (
    "delete_vm",
    "stop_vm",
    "reset_vm",
    "rollback_snapshot",
    "delete_snapshot",
    "stop_container",
)
SMOKE_ARGS_CONFIRMED = {
    n: ({**a, "confirm": True} if n in CONFIRM_TOOLS else a) for n, a in SMOKE_ARGS.items()
}


def test_smoke_table_matches_golden():
    golden = {t["name"] for t in json.loads(GOLDEN.read_text())}
    assert set(SMOKE_ARGS) == golden


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(SMOKE_ARGS))
async def test_every_tool_runs_through_fake(fake_pve_server, fake_pve, name):
    if name == "create_vm":
        fake_pve.fail(
            "GET",
            "nodes/*/qemu/200/config",
            ResourceException(500, "Internal Server Error", "Configuration file does not exist"),
        )
    with patch("asyncio.sleep", new=AsyncMock()):
        try:
            result = await fake_pve_server.mcp.call_tool(name, SMOKE_ARGS_CONFIRMED[name])
        except UnmockedCallError:
            raise
        except Exception as exc:  # legitimate business refusals are tolerated
            assert not isinstance(exc.__cause__, UnmockedCallError)
            return
    assert tool_text(result).strip()


@pytest.mark.asyncio
async def test_harness_proves_no_calls(fake_pve_server, fake_pve):
    fake_pve.reset_calls()
    with pytest.raises((ToolError, ValueError)):
        await fake_pve_server.mcp.call_tool("get_node_status", {"node": "../x"})
    assert fake_pve.calls == []


def test_fake_pve_http_server_builds(fake_pve_http_server, fake_pve):
    assert fake_pve_http_server.auth_enabled
