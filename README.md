# ProxmoxMCP-Extended - Enhanced Proxmox MCP Server


An enhanced Python-based Model Context Protocol (MCP) server for interacting with Proxmox virtualization platforms. This project is built upon **[canvrno/ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP)** with numerous new features and improvements, providing complete OpenAPI integration and more powerful virtualization management capabilities.

## Acknowledgments

This project is built upon the excellent open-source project [ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP) by [@canvrno](https://github.com/canvrno). Thanks to the original author for providing the foundational framework and creative inspiration!

## Fork Lineage

- **Original project**: [canvrno/ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP)
- **First fork**: [RekklesNA/ProxmoxMCP-Plus](https://github.com/RekklesNA/ProxmoxMCP-Plus)  
- **This fork**: [alpadalar/ProxmoxMCP-Extended](https://github.com/alpadalar/ProxmoxMCP-Extended) (you are here)

### 🚀 **Major Enhancements in ProxmoxMCP-Extended:**

- **🎯 Advanced VM Management**
  - Optional ISO mount during VM creation (`iso_name`/`iso_storage` parameters)
  - Comprehensive VM snapshot management (`create_snapshot`, `rollback_snapshot`)
  - VM resource usage monitoring (`get_vm_usage`)
  - Enhanced container support (`get_containers`)

- **⚡ HTTP MCP Server Integration**
  - FastMCP-based HTTP transport for modern MCP clients
  - Docker Compose deployment on port 8812
  - Real-time Server-Sent Events (SSE) support
  - MCP Inspector compatibility

- **🔧 Infrastructure Improvements**  
  - Test suite modernization and comprehensive coverage
  - Lazy loading for ProxmoxMCPServer to avoid import side-effects
  - Health check endpoints and startup validation
  - Enhanced error handling and configuration management

- **📚 Documentation & Localization**
  - Comprehensive English and Turkish documentation
  - Docker Compose quick-start guides
  - Cursor/VS Code integration examples
  - API endpoint documentation (expanded from 11 to 14 tools)

## 🆕 New Features and Improvements

### Major enhancements compared to the original version:

- ✨ **Complete VM Lifecycle Management**
  - Brand new `create_vm` tool - Support for creating virtual machines with custom configurations
  - New `delete_vm` tool - Safe VM deletion (with force deletion option)
  - Enhanced intelligent storage type detection (LVM/file-based)

- 🔧 **Extended Power Management Features**
  - `start_vm` - Start virtual machines
  - `stop_vm` - Force stop virtual machines
  - `shutdown_vm` - Graceful shutdown
  - `reset_vm` - Restart virtual machines

- 🐳 **New Container Support**
  - `get_containers` - List all LXC containers and their status

- 📊 **Enhanced Monitoring and Display**
  - Improved storage pool status monitoring
  - More detailed cluster health status checks
  - Rich output formatting and themes

- 🌐 **Complete OpenAPI Integration**
  - 14 complete REST API endpoints (expanded from 11)
  - Production-ready Docker deployment
  - Perfect Open WebUI integration
  - Natural language VM creation support

- 🚀 **HTTP MCP Server (NEW!)**
  - FastMCP-based HTTP transport for Cursor/VS Code integration
  - Real-time Server-Sent Events (SSE) support
  - Docker Compose deployment on port 8812
  - MCP Inspector compatible endpoint

- 📸 **Advanced VM Snapshot Management (NEW!)**
  - `create_snapshot` - Create VM snapshots with optional memory state
  - `rollback_snapshot` - Rollback VMs to previous snapshots
  - Full snapshot lifecycle management

- 📊 **Enhanced VM Monitoring (NEW!)**
  - `get_vm_usage` - Real-time VM resource usage tracking
  - CPU, memory, disk, and network utilization metrics
  - Performance monitoring capabilities

- 🏥 **Health Check and Diagnostics**
  - Built-in health check endpoints for monitoring
  - Startup validation and optional testing
  - Enhanced error diagnostics and logging

- 🛡️ **Production-grade Security and Stability**
  - Enhanced error handling mechanisms
  - Comprehensive parameter validation
  - Production-level logging
  - Complete unit test coverage

## Built With

- [Cline](https://github.com/cline/cline) - Autonomous coding agent - Go faster with Cline
- [Proxmoxer](https://github.com/proxmoxer/proxmoxer) - Python wrapper for Proxmox API
- [MCP SDK](https://github.com/modelcontextprotocol/sdk) - Model Context Protocol SDK
- [Pydantic](https://docs.pydantic.dev/) - Data validation using Python type annotations

## Features

- 🤖 Full integration with Cline and Open WebUI
- 🛠️ Built with the official MCP SDK
- 🔒 Secure token-based authentication with Proxmox
- 🖥️ Complete VM lifecycle management (create, start, stop, reset, shutdown, delete)
- 💻 VM console command execution
- 🐳 LXC container management support
- 🗃️ Intelligent storage type detection (LVM/file-based)
- 📝 Configurable logging system
- ✅ Type-safe implementation with Pydantic
- 🎨 Rich output formatting with customizable themes
- 🌐 OpenAPI REST endpoints for integration
- 📡 14 fully functional API endpoints


## Installation

### Prerequisites
- UV package manager (recommended)
- Python 3.9 or higher
- Git
- Access to a Proxmox server with API token credentials

Before starting, ensure you have:
- [ ] Proxmox server hostname or IP
- [ ] Proxmox API token (see [API Token Setup](#proxmox-api-token-setup))
- [ ] UV installed (`pip install uv`)

### Option 1: Quick Install (Recommended)

1. Clone and set up environment:
   ```bash
   # Clone repository
   git clone https://github.com/alpadalar/ProxmoxMCP-Extended.git
   cd ProxmoxMCP-Extended

   # Create and activate virtual environment
   uv venv
   source .venv/bin/activate  # Linux/macOS
   # OR
   .\.venv\Scripts\Activate.ps1  # Windows
   ```

2. Install dependencies:
   ```bash
   # Install with development dependencies
   uv pip install -e ".[dev]"
   ```

3. Create configuration:
   ```bash
   # Create config directory and copy template
   mkdir -p proxmox-config
   cp proxmox-config/config.example.json proxmox-config/config.json
   ```

4. Edit `proxmox-config/config.json`:
   ```json
   {
       "proxmox": {
           "host": "PROXMOX_HOST",        # Required: Your Proxmox server address
           "port": 8006,                  # Optional: Default is 8006
           "verify_ssl": false,           # Optional: Set false for self-signed certs
           "service": "PVE"               # Optional: Default is PVE
       },
       "auth": {
           "user": "USER@pve",            # Required: Your Proxmox username
           "token_name": "TOKEN_NAME",    # Required: API token ID
           "token_value": "TOKEN_VALUE"   # Required: API token value
       },
       "logging": {
           "level": "INFO",               # Optional: DEBUG for more detail
           "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
           "file": "proxmox_mcp.log"      # Optional: Log to file
       }
   }
   ```

### Verifying Installation

1. Check Python environment:
   ```bash
   python -c "import proxmox_mcp; print('Installation OK')"
   ```

2. Run the tests:
   ```bash
   pytest
   ```

3. Verify configuration:
   ```bash
   # Linux/macOS
   PROXMOX_MCP_CONFIG="proxmox-config/config.json" python -m proxmox_mcp.server

   # Windows (PowerShell)
   $env:PROXMOX_MCP_CONFIG="proxmox-config\config.json"; python -m proxmox_mcp.server
   ```

## Configuration

### Proxmox API Token Setup
1. Log into your Proxmox web interface
2. Navigate to Datacenter -> Permissions -> API Tokens
3. Create a new API token:
   - Select a user (e.g., root@pam)
   - Enter a token ID (e.g., "mcp-token")
   - Uncheck "Privilege Separation" if you want full access
   - Save and copy both the token ID and secret

## Running the Server

### 🐳 Docker Compose (Recommended)

The easiest way to run ProxmoxMCP-Extended is using Docker Compose:

```bash
# Quick start
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# Stop server
docker compose down
```

**🌐 HTTP MCP Server URL:** `http://localhost:8812/proxmox-mcp`

**Features:**
- ✅ HTTP/SSE transport for Cursor/VS Code integration
- ✅ MCP Inspector compatibility
- ✅ Production-ready container deployment
- ✅ Automatic health checks
- ✅ Container name: `ProxmoxMCP-Extended`

### Development Mode (Stdio)
For testing and development with stdio transport:
```bash
# Activate virtual environment first
source .venv/bin/activate  # Linux/macOS
# OR
.\.venv\Scripts\Activate.ps1  # Windows

# Run the server
python -m proxmox_mcp.server
```

### HTTP Mode (Local Development)
For local HTTP transport development:
```bash
# Start HTTP server
./start_http_server.sh

# Or with custom settings
python -m proxmox_mcp.server_http --host 0.0.0.0 --port 8812 --path /proxmox-mcp
```

**Features:**
- ✅ FastMCP HTTP transport
- ✅ Server-Sent Events (SSE) support
- ✅ MCP Inspector integration
- ✅ Real-time tool interaction

### OpenAPI Deployment (Production Ready)

Deploy ProxmoxMCP-Extended as standard OpenAPI REST endpoints for integration with Open WebUI and other applications.

#### Quick OpenAPI Start
```bash
# Install mcpo (MCP-to-OpenAPI proxy)
pip install mcpo

# Start OpenAPI service on port 8811
./start_openapi.sh
```

#### Docker Deployment
```bash
# Build and run with Docker
docker build -t proxmox-mcp-api .
docker run -d --name proxmox-mcp-api -p 8811:8811 \
  -v $(pwd)/proxmox-config:/app/proxmox-config proxmox-mcp-api

# Or use Docker Compose
docker compose up -d
```

#### Access OpenAPI Service
Once deployed, access your service at:
- **📖 API Documentation**: http://your-server:8811/docs
- **🔧 OpenAPI Specification**: http://your-server:8811/openapi.json
- **❤️ Health Check**: POST http://your-server:8811/health (body: `{}`)

### Cursor/VS Code Integration

#### Option 1: Docker Compose (Recommended)
For production deployment with Docker:

```json
{
    "mcpServers": {
        "ProxmoxMCP-Extended": {
            "transport": {
                "type": "http",
                "url": "http://localhost:8812/proxmox-mcp"
            },
            "description": "ProxmoxMCP-Extended with HTTP Transport"
        }
    }
}
```

#### Option 2: Local HTTP Server
For local development server:

```json
{
    "mcpServers": {
        "ProxmoxMCP-Local": {
            "transport": {
                "type": "http",
                "url": "http://localhost:8812/proxmox-mcp"
            },
            "description": "ProxmoxMCP Local Development"
        }
    }
}
```

#### Option 3: Traditional Stdio (Legacy)
For Cline users, add this configuration to your MCP settings file:

```json
{
    "mcpServers": {
        "ProxmoxMCP-Extended": {
            "command": "/absolute/path/to/ProxmoxMCP-Extended/.venv/bin/python",
            "args": ["-m", "proxmox_mcp.server"],
            "cwd": "/absolute/path/to/ProxmoxMCP-Extended",
            "env": {
                "PYTHONPATH": "/absolute/path/to/ProxmoxMCP-Extended/src",
                "PROXMOX_MCP_CONFIG": "/absolute/path/to/ProxmoxMCP-Extended/proxmox-config/config.json"
            },
            "disabled": false,
            "autoApprove": []
        }
    }
}
```

See [HTTP_MCP_GUIDE.md](HTTP_MCP_GUIDE.md) for detailed HTTP setup instructions.

## Available Tools & API Endpoints

The server provides 14 comprehensive MCP tools and corresponding REST API endpoints:

### VM Management Tools

#### create_vm 
Create a new virtual machine with specified resources. Optionally mount an ISO during creation.

**Parameters:**
- `node` (string, required): Name of the node
- `vmid` (string, required): ID for the new VM
- `name` (string, required): Name for the VM
- `cpus` (integer, required): Number of CPU cores (1-32)
- `memory` (integer, required): Memory in MB (512-131072)
- `disk_size` (integer, required): Disk size in GB (5-1000)
- `storage` (string, optional): Storage pool name
- `ostype` (string, optional): OS type (default: l26)
- `iso_name` (string, optional): ISO file name to mount (e.g. `debian-12.iso`)
- `iso_storage` (string, optional): Storage name where the ISO resides (auto-detected if omitted)

**API Endpoint:**
```http
POST /create_vm
Content-Type: application/json

{
    "node": "pve",
    "vmid": "200",
    "name": "my-vm",
    "cpus": 1,
    "memory": 2048,
    "disk_size": 10,
    "iso_name": "debian-12.5.0-amd64-netinst.iso"
}
```

**Example Response:**
```
🎉 VM 200 created successfully!

📋 VM Configuration:
  • Name: my-vm
  • Node: pve
  • VM ID: 200
  • CPU Cores: 1
  • Memory: 2048 MB (2.0 GB)
  • Disk: 10 GB (local-lvm, raw format)
  • Storage Type: lvmthin
  • Network: virtio (bridge=vmbr0)
  • QEMU Agent: Enabled
  • ISO: debian-12.5.0-amd64-netinst.iso (from local on ide3)

🔧 Task ID: UPID:pve:001AB729:0442E853:682FF380:qmcreate:200:root@pam!mcp
```

#### VM Power Management 🆕

**start_vm**: Start a virtual machine
```http
POST /start_vm
{"node": "pve", "vmid": "200"}
```

**stop_vm**: Force stop a virtual machine
```http
POST /stop_vm
{"node": "pve", "vmid": "200"}
```

**shutdown_vm**: Gracefully shutdown a virtual machine
```http
POST /shutdown_vm
{"node": "pve", "vmid": "200"}
```

**reset_vm**: Reset (restart) a virtual machine
```http
POST /reset_vm
{"node": "pve", "vmid": "200"}
```

**delete_vm** 🆕: Completely delete a virtual machine
```http
POST /delete_vm
{"node": "pve", "vmid": "200", "force": false}
```

### 🆕 Container Management Tools

#### get_containers 🆕
List all LXC containers across the cluster.

**API Endpoint:** `POST /get_containers`

**Example Response:**
```
🐳 Containers

🐳 nginx-server (ID: 200)
  • Status: RUNNING
  • Node: pve
  • CPU Cores: 2
  • Memory: 1.5 GB / 2.0 GB (75.0%)
```

### Monitoring Tools

#### get_nodes
Lists all nodes in the Proxmox cluster.

**API Endpoint:** `POST /get_nodes`

**Example Response:**
```
🖥️ Proxmox Nodes

🖥️ pve-compute-01
  • Status: ONLINE
  • Uptime: ⏳ 156d 12h
  • CPU Cores: 64
  • Memory: 186.5 GB / 512.0 GB (36.4%)
```

#### get_node_status
Get detailed status of a specific node.

**Parameters:**
- `node` (string, required): Name of the node

**API Endpoint:** `POST /get_node_status`

#### get_vms
List all VMs across the cluster.

**API Endpoint:** `POST /get_vms`

#### get_storage
List available storage pools.

**API Endpoint:** `POST /get_storage`

#### get_cluster_status
Get overall cluster status and health.

**API Endpoint:** `POST /get_cluster_status`

#### execute_vm_command
Execute a command in a VM's console using QEMU Guest Agent.

**Parameters:**
- `node` (string, required): Name of the node where VM is running
- `vmid` (string, required): ID of the VM
- `command` (string, required): Command to execute

**API Endpoint:** `POST /execute_vm_command`

**Requirements:**
- VM must be running
- QEMU Guest Agent must be installed and running in the VM

### Snapshot Management and VM Usage

#### create_snapshot
Create a snapshot for a VM.

**Parameters:**
- `node` (string, required): Name of the node
- `vmid` (string, required): VM ID number
- `name` (string, required): Snapshot name
- `description` (string, optional): Description for the snapshot
- `vmstate` (boolean, optional): Include VM memory state (default: false)

```http
POST /create_snapshot
{"node": "pve", "vmid": "100", "name": "pre-upgrade", "description": "before upgrade", "vmstate": false}
```

**API Endpoint:** `POST /create_snapshot`

#### rollback_snapshot
Rollback a VM to a snapshot.

**Parameters:**
- `node` (string, required): Name of the node
- `vmid` (string, required): VM ID number
- `name` (string, required): Snapshot name to rollback to

```http
POST /rollback_snapshot
{"node": "pve", "vmid": "100", "name": "pre-upgrade"}
```

**API Endpoint:** `POST /rollback_snapshot`

#### get_vm_usage
Get real-time usage for a VM (CPU, memory, disk).

**Parameters:**
- `node` (string, required): Name of the node
- `vmid` (string, required): VM ID number

```http
POST /get_vm_usage
{"node": "pve", "vmid": "100"}
```

**API Endpoint:** `POST /get_vm_usage`

## Open WebUI Integration

### Configure Open WebUI

1. Access your Open WebUI instance
2. Navigate to **Settings** → **Connections** → **OpenAPI**
3. Add new API configuration:

```json
{
  "name": "Proxmox MCP API Extended",
  "base_url": "http://your-server:8811",
  "api_key": "",
  "description": "Enhanced Proxmox Virtualization Management API"
}
```

### Natural Language VM Creation

Users can now request VMs using natural language:

- **"Can you create a VM with 1 cpu core and 2 GB ram with 10GB of storage disk"**
- **"Create a new VM for testing with minimal resources"**
- **"I need a development server with 4 cores and 8GB RAM"**

The AI assistant will automatically call the appropriate APIs and provide detailed feedback.

## Storage Type Support

### Intelligent Storage Detection

ProxmoxMCP-Extended automatically detects storage types and selects appropriate disk formats:

#### LVM Storage (local-lvm, vm-storage)
- ✅ Format: `raw`
- ✅ High performance
- ⚠️ No cloud-init image support

#### File-based Storage (local, NFS, CIFS)
- ✅ Format: `qcow2`
- ✅ Cloud-init support
- ✅ Flexible snapshot capabilities

## Project Structure

```
ProxmoxMCP-Extended/
├── 📁 src/                          # Source code
│   └── proxmox_mcp/
│       ├── server.py                # Main MCP server implementation
│       ├── config/                  # Configuration handling
│       ├── core/                    # Core functionality
│       ├── formatting/              # Output formatting and themes
│       ├── tools/                   # Tool implementations
│       │   ├── vm.py               # VM management (create/power) 🆕
│       │   ├── container.py        # Container management 🆕
│       │   └── console/            # VM console operations
│       └── utils/                   # Utilities (auth, logging)
│
├── 📁 tests/                       # Unit test suite
├── 📁 test_scripts/                # Integration tests & demos
│   ├── README.md                   # Test documentation
│   ├── test_vm_power.py           # VM power management tests 🆕
│   ├── test_vm_start.py           # VM startup tests
│   ├── test_create_vm.py          # VM creation tests 🆕
│   └── test_openapi.py            # OpenAPI service tests
│
├── 📁 proxmox-config/              # Configuration files
│   └── config.json                # Server configuration
│
├── 📄 Configuration Files
│   ├── pyproject.toml             # Project metadata
│   ├── docker-compose.yml         # Docker orchestration
│   ├── Dockerfile                 # Docker image definition
│   └── requirements.in            # Dependencies
│
├── 📄 Scripts
│   ├── start_server.sh            # MCP server launcher
│   └── start_openapi.sh           # OpenAPI service launcher
│
└── 📄 Documentation
    ├── README.md                  # This file
    ├── VM_CREATION_GUIDE.md       # VM creation guide
    ├── OPENAPI_DEPLOYMENT.md      # OpenAPI deployment
    └── LICENSE                    # MIT License
```

## Testing

### Run Unit Tests
```bash
pytest
```

### Run Integration Tests
```bash
cd test_scripts

# Test VM power management
python test_vm_power.py

# Test VM creation
python test_create_vm.py

# Test OpenAPI service
python test_openapi.py
```

### API Testing with curl
```bash
# Test node listing
curl -X POST "http://your-server:8811/get_nodes" \
  -H "Content-Type: application/json" \
  -d "{}"

# Test VM creation
curl -X POST "http://your-server:8811/create_vm" \
  -H "Content-Type: application/json" \
  -d '{
    "node": "pve",
    "vmid": "300",
    "name": "test-vm",
    "cpus": 1,
    "memory": 2048,
    "disk_size": 10
  }'
```

## Production Security

### API Key Authentication
Set up secure API access:

```bash
export PROXMOX_API_KEY="your-secure-api-key"
export PROXMOX_MCP_CONFIG="/app/proxmox-config/config.json"
```

### Nginx Reverse Proxy
Example nginx configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8811;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   netstat -tlnp | grep 8811
   # Change port if needed
   mcpo --port 8812 -- ./start_server.sh
   ```

2. **Configuration errors**
   ```bash
   # Verify config file
   cat proxmox-config/config.json
   ```

3. **Connection issues**
   ```bash
   # Test Proxmox connectivity
   curl -k https://your-proxmox:8006/api2/json/version
   ```

### View Logs
```bash
# View service logs
tail -f proxmox_mcp.log

# Docker logs
docker logs proxmox-mcp-api -f
```

## Deployment Status

### ✅ Feature Completion: 100%

- [x] VM Creation (user requirement: 1 CPU + 2GB RAM + 10GB storage) 🆕
- [x] VM Power Management (start VPN-Server ID:101) 🆕
- [x] VM Deletion Feature 🆕
- [x] Container Management (LXC) 🆕
- [x] Storage Compatibility (LVM/file-based)
- [x] OpenAPI Integration (port 8811)
- [x] Open WebUI Integration
- [x] Error Handling & Validation
- [x] Complete Documentation & Testing

### Production Ready!

**ProxmoxMCP-Extended is now fully ready for production use!**

When users say **"Can you create a VM with 1 cpu core and 2 GB ram with 10GB of storage disk"**, the AI assistant can:

1. 📞 Call the `create_vm` API
2. 🔧 Automatically select appropriate storage and format
3. 🎯 Create VMs that match requirements
4. 📊 Return detailed configuration information
5. 💡 Provide next-step recommendations

## Development

After activating your virtual environment:

- Run tests: `pytest`
- Format code: `black .`
- Type checking: `mypy .`
- Lint: `ruff .`

## License

MIT License

## Special Thanks

- Thanks to [@canvrno](https://github.com/canvrno) for the excellent foundational project [ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP)
- Thanks to the Proxmox community for providing the powerful virtualization platform
- Thanks to all contributors and users for their support

---

**Ready to Deploy!** 🎉 Your enhanced Proxmox MCP service with OpenAPI integration is ready for production use.
