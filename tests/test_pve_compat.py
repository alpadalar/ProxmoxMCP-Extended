"""Unit tests for proxmox_mcp.tools.pve_compat (PVE 8.x / 9.x API reality, TECH-02)."""
from unittest.mock import MagicMock

import pytest
import requests
from proxmoxer.core import ResourceException

from proxmox_mcp.tools.base import ProxmoxTool
from proxmox_mcp.tools.pve_compat import (
    describe_task_result,
    guest_agent_privilege_message,
    is_upid,
    parse_pve_version,
    require_vm_status,
    translate_pve_error,
    vm_listed,
    wait_task_stopped,
)
from proxmox_mcp.utils.redaction import register_secret
from tests.harness.fake_proxmox import FakeProxmox, load_fixture

UPID = "UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstop:100:monitor@pve!mcp:"


def rex(code, content="x", message="Err"):
    return ResourceException(code, message, content)


@pytest.mark.parametrize("op,priv,path", [
    ("start_vm", "VM.PowerMgmt", "/vms/100"),
    ("stop_vm", "VM.PowerMgmt", "/vms/100"),
    ("delete_vm", "VM.Allocate", "/vms/100"),
    ("create_snapshot", "VM.Snapshot", "/vms/100"),
    ("rollback_snapshot", "VM.Snapshot.Rollback", "/vms/100"),
    ("update_vm", "VM.Config", "/vms/100"),
    ("get_storage", "Datastore.Audit", "/storage"),
    ("get_node_status", "Sys.Audit", "/nodes/pve1"),
])
def test_403_names_privilege_and_path(op, priv, path):
    err = translate_pve_error(rex(403), op, node="pve1", vmid="100")
    assert isinstance(err, ValueError)
    assert "Permission denied" in str(err) and priv in str(err) and path in str(err)


def test_500_permission_check_failed_is_permission():
    err = translate_pve_error(
        rex(500, "Permission check failed (/vms/100, VM.PowerMgmt)"), "start_vm", vmid="100"
    )
    assert isinstance(err, ValueError) and "Permission denied" in str(err)


def test_401_404_lock_unreachable_and_generic():
    assert "Authentication" in str(translate_pve_error(rex(401), "start_vm"))
    nf = translate_pve_error(rex(404), "start_vm")
    assert isinstance(nf, ValueError) and "not found" in str(nf)
    for body in ("can't lock file '/var/lock/qemu-server/lock-100.conf' - got timeout",
                 "VM is locked (backup)"):
        lock = translate_pve_error(rex(500, body), "start_vm")
        assert "locked" in str(lock) and "retry" in str(lock)
    for code in (595, 596):
        assert "unreachable" in str(translate_pve_error(rex(code), "start_vm"))
    for exc in (requests.exceptions.ConnectionError("boom"), requests.exceptions.Timeout("t")):
        assert "unreachable" in str(translate_pve_error(exc, "start_vm"))
    other = translate_pve_error(rex(500, "weird failure"), "start_vm")
    assert isinstance(other, RuntimeError) and "weird failure" in str(other)


def test_token_secret_never_in_message():
    register_secret("tok-secret-abcdef123456")
    for exc in (rex(500, "echo tok-secret-abcdef123456"), rex(403, "tok-secret-abcdef123456")):
        assert "tok-secret-abcdef123456" not in str(translate_pve_error(exc, "start_vm"))


def test_base_handle_error_delegates_to_translate():
    tool = ProxmoxTool(MagicMock())
    with pytest.raises(ValueError, match="Sys.Audit"):
        tool._handle_error("get nodes", rex(403), privilege_key="get_nodes")
    with pytest.raises(ValueError, match="my own message"):
        tool._handle_error("x", ValueError("my own message"))
    with pytest.raises(RuntimeError, match="Failed to x"):
        tool._handle_error("x", Exception("plain"))


def test_describe_task_result():
    assert describe_task_result(UPID) == f"Task ID: {UPID}"
    assert describe_task_result("UPID:task") == "Task ID: UPID:task"
    none_text = describe_task_result(None)
    assert "no task id" in none_text and "verify" in none_text and "None" not in none_text
    assert len(describe_task_result({"a": "x" * 1000})) < 260
    assert "True" in describe_task_result(True)


@pytest.mark.parametrize("value,ok", [
    (UPID, True), ("../x", False), ("UPID:", False), (UPID + "\n", False),
    (UPID.replace("pve1", "pve 1"), False), (UPID + "/../x", False), (None, False),
    ("UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstop:100:a/b:", False),
])
def test_is_upid(value, ok):
    assert is_upid(value) is ok


