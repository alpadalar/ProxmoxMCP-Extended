"""
VM-related tools for Proxmox MCP.

This module provides tools for managing and interacting with Proxmox VMs:
- Listing all VMs across the cluster with their status
- Retrieving detailed VM information including:
  * Resource allocation (CPU, memory)
  * Runtime status
  * Node placement
- Executing commands within VMs via QEMU guest agent
- Handling VM console operations
- VM power management (start, stop, shutdown, reset)
- VM creation with customizable specifications

The tools implement fallback mechanisms for scenarios where
detailed VM information might be temporarily unavailable.
"""
import time
from typing import Callable, List, Optional
from mcp.types import TextContent as Content
from .base import ProxmoxTool
from .definitions import (
    GET_VMS_DESC,
    EXECUTE_VM_COMMAND_DESC,
    CREATE_SNAPSHOT_DESC,
    ROLLBACK_SNAPSHOT_DESC,
    GET_VM_USAGE_DESC,
)
from .console.manager import VMConsoleManager
from .tasks import task_result_text
from .pve_compat import (
    describe_task_result,
    is_upid,
    require_vm_status,
    vm_listed,
    wait_task_stopped,
)
from ..validators import (
    validate_wait_timeout,
    validate_node,
    validate_vmid,
    validate_storage,
    validate_snapshot_name,
    validate_vm_name,
    validate_iso_name,
    validate_ostype,
    validate_description,
    validate_cpus,
    validate_memory_mb,
    validate_disk_gb,
    validate_optional,
)

