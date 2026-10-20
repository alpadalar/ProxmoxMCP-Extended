"""Secret/command/output leak tests (CONF-03). Fake sentinel values only."""
import logging
import os
import stat
from unittest.mock import MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError, ValidationError

from proxmox_mcp.config.models import AuthConfig, LoggingConfig, ProxmoxConfig
from proxmox_mcp.core.logging import setup_logging
from proxmox_mcp.utils import redaction
from proxmox_mcp.utils.redaction import RedactingFilter, redact, redact_local, register_secret
from tests.helpers import tool_text


@pytest.fixture(autouse=True)
def _clean_secrets():
    with redaction._lock:
        saved = set(redaction._secrets)
        redaction._secrets.clear()
    yield
    with redaction._lock:
        redaction._secrets.clear()
        redaction._secrets.update(saved)


@pytest.fixture
def restore_root_logger():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()
    for h in handlers:
        root.addHandler(h)
    root.setLevel(level)


def test_redact_basic_and_short_ignored():
    register_secret("tok-SECRET")
    register_secret("ab")  # too short, ignored
    register_secret("")
    assert redact("x tok-SECRET y ab") == "x [REDACTED] y ab"
    assert redact(redact("tok-SECRET")) == "[REDACTED]"


def test_redact_multiple_longest_first_and_header_form():
    register_secret("abcd")
    register_secret("abcdefgh")
    assert redact("abcdefgh abcd") == "[REDACTED] [REDACTED]"
    register_secret("HEADERSECRET")
    assert "HEADERSECRET" not in redact("PVEAPIToken=u@pve!t=HEADERSECRET")
    assert "HEADERSECRET" not in redact(repr(Exception("https://h/?k=HEADERSECRET")))


def test_filter_rewrites_message_args_and_exc_text():
    register_secret("tok-SECRET")
    rec = logging.LogRecord("n", logging.ERROR, "f", 1, "bad %s", ("tok-SECRET",), None)
    rec.exc_text = "Traceback tok-SECRET"
    assert RedactingFilter().filter(rec) is True
    assert "tok-SECRET" not in rec.getMessage()
    assert "tok-SECRET" not in rec.exc_text


def test_setup_logging_file_mode_and_redaction(tmp_path, restore_root_logger):
    path = tmp_path / "x.log"
    path.write_text("")
    os.chmod(path, 0o644)
    register_secret("tok-SECRET")
    logger = setup_logging(LoggingConfig(level="INFO", file=str(path)))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    logger.info("leak tok-SECRET here")
    for h in logging.getLogger().handlers:
        h.flush()
        assert any(isinstance(f, RedactingFilter) for f in h.filters)
    text = path.read_text()
    assert "tok-SECRET" not in text and "[REDACTED]" in text


def test_setup_logging_new_file_0600_and_idempotent(tmp_path, restore_root_logger):
    old = os.umask(0o000)
    try:
        path = tmp_path / "new.log"
        cfg = LoggingConfig(file=str(path))
        setup_logging(cfg)
        n = len(logging.getLogger().handlers)
        setup_logging(cfg)
        assert len(logging.getLogger().handlers) == n
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    finally:
        os.umask(old)


def test_default_level_info_and_invalid_rejected():
    assert LoggingConfig().level == "INFO"
    with pytest.raises(ValueError):
        LoggingConfig(level="LOUD")


def _manager(failure=None):
    from proxmox_mcp.core.proxmox import ProxmoxManager

    cfg = ProxmoxConfig(host="h.example", verify_ssl=True)
    auth = AuthConfig(user="u@pve", token_name="t", token_value="SENTINEL_TOKEN")
    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as api:
        if failure:
            api.return_value.version.get.side_effect = failure
        return ProxmoxManager(cfg, auth)


