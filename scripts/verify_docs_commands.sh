#!/usr/bin/env bash
# Re-runnable clean-room check of every command documented in README.md / README.tr.md /
# HTTP_MCP_GUIDE.md. The tracked + untracked-but-not-ignored files are copied to a fresh temp
# directory (so proxmox-config/config.json, .venv and other ignored files never come along), the
# copy is turned into a throw-away git repository (some tests inspect git state), and the
# documented commands are run there with a FAKE config and a throw-away API key.
#
#   bash scripts/verify_docs_commands.sh              # everything except docker
#   VERIFY_DOCKER=1 bash scripts/verify_docs_commands.sh   # also docker build/compose (local only)
#   SKIP_PYTEST=1 bash scripts/verify_docs_commands.sh     # skip the (slow) full test run
#
# Prints one PASS/FAIL line per documented command. Never prints key or token values (only the
# first 8 characters of the throw-away digest) and never touches proxmox-config/config.json.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
FAILS=0
SERVER_PGID=""

cleanup() {
    if [ -n "$SERVER_PGID" ]; then kill -- "-$SERVER_PGID" 2>/dev/null || true; fi
    if [ "${VERIFY_DOCKER:-0}" = "1" ] && [ -f "$WORK/docker-compose.yml" ]; then
        (cd "$WORK" && docker compose -f docker-compose.yml -f "$WORK/override.yml" down -v >/dev/null 2>&1) || true
        docker rmi -f proxmox-mcp-extended:verify >/dev/null 2>&1 || true
    fi
    rm -rf "$WORK"
}
trap cleanup EXIT

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }
# check <label> <command...>: run quietly, report PASS/FAIL
check() {
    local label="$1"
    shift
    if "$@" >"$WORK/last.log" 2>&1; then pass "$label"; else fail "$label"; tail -n 15 "$WORK/last.log" | sed 's/^/      /'; fi
}

free_port() { python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'; }

wait_health() { # <port> <seconds>
    local i
    for i in $(seq 1 "$2"); do
        if curl -fsS -m 2 "http://127.0.0.1:$1/health" >/dev/null 2>&1; then return 0; fi
        sleep 1
    done
    return 1
}

CLEAN="$WORK/repo"
mkdir -p "$CLEAN"
(cd "$SRC" && git ls-files -co --exclude-standard -z | grep -zv '^proxmox-config/config\.json$' | xargs -0 -I{} cp --parents {} "$CLEAN")
cd "$CLEAN"
# throw-away repository so git-based tests behave as in a real checkout
git init -q
git add -A
git -c user.name=verify -c user.email=verify@example.invalid commit -q -m "verification copy"
pass "clean copy at throw-away path, git init + add + commit"
test ! -e proxmox-config/config.json || { fail "real config must not be in the copy"; exit 1; }

# fake config + throw-away key (never the real config)
mkdir -p "$WORK/cfg"
cat >"$WORK/cfg/config.json" <<'EOF'
{"proxmox": {"host": "127.0.0.1", "port": 8006, "verify_ssl": true, "service": "PVE", "timeout": 5},
 "auth": {"user": "monitor@pve", "token_name": "fake", "token_value": "fake-not-a-real-secret"},
 "logging": {"level": "INFO"}}
EOF
KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"

# README: Install
check "uv sync --locked" uv sync --locked
check "cp proxmox-config/config.example.json proxmox-config/config.json" \
    cp proxmox-config/config.example.json proxmox-config/config.json

# README: CLI help
check "uv run proxmox-mcp --help" uv run proxmox-mcp --help
check "uv run python -m proxmox_mcp.server_http --help" uv run python -m proxmox_mcp.server_http --help

# README: digest generation (stdout is the digest, the hint goes to stderr, no runpy warning)
DIGEST="$(printf '%s' "$KEY" | uv run python -m proxmox_mcp.auth.apikey 2>"$WORK/digest.err")"
if [[ "$DIGEST" =~ ^[0-9a-f]{64}$ ]] && ! grep -q RuntimeWarning "$WORK/digest.err"; then
    pass "echo -n KEY | python -m proxmox_mcp.auth.apikey (digest ${DIGEST:0:8}...)"
else
    fail "python -m proxmox_mcp.auth.apikey"
fi
export PROXMOX_MCP_API_KEY_HASHES="$DIGEST"

# README: fail-closed start without digests
if env -u PROXMOX_MCP_API_KEY_HASHES uv run python -m proxmox_mcp.server_http \
    --config "$WORK/cfg/config.json" --port "$(free_port)" >"$WORK/last.log" 2>&1; then
    fail "server_http refuses to start without digests"
else
    pass "server_http refuses to start without digests"
fi

INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"verify","version":"0"}}}'
probe() { # <port> <path> ; prints "<code-without-key> <code-with-key>"
    local nokey withkey
    nokey="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' -d "$INIT" "http://127.0.0.1:$1$2")"
    withkey="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' -H "Authorization: Bearer $KEY" \
        -d "$INIT" "http://127.0.0.1:$1$2")"
    echo "$nokey $withkey"
}