class VMTools(ProxmoxTool):
    """Tools for managing Proxmox VMs.
    
    Provides functionality for:
    - Retrieving cluster-wide VM information
    - Getting detailed VM status and configuration
    - Executing commands within VMs
    - Managing VM console operations
    - VM power management (start, stop, shutdown, reset)
    - VM creation with customizable specifications
    
    Implements fallback mechanisms for scenarios where detailed
    VM information might be temporarily unavailable. Integrates
    with QEMU guest agent for VM command execution.
    """

    def __init__(
        self,
        proxmox_api,
        exec_timeout: float = 30.0,
        exec_max_output: int = 65536,
        exec_max_concurrent: int = 2,
        pve_major: Callable[[], Optional[int]] = lambda: None,
    ):
        """Initialize VM tools.

        Args:
            proxmox_api: Initialized ProxmoxAPI instance
            exec_timeout: Seconds to wait for a guest command to exit
            exec_max_output: Maximum bytes kept per output stream of a guest command
            exec_max_concurrent: Maximum guest commands polled at the same time
            pve_major: Returns the PVE major version (or None) for version-aware hints
        """
        super().__init__(proxmox_api)
        self._sleep = time.sleep
        self._clock = time.monotonic
        self._pve_major = pve_major
        self.console_manager = VMConsoleManager(
            proxmox_api, exec_timeout=exec_timeout, exec_max_output=exec_max_output,
            exec_max_concurrent=exec_max_concurrent, pve_major=pve_major,
        )

    def _task_text(self, task_result, wait: bool, timeout: int) -> str:
        """Task line for a mutation result; polls the task when ``wait`` is true."""
        return task_result_text(
            self.proxmox, task_result, wait, timeout, sleep=self._sleep, clock=self._clock
        )

    STOP_WAIT_SECONDS = 30.0
    STOP_POLL_INTERVAL = 1.0

    def _wait_until_stopped(self, node: str, vmid: str, stop_result) -> None:
        """Block (bounded) until a just-issued stop has finished; raise otherwise.

        A UPID is followed through the task status (exitstatus must be OK, WARNINGS is not).
        Without a UPID (null return) ``status.current`` is polled until "stopped".
        """
        if is_upid(stop_result):
            wait_task_stopped(
                self.proxmox, node, stop_result, timeout=self.STOP_WAIT_SECONDS,
                interval=self.STOP_POLL_INTERVAL, sleep=self._sleep,
            )
            return
        attempts = int(self.STOP_WAIT_SECONDS / self.STOP_POLL_INTERVAL)
        for _ in range(attempts):
            status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
            if isinstance(status, dict) and status.get("status") == "stopped":
                return
            self._sleep(self.STOP_POLL_INTERVAL)
        raise RuntimeError(f"VM {vmid} did not stop within {self.STOP_WAIT_SECONDS:g}s; not deleted")

    def get_vms(self) -> List[Content]:
        """List all virtual machines across the cluster with detailed status.

        Retrieves comprehensive information for each VM including:
        - Basic identification (ID, name)
        - Runtime status (running, stopped)
        - Resource allocation and usage:
          * CPU cores
          * Memory allocation and usage
        - Node placement
        
        Implements a fallback mechanism that returns basic information
        if detailed configuration retrieval fails for any VM.

        Returns:
            List of Content objects containing formatted VM information:
            {
                "vmid": "100",
                "name": "vm-name",
                "status": "running/stopped",
                "node": "node-name",
                "cpus": core_count,
                "memory": {
                    "used": bytes,
                    "total": bytes
                }
            }

        Raises:
            RuntimeError: If the cluster-wide VM query fails
        """
        try:
            result = []
            for node in self.proxmox.nodes.get():
                node_name = node["node"]
                vms = self.proxmox.nodes(node_name).qemu.get()
                for vm in vms:
                    vmid = vm["vmid"]
                    # Get VM config for CPU cores
                    try:
                        config = self.proxmox.nodes(node_name).qemu(vmid).config.get()
                        result.append({
                            "vmid": vmid,
                            "name": vm["name"],
                            "status": vm["status"],
                            "node": node_name,
                            "cpus": config.get("cores", "N/A"),
                            "memory": {
                                "used": vm.get("mem", 0),
                                "total": vm.get("maxmem", 0)
                            }
                        })
                    except Exception:
                        # Fallback if can't get config
                        result.append({
                            "vmid": vmid,
                            "name": vm["name"],
                            "status": vm["status"],
                            "node": node_name,
                            "cpus": "N/A",
                            "memory": {
                                "used": vm.get("mem", 0),
                                "total": vm.get("maxmem", 0)
                            }
                        })
            return self._format_response(result, "vms")
        except Exception as e:
            self._handle_error("get VMs", e, privilege_key="get_vms")

    def create_vm(self, node: str, vmid: str, name: str, cpus: int, memory: int,
                  disk_size: int, storage: Optional[str] = None, ostype: Optional[str] = None,
                  iso_name: Optional[str] = None, iso_storage: Optional[str] = None) -> List[Content]:
        """Create a new virtual machine with specified configuration.
        
        Args:
            node: Host node name (e.g., 'pve')
            vmid: New VM ID number (e.g., '200')
            name: VM name (e.g., 'my-new-vm')
            cpus: Number of CPU cores (e.g., 1, 2, 4)
            memory: Memory size in MB (e.g., 2048 for 2GB)
            disk_size: Disk size in GB (e.g., 10, 20, 50)
            storage: Storage name (e.g., 'local-lvm', 'vm-storage'). If None, will auto-detect
            ostype: OS type (e.g., 'l26' for Linux, 'win10' for Windows). Default: 'l26'
            iso_name: Optional ISO file name to mount on creation (e.g., 'debian-12.iso')
            iso_storage: Optional storage name where ISO resides (auto-detected if not provided)
            
        Returns:
            List of Content objects containing creation result
            
        Raises:
            ValueError: If VM ID already exists or invalid parameters
            RuntimeError: If VM creation fails
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        name = validate_vm_name(name)
        storage = validate_optional(validate_storage, storage)
        iso_storage = validate_optional(validate_storage, iso_storage, "iso_storage")
        iso_name = validate_optional(validate_iso_name, iso_name, "iso_name")
        ostype = validate_optional(validate_ostype, ostype)
        # Same limits as the stdio Field bounds, enforced here so every transport is covered.
        cpus = validate_cpus(cpus, hi=32)
        memory = validate_memory_mb(memory, lo=512, hi=131072)
        disk_size = validate_disk_gb(disk_size, lo=5, hi=1000)
        try:
            # Check if VM ID already exists
            if vm_listed(self.proxmox, node, vmid):
                raise ValueError(f"VM {vmid} already exists on node {node}")
            
            # Get storage information
            storage_list = self.proxmox.nodes(node).storage.get()
            storage_info = {}
            for s in storage_list:
                storage_info[s["storage"]] = s
            
            # Auto-detect storage if not specified
            if storage is None:
                # Prefer local-lvm for VM images first
                for s in storage_list:
                    if s["storage"] == "local-lvm" and "images" in s.get("content", ""):
                        storage = s["storage"]
                        break
                if storage is None:
                    # Then try vm-storage 
                    for s in storage_list:
                        if s["storage"] == "vm-storage" and "images" in s.get("content", ""):
                            storage = s["storage"]
                            break
                if storage is None:
                    # Fallback to any storage that supports images
                    for s in storage_list:
                        if "images" in s.get("content", ""):
                            storage = s["storage"]
                            break
                    if storage is None:
                        raise ValueError("No suitable storage found for VM images")
            
            # Validate storage exists and supports images
            if storage not in storage_info:
                raise ValueError(f"Storage '{storage}' not found on node {node}")
            
            if "images" not in storage_info[storage].get("content", ""):
                raise ValueError(f"Storage '{storage}' does not support VM images")
            
            # Determine appropriate disk format based on storage type
            storage_type = storage_info[storage]["type"]
            
            if storage_type in ["lvm", "lvmthin"]:
                # LVM storages use raw format and no cloudinit
                disk_format = "raw"
                vm_config_storage = {
                    "scsi0": f"{storage}:{disk_size},format={disk_format}",
                }
            elif storage_type in ["dir", "nfs", "cifs"]:
                # File-based storages can use qcow2
                disk_format = "qcow2"
                vm_config_storage = {
                    "scsi0": f"{storage}:{disk_size},format={disk_format}",
                    "ide2": f"{storage}:cloudinit",
                }
            else:
                # Default to raw for unknown storage types
                disk_format = "raw"
                vm_config_storage = {
                    "scsi0": f"{storage}:{disk_size},format={disk_format}",
                }

            # Optional ISO mount configuration
            iso_config_note = ""
            if iso_name:
                # Auto-detect ISO-capable storage if not provided
                if not iso_storage:
                    for s in storage_list:
                        if "iso" in s.get("content", ""):
                            iso_storage = s["storage"]
                            break
                    if not iso_storage:
                        raise ValueError("No storage with ISO content found to mount the ISO")

                # Choose IDE device (avoid overwriting cloudinit on ide2)
                ide_dev = "ide2" if "ide2" not in vm_config_storage else "ide3"
                vm_config_storage[ide_dev] = f"{iso_storage}:iso/{iso_name},media=cdrom"
                iso_config_note = f"\n  • ISO: {iso_name} (from {iso_storage} on {ide_dev})"
            
            # Set default OS type
            if ostype is None:
                ostype = "l26"  # Linux 2.6+ kernel
            
            # Prepare VM configuration
            vm_config = {
                "vmid": vmid,
                "name": name,
                "cores": cpus,
                "memory": memory,
                "ostype": ostype,
                "scsihw": "virtio-scsi-pci",
                "boot": "order=scsi0",
                "agent": "1",  # Enable QEMU guest agent
                "vga": "std",
                "net0": "virtio,bridge=vmbr0",
            }
            
            # Add storage configuration
            vm_config.update(vm_config_storage)
            
            # Create the VM
            task_result = self.proxmox.nodes(node).qemu.create(**vm_config)
            
            cloudinit_note = ""
            if storage_type in ["lvm", "lvmthin"]:
                cloudinit_note = "\n  ⚠️  Note: LVM storage doesn't support cloud-init image"
            
            result_text = f"""🎉 VM {vmid} creation queued!

