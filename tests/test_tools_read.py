"""Mock-based tests for the read-only tools, called through ``server.mcp.call_tool``."""
import json

import pytest
from fastmcp.exceptions import ToolError, ValidationError

from tests.helpers import tool_text


@pytest.mark.asyncio
async def test_get_nodes_lists_each_node(server, api):
    """get_nodes renders every node and queries the cluster node list."""
    api.nodes.get.return_value = [
        {"node": "node1", "status": "online", "mem": 1024, "maxmem": 4096},
        {"node": "node2", "status": "online", "mem": 2048, "maxmem": 8192},
    ]
    api.nodes.return_value.status.get.return_value = {
        "uptime": 3600,
        "cpuinfo": {"cpus": 4},
        "memory": {"used": 1024, "total": 4096},
    }
    text = tool_text(await server.mcp.call_tool("get_nodes", {}))
    api.nodes.get.assert_called()
    assert "node1" in text and "node2" in text


@pytest.mark.asyncio
async def test_get_nodes_falls_back_to_basic_info(server, api):
    """A failing per-node status call falls back to the cluster listing values."""
    api.nodes.get.return_value = [
        {"node": "node1", "status": "online", "mem": 1024, "maxmem": 4096},
    ]
    api.nodes.return_value.status.get.side_effect = Exception("boom")
    text = tool_text(await server.mcp.call_tool("get_nodes", {}))
    assert "node1" in text


@pytest.mark.asyncio
async def test_get_node_status_renders_status(server, api):
    """get_node_status queries the node status endpoint and renders the node."""
    api.nodes.return_value.status.get.return_value = {
        "uptime": 7200,
        "cpu": 0.25,
        "cpuinfo": {"cpus": 8},
        "memory": {"used": 1024, "total": 4096, "free": 3072},
    }
    text = tool_text(await server.mcp.call_tool("get_node_status", {"node": "node1"}))
    api.nodes.assert_any_call("node1")
    api.nodes.return_value.status.get.assert_called()
    assert "node1" in text


@pytest.mark.asyncio
async def test_get_node_status_requires_node(server, api):
    """Calling get_node_status without a node is rejected before any API call."""
    with pytest.raises((ToolError, ValidationError)):
        await server.mcp.call_tool("get_node_status", {})
    api.nodes.return_value.status.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_vms_lists_qemu_vms(server, api):
    """get_vms queries qemu on each node and renders vmid and name."""
    api.nodes.return_value.qemu.get.return_value = [
        {"vmid": 100, "name": "web01", "status": "running", "mem": 512, "maxmem": 2048},
    ]
    api.nodes.return_value.qemu.return_value.config.get.return_value = {"cores": 2}
    text = tool_text(await server.mcp.call_tool("get_vms", {}))
    api.nodes.return_value.qemu.get.assert_called()
    assert "web01" in text and "100" in text


@pytest.mark.asyncio
async def test_get_containers_skips_failing_node(server, api):
    """A node whose lxc listing raises is skipped; healthy containers are returned."""
    def nodes_call(name):
        node = api.nodes.return_value
        if name == "node1":
            node = type(node)()
            node.lxc.get.return_value = [{"vmid": 200, "name": "ct-ok", "status": "running"}]
        else:
            node = type(node)()
            node.lxc.get.side_effect = Exception("node down")
        return node

    api.nodes.side_effect = nodes_call
    result = await server.mcp.call_tool("get_containers", {})
    data = json.loads(tool_text(result))
    api.nodes.get.assert_called()
    assert [c["name"] for c in data] == ["ct-ok"]


@pytest.mark.asyncio
async def test_get_storage_renders_pools(server, api):
    """get_storage renders storage pools with usage from the status endpoint."""
    api.storage.get.return_value = [
        {"storage": "local-lvm", "type": "lvmthin", "content": "images,rootdir", "node": "node1"},
    ]
    api.nodes.return_value.storage.return_value.status.get.return_value = {
        "used": 1024, "total": 4096, "avail": 3072,
    }
    text = tool_text(await server.mcp.call_tool("get_storage", {}))
    api.storage.get.assert_called()
    assert "local-lvm" in text


@pytest.mark.asyncio
async def test_get_cluster_status_renders_cluster(server, api):
    """get_cluster_status renders the cluster name from cluster.status.get."""
    api.cluster.status.get.return_value = [
        {"type": "cluster", "name": "lab-cluster", "quorate": 1, "nodes": 2},
        {"type": "node", "name": "node1", "online": 1},
        {"type": "node", "name": "node2", "online": 1},
    ]
    text = tool_text(await server.mcp.call_tool("get_cluster_status", {}))
    api.cluster.status.get.assert_called()
    assert "lab-cluster" in text


@pytest.mark.asyncio
async def test_get_vm_usage_renders_cpu_and_memory(server, api):
    """get_vm_usage renders CPU percent and memory from status.current."""
    chain = api.nodes.return_value.qemu.return_value.status.current.get
    chain.return_value = {"cpu": 0.5, "mem": 1024 ** 3, "maxmem": 2 * 1024 ** 3}
    text = tool_text(await server.mcp.call_tool("get_vm_usage", {"node": "node1", "vmid": "100"}))
    api.nodes.assert_any_call("node1")
    api.nodes.return_value.qemu.assert_any_call("100")
    chain.assert_called()
    assert "CPU: 50.0%" in text
    assert "50.0%" in text


@pytest.mark.asyncio
async def test_health_unknown_without_startup_tests(server):
    """health reports unknown status and null tests_passed when no tests ran."""
    data = json.loads(tool_text(await server.mcp.call_tool("health", {})))
    assert data["status"] == "unknown"
    assert data["tests_passed"] is None


@pytest.mark.asyncio
async def test_get_containers_node_listing_failure_is_an_error_on_both_transports(
    server, api, mock_env_vars, mock_proxmox
):
    """A failing nodes listing must raise, never look like 'no containers'."""
    from proxmox_mcp.auth.apikey import hash_api_key
    from proxmox_mcp.server_http import ProxmoxMCPHTTPServer

    http = ProxmoxMCPHTTPServer(api_key_digests=[hash_api_key("k" * 16)])
    api.nodes.get.side_effect = Exception("connection refused")
    for srv in (server, http):
        with pytest.raises(Exception):
            await srv.mcp.call_tool("get_containers", {})


TASK_UPID = "UPID:node1:0000ABCD:00123456:65A1B2C3:qmstart:100:monitor@pve!mcp:"


@pytest.mark.asyncio
async def test_get_task_status_reads_task_on_upid_node(server, api):
    """get_task_status queries the node named in the UPID and reports success for OK only."""
    status = api.nodes.return_value.tasks.return_value.status
    status.get.return_value = {"status": "stopped", "exitstatus": "OK"}
    data = json.loads(tool_text(await server.mcp.call_tool("get_task_status", {"upid": TASK_UPID})))
    api.nodes.assert_called_with("node1")
    api.nodes.return_value.tasks.assert_called_with(TASK_UPID)
    assert data["success"] is True and data["state"] == "ok"


@pytest.mark.asyncio
async def test_wait_for_task_rejects_out_of_range_timeout(server, api):
    """wait_for_task bounds the timeout to 1..300 before any Proxmox call."""
    api.nodes.reset_mock()
    with pytest.raises((ToolError, ValidationError)):
        await server.mcp.call_tool("wait_for_task", {"upid": TASK_UPID, "timeout": 301})
    assert api.nodes.called is False
