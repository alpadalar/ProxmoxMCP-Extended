# ProxmoxMCP Live Cluster Scripts

These scripts require a live Proxmox cluster and are run manually. They are NOT part of the pytest suite (`testpaths = ["tests"]`) and must never run in CI.

Example: `uv run python scripts/live/test_vm_power.py`

## 📁 File Description

### 🔧 VM Management Tests
- **`test_vm_power.py`** - VM power management functionality test
  - Test VM start, stop, restart and other operations
  - Check VM status and available operations

- **`test_vm_start.py`** - VM startup functionality specific test
  - Dedicated test for VM startup functionality
  - Suitable for single VM startup testing

- **`test_create_vm.py`** - VM creation functionality test
  - Test complete workflow of creating new virtual machines
  - Verify 1 CPU core + 2GB RAM + 10GB storage configuration

### HTTP server test
- **`test_http_server.py`** - exercises a running HTTP MCP server (needs `PROXMOX_MCP_TEST_KEY`,
  the plain API key whose sha256 digest the server was started with)

## 🚀 Usage

### Environment Setup
```bash
# Activate virtual environment
source .venv/bin/activate

# Set configuration path (if needed)
export PROXMOX_MCP_CONFIG=proxmox-config/config.json
```

### Running Tests

#### 1. Test VM Power Management
```bash
uv run python scripts/live/test_vm_power.py
```

#### 2. Test VM Creation
```bash
uv run python scripts/live/test_create_vm.py
```

#### 3. Test the HTTP server
```bash
PROXMOX_MCP_TEST_KEY=<your key> uv run python scripts/live/test_http_server.py
```

#### 4. Test VM Startup
```bash
uv run python scripts/live/test_vm_start.py
```

## 📋 Test Coverage

### ✅ Tested Features
- [x] VM list retrieval
- [x] VM status query
- [x] VM power management (start/stop/restart/shutdown)
- [x] VM creation (support custom CPU/memory/storage)
- [x] Storage type auto-detection
- [x] Disk format intelligent selection
- [x] Error handling verification

### 🎯 Test Scenarios
- **Basic functionality**: Connection, authentication, basic operations
- **VM lifecycle**: Create, start, stop, delete
- **Storage compatibility**: LVM, filesystem storage
- **HTTP integration**: MCP over HTTP with API-key auth
- **Error recovery**: Exception handling

## 🔗 Related Documentation

- **Main project documentation**: [../README.md](../../README.md)
- **Changelog**: [../CHANGELOG.md](../../CHANGELOG.md)

## 📊 Test Results Examples

### Success Cases
```
✅ VM 995: Created successfully (local-lvm, raw)
✅ VM 996: Created successfully (vm-storage, raw)  
✅ VM 998: Created successfully (local-lvm, raw)
✅ VM 999: Created successfully (local-lvm, raw)
```

## 🛠️ Troubleshooting

If tests fail, please check:

1. **Configuration file**: Whether `proxmox-config/config.json` is correct
2. **Network connection**: Whether Proxmox server is reachable
3. **Authentication info**: Whether API token is valid
4. **Service status**: Whether the HTTP server is running (`/health`)

## 📝 Contributing Guidelines

When adding new tests, please:

1. Use descriptive filenames (e.g., `test_function_name.py`)
2. Include detailed docstrings
3. Add appropriate error handling
4. Update this README file

---

**Last Updated**: August 2025
**Maintainer**: Alperen Adalar <alp.adalar@gmail.com>