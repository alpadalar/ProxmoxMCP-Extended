"""
Module for managing VM console operations.

This module provides functionality for interacting with VM consoles:
- Executing commands within VMs via QEMU guest agent
- Handling command execution lifecycle
- Managing command output and status
- Error handling and logging

The module implements a robust command execution system with:
- VM state verification
- Asynchronous command execution
- Detailed status tracking
- Comprehensive error handling
"""

import asyncio
import logging
from functools import partial
from typing import Any, Dict

from ...utils.redaction import redact_local


class VMConsoleManager:
    """Manager class for VM console operations.
    
    Provides functionality for:
    - Executing commands in VM consoles
    - Managing command execution lifecycle
    - Handling command output and errors
    - Monitoring execution status
    
    Uses QEMU guest agent for reliable command execution with:
    - VM state verification before execution
    - Asynchronous command processing
    - Detailed output capture
    - Comprehensive error handling
    """

    def __init__(self, proxmox_api):
        """Initialize the VM console manager.

        Args:
            proxmox_api: Initialized ProxmoxAPI instance
        """
        self.proxmox = proxmox_api
        self.logger = logging.getLogger("proxmox-mcp.vm-console")

    async def execute_command(self, node: str, vmid: str, command: str) -> Dict[str, Any]:
        """Execute a command in a VM's console via QEMU guest agent.

        Implements a two-phase command execution process:
        1. Command Initiation:
           - Verifies VM exists and is running
           - Initiates command execution via guest agent
           - Captures command PID for tracking
        
        2. Result Collection:
           - Monitors command execution status
           - Captures command output and errors
           - Handles completion status
        
        Requirements:
        - VM must be running
        - QEMU guest agent must be installed and active
        - Command execution permissions must be enabled

        Args:
            node: Name of the node where VM is running (e.g., 'pve1')
            vmid: ID of the VM to execute command in (e.g., '100')
            command: Shell command to execute in the VM

        Returns:
            Dictionary containing command execution results:
            {
                "success": true/false,
                "output": "command output",
                "error": "error output if any",
                "exit_code": command_exit_code
            }

        Raises:
            ValueError: If:
                     - VM is not found
                     - VM is not running
                     - Guest agent is not available
            RuntimeError: If:
                       - Command execution fails
                       - Unable to get command status
                       - API communication errors occur
        """
        # The command may embed secrets and is never logged; it is scrubbed from error text
        # per call only (never stored in the global redaction registry).
        try:
            # Verify VM exists and is running
            # proxmoxer is synchronous; run every call in a worker thread so the
            # event loop (and /health) stays responsive.
            vm_status = await asyncio.to_thread(
                self.proxmox.nodes(node).qemu(vmid).status.current.get
            )
            if vm_status["status"] != "running":
                self.logger.error(f"Failed to execute command on VM {vmid}: VM is not running")
                raise ValueError(f"VM {vmid} on node {node} is not running")

            self.logger.info(f"Executing command on VM {vmid} (node: {node})")

            # Use the guest agent exec endpoint
            endpoint = self.proxmox.nodes(node).qemu(vmid).agent

            # Execute the command using two-step process
            try:
                # Start command execution
                try:
                    exec_result = await asyncio.to_thread(
                        partial(endpoint("exec").post, command=command)
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to start command on VM {vmid} (node: {node}): {type(e).__name__}"
                    )
                    raise RuntimeError(f"Failed to start command: {type(e).__name__}") from None

                if 'pid' not in exec_result:
                    raise RuntimeError("No PID returned from command execution")

                pid = exec_result['pid']
                self.logger.info(f"Command started on VM {vmid} (PID: {pid})")

                # Add a small delay to allow command to complete
                await asyncio.sleep(1)

                # Get command output using exec-status
                try:
                    console = await asyncio.to_thread(
                        partial(endpoint("exec-status").get, pid=pid)
                    )
                    if not console:
                        raise RuntimeError("No response from exec-status")
                except Exception as e:
                    self.logger.error(
                        f"Failed to get command status for PID {pid}: {type(e).__name__}"
                    )
                    raise RuntimeError(
                        f"Failed to get command status: {type(e).__name__}"
                    ) from None
            except Exception as e:
                self.logger.error(f"API call failed on VM {vmid}: {type(e).__name__}")
                raise RuntimeError(f"API call failed: {redact_local(str(e), command)}") from None

            # Handle different response structures
            if isinstance(console, dict):
                # Handle exec-status response format
                output = console.get("out-data", "")
                error = console.get("err-data", "")
                exit_code = console.get("exitcode", 0)
                exited = console.get("exited", 0)

                if not exited:
                    self.logger.warning("Command may not have completed")
            else:
                # Some versions might return data differently
                output = str(console)
                error = ""
                exit_code = 0

            self.logger.info(
                f"Command finished on VM {vmid} (node: {node}, PID: {pid}, exit_code: {exit_code}, "
                f"exited: {bool(exited) if isinstance(console, dict) else 'unknown'}, "
                f"output_len: {len(output)}, error_len: {len(error)})"
            )

            return {
                "success": True,
                "output": output,
                "error": error,
                "exit_code": exit_code
            }

        except ValueError:
            # Re-raise ValueError for VM not running
            raise
        except Exception as e:
            self.logger.error(f"Failed to execute command on VM {vmid}: {type(e).__name__}")
            if "not found" in str(e).lower():
                raise ValueError(f"VM {vmid} not found on node {node}") from None
            detail = redact_local(str(e), command)
            raise RuntimeError(f"Failed to execute command: {detail}") from None
