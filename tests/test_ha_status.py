"""get_ha_status (FEAT-06) on PVE 8 and PVE 9 fixtures."""
import json

import pytest
from fastmcp.exceptions import ToolError
from proxmoxer.core import ResourceException

from proxmox_mcp.utils.redaction import register_secret
from tests.helpers import tool_text

STATUS = "cluster/ha/status/current"
RESOURCES = "cluster/ha/resources"


@pytest.fixture
def app(policy_app):
    return policy_app(read_only=True)


async def _status(app):
    return json.loads(tool_text(await app.mcp.call_tool("get_ha_status", {})))


@pytest.mark.asyncio
async def test_payload_shape(app, fake_pve):
    data = await _status(app)
    assert data["ha_configured"] is True and data["quorate"] is True
    assert data["master"]["node"] == "pve1" and "active" in data["master"]["status"]
    assert [item["node"] for item in data["lrm"]] == ["pve1"]
    assert data["services"] == [{
        "sid": "vm:100", "node": "pve1", "state": "started", "request_state": "started",
        "crm_state": "started"}]
    resource = data["resources"][0]
    assert resource["sid"] == "vm:100" and resource["group"] == "prod"
    assert resource["max_restart"] == 1 and resource["comment"] == "web frontend"


@pytest.mark.asyncio
async def test_pve9_failback_field_passes_through(app, fake_pve):
    data = await _status(app)
    resource = data["resources"][0]
    major = fake_pve.version.get()["release"].split(".")[0]
    assert ("failback" in resource) is (major == "9")


@pytest.mark.asyncio
async def test_exactly_two_gets_no_mutation(app, fake_pve):
    fake_pve.reset_calls()
    await _status(app)
    assert [(c.method, c.path) for c in fake_pve.calls if c.path != "version"] == [
        ("GET", STATUS), ("GET", RESOURCES)]
    assert fake_pve.mutating_calls() == []


@pytest.mark.asyncio
async def test_whitelist_drops_unknown_keys_and_redacts_text(app, fake_pve):
    register_secret("s3cr3t-sentinel-value")
    fake_pve.set("GET", RESOURCES, [{
        "sid": "ct:200", "type": "ct", "state": "started", "evil": "leak-me",
        "comment": "token s3cr3t-sentinel-value " + "c" * 600, "group": "g" * 400}])
    fake_pve.set("GET", STATUS, [
        {"type": "quorum", "quorate": 0, "secret_field": "leak-me"},
        {"type": "service", "sid": "ct:200", "state": "error", "leak": "leak-me"},
        {"type": "somethingelse", "x": "leak-me"}])
    text = tool_text(await app.mcp.call_tool("get_ha_status", {}))
    assert "leak-me" not in text and "s3cr3t-sentinel-value" not in text
    data = json.loads(text)
    assert data["quorate"] is False and len(data["resources"][0]["comment"]) == 300
    assert len(data["resources"][0]["group"]) == 300
    assert data["services"] == [{"sid": "ct:200", "state": "error"}]


@pytest.mark.asyncio
async def test_empty_ha_is_not_an_error(app, fake_pve):
    fake_pve.set("GET", STATUS, [{"id": "quorum", "type": "quorum", "quorate": 1}])
    fake_pve.set("GET", RESOURCES, [])
    data = await _status(app)
    assert data["ha_configured"] is False
    assert data["services"] == [] and data["resources"] == [] and data["lrm"] == []
    assert data["master"] is None and data["quorate"] is True


@pytest.mark.asyncio
async def test_403_names_sys_audit(app, fake_pve):
    fake_pve.fail("GET", STATUS, ResourceException(403, "Forbidden", "Permission check failed"))
    with pytest.raises(ToolError) as ei:
        await app.mcp.call_tool("get_ha_status", {})
    assert "Sys.Audit" in str(ei.value) and "Permission denied" in str(ei.value)


@pytest.mark.parametrize(
    "raw,expected",
    [(1, True), ("1", True), (True, True), (0, False), ("0", False), (False, False),
     ("", False), (None, None)],
)
def test_quorate_is_strict(raw, expected):
    from proxmox_mcp.tools.cluster import _as_quorate

    assert _as_quorate(raw) is expected
