# Security Policy

ProxmoxMCP-Extended gives an MCP client (and therefore an LLM) a set of tools that operate on your
Proxmox VE cluster. This document explains what the server can do to your hypervisor, how access is
limited, and how to report a vulnerability.

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a vulnerability

Do not open a public issue for security problems.

- Preferred: GitHub private vulnerability reporting,
  <https://github.com/alpadalar/ProxmoxMCP-Extended/security/advisories/new>
- Alternative: email alp.adalar@gmail.com with the subject "ProxmoxMCP-Extended security".

Please include the affected version, a reproduction and the impact. This is a hobby-scale project:
responses are best effort, normally within a week, and there is no bug bounty. Please do not include
real tokens, API keys or cluster addresses in a report.

## What this server can do to your hypervisor

The server authenticates to the Proxmox API with the token you configure and can do anything that
token is allowed to do through the 27 tools below. The server adds its own gates on top of the token
privileges; they are a second line of defence, not a replacement for a least-privilege token.

Risk classes are defined in `RISK_CLASSES` (`src/proxmox_mcp/tools/registry.py`) and enforced at call
time by `src/proxmox_mcp/policy.py`.

| Risk class | Tools | Effect on the hypervisor | Gate |
|------------|-------|--------------------------|------|
| read (13) | `get_nodes`, `get_node_status`, `get_vms`, `get_containers`, `get_storage`, `get_cluster_status`, `get_vm_usage`, `health`, `get_task_status`, `wait_for_task`, `list_snapshots`, `list_backups`, `get_ha_status` | Reads inventory, status, tasks, snapshots, backups and HA state. Task log tails of failed tasks are shown to the model (redacted). | none (always available) |
| write (6) | `create_vm`, `start_vm`, `shutdown_vm`, `create_snapshot`, `start_container`, `shutdown_container` | Power on / graceful shutdown, creates a VM (queues a task), takes a snapshot (uses storage). Recoverable. | blocked by `read_only` |
| destructive (7) | `stop_vm`, `reset_vm`, `delete_vm`, `rollback_snapshot`, `update_vm`, `delete_snapshot`, `stop_container` | Hard power off / reset (data loss risk), destroys a VM (optionally forced), discards the VM state back to a snapshot, overwrites VM configuration (memory, cores, name), deletes a snapshot, hard-stops a container. | needs `allow_destructive`; blocked by `read_only`; `confirm=true` required except for `update_vm` |
| exec (1) | `execute_vm_command` | Runs a program inside a guest through the QEMU guest agent. This is arbitrary code execution in the guest (see below). | needs `allow_exec`; blocked by `read_only` |

Default posture: `read_only=false`, `allow_destructive=false`, `allow_exec=false`. Gated tools stay
registered (the tool list never changes, so existing client configurations keep working) and refuse at
call time with a `policy_denied` error that names the flag; no request is sent to Proxmox. Set
`read_only=true` to block every write, destructive and exec tool regardless of the `allow_*` flags.

Confirm preview: `delete_vm`, `stop_vm`, `reset_vm`, `rollback_snapshot`, `delete_snapshot` and
`stop_container` only return a static preview unless called with `confirm=true`. The preview performs
no lookup and `confirm=true` is a speed bump for the model, not an authorization. The real gate is
`allow_destructive`.

`update_vm` was reclassified as destructive in 1.0.0 and has no `confirm` parameter (adding one would
change the tool schema).

Mutating tools accept optional `wait` and `timeout` (1 to 300 seconds). A waiting call occupies a worker
thread; at most 8 waits run at once and further waits fail immediately (the UPID is still returned).

## Recommended Proxmox token setup

1. Create a dedicated user (for example `mcp@pve`), not `root@pam`.
2. Create a privilege-separated API token for it (`pveum user token add mcp@pve mcp --privsep 1`).
   With privilege separation the token has no permissions until you grant them to the token itself.
