#!/usr/bin/env bash
# Start the ProxmoxMCP HTTP server (streamable HTTP, API-key auth required).
#
# Settings (environment): MCP_HTTP_HOST (default 127.0.0.1), MCP_HTTP_PORT (default 8812),
# MCP_HTTP_PATH (default /proxmox-mcp), PROXMOX_MCP_CONFIG (default proxmox-config/config.json).
# API key digests come from PROXMOX_MCP_API_KEY_HASHES or `http.api_key_digests` in the config:
#   echo -n 'my-secret-key' | uv run python -m proxmox_mcp.auth.apikey
#   export PROXMOX_MCP_API_KEY_HASHES=<digest>
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

HOST="${MCP_HTTP_HOST:-127.0.0.1}"
PORT="${MCP_HTTP_PORT:-8812}"
PATH_PREFIX="${MCP_HTTP_PATH:-/proxmox-mcp}"
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

echo "Starting ProxmoxMCP HTTP server on http://${HOST}:${PORT}${PATH_PREFIX}"
echo "Authentication: API key (Authorization: Bearer <key> or X-API-Key: <key>)"
echo "Press Ctrl+C to stop"

exec uv run python -m proxmox_mcp.server_http \
    --host "$HOST" \
    --port "$PORT" \
    --path "$PATH_PREFIX" \
    --config "$CONFIG_FILE"
