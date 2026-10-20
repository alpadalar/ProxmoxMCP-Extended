# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - Unreleased

<!-- Release checklist: replace "Unreleased" with the tag date and add the
     [1.0.0] release-tag link reference at the bottom of this file. -->

First release of ProxmoxMCP-Extended as an independent, hardened fork of
[RekklesNA/ProxmoxMCP-Plus](https://github.com/RekklesNA/ProxmoxMCP-Plus) (itself a fork of
[canvrno/ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP)). Read the breaking changes before
upgrading an existing setup.

### Breaking changes

- **Stricter config and `create_vm` validation**: the config now rejects unknown keys, requires
  `user@realm` users, a `service` of the allowed values, a restricted token-name charset and a valid
  port range; `create_vm` limits (cpus, memory, disk) are now also enforced over HTTP. Configs that
  used to load may be rejected with a clear error.
- **`/health` `pve` version** is `null` until the first tool call has connected to Proxmox.
- **Python 3.10 or newer is required** (was 3.9). Supported and tested: 3.10 to 3.14. Migration:
  upgrade the interpreter, then run `uv sync`.
- **Dependencies moved to `fastmcp>=4.1.2,<5` and `mcp>=2,<3`** (FastMCP is taken from PyPI).
  Migration: reinstall with `uv sync`; custom code importing the old FastMCP or MCP APIs must be
  updated.
- **Django / Yartu authentication, default tokens and the Django management commands were removed.**
  HTTP mode now requires API keys, configured as sha256 digests in `PROXMOX_MCP_API_KEY_HASHES` or
  `http.api_key_digests`. The server refuses to start without digests (fail closed). Migration:
  generate a digest with `echo -n 'my-secret-key' | uv run python -m proxmox_mcp.auth.apikey`, set
  it, and send the plain key as `Authorization: Bearer <key>` or `X-API-Key`. Digest sources replace
  each other (CLI > environment > config) and are never merged.
- **HTTP default bind address is now `127.0.0.1`** (was all interfaces). `--no-auth` is accepted on
  loopback only. Migration: to listen elsewhere pass `--host` explicitly and put a TLS reverse proxy
  in front; the server has no built-in TLS.
- **Default HTTP endpoint path is `/proxmox-mcp`** (was `/mcp` in the upstream fork). Migration: update
  client URLs or pass `--path /mcp`.
- **Safety policy, closed by default.** New `policy.read_only`, `policy.allow_destructive` and
  `policy.allow_exec` settings (also `PROXMOX_MCP_READ_ONLY`, `PROXMOX_MCP_ALLOW_DESTRUCTIVE`,
  `PROXMOX_MCP_ALLOW_EXEC` and `--read-only`, `--allow-destructive`, `--allow-exec`). All gates default
  to `false`: destructive and exec calls are refused at call time with a `policy_denied` error, although
  the tools stay registered, so the tool list is unchanged. Migration: set `allow_destructive` and/or
  `allow_exec` to `true` if you rely on those tools.
- **`update_vm` now counts as destructive** and requires `allow_destructive` (it overwrites existing
  configuration). It has no `confirm` parameter.
- **`confirm=true` is required** for `delete_vm`, `stop_vm`, `reset_vm`, `rollback_snapshot`,
  `delete_snapshot` and `stop_container`. Without it the call returns a preview and changes nothing.
  Migration: have clients pass `confirm=true` after reviewing the preview.
- **`get_containers` output format changed.** The HTTP transport now returns the same JSON as stdio
  (it previously returned formatted text). Migration: parse the JSON output.
- **`/health` is minimal when unauthenticated** (`{"status": "ok"}`). Detail (auth mode, Proxmox
  reachability, transport, policy summary, Proxmox version) needs a valid API key or the `health`
  tool.
- **`execute_vm_command` changed.** It sends an argument list to the guest agent without a shell:
  pass `command` plus the new `args` list (use `/bin/sh` with `["-c", "..."]` explicitly for shell
  features). A non-zero exit code, a signal kill or a timeout is reported as failed (before, a
  non-zero exit still said SUCCESS). Output per stream is capped (`policy.exec_max_output_bytes`,
  default 65536), the wait is bounded (`policy.exec_timeout_seconds`, default 30), concurrent calls
  are limited (`policy.exec_max_concurrent`, default 2) and argv size is limited. The command and its
  output are never logged. Requires `allow_exec`.
- **Configuration is strict.** Unknown keys are rejected (`extra=forbid`), `verify_ssl` is parsed
  strictly (a typo such as `ture` is an error instead of silently disabling verification), and TLS
  verification is on by default. Migration: remove unknown keys and set `proxmox.ca_bundle` for a
  private CA instead of disabling verification.
- **The mcpo / OpenAPI proxy was removed** (`start_openapi.sh`, its live test and the related
  docs). Use the stdio or streamable HTTP transport.
- **`setup.py` and `requirements*.in` were removed** in favour of `pyproject.toml` and `uv.lock`.
  `black` was replaced by `ruff format`. Migration: use `uv sync`.
- **Server signal handlers were removed**; shutdown is managed by uvicorn / FastMCP (Ctrl-C raises
  `KeyboardInterrupt` as usual).