def test_manager_registers_token_and_scrubs_connect_error(caplog):
    err = Exception("401 Unauthorized for PVEAPIToken=u@pve!t=SENTINEL_TOKEN")
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError) as exc:
        _manager(err)
    assert "SENTINEL_TOKEN" not in str(exc.value)
    assert "SENTINEL_TOKEN" not in caplog.text
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_handle_error_scrubs(caplog):
    from proxmox_mcp.tools.base import ProxmoxTool

    register_secret("SENTINEL_TOKEN")
    tool = ProxmoxTool(MagicMock())
    with caplog.at_level(logging.DEBUG), pytest.raises(Exception) as exc:
        tool._handle_error("op", Exception("boom SENTINEL_TOKEN"))
    assert "SENTINEL_TOKEN" not in str(exc.value)
    assert "SENTINEL_TOKEN" not in caplog.text


def _exec_mocks(api, post_side_effect=None):
    api.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "running"}
    exec_ep = MagicMock()
    if post_side_effect:
        exec_ep.post.side_effect = post_side_effect
    else:
        exec_ep.post.return_value = {"pid": 7}
    status_ep = MagicMock()
    status_ep.get.return_value = {
        "out-data": "SENTINEL_OUT", "err-data": "SENTINEL_ERR", "exitcode": 0, "exited": 1}
    agent = MagicMock()
    agent.side_effect = lambda p: exec_ep if p == "exec" else status_ep
    api.nodes.return_value.qemu.return_value.agent = agent


@pytest.mark.asyncio
async def test_exec_not_logged_but_returned(server, api, caplog):
    _exec_mocks(api)
    for name in ("proxmox-mcp", "proxmox-mcp.vm-console"):
        logging.getLogger(name).propagate = True
    with caplog.at_level(logging.DEBUG), patch("asyncio.sleep", return_value=None):
        result = await server.mcp.call_tool(
            "execute_vm_command", {"node": "n1", "vmid": "100", "command": "echo SENTINEL_CMD"})
    for s in ("SENTINEL_CMD", "SENTINEL_OUT", "SENTINEL_ERR", "out-data"):
        assert s not in caplog.text, s
    assert "SENTINEL_OUT" in tool_text(result)


@pytest.mark.asyncio
async def test_exec_failure_logs_only_type(server, api, caplog):
    _exec_mocks(api, post_side_effect=Exception("rejected command SENTINEL_CMD"))
    for name in ("proxmox-mcp", "proxmox-mcp.vm-console"):
        logging.getLogger(name).propagate = True
    with caplog.at_level(logging.DEBUG), patch("asyncio.sleep", return_value=None):
        with pytest.raises((ToolError, ValidationError)):
            await server.mcp.call_tool(
                "execute_vm_command",
                {"node": "n1", "vmid": "100", "command": "echo SENTINEL_CMD"})
    assert "SENTINEL_CMD" not in caplog.text


# --- Caller-supplied values never enter the global registry (review WR-04) ---

@pytest.mark.parametrize("short", ["a", "error", "root", "date", "ping"])
@pytest.mark.asyncio
async def test_short_command_does_not_alter_other_logs(server, api, caplog, short):
    _exec_mocks(api)
    for name in ("proxmox-mcp", "proxmox-mcp.vm-console"):
        logging.getLogger(name).propagate = True
    with patch("asyncio.sleep", return_value=None):
        await server.mcp.call_tool(
            "execute_vm_command", {"node": "n1", "vmid": "100", "command": short})
    assert redact("an error occurred for root at date: ping") == (
        "an error occurred for root at date: ping")
    assert redact("a" * 10 + short) == "a" * 10 + short


@pytest.mark.asyncio
async def test_registry_stays_bounded_after_many_calls(server, api):
    _exec_mocks(api)
    with redaction._lock:
        before = (len(redaction._secrets), len(vars(redaction)))
    with patch("asyncio.sleep", return_value=None):
        for i in range(300):
            await server.mcp.call_tool(
                "execute_vm_command",
                {"node": "n1", "vmid": "100", "command": f"echo unique-command-{i}"})
    with redaction._lock:
        assert (len(redaction._secrets), len(vars(redaction))) == before
    assert not hasattr(redaction, "register_sensitive")


def test_redact_local_is_call_scoped_and_min_length():
    assert redact_local("x failed: long-secret-cmd", "long-secret-cmd") == "x failed: [REDACTED]"
    assert redact_local("root error a", "root", "error", "a") == "root error a"
    assert redact("long-secret-cmd") == "long-secret-cmd"
