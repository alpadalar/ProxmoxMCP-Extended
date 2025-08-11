#!/bin/bash
# ProxmoxMCP HTTP Server startup script
# Start MCP server with HTTP transport (streamable)

# Get host and port from environment variables or use defaults
HOST=${MCP_HTTP_HOST:-"0.0.0.0"}
PORT=${MCP_HTTP_PORT:-"8812"}
PATH_PREFIX=${MCP_HTTP_PATH:-"/mcp"}
CONFIG_FILE=${PROXMOX_MCP_CONFIG:-"proxmox-config/config.json"}

echo "🛰️ Starting ProxmoxMCP HTTP Server..."
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment does not exist, please run installation steps first"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check configuration file
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Configuration file does not exist: $CONFIG_FILE"
    echo "Please ensure the configuration file is properly set up"
    exit 1
fi

echo "✅ Configuration file: $CONFIG_FILE"
echo "✅ Virtual environment activated"
echo ""
echo "🚀 Starting HTTP MCP server..."
echo "🌐 Service address: http://${HOST}:${PORT}${PATH_PREFIX}"
echo "📡 Protocol: MCP over HTTP (streamable)"
echo "🔒 Authentication: Django Integration"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
echo "💡 Usage with Cursor/VS Code:"
echo "   Add HTTP MCP server configuration to your editor"
echo "   URL: http://${HOST}:${PORT}${PATH_PREFIX}"
echo "   Headers: Authorization: Bearer <your-token>"
echo ""

# Set environment variables
export PROXMOX_MCP_CONFIG="$(pwd)/$CONFIG_FILE"

# Start HTTP server with Python module
python -m proxmox_mcp.server_http \
    --host "$HOST" \
    --port "$PORT" \
    --path "$PATH_PREFIX" \
    --config "$CONFIG_FILE"
