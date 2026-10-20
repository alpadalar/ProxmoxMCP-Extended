"""
Tool descriptions for Proxmox MCP tools.
"""

# Node tool descriptions
GET_NODES_DESC = """List all nodes in the Proxmox cluster with their status, CPU, memory, and \
role information.

Example:
{"node": "pve1", "status": "online", "cpu_usage": 0.15, "memory": {"used": "8GB", "total": \
"32GB"}}"""

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
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). Timing out is not \
a failure: the task is reported as still running

Example:
Create snapshot 'pre-upgrade' for VM 100 on node pve"""

ROLLBACK_SNAPSHOT_DESC = """Rollback a virtual machine to a specific snapshot.

⚠️ WARNING: Rolling back will discard the current VM state!

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')
name* - Snapshot name to rollback to (e.g. 'pre-upgrade')
confirm - Must be true to actually perform the operation; without it only a preview is returned \
(default: false)
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). Timing out is not \
a failure: the task is reported as still running

Example:
Rollback VM 100 on node pve to snapshot 'pre-upgrade'"""

LIST_SNAPSHOTS_DESC = """List the snapshots of a QEMU virtual machine (read-only).

The live-state pseudo entry 'current' is not a snapshot and is omitted. Snapshots are sorted by \
creation time. LXC snapshots are not covered.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')

Example:
List the snapshots of VM 100 on node pve"""

DELETE_SNAPSHOT_DESC = """Delete a snapshot of a QEMU virtual machine.

⚠️ WARNING: Deleting a snapshot is permanent; it can no longer be rolled back to!

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')
name* - Snapshot name to delete (e.g. 'pre-upgrade'); must exist, 'current' is not a snapshot
confirm - Must be true to actually perform the operation; without it only a preview is returned \
(default: false)
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). Timing out is not \
a failure: the task is reported as still running

Only QEMU VMs are supported. Requires policy.allow_destructive.

Example:
Delete snapshot 'pre-upgrade' of VM 100 on node pve"""

LIST_BACKUPS_DESC = """List backup volumes (vzdump archives) stored on a node (read-only inventory).

Without storage, every enabled storage on the node that supports backups is queried; a storage \
that fails is reported under 'skipped' instead of aborting the listing. Results are sorted newest \
first. Restoring or creating backups is not covered.

Parameters:
node* - Host node name (e.g. 'pve'); required because storage content is node-scoped
storage - Storage name to list (optional, e.g. 'local')
vmid - Only backups of this VM/CT ID (optional, e.g. '100')

The token needs Datastore.Audit on /storage/<id>.

Example:
List the backups of VM 100 on node pve"""

START_CONTAINER_DESC = """Start an LXC container.

Parameters:
vmid* - Container ID number (e.g. '200'); the node and the guest type are looked up in the \
cluster on every call
node - Optional consistency check (e.g. 'pve'); must match the node the container currently runs on
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). This is only the \
MCP wait bound and is NOT forwarded to Proxmox; timing out is not a failure: the task is reported \
as still running

QEMU VM ids are refused (use start_vm/stop_vm/shutdown_vm); templates and invisible guests are \
refused too.

Example:
Start container 200"""

STOP_CONTAINER_DESC = """Stop an LXC container immediately (no graceful shutdown).

⚠️ WARNING: Processes are killed and unsaved data may be lost! Use shutdown_container for a \
graceful stop.

Parameters:
vmid* - Container ID number (e.g. '200'); the node and the guest type are looked up in the \
cluster on every call
node - Optional consistency check (e.g. 'pve'); must match the node the container currently runs on
confirm - Must be true to actually perform the operation; without it only a preview is returned \
and nothing is looked up or changed (default: false)
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). This is only the \
MCP wait bound and is NOT forwarded to Proxmox; timing out is not a failure: the task is reported \
as still running

QEMU VM ids are refused (use start_vm/stop_vm/shutdown_vm); templates and invisible guests are \
refused too.

Example:
Stop container 200 (confirm=true)"""

SHUTDOWN_CONTAINER_DESC = """Gracefully shut down an LXC container.

Parameters:
vmid* - Container ID number (e.g. '200'); the node and the guest type are looked up in the \
cluster on every call
node - Optional consistency check (e.g. 'pve'); must match the node the container currently runs on
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). This is only the \
MCP wait bound and is NOT forwarded to Proxmox; timing out is not a failure: the task is reported \
as still running

QEMU VM ids are refused (use start_vm/stop_vm/shutdown_vm); templates and invisible guests are \
refused too.

Example:
Shut down container 200"""

GET_HA_STATUS_DESC = """Get the High Availability (HA) status of the cluster (read-only).

Returns quorum, the HA master, the local resource managers (lrm), the HA services with their \
states and the configured HA resources. 'ha_configured' is false when no service or resource \
exists. HA changes and PVE 9 HA affinity rules are not covered.

Requires Sys.Audit on /.

Example:
Show the HA status of the cluster"""

GET_VM_USAGE_DESC = """Get real-time resource usage details for a specific VM.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')

