"""Tool policy (SEC-01): engine, wrapper and zero-traffic denial."""
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from proxmox_mcp.app import create_app
from proxmox_mcp.config.loader import load_config
from proxmox_mcp.config.models import PolicyConfig
from proxmox_mcp.policy import PolicyDeniedError, ToolPolicy, compose_wraps, make_policy_wrap
from tests.test_harness import SMOKE_ARGS


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
async def test_denied_call_makes_no_proxmox_calls(mock_env_vars, fake_pve):
    config = load_config(None, cli_overrides={
        "policy": {"allow_destructive": "false", "allow_exec": "false"},
    })
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI", return_value=fake_pve) as ctor:
        app = create_app(config, "stdio")
        for name in ("delete_vm", "execute_vm_command"):
            with pytest.raises(ToolError, match="policy_denied"):
                await app.mcp.call_tool(name, SMOKE_ARGS[name])
        ctor.assert_not_called()
    assert fake_pve.calls == []