- **The default log level is INFO** and the log file is created with mode 0600.
- **Docker and Compose changed.** The `HTTP_HOST`, `HTTP_PORT` and `HTTP_PATH` environment variables
  no longer have any effect: host, port and path are fixed in the image `ENTRYPOINT`, and extra
  `docker run` arguments are now appended to it instead of replacing the command (use a compose
  `command:` or the `PROXMOX_MCP_*` variables to change behaviour). The config mount moved from
  `/app/proxmox-config` to `/config`. The compose port is published on `127.0.0.1` only, so remote
  access that used to work stops working; put a TLS reverse proxy in front. The `proxmox-network`
  network was removed. The container now runs as uid 10001 on a read-only root filesystem and needs
  `PROXMOX_MCP_API_KEY_HASHES` (compose refuses to render without it). Migration: mount the config at
  `/config`, make `config.json` readable by uid 10001 (see the README Docker section), and set the
  key digests.
- **Error messages changed.** Missing VMs report "VM <id> not found on node <node>"; permission
  errors name the privilege and ACL path; `create_vm` says "creation queued" because it only queues a
  task. Clients that matched on the old text must be updated.

### Added

- New tools (tool count 18 to 27; read unless noted):
  - `get_task_status(upid)` and `wait_for_task(upid, timeout=30)`: task state with a redacted log
    tail; success only when the exit status is exactly `OK` (`WARNINGS` is reported as warnings).
  - `list_snapshots(node, vmid)`.
  - `delete_snapshot(node, vmid, name, confirm=false, wait=false, timeout=30)` (destructive).
  - `list_backups(node, storage=None, vmid=None)`.
  - `start_container(vmid, node=None, wait=false, timeout=30)` and
    `shutdown_container(vmid, node=None, wait=false, timeout=30)` (write).
  - `stop_container(vmid, node=None, confirm=false, wait=false, timeout=30)` (destructive).
  - `get_ha_status()`.
- Optional `wait` (bool, default false) and `timeout` (1 to 300 seconds, default 30) on `start_vm`,
  `stop_vm`, `shutdown_vm`, `reset_vm`, `delete_vm`, `create_snapshot` and `rollback_snapshot`.
  Omitting `wait` keeps the previous behaviour.
- Optional `confirm` on `delete_vm`, `stop_vm`, `reset_vm`, `rollback_snapshot` and optional `args`
  on `execute_vm_command`.
- MCP tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) derived
  from each tool's risk class.
- `proxmox.ca_bundle` for private CAs, `proxmox.timeout`, and lazy connection to Proxmox (the server
  starts without reaching the cluster).
- `/health` reports `pve: {version, release, major}` once connected, plus `transport`, Proxmox
  reachability and the active policy.
- HTTP gained `update_vm` and the full stdio tool descriptions and parameter schemas (both
  transports register the same 27 tools from one registry).
- Fixture-driven mock Proxmox harness (PVE 8 and PVE 9) and a golden snapshot of the tool surface.
- Client configuration examples for Claude Desktop, Cursor and Cline; English and Turkish README.
- Hardened multi-stage Dockerfile (pinned base images, non-root, health check) and compose file
  (loopback publish, read-only root filesystem, dropped capabilities, digests required).
- CI workflow files, release dry-run and Dependabot configuration (written, see `.github/`), plus
  SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, issue forms and a pull request template.
- Scripts: `scripts/gen_tool_table.py`, `scripts/verify_docs_commands.sh`,
  `scripts/scan_history.py`.

### Changed

- Proxmox VE 8.x and 9.x compatibility: errors are mapped from HTTP status codes (403 and the 500
  "Permission check failed" name the required privilege and path; lock conflicts and unreachable nodes
  get actionable messages); VM existence comes from a qemu listing instead of error text; null task
  returns (rollback and config updates on PVE 9.1) print "no task id returned; verify VM state"; the
  removed `VM.Monitor` privilege is handled with version-aware guest agent hints; `delete_vm force=true`
  waits (up to 30 seconds) for the stop task and aborts without deleting on failure.
- `list_snapshots` omits the `current` pseudo snapshot; descriptions and notes are redacted and
  capped at 300 characters.
- Tools validate all inputs first (node, vmid, storage, snapshot name, UPID and so on) before any
  Proxmox call.
- Logging: with no `logging.file` the server logs to stderr at the configured level (previously
  only errors reached the console). The container no longer sets `LOG_FILE`; compose uses the
  `json-file` driver (10 MB x 5) and `config.example.json` no longer sets a log file. The optional
  log file is now rotated (10 MiB x 5 backups), and active and rotated files are created with mode
  0600.
- Linting and type checking: `ruff check`, `ruff format` and `mypy src` are clean and enforced.
- Version bumped to 1.0.0; development status Beta.

### Security

- The API token is a `SecretStr`; tokens, API keys, exec commands and output are redacted from logs,
  errors and `repr`. A redaction filter covers every log handler.
- Central path-injection validators and a UPID validator that rejects URL metacharacters and `..`.
- TLS verification on by default, with a warning when it is disabled.
- API keys are stored and compared as sha256 digests with a constant-time comparison; HTTP is
  fail-closed and loopback by default.
- Call-time policy gates with a confirm preview for destructive tools; bounded waits (at most 8
  concurrent) and bounded exec.
- The container runs as a non-root user.

### Removed

- Django, Django REST framework and Yartu authentication, default tokens and the management
  commands.
- The mcpo / OpenAPI proxy script, its live test and documentation.
- `setup.py`, `requirements.in` and `requirements-dev.in`.
- `examples/django_models.py`.
