"""Application factory shared by the stdio and HTTP transports.

``create_app`` is the only place that wires configuration, the lazy Proxmox manager,
the tool registry, the ``/health`` route and the auth middleware.  For HTTP the ASGI
application is built exactly once and ``serve_asgi`` serves that same object.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import uvicorn
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth.apikey import APIKeyAuthMiddleware, is_authorized
from .auth.hostguard import LoopbackHostGuardMiddleware
from .auth.policy import LOOPBACK_HOSTS, resolve_auth_policy
from .core.proxmox import ProxmoxManager
from .policy import ToolPolicy, compose_wraps, make_policy_wrap
from .tools.cluster import ClusterTools
from .tools.container import ContainerTools
from .tools.node import NodeTools
from .tools.registry import ToolContext, ToolSpec, build_registry, register_tools
from .tools.storage import StorageTools
from .tools.tasks import TaskTools
from .tools.vm import VMTools

logger = logging.getLogger("proxmox-mcp.app")


def build_uvicorn_server(asgi: Any, host: str, port: int) -> uvicorn.Server:
    """Construct the uvicorn server used in production (and by the E2E tests)."""
    return uvicorn.Server(
        uvicorn.Config(asgi, host=host, port=port, log_config=None, access_log=False)
    )


def serve_asgi(asgi: Any, host: str, port: int) -> None:
    """Serve ``asgi`` with uvicorn (blocking)."""
    build_uvicorn_server(asgi, host, port).run()


@dataclass
class ProxmoxApp:
    """Everything ``create_app`` wires together."""

    config: Any
    manager: ProxmoxManager
    mcp: FastMCP
    transport: str
    asgi: Any | None = None
    auth_state: str = "n/a"
    host: str = "127.0.0.1"
    port: int = 8812
    path: str = "/proxmox-mcp"
    tests_passed: bool | None = None
    specs: list[ToolSpec] = field(default_factory=list)
    policy: ToolPolicy | None = None
    node_tools: Any = None
    vm_tools: Any = None
    storage_tools: Any = None
    cluster_tools: Any = None
    task_tools: Any = None
    container_tools: Any = None

    def _policy_summary(self) -> dict[str, bool]:
        return self.policy.summary() if self.policy else {}

    def _pve_summary(self) -> dict[str, Any] | None:
        info = self.manager.version_info()
        if info is None:
            return None
        return {"version": info.version, "release": info.release, "major": info.major}

    def health_payload(self) -> dict[str, Any]:
        """Health information; performs no network I/O."""
        if self.transport == "http":
            return {
                "status": "ok",
                "server": "ProxmoxMCP-HTTP",
                "transport": "http",
                "auth": self.auth_state,
                "policy": self._policy_summary(),
                "proxmox": self.manager.connection_state(),
                "pve": self._pve_summary(),
                "timestamp": datetime.now().isoformat(),
            }
        if self.tests_passed is True:
            status = "ok"
        elif self.tests_passed is False:
            status = "degraded"
        else:
            status = "unknown"
        return {
            "status": status,
            "tests_passed": self.tests_passed,
            "policy": self._policy_summary(),
            "pve": self._pve_summary(),
            "details": (
                "Startup tests passed"
                if self.tests_passed
                else ("Startup tests failed" if self.tests_passed is False else "No tests executed")
            ),
        }

    def run(self) -> None:
        """Run the transport (blocking)."""
        if self.transport == "stdio":
            self.mcp.run(transport="stdio")
        else:
            serve_asgi(self.asgi, self.host, self.port)


def create_app(
    config: Any,
    transport: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8812,
    path: str = "/proxmox-mcp",
    api_key_digests: list[str] | None = None,
    insecure_no_auth: bool = False,
    wrap: Callable[[ToolSpec, Callable[..., Any]], Callable[..., Any]] | None = None,
) -> ProxmoxApp:
    """Build a ProxmoxApp for ``transport`` ("stdio" or "http")."""
    if transport not in ("stdio", "http"):
        raise ValueError(f"Unknown transport {transport!r}; expected 'stdio' or 'http'")

    policy = None
    if transport == "http":
        # Fail closed before anything else is built.
        policy = resolve_auth_policy(
            config,
            host=host,
            explicit_digests=api_key_digests,
            insecure_no_auth=insecure_no_auth,
        )
        if not policy.enabled:
            logger.warning(
                "AUTHENTICATION DISABLED (--no-auth): all MCP tools, including VM "
                "create/delete/exec, are open to anyone who can reach %s:%s",
                host,
                port,
            )

        elif host not in LOOPBACK_HOSTS:
            logger.warning(
                "Serving the API key over plaintext HTTP on non-loopback host %s; "
                "there is no built-in TLS, so terminate TLS in a reverse proxy in front of "
                "this server",
                host,
            )

    manager = ProxmoxManager(config.proxmox, config.auth)
    api = manager.get_api()
    node_tools = NodeTools(api)
    vm_tools = VMTools(
        api,
        exec_timeout=config.policy.exec_timeout_seconds,
        exec_max_output=config.policy.exec_max_output_bytes,
        exec_max_concurrent=config.policy.exec_max_concurrent,
        pve_major=manager.pve_major,
    )
    storage_tools = StorageTools(api)
    cluster_tools = ClusterTools(api)
    task_tools = TaskTools(api)
    task_tools._pve_major = manager.pve_major
    container_tools = ContainerTools(api)
    container_tools._pve_major = manager.pve_major

    app = ProxmoxApp(
        config=config,
        manager=manager,
        mcp=FastMCP("ProxmoxMCP-HTTP" if transport == "http" else "ProxmoxMCP"),
        transport=transport,
        auth_state=policy.state if policy else "n/a",
        host=host,
        port=port,
        path=path,
        node_tools=node_tools,
        vm_tools=vm_tools,
        storage_tools=storage_tools,
        cluster_tools=cluster_tools,
        task_tools=task_tools,
        container_tools=container_tools,
    )
    ctx = ToolContext(
        node_tools=node_tools,
        vm_tools=vm_tools,
        storage_tools=storage_tools,
        cluster_tools=cluster_tools,
        health_payload=app.health_payload,
        task_tools=task_tools,
        container_tools=container_tools,
    )
    app.specs = build_registry(ctx)
    tool_policy = ToolPolicy(config.policy)
    app.policy = tool_policy
    logger.info(
        "policy: read_only=%s allow_destructive=%s allow_exec=%s",
        *(tool_policy.summary()[k] for k in ("read_only", "allow_destructive", "allow_exec")),
    )
    if config.policy.allow_destructive:
        logger.warning("policy: allow_destructive is ON (stop/reset/delete/rollback enabled)")
    if config.policy.allow_exec:
        logger.warning("policy: allow_exec is ON (execute_vm_command enabled)")
    register_tools(app.mcp, app.specs, wrap=compose_wraps(make_policy_wrap(tool_policy), wrap))

    if transport == "http":
        assert policy is not None

        @app.mcp.custom_route("/health", methods=["GET"])
        async def health_route(request: Request) -> JSONResponse:
            # Unauthenticated callers get liveness only; auth mode and Proxmox
            # reachability are disclosed solely to authenticated callers (or when
            # auth is disabled, where every tool is already open).
            if policy.enabled and not is_authorized(
                request.scope.get("headers", []), policy.digests
            ):
                return JSONResponse({"status": "ok"})
            return JSONResponse(app.health_payload())

        if policy.enabled:
            middleware = [Middleware(APIKeyAuthMiddleware, digests=policy.digests)]
        else:
            # No-auth dev mode: still refuse DNS-rebinding / cross-site browser requests.
            middleware = [Middleware(LoopbackHostGuardMiddleware)]
        app.asgi = app.mcp.http_app(path=path, middleware=middleware)
        logger.info("HTTP app on %s:%s%s, authentication: %s", host, port, path, app.auth_state)
    return app
