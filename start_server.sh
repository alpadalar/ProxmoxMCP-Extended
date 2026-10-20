#!/usr/bin/env bash
# Start the ProxmoxMCP server on stdio (for MCP clients that launch it as a subprocess).
# Configuration: PROXMOX_MCP_CONFIG (default proxmox-config/config.json).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

CONFIG_FILE="${PROXMOX_MCP_CONFIG:-proxmox-config/config.json}"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed (https://docs.astral.sh/uv/); run 'uv sync' after installing it" >&2
    exit 1
fi
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Configuration file not found: $CONFIG_FILE" >&2
    echo "Copy proxmox-config/config.example.json to proxmox-config/config.json and edit it" >&2
    exit 1
fi

exec uv run proxmox-mcp --config "$CONFIG_FILE"