# README: HTTP mode (documented module command)
PORT="$(free_port)"
setsid uv run python -m proxmox_mcp.server_http --config "$WORK/cfg/config.json" \
    --port "$PORT" --path /proxmox-mcp >"$WORK/http.log" 2>&1 &
SERVER_PGID=$!
if wait_health "$PORT" 40; then pass "python -m proxmox_mcp.server_http starts, /health reachable"; else fail "server_http start"; tail -n 15 "$WORK/http.log" | sed 's/^/      /'; fi
[ "$(curl -s -m 5 "http://127.0.0.1:$PORT/health")" = '{"status":"ok"}' ] && pass "GET /health returns only {\"status\":\"ok\"}" || fail "GET /health body"
[ "$(probe "$PORT" /proxmox-mcp)" = "401 200" ] && pass "MCP initialize: 401 without key, 200 with Authorization: Bearer" || fail "auth probe"
XCODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -H "X-API-Key: $KEY" -d "$INIT" "http://127.0.0.1:$PORT/proxmox-mcp")"
[ "$XCODE" = "200" ] && pass "MCP initialize with X-API-Key header: 200" || fail "X-API-Key probe"
kill -- "-$SERVER_PGID" 2>/dev/null || true
wait "$SERVER_PGID" 2>/dev/null || true
SERVER_PGID=""

# README: ./start_http_server.sh
PORT="$(free_port)"
PROXMOX_MCP_CONFIG="$WORK/cfg/config.json" MCP_HTTP_PORT="$PORT" setsid ./start_http_server.sh >"$WORK/script.log" 2>&1 &
SERVER_PGID=$!
if wait_health "$PORT" 40; then pass "./start_http_server.sh starts, /health reachable"; else fail "./start_http_server.sh"; tail -n 15 "$WORK/script.log" | sed 's/^/      /'; fi
[ "$(probe "$PORT" /proxmox-mcp)" = "401 200" ] && pass "start_http_server.sh: 401 without key, 200 with key" || fail "start_http_server.sh auth probe"
kill -- "-$SERVER_PGID" 2>/dev/null || true
wait "$SERVER_PGID" 2>/dev/null || true
SERVER_PGID=""

# README: stdio
STDIO_OUT="$(printf '%s\n' "$INIT" | PROXMOX_MCP_CONFIG="$WORK/cfg/config.json" LOG_FILE="$WORK/stdio.log" timeout 60 uv run proxmox-mcp --config "$WORK/cfg/config.json" 2>/dev/null | head -n 1 || true)"
if echo "$STDIO_OUT" | grep -q '"protocolVersion"'; then pass "uv run proxmox-mcp --config <file> answers MCP initialize on stdio"; else fail "stdio initialize"; fi

# README: Development
check "uv run ruff check src tests scripts" uv run ruff check src tests scripts
check "uv run ruff format --check src tests scripts" uv run ruff format --check src tests scripts
check "uv run mypy src" uv run mypy src
check "uv run python scripts/gen_tool_table.py (matches README block)" bash -c '
    gen="$(uv run python scripts/gen_tool_table.py)"
    for f in README.md README.tr.md; do
        block="$(sed -n "/<!-- tools:start -->/,/<!-- tools:end -->/p" "$f" | sed "1d;\$d")"
        [ "$block" = "$gen" ] || exit 1
    done'
if [ "${SKIP_PYTEST:-0}" = "1" ]; then
    echo "SKIP  uv run pytest -q (SKIP_PYTEST=1)"
else
    check "uv run pytest -q" uv run pytest -q
fi

# README: Docker Compose (optional, local only, no push)
if [ "${VERIFY_DOCKER:-0}" = "1" ]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "SKIP  docker not available"
    else
        DPORT="$(free_port)"
        cat >"$WORK/override.yml" <<EOF
services:
  proxmox-mcp-extended:
    ports: !override
      - "127.0.0.1:${DPORT}:8812"
    volumes: !override
      - ${WORK}/cfg:/config:ro
EOF
        check "docker compose config fails without PROXMOX_MCP_API_KEY_HASHES" bash -c \
            '! env -u PROXMOX_MCP_API_KEY_HASHES docker compose config -q'
        check "docker compose up -d --build" docker compose -f docker-compose.yml -f "$WORK/override.yml" up -d --build
        HEALTH=""
        for _ in $(seq 1 40); do
            HEALTH="$(docker inspect --format '{{.State.Health.Status}}' ProxmoxMCP-Extended 2>/dev/null || true)"
            [ "$HEALTH" = healthy ] && break
            sleep 3
        done
        [ "$HEALTH" = healthy ] && pass "container healthy" || fail "container health ($HEALTH)"
        [ "$(probe "$DPORT" /proxmox-mcp)" = "401 200" ] && pass "container: 401 without key, 200 with key" || fail "container auth probe"
        [ "$(docker inspect --format '{{.Config.User}}' ProxmoxMCP-Extended)" = "10001" ] && pass "container runs as uid 10001" || fail "container user"
    fi
fi

echo
if [ "$FAILS" -eq 0 ]; then echo "ALL PASS"; else echo "$FAILS FAILED"; exit 1; fi