def test_parse_pve_version():
    v = parse_pve_version({"version": "9.0.3", "release": "9.0"})
    assert (v.major, v.minor, v.version, v.release) == (9, 0, "9.0.3", "9.0")
    assert parse_pve_version({"version": "8.4.1"}).major == 8
    for junk in (None, MagicMock(), {}, {"version": "x"}, {"version": 9}, "9.0", []):
        assert parse_pve_version(junk) is None


def test_guest_agent_privilege_message():
    m8 = guest_agent_privilege_message("100", 8)
    assert "VM.Monitor" in m8 and "VM.GuestAgent" not in m8 and "/vms/100" in m8
    m9 = guest_agent_privilege_message("100", 9)
    assert "VM.Monitor was removed" in m9 and "VM.GuestAgent.Unrestricted" in m9
    assert "unverified" in m9
    mu = guest_agent_privilege_message("100", None)
    assert "VM.Monitor" in mu and "VM.GuestAgent.Unrestricted" in mu


def _fake():
    return FakeProxmox(load_fixture("pve9"))


def test_wait_task_stopped_ok_after_polling():
    fake = _fake()
    states = iter([{"status": "running"}, {"status": "stopped", "exitstatus": "OK"}])
    fake.set("GET", "nodes/*/tasks/*/status", lambda p, s: next(states))
    sleeps = []
    result = wait_task_stopped(fake, "pve1", UPID, sleep=sleeps.append)
    assert result["exitstatus"] == "OK" and len(sleeps) == 1


@pytest.mark.parametrize("exitstatus", ["some error", "WARNINGS: 1", None])
def test_wait_task_stopped_bad_exit(exitstatus):
    fake = _fake()
    fake.set("GET", "nodes/*/tasks/*/status",
             {"status": "stopped", "exitstatus": exitstatus})
    with pytest.raises(RuntimeError, match="exitstatus"):
        wait_task_stopped(fake, "pve1", UPID, sleep=lambda s: None)


def test_wait_task_stopped_timeout_and_invalid_upid():
    fake = _fake()
    fake.set("GET", "nodes/*/tasks/*/status", {"status": "running"})
    now = [0.0]

    def sleep(s):
        now[0] += s

    with pytest.raises(RuntimeError, match="Timed out"):
        wait_task_stopped(fake, "pve1", UPID, timeout=5, interval=1, sleep=sleep,
                          clock=lambda: now[0])
    fake.reset_calls()
    with pytest.raises(ValueError):
        wait_task_stopped(fake, "pve1", "../x", sleep=lambda s: None)
    fake.assert_no_calls()


def test_require_vm_status_ok_and_403():
    fake = _fake()
    assert require_vm_status(fake, "pve1", "100", "start_vm")["status"] == "running"
    fake.fail("GET", "nodes/pve1/qemu/100/status/current", rex(403))
    fake.reset_calls()
    with pytest.raises(ValueError, match="VM.PowerMgmt"):
        require_vm_status(fake, "pve1", "100", "start_vm", )
    assert not any(c.path.endswith("/qemu") for c in fake.calls)


def test_require_vm_status_missing_vm_via_listing():
    fake = _fake()
    fake.fail("GET", "nodes/pve1/qemu/999/status/current",
              rex(500, "Configuration file 'nodes/pve1/qemu-server/999.conf' does not exist"))
    with pytest.raises(ValueError, match="VM 999 not found on node pve1"):
        require_vm_status(fake, "pve1", "999", "start_vm")


def test_require_vm_status_text_says_not_found_but_vm_listed():
    """Anti-substring trap: text alone never decides existence."""
    fake = _fake()
    fake.fail("GET", "nodes/pve1/qemu/100/status/current", rex(500, "storage not found"))
    with pytest.raises(RuntimeError) as ei:
        require_vm_status(fake, "pve1", "100", "start_vm")
    assert not isinstance(ei.value, ValueError) and "VM 100 not found" not in str(ei.value)


def test_require_vm_status_404():
    fake = _fake()
    fake.fail("GET", "nodes/pve1/qemu/999/status/current", rex(404))
    with pytest.raises(ValueError, match="VM 999 not found on node pve1"):
        require_vm_status(fake, "pve1", "999", "start_vm")


def test_vm_listed():
    fake = _fake()
    assert vm_listed(fake, "pve1", "100") and not vm_listed(fake, "pve1", "999")
