"""Tool registry: parity with the golden contract and Phase 4 hooks."""
import functools
import json
from unittest.mock import MagicMock

import pytest
from fastmcp import FastMCP

from proxmox_mcp.tools.registry import ToolContext, ToolSpec, build_registry, register_tools
from tests.test_tool_schema_snapshot import EXPECTED_TOOL_COUNT, GOLDEN_PATH, normalize_tool

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _ctx():
    return ToolContext(
        node_tools=MagicMock(),
        vm_tools=MagicMock(),
        storage_tools=MagicMock(),
        cluster_tools=MagicMock(),
        health_payload=lambda: {"status": "ok"},
    )


async def _snapshot(mcp):
    return sorted((normalize_tool(t) for t in await mcp.list_tools()), key=lambda t: t["name"])


def test_registry_names_match_golden():
    specs = build_registry(_ctx())
    assert len(specs) == EXPECTED_TOOL_COUNT
    assert sorted(s.name for s in specs) == [t["name"] for t in GOLDEN]


def test_spec_fields():
    for spec in build_registry(_ctx()):
        assert isinstance(spec.name, str) and callable(spec.handler)
        assert spec.description
        assert set(spec.annotations) == {
            "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint",
        }
        assert spec.risk in {"read", "write", "destructive", "exec"}
        assert spec.tags == frozenset()


def test_risk_classes_cover_every_tool_once():
    from proxmox_mcp.tools.registry import RISK_CLASSES

    assigned = [n for names in RISK_CLASSES.values() for n in names]
    assert sorted(assigned) == sorted(t["name"] for t in GOLDEN)
    assert len(assigned) == len(set(assigned))
    risks = {s.name: s.risk for s in build_registry(_ctx())}
    assert risks["delete_vm"] == "destructive" and risks["execute_vm_command"] == "exec"
    assert risks["update_vm"] == "destructive" and risks["health"] == "read"


@pytest.mark.asyncio
async def test_register_matches_golden():
    mcp = FastMCP("t")
    register_tools(mcp, build_registry(_ctx()))
    assert await _snapshot(mcp) == GOLDEN


@pytest.mark.asyncio
async def test_identity_and_wraps_keep_schema():
    mcp = FastMCP("t")
    register_tools(mcp, build_registry(_ctx()), wrap=lambda spec, h: h)
    assert await _snapshot(mcp) == GOLDEN

    def wrap(spec, handler):
        @functools.wraps(handler)
        def inner(*a, **kw):
            return handler(*a, **kw)

        return inner

    mcp2 = FastMCP("t2")
    register_tools(mcp2, build_registry(_ctx()), wrap=wrap)
    assert await _snapshot(mcp2) == GOLDEN


@pytest.mark.asyncio
async def test_annotations_passed_through():
    specs = build_registry(_ctx())
    specs = [
        ToolSpec(s.name, s.handler, s.description, {"readOnlyHint": True}, s.risk)
        if s.name == "get_nodes"
        else s
        for s in specs
    ]
    mcp = FastMCP("t")
    register_tools(mcp, specs)
    tool = next(t for t in await mcp.list_tools() if t.name == "get_nodes")
    assert tool.annotations.read_only_hint is True


def test_duplicate_names_rejected():
    specs = build_registry(_ctx())
    with pytest.raises(ValueError):
        register_tools(FastMCP("t"), specs + [specs[0]])


@pytest.mark.asyncio
async def test_get_containers_and_health_outputs():
    ctx = _ctx()
    ctx.cluster_tools.list_containers.return_value = [{"vmid": 1}]
    mcp = FastMCP("t")
    register_tools(mcp, build_registry(ctx))
    res = await mcp.call_tool("get_containers", {})
    assert json.loads(res.content[0].text) == [{"vmid": 1}]
    res = await mcp.call_tool("health", {})
    assert json.loads(res.content[0].text) == {"status": "ok"}


@pytest.mark.parametrize("risk", ["", "READ", "unclassified"])
def test_toolspec_requires_known_risk(risk):
    """A ToolSpec without an explicit known risk class can not be built (fail closed)."""
    with pytest.raises(ValueError, match="explicit risk class"):
        ToolSpec("x", lambda: None, "d", None, risk)
    with pytest.raises(ValueError, match="explicit risk class"):
        ToolSpec("x", lambda: None, "d")


def test_destructive_annotation_matches_gate():
    """A tool annotated destructive is also gated as destructive (or exec)."""
    for spec in build_registry(_ctx()):
        if spec.annotations.get("destructiveHint"):
            assert spec.risk in ("destructive", "exec"), spec.name


@pytest.mark.parametrize("name", ["get_task_status", "wait_for_task"])
def test_task_tools_are_literally_read_risk(name):
    spec = next(s for s in build_registry(_ctx()) if s.name == name)
    assert spec.risk == "read"
    assert spec.annotations["readOnlyHint"] is True


def test_snapshot_tools_literal_risk():
    specs = {s.name: s for s in build_registry(_ctx())}
    assert specs["list_snapshots"].risk == "read"
    assert specs["list_snapshots"].annotations["readOnlyHint"] is True
    assert specs["delete_snapshot"].risk == "destructive"
    assert specs["delete_snapshot"].annotations["readOnlyHint"] is False
    assert specs["delete_snapshot"].annotations["destructiveHint"] is True


def test_list_backups_literally_read_risk():
    spec = next(s for s in build_registry(_ctx()) if s.name == "list_backups")
    assert spec.risk == "read" and spec.annotations["readOnlyHint"] is True


def test_container_tools_literal_risk():
    specs = {s.name: s for s in build_registry(_ctx())}
    for name in ("start_container", "shutdown_container"):
        assert specs[name].risk == "write"
        assert specs[name].annotations["idempotentHint"] is True
        assert specs[name].annotations["destructiveHint"] is False
    assert specs["stop_container"].risk == "destructive"
    assert specs["stop_container"].annotations["destructiveHint"] is True


def test_get_ha_status_literally_read_risk():
    spec = next(s for s in build_registry(_ctx()) if s.name == "get_ha_status")
    assert spec.risk == "read" and spec.annotations["readOnlyHint"] is True
