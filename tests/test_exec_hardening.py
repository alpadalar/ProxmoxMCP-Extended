"""SEC-03: execute_vm_command argv, bounded polling, output cap, no logging."""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from proxmox_mcp.tools.console import VMConsoleManager
from proxmox_mcp.tools.vm import VMTools
from tests.helpers import tool_text

MANAGER = "proxmox_mcp.tools.console.manager"


def _status(exited=1, out="", err="", code=0, **extra):
    return {"exited": exited, "exitcode": code, "out-data": out, "err-data": err, **extra}


def _api(*statuses, post_error=None):
    api = MagicMock()
    api.nodes.return_value.qemu.return_value.status.current.get.return_value = {"status": "running"}
    exec_ep, status_ep = MagicMock(), MagicMock()
    if post_error:
        exec_ep.post.side_effect = post_error
    else:
        exec_ep.post.return_value = {"pid": 42}
    status_ep.get.side_effect = list(statuses) if len(statuses) > 1 else None
    if len(statuses) == 1:
        status_ep.get.return_value = statuses[0]
    agent = MagicMock(side_effect=lambda p: exec_ep if p == "exec" else status_ep)
    api.nodes.return_value.qemu.return_value.agent = agent
    return api, exec_ep, status_ep


def _mgr(api, **kw):
    return VMConsoleManager(api, **kw)


@pytest.mark.asyncio
async def test_args_become_argv_list():
    api, ex, _ = _api(_status(out="x"))
    with patch("asyncio.sleep", new=AsyncMock()):
        await _mgr(api).execute_command("n", "100", "ls", ["-l", "/tmp"])
    ex.post.assert_called_once_with(command=["ls", "-l", "/tmp"])


