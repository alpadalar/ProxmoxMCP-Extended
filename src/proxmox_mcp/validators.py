"""Central, strict input validators for Proxmox identifiers and limits.

Validators reject bad input and never rewrite it (the one exception is
``validate_vmid`` which returns the canonical decimal string). Patterns follow
Proxmox VE's own formats; tool-level ``Field`` bounds in the server are
intentionally tighter than the limits here and are unchanged.
"""

from __future__ import annotations

import re
from typing import Callable, Optional, TypeVar

__all__ = [
    "InputValidationError",
    "validate_node",
    "validate_vmid",
    "validate_storage",
    "validate_snapshot_name",
    "validate_vm_name",
    "validate_iso_name",
    "validate_ostype",
    "validate_description",
    "validate_cpus",
    "validate_memory_mb",
    "validate_disk_gb",
    "validate_optional",
]

T = TypeVar("T")


class InputValidationError(ValueError):
    """Raised when a tool argument fails validation."""


_NODE_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_STORAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,61}[A-Za-z0-9]|[A-Za-z]")
_SNAPSHOT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}")
_VM_NAME_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9.-]{0,61}[A-Za-z0-9])?")
_ISO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}")
_OSTYPE_RE = re.compile(r"[a-z0-9]{2,16}")
_DIGITS_RE = re.compile(r"[0-9]+")

VMID_MIN = 100
VMID_MAX = 999_999_999
DESCRIPTION_MAX = 1024


def _fail(field: str, rule: str, value: object) -> InputValidationError:
    shown = repr(value)
    if len(shown) > 40:
        shown = shown[:40] + "..."
    return InputValidationError(f"Invalid {field}: {rule} (got {shown})")


def _match(value: object, pattern: "re.Pattern[str]", field: str, rule: str) -> str:
    if not isinstance(value, str) or not value.isascii() or not pattern.fullmatch(value):
        raise _fail(field, rule, value)
    return value


def validate_node(value: object, field: str = "node") -> str:
    """Node name: PVE hostname form (letters, digits, hyphen; max 63)."""
    return _match(value, _NODE_RE, field, "must be a hostname of letters, digits and '-'")


def validate_vmid(value: object, field: str = "vmid") -> str:
    """VMID 100..999999999; returns the canonical decimal string."""
    if isinstance(value, bool):
        raise _fail(field, "must be an integer 100-999999999", value)
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.isascii() and _DIGITS_RE.fullmatch(value):
        number = int(value)
    else:
        raise _fail(field, "must be an integer 100-999999999", value)
    if not VMID_MIN <= number <= VMID_MAX:
        raise _fail(field, "must be in range 100-999999999", value)
    return str(number)


def validate_storage(value: object, field: str = "storage") -> str:
    """Storage id: starts with a letter; letters, digits, '.', '_', '-'."""
    text = _match(value, _STORAGE_RE, field, "must be a storage id (letters, digits, '._-')")
    if ".." in text:
        raise _fail(field, "must not contain '..'", value)
    return text


def validate_snapshot_name(value: object, field: str = "snapshot") -> str:
    """Snapshot name: starts with a letter; letters, digits, '_', '-'; max 40."""
    text = _match(value, _SNAPSHOT_RE, field, "must start with a letter, then letters/digits/_-")
    if text == "current":
        raise _fail(field, "'current' is reserved", value)
    return text


def validate_vm_name(value: object, field: str = "name") -> str:
    """VM name: DNS-style name (letters, digits, '.', '-'; max 63)."""
    text = _match(value, _VM_NAME_RE, field, "must be a DNS-style name")
    if ".." in text:
        raise _fail(field, "must not contain '..'", value)
    return text


def validate_iso_name(value: object, field: str = "iso") -> str:
    """ISO volume name: no separators, commas, colons or '..'."""
    text = _match(value, _ISO_RE, field, "must be a plain file name (letters, digits, '._+-')")
    if ".." in text:
        raise _fail(field, "must not contain '..'", value)
    return text


def validate_ostype(value: object, field: str = "ostype") -> str:
    """OS type token such as 'l26' or 'win10'."""
    return _match(value, _OSTYPE_RE, field, "must be 2-16 lowercase letters/digits")


def validate_description(value: object, field: str = "description") -> str:
    """Printable text up to 1024 chars; only newline and tab allowed as control chars."""
    if not isinstance(value, str):
        raise _fail(field, "must be a string", value)
    if len(value) > DESCRIPTION_MAX:
        raise _fail(field, f"must be at most {DESCRIPTION_MAX} characters", value)
    for ch in value:
        if (ord(ch) < 32 and ch not in "\n\t") or ord(ch) == 127:
            raise _fail(field, "must not contain control characters", value)
    return value


def _int_range(value: object, lo: int, hi: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(field, "must be an integer", value)
    if not lo <= value <= hi:
        raise _fail(field, f"must be in range {lo}-{hi}", value)
    return value


def validate_cpus(value: object, field: str = "cpus", lo: int = 1, hi: int = 128) -> int:
    """CPU count 1..128 (server Field bounds for create_vm are tighter)."""
    return _int_range(value, lo, hi, field)


def validate_memory_mb(
    value: object, field: str = "memory", lo: int = 16, hi: int = 4_194_304
) -> int:
    """Memory in MiB, 16..4194304 (4 TiB)."""
    return _int_range(value, lo, hi, field)


def validate_disk_gb(value: object, field: str = "disk_size", lo: int = 1, hi: int = 65_536) -> int:
    """Disk size in GiB, 1..65536."""
    return _int_range(value, lo, hi, field)


def validate_optional(fn: Callable[..., T], value: object, *args: object) -> Optional[T]:
    """Return None for None, otherwise delegate to ``fn(value, *args)``."""
    if value is None:
        return None
    return fn(value, *args)
