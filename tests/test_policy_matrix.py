"""Tool policy (SEC-01): engine, wrapper and zero-traffic denial."""
import inspect
import itertools
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.exceptions import ToolError
from proxmoxer.core import ResourceException
from starlette.testclient import TestClient

from proxmox_mcp.config.models import PolicyConfig
from proxmox_mcp.policy import PolicyDeniedError, ToolPolicy, compose_wraps, make_policy_wrap
from proxmox_mcp.tools.registry import RISK_CLASSES
from tests.test_harness import SMOKE_ARGS, SMOKE_ARGS_CONFIRMED


def _spec(risk, name="some_tool"):
    return SimpleNamespace(risk=risk, name=name)


def test_default_policy_denies_destructive_and_exec():
    p = ToolPolicy(PolicyConfig())
    assert p.check(_spec("read")) is None
    assert p.check(_spec("write")) is None
    assert p.check(_spec("destructive")).flag == "allow_destructive"
    assert p.check(_spec("exec")).flag == "allow_exec"


def test_read_only_overrides_allow_flags():
    p = ToolPolicy(PolicyConfig(read_only=True, allow_destructive=True, allow_exec=True))
    assert p.check(_spec("read")) is None
    for risk in ("write", "destructive", "exec"):
        assert p.check(_spec(risk)).flag == "read_only"


def test_wrapper_preserves_signature_and_asyncness():
    wrap = make_policy_wrap(ToolPolicy(PolicyConfig()))

    def sync_tool(node: str, vmid: int = 1):
        return "ok"

    async def async_tool(node: str):
        return "ok"

    ws = wrap(_spec("read"), sync_tool)
    wa = wrap(_spec("read"), async_tool)
    assert inspect.signature(ws) == inspect.signature(sync_tool)
    assert inspect.signature(wa) == inspect.signature(async_tool)
    assert not inspect.iscoroutinefunction(ws)
    assert inspect.iscoroutinefunction(wa)
    assert ws("n") == "ok"


def test_denied_message_is_actionable():
    wrap = make_policy_wrap(ToolPolicy(PolicyConfig()))
    w = wrap(_spec("exec", "execute_vm_command"), lambda: "never")
    with pytest.raises(PolicyDeniedError) as ei:
        w()
    assert isinstance(ei.value, ToolError)
    msg = str(ei.value)
    assert msg.startswith("policy_denied:")
    for needle in (
        "execute_vm_command", "exec", "policy.allow_exec", "PROXMOX_MCP_ALLOW_EXEC",
        "--allow-exec", "No request was sent to Proxmox.",
    ):
        assert needle in msg


def test_compose_puts_policy_outermost():
    order = []

    def mk(tag):
        def wrap(spec, handler):
            def inner():
                order.append(tag)
                return handler()
            return inner
        return wrap

    composed = compose_wraps(mk("policy"), None, mk("user"))
    composed(_spec("read"), lambda: order.append("handler"))()
    assert order == ["policy", "user", "handler"]


@pytest.mark.asyncio
async def test_denied_call_makes_no_proxmox_calls(policy_app, fake_pve):
    app = policy_app()
    for name in ("delete_vm", "execute_vm_command"):
        with pytest.raises(ToolError, match="policy_denied"):
            await app.mcp.call_tool(name, SMOKE_ARGS[name])
    policy_app.api_ctor.assert_not_called()
    assert fake_pve.calls == []


COMBOS = list(itertools.product([False, True], repeat=3))  # read_only, destructive, exec
RISK_OF = {n: r for r, names in RISK_CLASSES.items() for n in names}


def expected_allowed(risk, read_only, allow_destructive, allow_exec):
    """Independent oracle: literal boolean logic, no ToolPolicy."""
    if risk == "read":
        return True
    if risk == "write":
        return not read_only
    if risk == "destructive":
        return (not read_only) and allow_destructive
    if risk == "exec":
        return (not read_only) and allow_exec
    raise AssertionError(risk)


def _blocking_flag(risk, read_only, allow_destructive, allow_exec):
    if read_only:
        return "read_only"
    return "allow_destructive" if risk == "destructive" else "allow_exec"


@pytest.mark.asyncio
@pytest.mark.parametrize("combo", COMBOS, ids=lambda c: "ro%d-d%d-x%d" % tuple(map(int, c)))
@pytest.mark.parametrize("name", sorted(SMOKE_ARGS))
async def test_policy_matrix(policy_app, fake_pve, name, combo):
    read_only, allow_destructive, allow_exec = combo
    risk = RISK_OF[name]
    app = policy_app(
        read_only=read_only, allow_destructive=allow_destructive, allow_exec=allow_exec
    )
    if name == "create_vm":
        fake_pve.fail(
            "GET", "nodes/*/qemu/200/config",
            ResourceException(500, "Internal Server Error", "Configuration file does not exist"),
        )
    fake_pve.reset_calls()
    allowed = expected_allowed(risk, *combo)
    with patch("asyncio.sleep", new=AsyncMock()):
        if allowed:
            try:
                await app.mcp.call_tool(name, SMOKE_ARGS_CONFIRMED[name])
            except Exception as exc:  # business refusals are fine, policy denials are not
                assert "policy_denied" not in str(exc)
            if name != "health":
                assert fake_pve.calls, f"{name} allowed but made no Proxmox call"
        else:
            with pytest.raises(ToolError) as ei:
                await app.mcp.call_tool(name, SMOKE_ARGS[name])
            assert "policy_denied" in str(ei.value)
            assert _blocking_flag(risk, *combo) in str(ei.value)
            assert fake_pve.calls == []
            policy_app.api_ctor.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("combo", COMBOS)
async def test_tool_list_identical_under_every_combination(policy_app, combo):
    app = policy_app(read_only=combo[0], allow_destructive=combo[1], allow_exec=combo[2])
    names = sorted(t.name for t in await app.mcp.list_tools())
    assert names == sorted(SMOKE_ARGS)
    assert len(names) == 18


@pytest.mark.asyncio
async def test_defaults_and_read_only_focus(policy_app, fake_pve):
    app = policy_app()
    for name in ("delete_vm", "execute_vm_command"):
        with pytest.raises(ToolError, match="policy_denied"):
            await app.mcp.call_tool(name, SMOKE_ARGS[name])
    await app.mcp.call_tool("start_vm", SMOKE_ARGS["start_vm"])
    assert fake_pve.calls

    locked = policy_app(read_only=True, allow_destructive=True, allow_exec=True)
    fake_pve.reset_calls()
    with pytest.raises(ToolError, match="policy_denied.*read.only"):
        await locked.mcp.call_tool("start_vm", SMOKE_ARGS["start_vm"])
    assert fake_pve.calls == []


@pytest.mark.asyncio
async def test_denial_log_never_contains_arguments(policy_app, caplog):
    app = policy_app()
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ToolError) as ei:
            await app.mcp.call_tool("execute_vm_command", {
                "node": "pve1", "vmid": "100", "command": "SENTINEL-do-not-log",
            })
    assert "SENTINEL-do-not-log" not in caplog.text
    assert "SENTINEL-do-not-log" not in str(ei.value)
    assert "policy denied tool=execute_vm_command" in caplog.text


def test_health_shows_policy_summary_over_http(policy_app):
    app = policy_app("http", allow_exec=True)
    with TestClient(app.asgi) as c:
        body = c.get("/health", headers={"X-API-Key": "test-api-key"}).json()
    assert body["policy"] == {"read_only": False, "allow_destructive": False, "allow_exec": True}