@pytest.mark.asyncio
async def test_command_is_shlex_split_without_args():
    api, ex, _ = _api(_status())
    with patch("asyncio.sleep", new=AsyncMock()):
        await _mgr(api).execute_command("n", "100", "echo hello world")
        await _mgr(api).execute_command("n", "100", "echo 'a b' c")
    assert ex.post.call_args_list[0].kwargs == {"command": ["echo", "hello", "world"]}
    assert ex.post.call_args_list[1].kwargs == {"command": ["echo", "a b", "c"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("command,args", [
    ("echo 'unbalanced SENTINEL-CMD-xyz", None),
    ("", None),
    ("   ", None),
    ("", ["a"]),
    ("ls", ["a"] * 64),  # 65 elements with the program
    ("ls", ["x" * 4097]),
    ("x" * 4097, []),
    ("ls", ["a" * 4000] * 9),  # total over 32768
    ("ls", ["a\x00b"]),
    ("ls", ["ok", 5]),
    ("l\x00s", None),
])
async def test_invalid_argv_rejected_before_any_api_call(command, args):
    api, ex, _ = _api(_status())
    with pytest.raises(ValueError) as ei:
        await _mgr(api).execute_command("n", "100", command, args)
    assert "SENTINEL-CMD-xyz" not in str(ei.value)
    api.nodes.assert_not_called()
    ex.post.assert_not_called()


@pytest.mark.asyncio
async def test_polling_backs_off_until_exit():
    api, _, st = _api(_status(0), _status(0), _status(1, out="done", code=1))
    sleep = AsyncMock()
    with patch("asyncio.sleep", new=sleep):
        result = await _mgr(api).execute_command("n", "100", "ls")
    assert st.get.call_count == 3
    assert [c.args[0] for c in sleep.call_args_list] == [0.5, 1.0, 2.0]
    assert result["output"] == "done" and result["exit_code"] == 1
    assert result["exited"] is True and result["timed_out"] is False


@pytest.mark.asyncio
async def test_deadline_reports_timed_out_not_failure():
    api, _, st = _api(_status(0, out="partial"))
    ticks = iter([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    with patch("asyncio.sleep", new=AsyncMock()), patch(
        f"{MANAGER}.time", MagicMock(monotonic=lambda: next(ticks))
    ):
        result = await _mgr(api, exec_timeout=2.5).execute_command("n", "100", "sleep 99")
    assert result["timed_out"] is True and result["exited"] is False
    assert result["output"] == "partial" and result["pid"] == 42
    assert result["message"] == "still running in the guest; MCP wait limit reached"
    assert st.get.call_count == 3


@pytest.mark.asyncio
async def test_timed_out_formatted_distinctly():
    api, _, _ = _api(_status(0, out="partial"))
    ticks = iter([0.0, 100.0, 200.0])
    tools = VMTools(api, exec_timeout=1.0)
    with patch("asyncio.sleep", new=AsyncMock()), patch(
        f"{MANAGER}.time", MagicMock(monotonic=lambda: next(ticks))
    ):
        text = tool_text(await tools.execute_command("n", "100", "sleep 99"))
    assert "Timed out" in text and "still running in the guest" in text
    assert "partial" in text


@pytest.mark.asyncio
async def test_output_capped_on_utf8_boundary():
    big = "é" * 100_000  # 2 bytes each
    api, _, _ = _api(_status(out=big, err="e" * 70_000))
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await _mgr(api, exec_max_output=65536).execute_command("n", "100", "cat")
    body, marker, _ = result["output"].partition("\n[output truncated at 65536 bytes]")
    assert marker and len(body.encode()) <= 65536
    assert body == "é" * (65536 // 2)
    assert result["error"].startswith("e" * 65536) and result["truncated"] is True


@pytest.mark.asyncio
async def test_pve_truncation_flags_surfaced():
    api, _, _ = _api(_status(out="short", **{"out-truncated": 1}))
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await _mgr(api).execute_command("n", "100", "cat")
    assert result["truncated"] is True and result["output"] == "short"
    api, _, _ = _api(_status(out="short"))
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await _mgr(api).execute_command("n", "100", "cat")
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_nonzero_exit_reports_failed_status_with_exit_code():
    api, _, _ = _api(_status(out="", err="boom", code=3))
    tools = VMTools(api)
    with patch("asyncio.sleep", new=AsyncMock()):
        text = tool_text(await tools.execute_command("n", "100", "false"))
    assert "Status: FAILED" in text and "Exit code: 3" in text and "boom" in text


@pytest.mark.asyncio
async def test_timeout_is_not_success_and_exit_code_unknown():
    api, _, _ = _api(_status(0, out="partial"))
    ticks = iter([0.0, 100.0, 200.0])
    tools = VMTools(api, exec_timeout=1.0)
    with patch("asyncio.sleep", new=AsyncMock()), patch(
        f"{MANAGER}.time", MagicMock(monotonic=lambda: next(ticks))
    ):
        text = tool_text(await tools.execute_command("n", "100", "sleep 99"))
    assert "Status: FAILED" in text and "Exit code: unknown" in text and "Timed out" in text


@pytest.mark.asyncio
async def test_signal_kill_is_failure_not_exit_zero():
    status = {"exited": 1, "signal": 9, "out-data": "", "err-data": ""}
    api, _, _ = _api(status)
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await _mgr(api).execute_command("n", "100", "x")
        text = tool_text(await VMTools(api).execute_command("n", "100", "x"))
    assert result["success"] is False and result["signal"] == 9 and result["exit_code"] is None
    assert "Status: FAILED" in text and "Killed by signal: 9" in text


@pytest.mark.asyncio
async def test_no_command_or_output_in_logs_or_errors(caplog):
    for name in ("proxmox-mcp", "proxmox-mcp.vm-console"):
        logging.getLogger(name).propagate = True
    cmd, out = "SENTINEL-CMD-xyz", "SENTINEL-OUT-xyz"
    scenarios = [
        _api(_status(out=out, err=out)),
        _api(_status(out=out, err=out, code=1)),
        _api(_status(1), post_error=Exception(f"rejected {cmd} {out}")),
    ]
    for api, _, _ in scenarios:
        tools = VMTools(api)
        with caplog.at_level(logging.DEBUG), patch("asyncio.sleep", new=AsyncMock()):
            try:
                await tools.execute_command("n", "100", cmd, ["SENTINEL-ARG-xyz"])
            except Exception as exc:
                assert cmd not in str(exc) and "SENTINEL-ARG-xyz" not in str(exc)
    for s in (cmd, out, "SENTINEL-ARG-xyz"):
        assert s not in caplog.text


@pytest.mark.asyncio
async def test_exec_denied_without_allow_exec(policy_app, fake_pve):
    app = policy_app(allow_destructive=True)
    fake_pve.reset_calls()
    with pytest.raises(ToolError, match="policy_denied"):
        await app.mcp.call_tool(
            "execute_vm_command", {"node": "pve1", "vmid": "100", "command": "id"})
    assert fake_pve.calls == []


@pytest.mark.asyncio
async def test_exec_runs_with_allow_exec(policy_app, fake_pve):
    app = policy_app(allow_exec=True)
    fake_pve.reset_calls()
    with patch("asyncio.sleep", new=AsyncMock()):
        await app.mcp.call_tool("execute_vm_command", {
            "node": "pve1", "vmid": "100", "command": "ls", "args": ["-l"]})
    post = [c for c in fake_pve.calls if c.method == "POST"]
    assert post and post[0].path.endswith("agent/exec")


@pytest.mark.asyncio
async def test_limits_come_from_policy_config(policy_app):
    app = policy_app(allow_exec=True)
    mgr = app.vm_tools.console_manager if hasattr(app, "vm_tools") else None
    if mgr is not None:
        assert mgr.exec_timeout == 30.0 and mgr.exec_max_output == 65536
