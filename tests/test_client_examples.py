"""The shipped client config examples are valid, secret-free and their stdio entry works."""

import asyncio
import json
import re
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
FILES = ["claude_desktop_config.json", "cursor_mcp_config.json", "cline_mcp_settings.json"]
PLACEHOLDER_DIR = "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended"
GOLDEN_NAMES = sorted(
    t["name"] for t in json.loads((ROOT / "tests" / "golden" / "tools.json").read_text("utf-8"))
)


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", FILES)
def test_examples_are_valid_and_secret_free(name: str) -> None:
    raw = (EXAMPLES / name).read_text(encoding="utf-8")
    data = json.loads(raw)
    assert set(data["mcpServers"]) == {"proxmox-mcp", "proxmox-mcp-http"}
    assert "YOUR_API_KEY" in raw
    assert not re.search(r"\b[0-9a-fA-F]{64}\b", raw), "digest-shaped literal"
    assert not re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-", raw), "uuid-shaped"
    assert "curl" not in raw and '"transport"' not in raw


def test_http_entries_point_at_default_endpoint() -> None:
    for name in ("cursor_mcp_config.json", "cline_mcp_settings.json"):
        entry = _load(name)["mcpServers"]["proxmox-mcp-http"]
        assert entry["url"] == "http://127.0.0.1:8812/proxmox-mcp"
        assert entry["headers"]["Authorization"] == "Bearer YOUR_API_KEY"
    assert _load("cline_mcp_settings.json")["mcpServers"]["proxmox-mcp-http"]["type"] == (
        "streamableHttp"
    )


@pytest.mark.parametrize("name", FILES)
def test_stdio_entry_completes_a_real_handshake(name: str, tmp_path: Path) -> None:
    entry = _load(name)["mcpServers"]["proxmox-mcp"]
    args = [a.replace(PLACEHOLDER_DIR, str(ROOT)) for a in entry["args"]]
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "proxmox": {"host": "127.0.0.1", "port": 8006, "verify_ssl": True, "timeout": 5},
                "auth": {
                    "user": "monitor@pve",
                    "token_name": "fake",
                    "token_value": "fake-not-a-real-secret",
                },
            }
        ),
        encoding="utf-8",
    )
    env = dict(entry["env"])
    assert env["PROXMOX_MCP_CONFIG"].startswith(PLACEHOLDER_DIR)
    env["PROXMOX_MCP_CONFIG"] = str(config)
    env["LOG_FILE"] = str(tmp_path / "proxmox_mcp.log")

    async def run() -> list[str]:
        transport = StdioTransport(command=entry["command"], args=args, env=env, cwd=str(tmp_path))
        async with Client(transport, timeout=60) as client:
            return sorted(t.name for t in await client.list_tools())

    names = asyncio.run(asyncio.wait_for(run(), timeout=120))
    assert names == GOLDEN_NAMES
    assert len(names) == 27
