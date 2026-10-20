"""Independent literal expectations for the final Phase 5 surface (27 tools)."""

import json

import pytest
from fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from tests.helpers import tool_text
from tests.test_harness import SMOKE_ARGS, SMOKE_ARGS_CONFIRMED
from tests.test_tool_schema_snapshot import (
    PHASE5_NEW_TOOLS,
    PHASE5_PARAM_ADDITIONS,
    build_snapshot,
)

NEW_TOOLS = (
    "get_task_status",
    "wait_for_task",
    "list_snapshots",
    "delete_snapshot",
    "list_backups",
    "start_container",
    "stop_container",
    "shutdown_container",
    "get_ha_status",
)
# tool -> (risk class, readOnlyHint, destructiveHint, idempotentHint); stated independently of
# RISK_CLASSES and ToolPolicy.
EXPECTED = {
    "get_task_status": ("read", True, False, True),
    "wait_for_task": ("read", True, False, True),
    "list_snapshots": ("read", True, False, True),
    "list_backups": ("read", True, False, True),
    "get_ha_status": ("read", True, False, True),
    "start_container": ("write", False, False, True),
    "shutdown_container": ("write", False, False, True),
    "delete_snapshot": ("destructive", False, True, False),
    "stop_container": ("destructive", False, True, False),
}
KEY_API = "test-api-key"


def test_delta_cardinality_is_nine_tools_fourteen_params():
    assert set(PHASE5_NEW_TOOLS) == set(NEW_TOOLS) and len(PHASE5_NEW_TOOLS) == 9
    assert sum(len(v) for v in PHASE5_PARAM_ADDITIONS.values()) == 14


@pytest.mark.asyncio
async def test_literal_tool_count_and_names(policy_app):
    app = policy_app()
    names = {t.name for t in await app.mcp.list_tools()}
    assert len(names) == 27
    assert set(NEW_TOOLS) <= names


@pytest.mark.asyncio
async def test_risk_and_annotation_table(policy_app):
    app = policy_app()
    tools = {t.name: t for t in await app.mcp.list_tools()}
    specs = {s.name: s for s in app.specs}
    for name, (risk, read_only, destructive, idempotent) in EXPECTED.items():
        assert specs[name].risk == risk, name
        ann = tools[name].annotations
        assert (ann.read_only_hint, ann.destructive_hint, ann.idempotent_hint) == (
            read_only,
            destructive,
            idempotent,
        ), name


@pytest.mark.asyncio
async def test_stdio_and_http_expose_identical_surface(policy_app):
    stdio = await build_snapshot(policy_app("stdio"))
    http = await build_snapshot(policy_app("http"))
    assert stdio == http and len(stdio) == 27


@pytest.mark.asyncio
async def test_default_policy_denies_destructive_new_tools_without_calls(policy_app, fake_pve):
    app = policy_app()
    for name, (risk, *_rest) in EXPECTED.items():
        if risk != "destructive":
            continue
        fake_pve.reset_calls()
        for confirm in (True, False):
            with pytest.raises(ToolError, match="policy_denied"):
                await app.mcp.call_tool(name, {**SMOKE_ARGS[name], "confirm": confirm})
        assert fake_pve.calls == [], name


@pytest.mark.asyncio
async def test_read_only_denies_every_non_read_new_tool_without_calls(policy_app, fake_pve):
    app = policy_app(read_only=True, allow_destructive=True)
    for name, (risk, *_rest) in EXPECTED.items():
        fake_pve.reset_calls()
        if risk == "read":
            await app.mcp.call_tool(name, SMOKE_ARGS_CONFIRMED[name])
            continue
        with pytest.raises(ToolError, match="policy_denied"):
            await app.mcp.call_tool(name, SMOKE_ARGS_CONFIRMED[name])
        assert fake_pve.calls == [], name


def _major(fake_pve):
    return int(fake_pve.version.get()["release"].split(".")[0])


@pytest.mark.asyncio
async def test_health_pve_null_then_populated_after_first_new_tool_call(policy_app, fake_pve):
    app = policy_app()
    major = _major(fake_pve)
    assert major in (8, 9)
    health = json.loads(tool_text(await app.mcp.call_tool("health", {})))
    assert health["pve"] is None and app.health_payload()["pve"] is None
    await app.mcp.call_tool("get_ha_status", {})
    expected = fake_pve.version.get()
    for payload in (
        json.loads(tool_text(await app.mcp.call_tool("health", {}))),
        app.health_payload(),
    ):
        assert payload["pve"] == {
            "version": expected["version"],
            "release": expected["release"],
            "major": major,
        }


def test_http_health_route_reports_pve_after_first_call(policy_app, fake_pve):
    import asyncio

    app = policy_app("http")
    headers = {"X-API-Key": KEY_API}
    with TestClient(app.asgi) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/health", headers=headers).json()["pve"] is None
        asyncio.run(app.mcp.call_tool("get_ha_status", {}))
        body = client.get("/health", headers=headers).json()
    expected = fake_pve.version.get()
    assert body["pve"] == {
        "version": expected["version"],
        "release": expected["release"],
        "major": int(expected["release"].split(".")[0]),
    }
