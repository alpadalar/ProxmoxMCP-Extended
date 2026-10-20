# syntax=docker/dockerfile:1
# Hardened image: digest-pinned base, multi-stage, locked deps, non-root, no secrets or config baked in.

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.6@sha256:88bc6eb1ccd4b82efd0e1b530caffabddf50dc2bf612e66c14ea25b8ee8a4d3d /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first (cache friendly); README.md is required because pyproject declares it.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

RUN groupadd --system --gid 10001 proxmoxmcp \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin proxmoxmcp

COPY --from=builder /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PROXMOX_MCP_CONFIG=/config/config.json

WORKDIR /app
USER 10001
EXPOSE 8812

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8812/health', timeout=4).status == 200 else 1)"]

# 0.0.0.0 is container-internal; compose publishes on 127.0.0.1 only and the server's
# non-loopback guard still requires API-key digests (PROXMOX_MCP_API_KEY_HASHES).
ENTRYPOINT ["python", "-m", "proxmox_mcp.server_http", "--host", "0.0.0.0", "--port", "8812", "--path", "/proxmox-mcp"]
