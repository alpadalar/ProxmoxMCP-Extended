"""list_backups (FEAT-05) on PVE 8 and PVE 9 fixtures."""
import json

import pytest
from fastmcp.exceptions import ToolError
from proxmoxer.core import ResourceException

from tests.helpers import tool_text

CONTENT = "nodes/*/storage/*/content"


@pytest.fixture
def app(policy_app):
    return policy_app(read_only=True)  # read class: allowed even in read-only mode


def _calls(fake):
    return [c for c in fake.calls if c.path != "version"]  # lazy connect probes /version


async def _call(app, **args):
    return json.loads(tool_text(await app.mcp.call_tool("list_backups", {"node": "pve1", **args})))


@pytest.mark.asyncio
async def test_explicit_storage_passes_content_and_vmid(app, fake_pve):
    fake_pve.reset_calls()
    data = await _call(app, storage="local", vmid="100")
    assert [(c.method, c.path, c.params) for c in _calls(fake_pve)] == [
        ("GET", "nodes/pve1/storage/local/content", {"content": "backup", "vmid": "100"})]
    assert [b["vmid"] for b in data["backups"]] == ["100"]  # local re-filter by vmid
    b = data["backups"][0]
    assert b["size_bytes"] == 1073741824 and b["size"] == "1.00 GB"
    assert b["ctime_utc"] == "2024-01-15T12:00:00Z" and b["notes"] == "nightly"
    assert b["protected"] is False and b["format"] == "vma.zst" and b["storage"] == "local"
    assert data["node"] == "pve1" and data["count"] == 1 and data["skipped"] == []


@pytest.mark.asyncio
async def test_explicit_storage_without_vmid_drops_non_backup_and_sorts(app, fake_pve):
    fake_pve.reset_calls()
    data = await _call(app, storage="local")
    assert _calls(fake_pve)[0].params == {"content": "backup"}
    assert [b["vmid"] for b in data["backups"]] == ["101", "100"]  # newest first, iso dropped
    assert data["backups"][0]["protected"] is True


@pytest.mark.asyncio
async def test_iteration_only_queries_backup_capable_active_storages(app, fake_pve):
    fake_pve.reset_calls()
    data = await _call(app)
    paths = [c.path for c in _calls(fake_pve)]
    assert paths == ["nodes/pve1/storage", "nodes/pve1/storage/local/content"]
    assert _calls(fake_pve)[0].params == {"content": "backup"}
    assert data["count"] == 2 and data["skipped"] == []


@pytest.mark.asyncio
async def test_iteration_skips_inactive_and_content_as_list(app, fake_pve):
    fake_pve.set("GET", "nodes/*/storage", [
        {"storage": "off", "content": "backup", "enabled": 0, "active": 1},
        {"storage": "down", "content": "backup", "enabled": 1, "active": 0},
        {"storage": "nas", "content": ["backup"]},
        {"storage": "imgs", "content": ["images"]},
    ])
    fake_pve.reset_calls()
    await _call(app)
    assert [c.path for c in _calls(fake_pve)] == [
        "nodes/pve1/storage", "nodes/pve1/storage/nas/content"]


@pytest.mark.asyncio
async def test_iteration_reports_failed_storage_and_continues(app, fake_pve):
    fake_pve.set("GET", "nodes/*/storage", [
        {"storage": "bad", "content": "backup"}, {"storage": "local", "content": "backup"}])
    fake_pve.fail("GET", "nodes/*/storage/bad/content",
                  ResourceException(403, "Forbidden", "Permission check failed"))
    data = await _call(app)
    assert data["count"] == 2
    assert [s["storage"] for s in data["skipped"]] == ["bad"] and data["skipped"][0]["reason"]


@pytest.mark.asyncio
async def test_explicit_storage_failure_is_raised_with_privilege(app, fake_pve):
    fake_pve.fail("GET", CONTENT, ResourceException(403, "Forbidden", "Permission check failed"))
    with pytest.raises(ToolError, match="Datastore.Audit"):
        await app.mcp.call_tool("list_backups", {"node": "pve1", "storage": "local"})


@pytest.mark.asyncio
async def test_notes_truncated(app, fake_pve):
    fake_pve.set("GET", CONTENT, [
        {"volid": "local:backup/x", "content": "backup", "vmid": 100, "notes": "n" * 900}])
    data = await _call(app, storage="local")
    assert len(data["backups"][0]["notes"]) == 300
    assert data["backups"][0]["size_bytes"] == 0 and data["backups"][0]["ctime_utc"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [
    {"node": "../x"}, {"node": "pve1", "storage": "a/b"}, {"node": "pve1", "storage": ""},
    {"node": "pve1", "vmid": "abc"}, {"node": "pve1", "vmid": "100/x"},
])
async def test_invalid_inputs_make_no_call(app, fake_pve, args):
    fake_pve.reset_calls()
    with pytest.raises(ToolError):
        await app.mcp.call_tool("list_backups", args)
    assert fake_pve.calls == []