📋 VM Configuration:
  • Name: {name}
  • Node: {node}
  • VM ID: {vmid}
  • CPU Cores: {cpus}
  • Memory: {memory} MB ({memory/1024:.1f} GB)
  • Disk: {disk_size} GB ({storage}, {disk_format} format)
  • Storage Type: {storage_type}
  • OS Type: {ostype}
  • Network: virtio (bridge=vmbr0)
  • QEMU Agent: Enabled{cloudinit_note}{iso_config_note}

🔧 {describe_task_result(task_result)}

💡 Next steps:
  1. Upload an ISO to install the operating system
  2. Start the VM using start_vm tool
  3. Access the console to complete OS installation"""
            
            return [Content(type="text", text=result_text)]
            
        except ValueError as e:
            raise e
        except Exception as e:
            self._handle_error(
                f"create VM {vmid}", e, privilege_key="create_vm", node=node, vmid=vmid
            )

    def start_vm(
        self, node: str, vmid: str, wait: bool = False, timeout: int = 30
    ) -> List[Content]:
        """Start a virtual machine.
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            
        Returns:
            List of Content objects containing operation result
            
        Raises:
            ValueError: If VM is not found
            RuntimeError: If start operation fails
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        validate_wait_timeout(timeout)
        try:
            # Check if VM exists and get current status
            vm_status = require_vm_status(self.proxmox, node, vmid, "start_vm")
            current_status = vm_status.get("status")

            if current_status == "running":
                result_text = f"🟢 VM {vmid} is already running"
            else:
                # Start the VM
                task_result = self.proxmox.nodes(node).qemu(vmid).status.start.post()
                result_text = f"🚀 VM {vmid} start initiated successfully\n{self._task_text(task_result, wait, timeout)}"
                
            return [Content(type="text", text=result_text)]
            
        except Exception as e:
            self._handle_error(
                f"start VM {vmid}", e, privilege_key="start_vm", node=node, vmid=vmid
            )

    def stop_vm(
        self, node: str, vmid: str, wait: bool = False, timeout: int = 30
    ) -> List[Content]:
        """Stop a virtual machine (force stop).
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2') 
            vmid: VM ID number (e.g., '100', '101')
            
        Returns:
            List of Content objects containing operation result
            
        Raises:
            ValueError: If VM is not found
            RuntimeError: If stop operation fails
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        validate_wait_timeout(timeout)
        try:
            # Check if VM exists and get current status
            vm_status = require_vm_status(self.proxmox, node, vmid, "stop_vm")
            current_status = vm_status.get("status")

            if current_status == "stopped":
                result_text = f"🔴 VM {vmid} is already stopped"
            else:
                # Stop the VM
                task_result = self.proxmox.nodes(node).qemu(vmid).status.stop.post()
                result_text = f"🛑 VM {vmid} stop initiated successfully\n{self._task_text(task_result, wait, timeout)}"
                
            return [Content(type="text", text=result_text)]
            
        except Exception as e:
            self._handle_error(
                f"stop VM {vmid}", e, privilege_key="stop_vm", node=node, vmid=vmid
            )

    def shutdown_vm(
        self, node: str, vmid: str, wait: bool = False, timeout: int = 30
    ) -> List[Content]:
        """Shutdown a virtual machine gracefully.
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            
        Returns:
            List of Content objects containing operation result
            
        Raises:
            ValueError: If VM is not found
            RuntimeError: If shutdown operation fails
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        validate_wait_timeout(timeout)
        try:
            # Check if VM exists and get current status
            vm_status = require_vm_status(self.proxmox, node, vmid, "shutdown_vm")
            current_status = vm_status.get("status")

            if current_status == "stopped":
                result_text = f"🔴 VM {vmid} is already stopped"
            else:
                # Shutdown the VM gracefully
                task_result = self.proxmox.nodes(node).qemu(vmid).status.shutdown.post()
                result_text = f"💤 VM {vmid} graceful shutdown initiated\n{self._task_text(task_result, wait, timeout)}"
                
            return [Content(type="text", text=result_text)]
            
        except Exception as e:
            self._handle_error(
                f"shutdown VM {vmid}", e, privilege_key="shutdown_vm", node=node, vmid=vmid
            )

    def reset_vm(
        self, node: str, vmid: str, wait: bool = False, timeout: int = 30
    ) -> List[Content]:
        """Reset (restart) a virtual machine.
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            
        Returns:
            List of Content objects containing operation result
            
        Raises:
            ValueError: If VM is not found
            RuntimeError: If reset operation fails
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        validate_wait_timeout(timeout)
        try:
            # Check if VM exists and get current status
            vm_status = require_vm_status(self.proxmox, node, vmid, "reset_vm")
            current_status = vm_status.get("status")

            if current_status == "stopped":
                result_text = f"⚠️ Cannot reset VM {vmid}: VM is currently stopped\nUse start_vm to start it first"
            else:
                # Reset the VM
                task_result = self.proxmox.nodes(node).qemu(vmid).status.reset.post()
                result_text = f"🔄 VM {vmid} reset initiated successfully\n{self._task_text(task_result, wait, timeout)}"
                
            return [Content(type="text", text=result_text)]
            
        except Exception as e:
            self._handle_error(
                f"reset VM {vmid}", e, privilege_key="reset_vm", node=node, vmid=vmid
            )

    async def execute_command(
        self, node: str, vmid: str, command: str, args: Optional[List[str]] = None
    ) -> List[Content]:
        """Execute a command in a VM via QEMU guest agent.

        Uses the QEMU guest agent to execute commands within a running VM.
        Requires:
        - VM must be running
        - QEMU guest agent must be installed and running in the VM
        - Command execution permissions must be enabled

        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            command: Program, or command line split with shlex rules when ``args`` is omitted
            args: Optional argument list (no shell is involved)

        Returns:
            List of Content objects containing formatted command output:
            {
                "success": true/false,
                "output": "command output",
                "error": "error message if any"
            }

        Raises:
            ValueError: If VM is not found, not running, or guest agent is not available
            RuntimeError: If command execution fails due to permissions or other issues
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        try:
            result = await self.console_manager.execute_command(node, vmid, command, args)
            # Use the command output formatter from ProxmoxFormatters
            from ..formatting import ProxmoxFormatters
            formatted = ProxmoxFormatters.format_command_output(
                success=result["success"],
                command=command,
                output=result["output"],
                error=result.get("error"),
                exit_code=result.get("exit_code"),
                exited=result.get("exited", True),
                signal=result.get("signal"),
                timed_out=result.get("timed_out", False),
                truncated=result.get("truncated", False),
            )
            return [Content(type="text", text=formatted)]
        except Exception as e:
            if getattr(e, "_pve_translated", False):
                raise  # already mapped from the HTTP status code by the console manager
            self._handle_error(
                f"execute command on VM {vmid}", e, privilege_key="execute_vm_command", node=node, vmid=vmid
            )

    def delete_vm(
        self, node: str, vmid: str, force: bool = False, wait: bool = False, timeout: int = 30
    ) -> List[Content]:
        """Delete/remove a virtual machine completely.
        
        This will permanently delete the VM and all its associated data including:
        - VM configuration
        - Virtual disks
        - Snapshots
        
        WARNING: This operation cannot be undone!
        
        Args:
            node: Host node name (e.g., 'pve1', 'proxmox-node2')
            vmid: VM ID number (e.g., '100', '101')
            force: Force deletion even if VM is running (will stop first)
            
        Returns:
            List of Content objects containing deletion result
            
        Raises:
            ValueError: If VM is not found or is running and force=False
            RuntimeError: If deletion fails
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        validate_wait_timeout(timeout)
        try:
            # Check if VM exists and get current status
            vm_status = require_vm_status(self.proxmox, node, vmid, "delete_vm")
            current_status = vm_status.get("status")
            vm_name = vm_status.get("name", f"VM-{vmid}")
            
            # Check if VM is running
            if current_status == "running":
                if not force:
                    raise ValueError(f"VM {vmid} ({vm_name}) is currently running. "
                                   f"Please stop it first or use force=True to stop and delete.")
                else:
                    # Force stop the VM first and wait (bounded) until it is really stopped;
                    # never delete while the stop task is running or after it failed.
                    try:
                        stop_result = self.proxmox.nodes(node).qemu(vmid).status.stop.post()
                    except Exception as stop_error:
                        # The VM may have stopped since the status read; if so carry on and
                        # let the re-check below decide, otherwise report the stop failure.
                        recheck = self.proxmox.nodes(node).qemu(vmid).status.current.get()
                        if not (isinstance(recheck, dict) and recheck.get("status") == "stopped"):
                            raise stop_error
                        stop_result = None
                    self._wait_until_stopped(node, vmid, stop_result)
                    # Re-read right before deleting: abort unless the same VM is stopped
                    # (HA restart / relocation or a recycled vmid during the stop wait).
                    after = self.proxmox.nodes(node).qemu(vmid).status.current.get()
                    if not isinstance(after, dict) or after.get("status") != "stopped":
                        raise RuntimeError(
                            f"VM {vmid} is not stopped after the stop wait; not deleted"
                        )
                    if after.get("name") not in (None, vm_status.get("name")):
                        raise RuntimeError(
                            f"VM {vmid} changed identity during the stop wait; not deleted"
                        )
                    result_text = f"🛑 Stopping VM {vmid} ({vm_name}) before deletion...\n"
            else:
                result_text = f"🗑️ Deleting VM {vmid} ({vm_name})...\n"
            
            # Delete the VM
            task_result = self.proxmox.nodes(node).qemu(vmid).delete()
            
            result_text += f"""🗑️ VM {vmid} ({vm_name}) deletion initiated successfully!

