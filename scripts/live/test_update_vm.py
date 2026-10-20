#!/usr/bin/env python3
"""
Test script for VM update functionality.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from proxmox_mcp.config.loader import load_config
from proxmox_mcp.core.proxmox import ProxmoxManager
from proxmox_mcp.tools.vm import VMTools


def test_update_vm():
    """Test VM update functionality."""

    # Load configuration
    config = load_config("proxmox-config/config.json")

    # Initialize Proxmox API
    proxmox_manager = ProxmoxManager(config.proxmox, config.auth)
    proxmox_api = proxmox_manager.get_api()

    # Initialize VM tools
    vm_tools = VMTools(proxmox_api)

    # Test parameters
    node = "pve"
    vmid = "100"  # cloudpanel VM
    new_memory = 6144  # 6GB

    print("🔄 Testing VM update functionality...")
    print("📋 Parameters:")
    print(f"  • Node: {node}")
    print(f"  • VM ID: {vmid}")
    print(f"  • New Memory: {new_memory} MB ({new_memory / 1024:.1f} GB)")
    print()

    try:
        # Get current VM status
        print("📊 Current VM status:")
        current_usage = vm_tools.get_vm_usage(node, vmid)
        print(current_usage[0].text)
        print()

        # Try to update VM
        print("🔄 Updating VM...")
        result = vm_tools.update_vm(node, vmid, memory=new_memory)
        print(result[0].text)

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    return True


if __name__ == "__main__":
    success = test_update_vm()
    if success:
        print("\n✅ Test completed successfully!")
    else:
        print("\n❌ Test failed!")
        sys.exit(1)