Example:
{\"cpu_percent\": 23.5, \"memory\": {\"used\": \"1.2GB\", \"total\": \"4.0GB\", \"percent\": \
30.0}, \"disk\": {\"used\": \"10GB\", \"total\": \"50GB\"}}"""

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
- Create VM with 1 CPU, 2GB RAM, 10GB disk: node='pve', vmid='200', name='test-vm', cpus=1, \
memory=2048, disk_size=10
- Create VM with 2 CPUs, 4GB RAM, 20GB disk: node='pve', vmid='201', name='web-server', cpus=2, \
memory=4096, disk_size=20
- Create VM and mount ISO: node='pve', vmid='202', name='iso-vm', cpus=2, memory=4096, \
disk_size=20, iso_name='debian-12.iso'"""

EXECUTE_VM_COMMAND_DESC = """Execute commands in a VM via QEMU guest agent.

Parameters:
node* - Host node name (e.g. 'pve1')
vmid* - VM ID number (e.g. '100')
command* - Program to run, or a command line split into words (e.g. 'uname -a')
args - Optional list of arguments; when given, command is the program (e.g. command='ls', \
args=['-l', '/tmp'])

Notes:
- Disabled unless the server is started with allow_exec (policy.allow_exec / \
PROXMOX_MCP_ALLOW_EXEC / --allow-exec).
- No shell is used. For pipes or redirects pass a shell explicitly, e.g. command='/bin/sh', \
args=['-c', '...'].
- Waits at most policy.exec_timeout_seconds (default 30s); a command that is still running is \
reported as FAILED with exit code unknown (still running in the guest).
- Output per stream is capped at policy.exec_max_output_bytes (default 65536) and marked as \
truncated.
- The QEMU guest agent must be installed and running in the VM.

Example:
{"success": true, "output": "Linux vm1 5.4.0", "exit_code": 0}"""

# VM Power Management tool descriptions
START_VM_DESC = """Start a virtual machine.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). Timing out is not \
a failure: the task is reported as still running

Example:
Power on VPN-Server with ID 101 on node pve"""

STOP_VM_DESC = """Stop a virtual machine (force stop).

Parameters:
node* - Host node name (e.g. 'pve')  
vmid* - VM ID number (e.g. '101')
confirm - Must be true to actually perform the operation; without it only a preview is returned \
(default: false)
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). Timing out is not \
a failure: the task is reported as still running

Example:
Force stop VPN-Server with ID 101 on node pve"""

SHUTDOWN_VM_DESC = """Shutdown a virtual machine gracefully.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). Timing out is not \
a failure: the task is reported as still running

Example:
Gracefully shutdown VPN-Server with ID 101 on node pve"""

RESET_VM_DESC = """Reset (restart) a virtual machine.

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '101')
confirm - Must be true to actually perform the operation; without it only a preview is returned \
(default: false)
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). Timing out is not \
a failure: the task is reported as still running

Example:
Reset VPN-Server with ID 101 on node pve"""

DELETE_VM_DESC = """Delete/remove a virtual machine completely.

⚠️ WARNING: This operation permanently deletes the VM and all its data!

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '998')
force - Force deletion even if VM is running (optional, default: false)
confirm - Must be true to actually perform the operation; without it only a preview is returned \
(default: false)
wait - Wait for the Proxmox task to finish before returning (optional, default: false). A failed \
task raises an error naming the task id; a task that finished with warnings is reported as such, \
not as success
timeout - Seconds to wait when wait=true (optional, default: 30, maximum: 300). Timing out is not \
a failure: the task is reported as still running

This will permanently remove:
- VM configuration
- All virtual disks
- All snapshots
- Cannot be undone!

Example:
Delete test VM with ID 998 on node pve"""

UPDATE_VM_DESC = """Update VM configuration (memory, CPU cores, name).

Parameters:
node* - Host node name (e.g. 'pve')
vmid* - VM ID number (e.g. '100')
memory - New memory size in MB (e.g. 4096 for 4GB, 6144 for 6GB) (optional)
cpus - New number of CPU cores (e.g. 1, 2, 4) (optional)
name - New VM name (optional)

⚠️ NOTE: Resource changes (memory/CPU) require the VM to be stopped first.
If VM is running, this tool will inform you to stop it before updating.

Examples:
- Update memory to 6GB: node='pve', vmid='100', memory=6144
- Update CPU cores to 4: node='pve', vmid='100', cpus=4
- Update both memory and CPU: node='pve', vmid='100', memory=8192, cpus=4
- Rename VM: node='pve', vmid='100', name='new-vm-name'"""

# Container tool descriptions
GET_CONTAINERS_DESC = """List all LXC containers across the cluster with their status and \
configuration.

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


# Task tracking tool descriptions
GET_TASK_STATUS_DESC = """Get the current status of an asynchronous Proxmox task (read-only).

Parameters:
upid* - Task id (UPID) returned by a mutating tool, e.g. \
'UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:user@pve!token:'

A task counts as successful ONLY when it has stopped with exitstatus 'OK'
(success=true). A stopped task with 'WARNINGS...' is reported as state 'warnings'
(not success); any other exit status is state 'failed' and includes the last log
lines. A task that has not stopped is state 'running'.

Example:
Check the task returned by start_vm: \
upid='UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:user@pve!token:'"""

WAIT_FOR_TASK_DESC = """Wait for an asynchronous Proxmox task to finish, with a bounded timeout \
(read-only).

Parameters:
upid* - Task id (UPID) returned by a mutating tool
timeout - Maximum seconds to wait (default 30, maximum 300) (optional)

Polls the task until it stops. Success means exitstatus 'OK' only; 'WARNINGS...' is
reported separately and is not success. If the task is still running when the timeout
expires the call does NOT fail: it returns state 'running' with timed_out=true, and you
can call wait_for_task again. The wait never exceeds 300 seconds.

Example:
Wait up to 60 seconds: upid='UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:user@pve!token:', \
timeout=60"""