⚠️ WARNING: This operation will permanently remove:
  • VM configuration
  • All virtual disks
  • All snapshots
  • Cannot be undone!

🔧 {self._task_text(task_result, wait, timeout)}

✅ VM {vmid} ({vm_name}) is being deleted from node {node}"""
            
            return [Content(type="text", text=result_text)]
            
        except ValueError as e:
            raise e
        except Exception as e:
            self._handle_error(
                f"delete VM {vmid}", e, privilege_key="delete_vm", node=node, vmid=vmid
            )

    def create_snapshot(
        self,
        node: str,
        vmid: str,
        name: str,
        description: Optional[str] = None,
        vmstate: bool = False,
        wait: bool = False,
        timeout: int = 30,
    ) -> List[Content]:
        """Create a snapshot for a VM.
        
        Args:
            node: Host node name
            vmid: VM ID number
            name: Snapshot name
            description: Optional description
            vmstate: Include VM memory state
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        name = validate_snapshot_name(name)
        description = validate_optional(validate_description, description)
        validate_wait_timeout(timeout)
        try:
            # Ensure VM exists
            require_vm_status(self.proxmox, node, vmid, "create_snapshot")
            params = {"snapname": name}
            if description:
                params["description"] = description
            if vmstate:
                params["vmstate"] = 1
            task_result = self.proxmox.nodes(node).qemu(vmid).snapshot.post(**params)
            result_text = (
                f"📸 Snapshot '{name}' creation initiated for VM {vmid} on node {node}\n"
                f"🔧 {self._task_text(task_result, wait, timeout)}"
            )
            return [Content(type="text", text=result_text)]
        except Exception as e:
            self._handle_error(
                f"create snapshot for VM {vmid}", e, privilege_key="create_snapshot", node=node, vmid=vmid
            )

    def rollback_snapshot(
        self, node: str, vmid: str, name: str, wait: bool = False, timeout: int = 30
    ) -> List[Content]:
        """Rollback a VM to a snapshot.
        
        WARNING: This discards current VM state.
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        name = validate_snapshot_name(name)
        validate_wait_timeout(timeout)
        try:
            # Ensure VM exists
            require_vm_status(self.proxmox, node, vmid, "rollback_snapshot")
            task_result = (
                self.proxmox.nodes(node)
                .qemu(vmid)
                .snapshot(name)
                .rollback.post()
            )
            result_text = (
                f"↩️ Rollback to snapshot '{name}' initiated for VM {vmid} on node {node}\n"
                f"🔧 {self._task_text(task_result, wait, timeout)}"
            )
            return [Content(type="text", text=result_text)]
        except Exception as e:
            self._handle_error(
                f"rollback VM {vmid} to snapshot {name}", e, privilege_key="rollback_snapshot", node=node, vmid=vmid
            )

    def get_vm_usage(self, node: str, vmid: str) -> List[Content]:
        """Get real-time resource usage for a VM (CPU, memory, disk)."""
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        try:
            status = require_vm_status(self.proxmox, node, vmid, "get_vm_usage")
            cpu = status.get("cpu", 0.0) * 100.0  # fraction to percent
            mem_used = status.get("mem", 0)
            mem_total = status.get("maxmem", 0)
            disk_used = status.get("disk", 0)
            disk_total = status.get("maxdisk", 0)

            # Format into a friendly output
            from ..formatting import ProxmoxFormatters

            mem_percent = (mem_used / mem_total * 100.0) if mem_total else 0.0
            result_lines = [
                "🧠 VM Real-time Usage",
                f"  • CPU: {cpu:.1f}%",
                f"  • Memory: {ProxmoxFormatters.format_bytes(mem_used)} / "
                f"{ProxmoxFormatters.format_bytes(mem_total)} ({mem_percent:.1f}%)",
            ]
            if disk_total:
                disk_percent = (disk_used / disk_total * 100.0) if disk_total else 0.0
                result_lines.append(
                    f"  • Disk: {ProxmoxFormatters.format_bytes(disk_used)} / "
                    f"{ProxmoxFormatters.format_bytes(disk_total)} ({disk_percent:.1f}%)"
                )

            return [Content(type="text", text="\n".join(result_lines))]
        except Exception as e:
            self._handle_error(
                f"get usage for VM {vmid}", e, privilege_key="get_vm_usage", node=node, vmid=vmid
            )

    def update_vm(self, node: str, vmid: str, memory: Optional[int] = None, 
                  cpus: Optional[int] = None, name: Optional[str] = None) -> List[Content]:
        """Update VM configuration (memory, CPU cores, name).
        
        This function allows updating VM resources. Note that some changes
        may require the VM to be stopped for the changes to take effect.
        
        Args:
            node: Host node name (e.g., 'pve')
            vmid: VM ID number (e.g., '100')
            memory: New memory size in MB (e.g., 4096 for 4GB, 6144 for 6GB)
            cpus: New number of CPU cores (e.g., 1, 2, 4)
            name: New VM name
            
        Returns:
            List of Content objects containing update result
            
        Raises:
            ValueError: If VM is not found or invalid parameters
            RuntimeError: If update operation fails
        """
        node = validate_node(node)
        vmid = validate_vmid(vmid)
        name = validate_optional(validate_vm_name, name)
        cpus = validate_optional(validate_cpus, cpus)
        memory = validate_optional(validate_memory_mb, memory)
        try:
            # Check if VM exists and get current status
            vm_status = require_vm_status(self.proxmox, node, vmid, "update_vm")
            current_status = vm_status.get("status")
            current_name = vm_status.get("name", f"VM-{vmid}")
            
            # Get current VM configuration
            current_config = self.proxmox.nodes(node).qemu(vmid).config.get()
            
            # Prepare update parameters
            update_params = {}
            changes = []
            
            # Memory update
            if memory is not None:
                if memory < 512 or memory > 131072:
                    raise ValueError("Memory must be between 512 MB and 131072 MB (128 GB)")
                current_memory = current_config.get("memory", 0)
                if memory != current_memory:
                    update_params["memory"] = memory
                    changes.append(f"Memory: {current_memory} MB → {memory} MB ({memory/1024:.1f} GB)")
            
            # CPU cores update
            if cpus is not None:
                if cpus < 1 or cpus > 32:
                    raise ValueError("CPU cores must be between 1 and 32")
                current_cpus = current_config.get("cores", 1)
                if cpus != current_cpus:
                    update_params["cores"] = cpus
                    changes.append(f"CPU Cores: {current_cpus} → {cpus}")
            
            # Name update
            if name is not None:
                if name != current_name:
                    update_params["name"] = name
                    changes.append(f"Name: '{current_name}' → '{name}'")
            
            # Check if any changes are requested
            if not update_params:
                result_text = f"ℹ️ No changes requested for VM {vmid} ({current_name})"
                return [Content(type="text", text=result_text)]
            
            # Check if VM needs to be stopped for changes
            if current_status == "running":
                if memory is not None or cpus is not None:
                    result_text = f"⚠️ VM {vmid} ({current_name}) is currently running.\n"
                    result_text += f"Resource changes require the VM to be stopped first.\n"
                    result_text += f"Please stop the VM using shutdown_vm or stop_vm before updating.\n\n"
                    result_text += f"Requested changes:\n"
                    for change in changes:
                        result_text += f"  • {change}\n"
                    return [Content(type="text", text=result_text)]
            
            # Apply updates
            if update_params:
                task_result = self.proxmox.nodes(node).qemu(vmid).config.put(**update_params)
                
                result_text = f"✅ VM {vmid} configuration updated successfully!\n\n"
                result_text += f"📋 Applied Changes:\n"
                for change in changes:
                    result_text += f"  • {change}\n"
                
                if current_status == "running":
                    result_text += f"\n⚠️ Note: Some changes may require VM restart to take full effect."
                
                result_text += f"\n🔧 {describe_task_result(task_result)}"
                
                return [Content(type="text", text=result_text)]
            
        except ValueError as e:
            raise e
        except Exception as e:
            self._handle_error(
                f"update VM {vmid}", e, privilege_key="update_vm", node=node, vmid=vmid
            )
