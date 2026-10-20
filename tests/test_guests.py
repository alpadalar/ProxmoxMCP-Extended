"""Guest resolver (cluster/resources based, uncached)."""

import pytest
from proxmoxer.core import ResourceException

from proxmox_mcp.tools.guests import Guest, resolve_guest


def test_found_returns_guest(fake_pve):
    guest = resolve_guest(fake_pve, "200", expected_type="lxc")
    assert guest == Guest("pve1", "200", "lxc", "running", "ct-01", False)
    assert [(c.method, c.path, c.params) for c in fake_pve.calls] == [
        ("GET", "cluster/resources", {"type": "vm"})
    ]


def test_expected_type_none_accepts_both(fake_pve):
    assert resolve_guest(fake_pve, "100").type == "qemu"
    assert resolve_guest(fake_pve, "200").type == "lxc"


def test_node_hint_must_agree(fake_pve):
    assert resolve_guest(fake_pve, "200", node="pve1").node == "pve1"
    with pytest.raises(ValueError, match="pve1.*pve2"):
        resolve_guest(fake_pve, "200", node="pve2")


def test_qemu_vmid_refused_for_lxc_with_hint(fake_pve):
    with pytest.raises(ValueError, match="qemu VM, not an LXC container.*start_vm/stop_vm"):
        resolve_guest(fake_pve, "100", expected_type="lxc")
    with pytest.raises(ValueError, match="LXC container, not a qemu VM"):
        resolve_guest(fake_pve, "200", expected_type="qemu")


def test_missing_guest_mentions_acl(fake_pve):
    with pytest.raises(ValueError, match="Guest 999 not found.*VM.Audit on /vms/999"):
        resolve_guest(fake_pve, "999")


def test_template_refused(fake_pve):
    with pytest.raises(ValueError, match="template"):
        resolve_guest(fake_pve, "201", expected_type="lxc")


def test_invalid_input_makes_no_call(fake_pve):
    for vmid, node in (("x/y", None), ("200", "../x"), ("200", ""), (None, None)):
        with pytest.raises(ValueError):
            resolve_guest(fake_pve, vmid, node=node)
    assert fake_pve.calls == []


def test_no_cache_between_calls(fake_pve):
    assert resolve_guest(fake_pve, "200").node == "pve1"
    fake_pve.set(
        "GET",
        "cluster/resources",
        [{"type": "lxc", "vmid": 200, "node": "pve2", "status": "running", "name": "ct-01"}],
    )
    assert resolve_guest(fake_pve, "200").node == "pve2"  # migrated between calls
    assert [c.path for c in fake_pve.calls] == ["cluster/resources", "cluster/resources"]


def test_api_errors_propagate(fake_pve):
    fake_pve.fail("GET", "cluster/resources", ResourceException(403, "Forbidden", "denied"))
    with pytest.raises(ResourceException):
        resolve_guest(fake_pve, "200")
