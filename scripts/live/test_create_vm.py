#!/usr/bin/env python3
"""
Test VM creation functionality
"""

import os
import sys


def test_create_vm():
    """Test creating VM - 1 CPU, 2GB RAM, 10GB storage"""

    # Set configuration
    os.environ["PROXMOX_MCP_CONFIG"] = "proxmox-config/config.json"

    try:
        from proxmox_mcp.config.loader import load_config
        from proxmox_mcp.core.proxmox import ProxmoxManager
        from proxmox_mcp.tools.vm import VMTools

        config = load_config("proxmox-config/config.json")
        manager = ProxmoxManager(config.proxmox, config.auth)
        api = manager.get_api()

        vm_tools = VMTools(api)

        print("🎉 Test creating new VM - user requested configuration")
        print("=" * 60)
        print("Configuration:")
        print("  • CPU: 1 core")
        print("  • RAM: 2 GB (2048 MB)")
        print("  • Storage: 10 GB")
        print("  • VM ID: 999 (test purpose)")
        print("  • Name: test-vm-demo")
        print()

        # Find an available VM ID
        vmid = "999"

        # Check if VM ID already exists
        try:
            api.nodes("pve").qemu(vmid).config.get()
            print(f"⚠️ VM {vmid} already exists, will try VM ID 998")
            vmid = "998"
            api.nodes("pve").qemu(vmid).config.get()
            print(f"⚠️ VM {vmid} also exists, will try VM ID 997")
            vmid = "997"
        except Exception:
            print(f"✅ VM ID {vmid} is available")

        # Create VM
        result = vm_tools.create_vm(
            node="pve",
            vmid=vmid,
            name="test-vm-demo",
            cpus=1,
            memory=2048,  # 2GB in MB
            disk_size=10,  # 10GB
        )

        for content in result:
            print(content.text)

        return True

    except Exception as e:
        print(f"❌ Creation failed: {e}")
        return False


def test_list_vms():
    """Test listing VMs to confirm successful creation"""

    os.environ["PROXMOX_MCP_CONFIG"] = "proxmox-config/config.json"

    try:
        from proxmox_mcp.config.loader import load_config
        from proxmox_mcp.core.proxmox import ProxmoxManager
        from proxmox_mcp.tools.vm import VMTools

        config = load_config("proxmox-config/config.json")
        manager = ProxmoxManager(config.proxmox, config.auth)
        api = manager.get_api()

        vm_tools = VMTools(api)

        print("\n🔍 List all VMs to confirm creation results:")
        print("=" * 40)

        result = vm_tools.get_vms()
        for content in result:
            # Only show newly created VM information
            lines = content.text.split("\n")
            for line in lines:
                if "test-vm-demo" in line or "VM 99" in line:
                    print(line)

        return True

    except Exception as e:
        print(f"❌ List query failed: {e}")
        return False


if __name__ == "__main__":
    print("🔍 Test VM creation functionality")
    print("=" * 50)

    success = test_create_vm()

    if success:
        print("\n✅ Creation test completed")
        # Test listing VMs
        test_list_vms()
    else:
        print("\n❌ Creation test failed")
        sys.exit(1)
