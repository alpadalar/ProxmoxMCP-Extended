"""Table-driven accept/reject tests for the central input validators."""

from __future__ import annotations

import pytest

from proxmox_mcp import validators as v


def _ok(fn, good):
    for value in good:
        assert fn(value) == value


@pytest.mark.parametrize("value", ["pve", "node1", "node2", "pve-2", "a", "A1"])
def test_node_accepts(value):
    assert v.validate_node(value) == value


@pytest.mark.parametrize(
    "value",
    ["../x", "a/b", "a b", "a.b", "", "-a", "a-", ".", "..", "a%2e", "a\x00", "a" * 64, 5, None],
)
def test_node_rejects(value):
    with pytest.raises(v.InputValidationError):
        v.validate_node(value)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("100", "100"),
        (100, "100"),
        (200, "200"),
        ("999999999", "999999999"),
        (999999999, "999999999"),
    ],
)
def test_vmid_accepts(value, expected):
    assert v.validate_vmid(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "99",
        "1000000000",
        "1e3",
        "100 ",
        "-100",
        "10.0",
        "",
        "0x64",
        "１００",
        "100/status",
        "100\n",
        True,
        None,
        100.0,
        99,
        1000000000,
    ],
)
def test_vmid_rejects(value):
    with pytest.raises(v.InputValidationError):
        v.validate_vmid(value)


@pytest.mark.parametrize("value", ["local", "local-lvm", "vm-storage", "ceph", "nfs.share_1", "a"])
def test_storage_accepts(value):
    assert v.validate_storage(value) == value


@pytest.mark.parametrize(
    "value", ["../etc", "a:b", "a,b", "a b", "a/b", "", "a" * 64, "a..b", "1abc", None, 3]
)
def test_storage_rejects(value):
    with pytest.raises(v.InputValidationError):
        v.validate_storage(value)


@pytest.mark.parametrize("value", ["pre", "pre-upgrade", "snap_1", "a" * 40])
def test_snapshot_accepts(value):
    assert v.validate_snapshot_name(value) == value


@pytest.mark.parametrize("value", ["1abc", "a b", "a/../b", "", "a" * 41, "current", None])
def test_snapshot_rejects(value):
    with pytest.raises(v.InputValidationError):
        v.validate_snapshot_name(value)


@pytest.mark.parametrize("value", ["web01", "new-vm", "my.vm", "a"])
def test_vm_name_accepts(value):
    assert v.validate_vm_name(value) == value


@pytest.mark.parametrize("value", ["my vm", "a/b", "a,b", "../", "", "-x", "a" * 64, "a..b", None])
def test_vm_name_rejects(value):
    with pytest.raises(v.InputValidationError):
        v.validate_vm_name(value)


@pytest.mark.parametrize("value", ["debian-12.iso", "a", "x_y+z.iso"])
def test_iso_accepts(value):
    assert v.validate_iso_name(value) == value


@pytest.mark.parametrize(
    "value", ["../../etc/passwd", "a,b=c", "x:y", "a b", "", "a..b", "a/b", "a" * 256, None]
)
def test_iso_rejects(value):
    with pytest.raises(v.InputValidationError):
        v.validate_iso_name(value)


@pytest.mark.parametrize("value", ["l26", "win10", "other"])
def test_ostype_accepts(value):
    assert v.validate_ostype(value) == value


@pytest.mark.parametrize("value", ["l26,foo", "L26 ", "", "a", None])
def test_ostype_rejects(value):
    with pytest.raises(v.InputValidationError):
        v.validate_ostype(value)


def test_error_message_is_escaped_and_capped():
    with pytest.raises(v.InputValidationError) as exc:
        v.validate_node("a\n[ERROR] forged" + "x" * 500)
    msg = str(exc.value)
    assert "\n" not in msg
    assert len(msg) <= 200
    assert "node" in msg
    assert isinstance(exc.value, ValueError)


# --- Task 2 -----------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "hello", "line1\nline2\ttab", "x" * 1024])
def test_description_accepts(value):
    assert v.validate_description(value) == value


@pytest.mark.parametrize("value", ["x" * 1025, "a\x00b", "a\x07b", "a\rb", None, 5])
def test_description_rejects(value):
    with pytest.raises(v.InputValidationError):
        v.validate_description(value)


@pytest.mark.parametrize(
    "fn,good,bad",
    [
        (v.validate_cpus, [1, 4, 128], [0, 129, -1, True, 2.0, "2", None]),
        (v.validate_memory_mb, [16, 2048, 4194304], [15, 4194305, True, 1.5, "512", None]),
        (v.validate_disk_gb, [1, 32, 65536], [0, 65537, True, 1.5, "5", None]),
    ],
)
def test_limits(fn, good, bad):
    for value in good:
        assert fn(value) == value
    for value in bad:
        with pytest.raises(v.InputValidationError):
            fn(value)


def test_validate_optional():
    assert v.validate_optional(v.validate_storage, None) is None
    assert v.validate_optional(v.validate_storage, "local") == "local"
    with pytest.raises(v.InputValidationError):
        v.validate_optional(v.validate_storage, "a b")
    with pytest.raises(v.InputValidationError) as exc:
        v.validate_optional(v.validate_storage, "a b", "iso_storage")
    assert "iso_storage" in str(exc.value)