3. Grant the smallest role on the narrowest path:
   - Read-only use: the built-in `PVEAuditor` role on `/` (use narrower paths such as `/vms/<id>` or
     `/storage/<id>` if you do not need the whole cluster).
   - Add write or destructive privileges only on the ACL paths that need them, only for the tools you
     enable. The privilege names the server reports in its "Permission denied" messages come from
     `OPERATION_PRIVILEGES` in `src/proxmox_mcp/tools/pve_compat.py`:

| Operation | Privilege | Path |
|-----------|-----------|------|
| start / stop / shutdown / reset VM, start / stop / shutdown container | `VM.PowerMgmt` | `/vms/<vmid>` |
| create VM | `VM.Allocate` (and `Datastore.AllocateSpace`) | `/vms/<vmid>`, `/storage/<id>` |
| delete VM | `VM.Allocate` | `/vms/<vmid>` |
| create / delete snapshot | `VM.Snapshot` | `/vms/<vmid>` |
| rollback snapshot | `VM.Snapshot.Rollback` | `/vms/<vmid>` |
| update VM | `VM.Config.CPU`, `VM.Config.Memory`, `VM.Config.Options` | `/vms/<vmid>` |
| VM / snapshot reads | `VM.Audit` | `/vms/<vmid>` |
| node / cluster / HA reads | `Sys.Audit` | `/nodes/<node>`, `/` |
| storage / backup reads | `Datastore.Audit` | `/storage/<id>` |
| task status | `Sys.Audit` or ownership of the task | `/nodes/<node>` |
| execute_vm_command | `VM.GuestAgent.Unrestricted` (PVE 9) or `VM.Monitor` (PVE 8) | `/vms/<vmid>` |

The exact minimal privilege per operation on your Proxmox version is not verified against a live
cluster (verify on your version, especially the PVE 9 privilege names). Treat the table as a starting
point and tighten it by trial: a missing privilege produces an explicit "Permission denied ... Required
privilege" message. Grant `VM.GuestAgent.Unrestricted` / `VM.Monitor` only if you enable `allow_exec`.

Never give the token more than the tools you actually enable need. Rotate it if it was ever shared,
logged or committed.

## Trust boundaries

1. MCP client / LLM -> this server. The model is not trusted: its tool arguments can be influenced by
   untrusted text (see prompt injection below). Inputs are validated (node, vmid, storage, snapshot
   name, UPID and so on are checked against strict patterns before any API path is built; see
   `src/proxmox_mcp/validators.py` and `tests/test_path_injection.py`).
2. This server -> Proxmox API. Authenticated by the API token over HTTPS.
3. HTTP client -> this server (HTTP transport only). Authenticated by API keys.

## HTTP transport

- API keys are mandatory. Only sha256 digests are configured (`PROXMOX_MCP_API_KEY_HASHES` or
  `http.api_key_digests`); generate one with
  `echo -n 'my-secret-key' | uv run python -m proxmox_mcp.auth.apikey`. The server refuses to start
  without digests (fail closed). There are no default keys.
- The default bind address is 127.0.0.1. `--no-auth` is accepted on loopback only.
- The server has no built-in TLS. If you expose it beyond localhost, put a TLS-terminating reverse
  proxy in front of it. Keys travel in the `Authorization: Bearer` or `X-API-Key` header and must not
  cross an untrusted network in clear text.
- `GET /health` is the only unauthenticated endpoint and returns only `{"status": "ok"}`. Detailed
  health (auth mode, Proxmox reachability, policy summary, Proxmox version) needs a valid key.
- The Docker image runs as a non-root user with a read-only root filesystem and dropped capabilities,
  and compose publishes on 127.0.0.1 only.

## Guest command execution

`execute_vm_command` runs a program inside a guest as whatever user the QEMU guest agent runs as
(usually root or SYSTEM). Enabling `allow_exec` therefore means: anyone who can drive the tool can run
arbitrary code in any guest the token can reach. Treat it like SSH access.

- argv without a shell: `command` plus `args` is sent as an argument list. A shell is used only if the
  caller passes `/bin/sh` with `-c` explicitly. Argument count and size are limited.
- Wait time is limited by `policy.exec_timeout_seconds`, each output stream by
  `policy.exec_max_output_bytes`, and concurrency by `policy.exec_max_concurrent`.
