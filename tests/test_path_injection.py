"""Golden-driven path/property-injection matrix (CONF-02).

Every tool in ``tests/golden/tools.json`` that takes a node/vmid/storage/snapshot/
VM-name style parameter must reject bad values before any proxmoxer call.
"""

import json
from pathlib import Path

import pytest
from fastmcp.exceptions import ToolError, ValidationError

GOLDEN = json.loads((Path(__file__).parent / "golden" / "tools.json").read_text())

# Known-good values per identifier-bearing parameter name.
GOOD = {
    "node": "node1",
    "vmid": "100",
    "name": "vm-1",
    "storage": "local-lvm",
    "iso_storage": "local",
    "iso_name": "debian.iso",
    "ostype": "l26",
    "upid": "UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:monitor@pve!mcp:",
}
# Tool-specific override for the generic "name" parameter (snapshot tools).
GOOD_BY_TOOL = {
    ("create_snapshot", "name"): "snap1",
    ("rollback_snapshot", "name"): "snap1",
    ("delete_snapshot", "name"): "snap1",
}
# Required non-identifier params with valid values.
OTHER = {"cpus": 2, "memory": 2048, "disk_size": 10, "command": "uname -a"}

BAD = ["../x", "a b", "a,b", "a/b", "x\n", ""]
BAD_VMID = BAD + ["99", "1000000000", "100/status"]
EXTRA_BAD = {
    ("create_vm", "iso_name"): ["x,media=disk"],
    ("create_vm", "ostype"): ["l26,x=1"],
    ("create_snapshot", "name"): ["current"],
    ("rollback_snapshot", "name"): ["current"],
    ("delete_snapshot", "name"): ["current"],
}

# Bad task ids (UPID); the generic BAD list does not exercise the UPID grammar.
BAD_UPID = [
    "../x",
    "a b",
    "x\n",
    "",
    "UPID:",
    "upid:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:u:",
    "UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:monitor@pve!mcp",  # no trailing colon
    "UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:../../x:",
    "UPID:../x:0000ABCD:00123456:65A1B2C3:qmstart:100:root@pam:",
    "UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:a b:",
    "UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:" + "1" * 600 + ":root@pam:",
]

# Tools without identifier parameters: explicitly exempt.
NO_INPUT_TOOLS = {
    "get_nodes",
    "get_vms",
    "get_containers",
    "get_storage",
    "get_cluster_status",
    "health",
    "get_ha_status",
}
IDENT_HINTS = ("node", "vmid", "storage", "snapshot", "name", "iso", "ostype", "upid")


def _good(tool, pname):
    return GOOD_BY_TOOL.get((tool, pname), GOOD.get(pname))


def _cases():
    for entry in GOLDEN:
        tool = entry["name"]
        for p in entry["params"]:
            pname = p["name"]
            if pname not in GOOD:
                continue
            base = BAD_UPID if pname == "upid" else (BAD_VMID if pname == "vmid" else BAD)
            bads = base + EXTRA_BAD.get((tool, pname), [])
            for bad in bads:
                yield tool, pname, bad


def _args(entry, tool, target, bad):
    args = {}
    for p in entry["params"]:
        pname = p["name"]
        if pname == target:
            args[pname] = bad
        elif pname in GOOD and (p["required"] or pname == target):
            args[pname] = _good(tool, pname)
        elif pname in OTHER and p["required"]:
            args[pname] = OTHER[pname]
    return args


def test_matrix_covers_every_golden_tool():
    """Fail if a golden tool has an identifier-style param the matrix cannot exercise."""
    for entry in GOLDEN:
        tool = entry["name"]
        if tool in NO_INPUT_TOOLS:
            assert entry["params"] == [], f"{tool} is exempt but takes parameters"
            continue
        for p in entry["params"]:
            pname = p["name"]
            if any(h in pname for h in IDENT_HINTS):
                assert pname in GOOD, f"{tool}.{pname} is not covered by the injection matrix"
            else:
                assert pname in OTHER or pname in {
                    "description",
                    "vmstate",
                    "force",
                    "confirm",
                    "args",
                    "wait",
                    "timeout",
                }, f"{tool}.{pname} is unknown to the injection matrix"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,pname,bad", list(_cases()))
async def test_bad_identifier_rejected_before_proxmoxer(server, api, tool, pname, bad):
    entry = next(e for e in GOLDEN if e["name"] == tool)
    args = _args(entry, tool, pname, bad)
    api.nodes.reset_mock()
    with pytest.raises((ToolError, ValidationError)):
        await server.mcp.call_tool(tool, args)
    assert api.nodes.called is False, f"{tool}({pname}={bad!r}) reached proxmoxer"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"cpus": 0},
        {"memory": 1},
        {"name": "a b"},
        {"name": "../x"},
    ],
)
async def test_update_vm_bad_values_rejected(server, api, kwargs):
    api.nodes.reset_mock()
    with pytest.raises((ToolError, ValidationError)):
        await server.mcp.call_tool("update_vm", {"node": "node1", "vmid": "100", **kwargs})
    assert api.nodes.called is False


@pytest.mark.asyncio
async def test_create_snapshot_bad_description_rejected(server, api):
    api.nodes.reset_mock()
    with pytest.raises((ToolError, ValidationError)):
        await server.mcp.call_tool(
            "create_snapshot",
            {"node": "node1", "vmid": "100", "name": "s1", "description": "x\x00y"},
        )
    assert api.nodes.called is False


@pytest.mark.asyncio
async def test_positive_controls_reach_proxmoxer(server, api):
    """Valid input still reaches the mock (validators do not reject everything)."""
    api.nodes.reset_mock()
    try:
        await server.mcp.call_tool("get_node_status", {"node": "node1"})
    except Exception:  # noqa: S110  # mock payload may not format; reaching proxmoxer is what matters
        pass
    assert api.nodes.called is True

    api.nodes.reset_mock()
    api.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "stopped",
        "name": "web01",
    }
    await server.mcp.call_tool("start_vm", {"node": "node1", "vmid": "100"})
    assert api.nodes.called is True

    api.nodes.reset_mock()
    await server.mcp.call_tool("create_snapshot", {"node": "node1", "vmid": "100", "name": "s1"})
    assert api.nodes.called is True
