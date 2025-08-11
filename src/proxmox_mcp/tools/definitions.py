"""
Tool descriptions for Proxmox MCP tools.
"""

# Node tool descriptions
GET_NODES_DESC = """List all nodes in the Proxmox cluster with their status, CPU, memory, and role information.

Example:
{"node": "pve1", "status": "online", "cpu_usage": 0.15, "memory": {"used": "8GB", "total": "32GB"}}"""

GET_NODE_STATUS_DESC = """Get detailed status information for a specific Proxmox node.

Parameters:
node* - Name/ID of node to query (e.g. 'pve1')

Example:
{"cpu": {"usage": 0.15}, "memory": {"used": "8GB", "total": "32GB"}}"""

# VM tool descriptions
GET_VMS_DESC = """List all virtual machines across the cluster with their status and resource usage.

Example:
{"vmid": "100", "name": "ubuntu", "status": "running", "cpu": 2, "memory": 4096}"""

CREATE_SNAPSHOT_DESC = """Create a snapshot for a virtual machine.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')
name* - Snapshot name (e.g. 'pre-upgrade')
description - Optional description for the snapshot
vmstate - Include VM memory state (optional, default: false)

Example:
Create snapshot 'pre-upgrade' for VM 100 on node pve"""

ROLLBACK_SNAPSHOT_DESC = """Rollback a virtual machine to a specific snapshot.

⚠️ WARNING: Rolling back will discard the current VM state!

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')
name* - Snapshot name to rollback to (e.g. 'pre-upgrade')

Example:
Rollback VM 100 on node pve to snapshot 'pre-upgrade'"""

GET_VM_USAGE_DESC = """Get real-time resource usage details for a specific VM.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')

Example:
{\"cpu_percent\": 23.5, \"memory\": {\"used\": \"1.2GB\", \"total\": \"4.0GB\", \"percent\": 30.0}, \"disk\": {\"used\": \"10GB\", \"total\": \"50GB\"}}"""

CREATE_VM_DESC = """Create a new virtual machine with specified configuration.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - New VM ID number (e.g. '200', '300')
name* - VM name (e.g. 'my-new-vm', 'web-server')
cpus* - Number of CPU cores (e.g. 1, 2, 4)
memory* - Memory size in MB (e.g. 2048 for 2GB, 4096 for 4GB)
disk_size* - Disk size in GB (e.g. 10, 20, 50)
storage - Storage name (optional, will auto-detect if not specified)
ostype - OS type (optional, default: 'l26' for Linux)
iso_name - ISO file name to mount (optional, e.g. 'debian-12.iso')
iso_storage - Storage name where the ISO is located (optional)

Examples:
- Create VM with 1 CPU, 2GB RAM, 10GB disk: node='pve', vmid='200', name='test-vm', cpus=1, memory=2048, disk_size=10
- Create VM with 2 CPUs, 4GB RAM, 20GB disk: node='pve', vmid='201', name='web-server', cpus=2, memory=4096, disk_size=20
- Create VM and mount ISO: node='pve', vmid='202', name='iso-vm', cpus=2, memory=4096, disk_size=20, iso_name='debian-12.iso'"""

EXECUTE_VM_COMMAND_DESC = """Execute commands in a VM via QEMU guest agent.

Parameters:
node* - Host node name (e.g. 'pve1')
vmid* - VM ID number (e.g. '100')
command* - Shell command to run (e.g. 'uname -a')

Example:
{"success": true, "output": "Linux vm1 5.4.0", "exit_code": 0}"""

# VM Power Management tool descriptions
START_VM_DESC = """Start a virtual machine.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')

Example:
Power on VPN-Server with ID 101 on node pve"""

STOP_VM_DESC = """Stop a virtual machine (force stop).

Parameters:
node* - Host node name (e.g. 'pve')  
vmid* - VM ID number (e.g. '101')

Example:
Force stop VPN-Server with ID 101 on node pve"""

SHUTDOWN_VM_DESC = """Shutdown a virtual machine gracefully.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')

Example:
Gracefully shutdown VPN-Server with ID 101 on node pve"""

RESET_VM_DESC = """Reset (restart) a virtual machine.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')

Example:
Reset VPN-Server with ID 101 on node pve"""

DELETE_VM_DESC = """Delete/remove a virtual machine completely.

⚠️ WARNING: This operation permanently deletes the VM and all its data!

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '998')
force - Force deletion even if VM is running (optional, default: false)

This will permanently remove:
- VM configuration
- All virtual disks
- All snapshots
- Cannot be undone!

Example:
Delete test VM with ID 998 on node pve"""

# Container tool descriptions
GET_CONTAINERS_DESC = """List all LXC containers across the cluster with their status and configuration.

Example:
{"vmid": "200", "name": "nginx", "status": "running", "template": "ubuntu-20.04"}"""

# Storage tool descriptions
GET_STORAGE_DESC = """List storage pools across the cluster with their usage and configuration.

Example:
{"storage": "local-lvm", "type": "lvm", "used": "500GB", "total": "1TB"}"""

# Cluster tool descriptions
GET_CLUSTER_STATUS_DESC = """Get overall Proxmox cluster health and configuration status.

Example:
{"name": "proxmox", "quorum": "ok", "nodes": 3, "ha_status": "active"}"""

# System tool descriptions
HEALTH_DESC = """Health check endpoint.

Returns the server health status. If startup tests were run and passed,
status will be 'ok'; otherwise returns 'degraded' or 'unknown'.

Example:
{"status": "ok", "tests_passed": true, "details": "Startup tests passed"}"""
