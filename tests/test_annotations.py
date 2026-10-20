"""MCP tool annotations (SEC-04), verified through a live fastmcp list_tools()."""

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastmcp import FastMCP

from proxmox_mcp.app import create_app
from proxmox_mcp.config.loader import load_config
from proxmox_mcp.tools.registry import (
    ANNOTATION_OVERRIDES,
    RISK_CLASSES,
    ToolContext,
    build_registry,
    register_tools,
)
from tests.test_tool_schema_snapshot import EXPECTED_TOOL_COUNT

DIGEST = "0" * 64


def _ctx():
    return ToolContext(
        node_tools=MagicMock(),
        vm_tools=MagicMock(),
        storage_tools=MagicMock(),
        cluster_tools=MagicMock(),
        health_payload=lambda: {"status": "ok"},
    )


async def _by_name(mcp):
    return {t.name: t.annotations for t in await mcp.list_tools()}


@pytest_asyncio.fixture
async def ann():
    mcp = FastMCP("t")
    register_tools(mcp, build_registry(_ctx()))
    return await _by_name(mcp)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_all_tools_annotated_on_both_transports(mock_env_vars, transport):
    config = load_config(None)
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI"):
        kwargs = {"api_key_digests": [DIGEST]} if transport == "http" else {}
        app = create_app(config, transport, **kwargs)
    found = await _by_name(app.mcp)
    assert len(found) == EXPECTED_TOOL_COUNT
    assert all(a is not None for a in found.values())


@pytest.mark.asyncio
async def test_read_tools(ann):
    for name in RISK_CLASSES["read"]:
        a = ann[name]
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint) == (
            True,
            False,
            True,
            False,
        )


@pytest.mark.asyncio
async def test_write_tools(ann):
    for name in ("create_vm", "start_vm", "shutdown_vm", "create_snapshot", "update_vm"):
        assert ann[name].read_only_hint is False
        assert ann[name].destructive_hint is (name == "update_vm")
    assert ann["start_vm"].idempotent_hint is True
    assert ann["shutdown_vm"].idempotent_hint is True
    assert ann["create_vm"].idempotent_hint is False
    assert ann["create_snapshot"].idempotent_hint is False


@pytest.mark.asyncio
async def test_destructive_and_exec_tools(ann):
    for name in (*RISK_CLASSES["destructive"], "execute_vm_command"):
        a = ann[name]
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint) == (False, True, False)
    assert ann["execute_vm_command"].open_world_hint is True
    assert ann["stop_vm"].open_world_hint is False


@pytest.mark.asyncio
async def test_table_consistency(ann):
    all_tools = {n for names in RISK_CLASSES.values() for n in names}
    assert set(ann) == all_tools
    assert set(ANNOTATION_OVERRIDES) <= all_tools
    for risk in ("write", "destructive", "exec"):
        for name in RISK_CLASSES[risk]:
            assert ann[name].read_only_hint is False
    for name in RISK_CLASSES["destructive"] + RISK_CLASSES["exec"]:
        assert ann[name].destructive_hint is True


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["get_task_status", "wait_for_task"])
async def test_task_tools_are_literally_read_only(ann, name):
    a = ann[name]
    assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint) == (
        True,
        False,
        True,
        False,
    )


@pytest.mark.asyncio
async def test_snapshot_tool_annotations(ann):
    assert ann["list_snapshots"].read_only_hint is True
    assert ann["list_snapshots"].destructive_hint is False
    assert ann["delete_snapshot"].read_only_hint is False
    assert ann["delete_snapshot"].destructive_hint is True


@pytest.mark.asyncio
async def test_list_backups_annotations(ann):
    assert ann["list_backups"].read_only_hint is True
    assert ann["list_backups"].destructive_hint is False


@pytest.mark.asyncio
async def test_container_tool_annotations(ann):
    for name in ("start_container", "shutdown_container"):
        assert ann[name].read_only_hint is False and ann[name].destructive_hint is False
        assert ann[name].idempotent_hint is True
    assert ann["stop_container"].destructive_hint is True
    assert ann["stop_container"].read_only_hint is False


@pytest.mark.asyncio
async def test_get_ha_status_annotations(ann):
    assert ann["get_ha_status"].read_only_hint is True
    assert ann["get_ha_status"].destructive_hint is False
