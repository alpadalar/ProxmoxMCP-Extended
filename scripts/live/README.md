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

### 🌐 API Tests
- **`test_openapi.py`** - OpenAPI service comprehensive test
  - Test all API endpoints
  - Include VM creation, power management and other functionalities
  - Verify integration with Open WebUI

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

#### 3. Test OpenAPI Service
```bash
uv run python scripts/live/test_openapi.py
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
- [x] OpenAPI service integration
- [x] Error handling verification

### 🎯 Test Scenarios
- **Basic functionality**: Connection, authentication, basic operations
- **VM lifecycle**: Create, start, stop, delete
- **Storage compatibility**: LVM, filesystem storage
- **API integration**: REST API calls and responses
- **Error recovery**: Exception handling

## 🔗 Related Documentation

- **Main project documentation**: [../README.md](../../README.md)
- **VM creation guide**: [../VM_CREATION_GUIDE.md](../../VM_CREATION_GUIDE.md)
- **OpenAPI deployment**: [../OPENAPI_DEPLOYMENT.md](../../OPENAPI_DEPLOYMENT.md)
- **Quick deployment**: [../QUICK_DEPLOY_8811.md](../../QUICK_DEPLOY_8811.md)

## 📊 Test Results Examples

### Success Cases
```
✅ VM 995: Created successfully (local-lvm, raw)
✅ VM 996: Created successfully (vm-storage, raw)  
✅ VM 998: Created successfully (local-lvm, raw)
✅ VM 999: Created successfully (local-lvm, raw)
```

### API Endpoint Verification
```
✅ get_nodes: 200 - 134 chars
✅ get_vms: 200 - 1843 chars
✅ create_vm: 200 - VM created successfully
✅ start_vm: 200 - VM started successfully
```

## 🛠️ Troubleshooting

If tests fail, please check:

1. **Configuration file**: Whether `proxmox-config/config.json` is correct
2. **Network connection**: Whether Proxmox server is reachable
3. **Authentication info**: Whether API token is valid
4. **Service status**: Whether OpenAPI service is running on port 8811

## 📝 Contributing Guidelines

When adding new tests, please:

1. Use descriptive filenames (e.g., `test_function_name.py`)
2. Include detailed docstrings
3. Add appropriate error handling
4. Update this README file

---

**Last Updated**: August 2025
**Maintainer**: Alperen Adalar <alp.adalar@gmail.com>