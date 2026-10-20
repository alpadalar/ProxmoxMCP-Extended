# ProxmoxMCP-Extended

English | [Türkçe](README.tr.md)

A Python [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that lets MCP
clients (Claude Desktop, Cursor, Cline, ...) inspect and manage a Proxmox VE cluster through the
Proxmox API: nodes, VMs, LXC containers, storage, snapshots, backups, tasks and HA status.

It exposes 27 tools over stdio or authenticated streamable HTTP. Everything that changes state is
gated by a safety policy that is closed by default (see [Safety model](#safety-model)).

## Fork lineage

- **Original project**: [canvrno/ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP)
- **First fork**: [RekklesNA/ProxmoxMCP-Plus](https://github.com/RekklesNA/ProxmoxMCP-Plus)
- **This fork**: [alpadalar/ProxmoxMCP-Extended](https://github.com/alpadalar/ProxmoxMCP-Extended) (you are here)

## Acknowledgments

This project is built upon the open-source [ProxmoxMCP](https://github.com/canvrno/ProxmoxMCP) by
[@canvrno](https://github.com/canvrno). Thanks to the original author for the foundation, to the
maintainers of ProxmoxMCP-Plus, and to the Proxmox community. Upstream copyright notices are kept
in [LICENSE](LICENSE) and [NOTICE](NOTICE).

Built with [Proxmoxer](https://github.com/proxmoxer/proxmoxer),
[FastMCP](https://gofastmcp.com), the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
and [Pydantic](https://docs.pydantic.dev/).

## Requirements

- Python 3.10 or newer
- [uv](https://docs.astral.sh/uv/)
- Proxmox VE 8.x or 9.x with an API token (see [Create an API token](#create-an-api-token))
- Docker with Compose v2 (only for the container deployment)

## Install

```bash
git clone https://github.com/alpadalar/ProxmoxMCP-Extended.git
cd ProxmoxMCP-Extended
uv sync
```

## Configuration

Create your configuration from the template (the real file is git-ignored; never commit it):

```bash
cp proxmox-config/config.example.json proxmox-config/config.json
```

Edit `proxmox-config/config.json`: set `proxmox.host`, `auth.user`, `auth.token_name` and
`auth.token_value`. TLS verification is on by default; for a private CA set `proxmox.ca_bundle`
instead of disabling verification.

Configuration is resolved by a single loader. Precedence (highest wins):
**CLI flags > environment variables > JSON config file > built-in defaults.**
Unknown keys, mistyped booleans (e.g. `PROXMOX_VERIFY_SSL=ture`) and invalid values fail at
startup with an error that never includes secret values.

| Setting | JSON key | Environment variable | CLI flag |
|---|---|---|---|
| Host | `proxmox.host` | `PROXMOX_HOST` | |
| Port (default 8006) | `proxmox.port` | `PROXMOX_PORT` | |
| TLS verification (default `true`) | `proxmox.verify_ssl` | `PROXMOX_VERIFY_SSL` | `--verify-ssl` |
| CA bundle file (private CA) | `proxmox.ca_bundle` | `PROXMOX_CA_BUNDLE` | `--ca-bundle` |
| Service (`PVE`/`PMG`/`PBS`) | `proxmox.service` | `PROXMOX_SERVICE` | |
| Request timeout, seconds (default 30, max 300) | `proxmox.timeout` | `PROXMOX_TIMEOUT` | |
| API user | `auth.user` | `PROXMOX_USER` | |
| Token name | `auth.token_name` | `PROXMOX_TOKEN_NAME` | |
| Token secret | `auth.token_value` | `PROXMOX_TOKEN_VALUE` | |
| HTTP API key digests | `http.api_key_digests` | `PROXMOX_MCP_API_KEY_HASHES` | |
| Read-only mode | `policy.read_only` | `PROXMOX_MCP_READ_ONLY` | `--read-only` |
| Allow destructive tools | `policy.allow_destructive` | `PROXMOX_MCP_ALLOW_DESTRUCTIVE` | `--allow-destructive` |
| Allow exec tool | `policy.allow_exec` | `PROXMOX_MCP_ALLOW_EXEC` | `--allow-exec` |
| Exec timeout seconds (default 30) | `policy.exec_timeout_seconds` | `PROXMOX_MCP_EXEC_TIMEOUT` | |
| Exec output cap per stream, bytes (default 65536) | `policy.exec_max_output_bytes` | `PROXMOX_MCP_EXEC_MAX_OUTPUT` | |
| Concurrent exec calls (default 2) | `policy.exec_max_concurrent` | `PROXMOX_MCP_EXEC_MAX_CONCURRENT` | |
| Log level (default `INFO`) | `logging.level` | `LOG_LEVEL` | `--log-level` |
| Log file | `logging.file` | `LOG_FILE` | `--log-file` |

Booleans accept `true/false`, `1/0`, `yes/no`, `on/off`. Empty environment variables are treated as
unset. `ca_bundle` cannot be combined with `verify_ssl=false`, and disabling verification logs a
warning.

### Create an API token

1. In the Proxmox web interface open Datacenter -> Permissions -> API Tokens and add a token.
2. Use a dedicated, least-privilege user (for example `monitor@pve`), not `root@pam`.
3. Keep **Privilege Separation** enabled and grant the token only the roles it needs on the paths
   it needs. A read-only role such as `PVEAuditor` on `/` is enough for every `read` tool;
   add VM/storage privileges (for example `VM.PowerMgmt`, `VM.Snapshot`, `VM.Allocate`) only for
   the write and destructive tools you intend to enable. Errors name the missing privilege.
4. Copy the token secret once; Proxmox does not show it again.

## Running

### stdio (Claude Desktop, Cursor, Cline launch it for you)

```bash
uv run proxmox-mcp --config proxmox-config/config.json
```

`./start_server.sh` does the same. Policy flags (`--read-only`, `--allow-destructive`,
`--allow-exec`) can be appended.

### HTTP (streamable HTTP, API key required)

HTTP mode refuses to start without API-key digests (fail-closed). Create a key, store only its
sha256 digest on the server, and give the plain key to your client:

```bash
echo -n 'my-secret-key' | uv run python -m proxmox_mcp.auth.apikey
export PROXMOX_MCP_API_KEY_HASHES=<digest>[,<digest2>]
```

Start the server (default bind `127.0.0.1:8812`, path `/proxmox-mcp`):

```bash
./start_http_server.sh
# or
uv run python -m proxmox_mcp.server_http --config proxmox-config/config.json
```

Clients send `Authorization: Bearer my-secret-key` or `X-API-Key: my-secret-key`:

```bash
curl -s -X POST http://127.0.0.1:8812/proxmox-mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Authorization: Bearer my-secret-key' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

Notes:

- `start_http_server.sh` reads `MCP_HTTP_HOST`, `MCP_HTTP_PORT`, `MCP_HTTP_PATH` and
  `PROXMOX_MCP_CONFIG`; the module accepts `--host`, `--port`, `--path` and `--config`.
- Digests can also be set as `http.api_key_digests` in the config file. Precedence: CLI/constructor
  > `PROXMOX_MCP_API_KEY_HASHES` > config; sources replace each other and are never merged.
- `--no-auth` is accepted on loopback only.
- `GET /health` is the only unauthenticated endpoint and returns just `{"status": "ok"}`. Callers
  with a valid key (and the `health` tool) also see auth mode, Proxmox reachability, policy and
  PVE version.
- The server has no built-in TLS. If you bind a non-loopback host the API key travels in
  cleartext; terminate TLS in a reverse proxy (a startup warning is logged).

See [HTTP_MCP_GUIDE.md](HTTP_MCP_GUIDE.md) (Turkish) for a longer HTTP walkthrough.

### Docker Compose

The image is pinned by digest, runs as a non-root user (uid 10001) on a read-only filesystem with
all capabilities dropped, and publishes the port on `127.0.0.1` only. The configuration is
mounted read-only from `./proxmox-config`; nothing secret is baked into the image.

```bash
echo -n 'my-secret-key' | uv run python -m proxmox_mcp.auth.apikey
export PROXMOX_MCP_API_KEY_HASHES=<digest>
docker compose up -d --build
docker compose ps
curl -s http://127.0.0.1:8812/health
docker compose down
```

`docker compose` refuses to start if `PROXMOX_MCP_API_KEY_HASHES` is unset. The container reports
its health through a built-in `HEALTHCHECK`.

## Safety model

All gates default to closed; gated tools stay registered (the tool list never changes) and refuse
at call time with an explanatory error.

| Flag | Default | Effect |
|---|---|---|
| `read_only` | `false` | When `true`, blocks every write, destructive and exec tool and overrides the `allow_*` flags |
| `allow_destructive` | `false` | Enables the destructive tools (stop/reset/delete VM, rollback/delete snapshot, stop container, update VM) |
| `allow_exec` | `false` | Enables `execute_vm_command` |

Set them with `--read-only` / `--allow-destructive` / `--allow-exec`, the `PROXMOX_MCP_*`
environment variables, or the `policy` section of the config file.

- Destructive tools that take `confirm` (`delete_vm`, `stop_vm`, `reset_vm`, `rollback_snapshot`,
  `delete_snapshot`, `stop_container`) return a preview of what would happen unless you pass
  `confirm=true`.
- `execute_vm_command` runs the program directly through the QEMU guest agent, without a shell:
  pass `command` plus an `args` list (use `/bin/sh` with `['-c', '...']` explicitly if you need
  one). Each stream is capped (`exec_max_output_bytes`), calls time out
  (`exec_timeout_seconds`) and concurrency is limited (`exec_max_concurrent`).
- Mutating tools accept optional `wait` and `timeout` to wait for the Proxmox task (UPID) to finish
  and report its real exit status.
- HTTP mode requires an API key and binds loopback by default.

See [SECURITY.md](SECURITY.md) for the threat model.

## Tools

27 tools. The table is generated from `tests/golden/tools.json` by
`scripts/gen_tool_table.py`; required parameters are bold.

<!-- tools:start -->
| Tool | Risk class | Gate | Parameters |
|---|---|---|---|
| `get_cluster_status` | read | always available |  |
| `get_containers` | read | always available |  |
| `get_ha_status` | read | always available |  |
| `get_node_status` | read | always available | **node** |
| `get_nodes` | read | always available |  |
| `get_storage` | read | always available |  |
| `get_task_status` | read | always available | **upid** |
| `get_vm_usage` | read | always available | **node**, **vmid** |
| `get_vms` | read | always available |  |
| `health` | read | always available |  |
| `list_backups` | read | always available | **node**, storage, vmid |
| `list_snapshots` | read | always available | **node**, **vmid** |
| `wait_for_task` | read | always available | timeout, **upid** |
| `create_snapshot` | write | blocked by `read_only` | description, **name**, **node**, timeout, **vmid**, vmstate, wait |
| `create_vm` | write | blocked by `read_only` | **cpus**, **disk_size**, iso_name, iso_storage, **memory**, **name**, **node**, ostype, storage, **vmid** |
| `shutdown_container` | write | blocked by `read_only` | node, timeout, **vmid**, wait |
| `shutdown_vm` | write | blocked by `read_only` | **node**, timeout, **vmid**, wait |
| `start_container` | write | blocked by `read_only` | node, timeout, **vmid**, wait |
| `start_vm` | write | blocked by `read_only` | **node**, timeout, **vmid**, wait |
| `delete_snapshot` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, **name**, **node**, timeout, **vmid**, wait |
| `delete_vm` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, force, **node**, timeout, **vmid**, wait |
| `reset_vm` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, **node**, timeout, **vmid**, wait |
| `rollback_snapshot` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, **name**, **node**, timeout, **vmid**, wait |
| `stop_container` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, node, timeout, **vmid**, wait |
| `stop_vm` | destructive | needs `allow_destructive`; blocked by `read_only`; `confirm=true` to execute (otherwise a preview) | confirm, **node**, timeout, **vmid**, wait |
| `update_vm` | destructive | needs `allow_destructive`; blocked by `read_only` | cpus, memory, name, **node**, **vmid** |
| `execute_vm_command` | exec | needs `allow_exec`; blocked by `read_only` | args, **command**, **node**, **vmid** |
<!-- tools:end -->

Usage notes:

- **Discovery**: `get_nodes`, `get_node_status`, `get_cluster_status`, `get_vms`, `get_containers`,
  `get_storage`, `get_vm_usage`, `health`. `get_vms` and `get_containers` list every guest in the
  cluster.
- **Tasks**: mutating tools return a UPID. Use `get_task_status` for a snapshot or
  `wait_for_task` to wait (bounded by `timeout`).
- **VM lifecycle**: `create_vm` (optional ISO via `iso_name`/`iso_storage`; disk format is chosen
  from the storage type), `start_vm`, `shutdown_vm` (graceful), `stop_vm` (force),
  `reset_vm`, `delete_vm`, `update_vm`.
- **Containers (LXC)**: `get_containers`, `start_container`, `shutdown_container`,
  `stop_container`.
- **Snapshots and backups**: `list_snapshots`, `create_snapshot`, `rollback_snapshot`,
  `delete_snapshot`, `list_backups` (read-only; restore is not implemented).
- **HA**: `get_ha_status`.
- **Guest exec**: `execute_vm_command` (needs the QEMU guest agent and `allow_exec`).

## Client configuration

Replace `/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended` with your checkout path and `YOUR_API_KEY` with
the plain API key (the one whose digest the server knows). The JSON below is exactly what the
files under [`examples/`](examples) contain. The stdio entries are exercised by the test suite
with a real MCP handshake that lists all 27 tools; client UI acceptance is a manual check.

### Claude Desktop

File: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows). Restart Claude Desktop after editing.
Remote HTTP servers are not configured in this file, so the HTTP entry uses the
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridge (requires Node.js). Source:
[`examples/claude_desktop_config.json`](examples/claude_desktop_config.json).

```json
{
  "mcpServers": {
    "proxmox-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended",
        "run",
        "proxmox-mcp"
      ],
      "env": {
        "PROXMOX_MCP_CONFIG": "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended/proxmox-config/config.json"
      }
    },
    "proxmox-mcp-http": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://127.0.0.1:8812/proxmox-mcp",
        "--allow-http",
        "--header",
        "Authorization:${PROXMOX_MCP_AUTH}"
      ],
      "env": {
        "PROXMOX_MCP_AUTH": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

### Cursor

File: `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` in a project. Cursor also supports
`${env:NAME}` interpolation in `url`, `headers` and `env`, which avoids putting the key in the
file. Source: [`examples/cursor_mcp_config.json`](examples/cursor_mcp_config.json).

```json
{
  "mcpServers": {
    "proxmox-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended",
        "run",
        "proxmox-mcp"
      ],
      "env": {
        "PROXMOX_MCP_CONFIG": "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended/proxmox-config/config.json"
      }
    },
    "proxmox-mcp-http": {
      "url": "http://127.0.0.1:8812/proxmox-mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

### Cline

File: `cline_mcp_settings.json` (open it from the MCP Servers panel in Cline). Remote servers need
`"type": "streamableHttp"`; without it Cline assumes legacy SSE. Source:
[`examples/cline_mcp_settings.json`](examples/cline_mcp_settings.json).

```json
{
  "mcpServers": {
    "proxmox-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended",
        "run",
        "proxmox-mcp"
      ],
      "env": {
        "PROXMOX_MCP_CONFIG": "/ABSOLUTE/PATH/TO/ProxmoxMCP-Extended/proxmox-config/config.json"
      },
      "disabled": false,
      "autoApprove": []
    },
    "proxmox-mcp-http": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8812/proxmox-mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Development

```bash
uv sync
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest -q
```

- The test suite runs against a mocked Proxmox API; no cluster is needed (or used) in CI.
- `tests/golden/tools.json` is the snapshot of the public tool surface. Changing a tool name or
  parameter changes the snapshot and is a breaking change; regenerate the README table with
  `uv run python scripts/gen_tool_table.py`.
- `bash scripts/verify_docs_commands.sh` re-runs the documented commands in a clean copy of the
  repository (set `VERIFY_DOCKER=1` to include the container).
- `scripts/live/` holds manual scripts that need a real cluster; they are not part of the suite.

## Troubleshooting

- **Server exits at startup mentioning API keys**: HTTP mode needs digests; see
  [HTTP (streamable HTTP, API key required)](#http-streamable-http-api-key-required).
- **401 from the HTTP endpoint**: send `Authorization: Bearer <plain key>` (not the digest).
- **TLS errors toward Proxmox**: use `proxmox.ca_bundle` for a private CA; `verify_ssl=false` is a
  last resort.
- **"Permission denied ... Required privilege"**: the token lacks the named privilege on that path.
- **A tool says it is disabled by policy**: see [Safety model](#safety-model).
- Logs go to the configured `logging.file` (in the container, `/tmp/proxmox_mcp.log`) and
  `docker compose logs`.

## Security

Read [SECURITY.md](SECURITY.md) for what this server can do to your hypervisor and how to report
vulnerabilities.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Notable changes are listed in [CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE); upstream attributions are in [NOTICE](NOTICE).
