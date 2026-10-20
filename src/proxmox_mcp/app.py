"""Application factory shared by the stdio and HTTP transports.

``create_app`` is the only place that wires configuration, the lazy Proxmox manager,
the tool registry, the ``/health`` route and the auth middleware.  For HTTP the ASGI
application is built exactly once and ``serve_asgi`` serves that same object.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import uvicorn
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth.apikey import APIKeyAuthMiddleware
from .auth.hostguard import LoopbackHostGuardMiddleware
from .auth.policy import resolve_auth_policy
from .core.proxmox import ProxmoxManager
from .tools.cluster import ClusterTools
from .tools.node import NodeTools
from .tools.registry import ToolContext, ToolSpec, build_registry, register_tools
from .tools.storage import StorageTools
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
    asgi: Optional[Any] = None
    auth_state: str = "n/a"
    host: str = "127.0.0.1"
    port: int = 8812
    path: str = "/proxmox-mcp"
    tests_passed: Optional[bool] = None
    specs: List[ToolSpec] = field(default_factory=list)
    node_tools: Any = None
    vm_tools: Any = None
    storage_tools: Any = None
    cluster_tools: Any = None

    def health_payload(self) -> Dict[str, Any]:
        """Health information; performs no network I/O."""
        if self.transport == "http":
            return {
                "status": "ok",
                "server": "ProxmoxMCP-HTTP",
                "transport": "http",
                "auth": self.auth_state,
                "proxmox": self.manager.connection_state(),
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
    api_key_digests: Optional[List[str]] = None,
    insecure_no_auth: bool = False,
    wrap: Optional[Callable[[ToolSpec, Callable[..., Any]], Callable[..., Any]]] = None,
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
                host, port,
            )

    manager = ProxmoxManager(config.proxmox, config.auth)
    api = manager.get_api()
    node_tools = NodeTools(api)
    vm_tools = VMTools(api)
    storage_tools = StorageTools(api)
    cluster_tools = ClusterTools(api)

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
    )
    ctx = ToolContext(
        node_tools=node_tools,
        vm_tools=vm_tools,
        storage_tools=storage_tools,
        cluster_tools=cluster_tools,
        health_payload=app.health_payload,
    )
    app.specs = build_registry(ctx)
    register_tools(app.mcp, app.specs, wrap=wrap)

    if transport == "http":
        assert policy is not None

        @app.mcp.custom_route("/health", methods=["GET"])
        async def health_route(request: Request) -> JSONResponse:
            return JSONResponse(app.health_payload())

        if policy.enabled:
            middleware = [Middleware(APIKeyAuthMiddleware, digests=policy.digests)]
        else:
            # No-auth dev mode: still refuse DNS-rebinding / cross-site browser requests.
            middleware = [Middleware(LoopbackHostGuardMiddleware)]
        app.asgi = app.mcp.http_app(path=path, middleware=middleware)
        logger.info("HTTP app on %s:%s%s, authentication: %s", host, port, path, app.auth_state)
    return app