- The guest agent has no kill endpoint: a timed-out or cancelled command keeps running in the guest.
- The command, argv and output are never written to the server log.

## LLM-specific risk: prompt injection

An LLM that reads untrusted text (a web page, a VM name, a task log, a snapshot description) can be
tricked into calling tools with attacker-chosen arguments. Mitigations, in order of strength:

1. Leave `allow_destructive` and `allow_exec` off, or run with `read_only=true`.
2. Use a privilege-separated token limited to the paths you need.
3. Keep the confirm preview in the loop and enable per-tool approval in your MCP client for write,
   destructive and exec tools.
4. Do not mix this server with tools that fetch untrusted content in the same session unless the
   gates stay closed.

Values that come from Proxmox (descriptions, notes, task log lines) are redacted and length-limited
before being returned, but they still reach the model as text.

## Secrets handling

- The token value is a `SecretStr`: it never appears in `repr`, model dumps, configuration error
  messages or logs. Config errors are secret-free.
- A redaction filter is installed on every log handler (message, arguments, exception text). Known
  secrets and exec commands are registered for redaction.
- The log file is created with mode 0600 (an existing file is tightened). The default level is INFO.
- API keys are stored and compared as digests.
- `proxmox-config/config.json` is git-ignored. Never commit it. If a real token was ever stored in a
  working copy that was shared, rotate it.

## TLS to Proxmox

`proxmox.verify_ssl` defaults to true and is parsed strictly (a typo is an error, not "false").
For a private CA set `proxmox.ca_bundle`. Disabling verification logs a warning; do it only on a
trusted network.

## Known limitations

- No audit log beyond the normal application log, and no rate limiting in the server. Use a reverse
  proxy for rate limits and Proxmox's own task log for an audit trail of what was executed.
- Behaviour is verified against a mock Proxmox harness (PVE 8 and PVE 9 fixtures), not against a live
  cluster in CI. Live-cluster checks are on the maintainer checklist (`.planning/HUMAN-TESTS.md`).
- The 8-wait limit and exec concurrency limit are per process and in memory.
- Process-level isolation is on you: run the server as an unprivileged user.

## Threat model (STRIDE)

| Category | Threat | Mitigation | Residual risk |
|----------|--------|------------|---------------|
| Spoofing | Unauthenticated caller reaches the HTTP endpoint | Mandatory API-key digests, fail-closed start, loopback default, constant-time digest comparison | Keys in clear text without a TLS proxy; stolen key |
| Spoofing | Man-in-the-middle between server and Proxmox | `verify_ssl` default true, `ca_bundle` support, warning when disabled | Operator disables verification |
| Tampering | Crafted arguments change the Proxmox API path or request | Strict validators before any call, UPID validator rejects `?#%/..`, path-injection test suite | New tools must add validators and tests |
| Tampering | Model-driven destructive change | Risk classes, default-deny gates, confirm preview, MCP annotations | Operator opens the gates; confirm is not an authorization |
| Repudiation | No record of who triggered an action | Denied calls and startup policy are logged; Proxmox task log records the token | No per-caller audit log in the server |
| Information disclosure | Token or key leaks in logs, errors, repr | `SecretStr`, redaction filter, 0600 log file, secret-free config errors, command and output never logged | Short secrets are harder to redact; task logs shown to the model |
| Information disclosure | Health endpoint reveals topology | Unauthenticated `/health` returns only status | none known |
| Denial of service | Parallel waits or exec calls exhaust workers | Wait cap (8), exec concurrency cap, bounded timeouts, output cap, argv limits | A client with a valid key can still load the Proxmox API |
| Elevation of privilege | Over-privileged token lets the model do more than intended | Privilege-separated token guidance, `read_only`, `allow_*` gates | Depends on operator discipline |
| Elevation of privilege | Exec reaches guest code execution | `allow_exec` default off, no shell by default, limits, privilege `VM.GuestAgent.Unrestricted` / `VM.Monitor` required | Full guest compromise if enabled and abused |
| Elevation of privilege | Prompt injection drives tool calls | Gates closed by default, read-only mode, client-side approval | Cannot be fully removed while write tools are enabled |
