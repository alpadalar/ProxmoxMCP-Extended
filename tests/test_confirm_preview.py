"""SEC-02: destructive tools return a preview unless confirm=true."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError, ValidationError

from proxmox_mcp.tools.registry import ToolContext, build_registry
from tests.helpers import tool_text
from tests.test_harness import CONFIRM_TOOLS, SMOKE_ARGS


def _preview(text):
    return json.loads(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CONFIRM_TOOLS)
@pytest.mark.parametrize("extra", [{}, {"confirm": False}])
async def test_without_confirm_returns_preview_and_no_calls(policy_app, fake_pve, name, extra):
    app = policy_app(allow_destructive=True)
    fake_pve.reset_calls()
    out = _preview(tool_text(await app.mcp.call_tool(name, {**SMOKE_ARGS[name], **extra})))
    assert out["preview"] is True and out["executed"] is False
    assert out["tool"] == name
    assert out["target"]["node"] == "pve1" and out["target"]["vmid"] == SMOKE_ARGS[name]["vmid"]
    assert out["effects"] and "confirm=true" in out["how_to_confirm"]
    assert fake_pve.calls == []
    policy_app.api_ctor.assert_not_called()


@pytest.mark.asyncio
async def test_preview_target_fields(policy_app):
    app = policy_app(allow_destructive=True)
    snap = _preview(
        tool_text(await app.mcp.call_tool("rollback_snapshot", SMOKE_ARGS["rollback_snapshot"]))
    )
    assert snap["target"]["name"] == "snap1"
    assert snap["target"]["node"] == "pve1" and snap["target"]["vmid"]
    assert "allow_destructive" in snap["note"] and "not an authorization" in snap["note"]
    d = _preview(tool_text(await app.mcp.call_tool("delete_vm", SMOKE_ARGS["delete_vm"])))
    assert d["target"]["force"] is False
    assert not any("stopped first" in e for e in d["effects"])
    df = _preview(
        tool_text(await app.mcp.call_tool("delete_vm", {**SMOKE_ARGS["delete_vm"], "force": True}))
    )
    assert df["target"]["force"] is True
    assert any("stopped first" in e for e in df["effects"])


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CONFIRM_TOOLS)
async def test_confirm_true_executes(policy_app, fake_pve, name):
    app = policy_app(allow_destructive=True)
    fake_pve.reset_calls()
    with patch("asyncio.sleep", new=AsyncMock()):
        try:
            out = tool_text(await app.mcp.call_tool(name, {**SMOKE_ARGS[name], "confirm": True}))
        except ToolError:
            out = ""  # business refusals are fine as long as the operation was attempted
    assert '"preview"' not in out
    assert fake_pve.calls


@pytest.mark.asyncio
async def test_invalid_input_rejected_even_in_preview(policy_app, fake_pve):
    app = policy_app(allow_destructive=True)
    fake_pve.reset_calls()
    bad = [
        ("delete_vm", {"node": "../x", "vmid": "101"}),
        ("stop_vm", {"node": "pve1", "vmid": "abc"}),
        ("reset_vm", {"node": "a b", "vmid": "100"}),
        ("rollback_snapshot", {"node": "pve1", "vmid": "100", "name": "bad name"}),
        ("rollback_snapshot", {"node": "pve1", "vmid": "100", "name": "../x"}),
        ("stop_container", {"vmid": "200", "node": ""}),
        ("stop_container", {"vmid": "200", "node": "../x"}),
        ("stop_container", {"vmid": "x/y"}),
    ]
    for name, args in bad:
        with pytest.raises(ToolError):
            await app.mcp.call_tool(name, args)
    assert fake_pve.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CONFIRM_TOOLS)
@pytest.mark.parametrize("confirm", [True, False])
@pytest.mark.parametrize(
    "flags", [{"allow_destructive": False}, {"read_only": True, "allow_destructive": True}]
)
async def test_policy_denial_wins_over_preview(policy_app, fake_pve, name, confirm, flags):
    app = policy_app(**flags)
    fake_pve.reset_calls()
    args = {**SMOKE_ARGS[name], "confirm": confirm}
    with pytest.raises(ToolError, match="policy_denied"):
        await app.mcp.call_tool(name, args)
    assert fake_pve.calls == []
    with pytest.raises(ToolError, match="policy_denied"):
        await app.mcp.call_tool(name, SMOKE_ARGS[name])


@pytest.mark.asyncio
async def test_string_confirm_follows_pydantic_bool_coercion(policy_app, fake_pve):
    """fastmcp validates bool params with pydantic: "true" is coerced to True, junk rejected.

    A falsy or absent value never skips the preview.
    """
    app = policy_app(allow_destructive=True)
    fake_pve.reset_calls()
    for falsy in ("false", "0", "no"):
        out = _preview(
            tool_text(
                await app.mcp.call_tool("stop_vm", {**SMOKE_ARGS["stop_vm"], "confirm": falsy})
            )
        )
        assert out["preview"] is True
    with pytest.raises((ToolError, ValidationError)):
        await app.mcp.call_tool("stop_vm", {**SMOKE_ARGS["stop_vm"], "confirm": "maybe"})
    assert fake_pve.calls == []
    with patch("asyncio.sleep", new=AsyncMock()):
        await app.mcp.call_tool("stop_vm", {**SMOKE_ARGS["stop_vm"], "confirm": "true"})
    assert fake_pve.mutating_calls()


@pytest.mark.asyncio
async def test_http_transport_parity(policy_app, fake_pve):
    app = policy_app("http", allow_destructive=True)
    fake_pve.reset_calls()
    out = _preview(tool_text(await app.mcp.call_tool("delete_vm", SMOKE_ARGS["delete_vm"])))
    assert out["preview"] is True and fake_pve.calls == []
    app = policy_app("http", allow_destructive=False)
    with pytest.raises(ToolError, match="policy_denied"):
        await app.mcp.call_tool("delete_vm", SMOKE_ARGS["delete_vm"])


@pytest.mark.parametrize("name", CONFIRM_TOOLS)
def test_closure_never_forwards_confirm(name):
    ctx = MagicMock()
    spec = next(
        s
        for s in build_registry(
            ToolContext(ctx, ctx.vm_tools, ctx, ctx, dict, container_tools=ctx.container_tools)
        )
        if s.name == name
    )
    args = {k: v for k, v in SMOKE_ARGS[name].items()}
    spec.handler(**args, confirm=True)
    delegate = ctx.container_tools if name.endswith("_container") else ctx.vm_tools
    method = getattr(delegate, name)
    method.assert_called_once()
    # Positional arguments forwarded to the VM tool, never including ``confirm``:
    #   delete_vm:           node, vmid (SMOKE_ARGS) + force, wait, timeout: len(args) + 3
    #   stop/reset/rollback: their SMOKE_ARGS (node, vmid[, name]) + wait, timeout: len(args) + 2
    #   stop_container:      vmid, node (always forwarded, None when omitted), wait, timeout: 4
    expected = 4 if name == "stop_container" else len(args) + (3 if name == "delete_vm" else 2)
    assert len(method.call_args.args) == expected and not method.call_args.kwargs
    assert method.call_args.args[-2:] == (False, 30)  # wait, timeout defaults
    assert True not in method.call_args.args[:-2]  # confirm=True was not forwarded
