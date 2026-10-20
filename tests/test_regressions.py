"""Regression catalog keyed to ``.planning/codebase/CONCERNS.md``.

Each row maps one CONCERNS item to exactly one test in this module.
Every row is FIXED: its test is green and guards the defect. (No strict-xfail pins remain
since Phase 4 / TECH-02.)

| CONCERNS item                                   | Test                                               | Status        | Phase / requirement |
|-------------------------------------------------|----------------------------------------------------|---------------|---------------------|
| Packaging: console script entry point           | test_console_script_main_exists                    | FIXED         | Phase 1 / STAB-02   |
| fastmcp 4 import path (stdio server)           | test_stdio_server_imports_on_fastmcp4              | FIXED         | Phase 1 / STAB-02   |
| Dependencies at Risk: FastMCP import fallbacks  | test_middleware_has_no_silent_fallback             | FIXED         | Phase 1 / TECH-01   |
| Packaging/config drift                          | test_packaging_single_source                       | FIXED         | Phase 1 / STAB-01   |
| HTTP server runs without authentication         | test_http_auth_not_hardcoded_off                   | FIXED         | Interim (SRV-02/03) |
| /health auth status and --no-auth meaningless   | test_health_reports_real_auth_state                | FIXED         | Interim (SRV-03)    |
| TLS verification can be silently weakened       | test_verify_ssl_typo_rejected                      | FIXED         | Phase 2 / CONF-01   |
| Secrets handling and logging (token in repr)    | test_token_value_not_in_repr                       | FIXED         | Phase 2 / CONF-01/03 |
| Input validation / injection (node path)        | test_path_traversal_node_rejected                  | FIXED         | Phase 2 / CONF-02   |
| Arbitrary command execution logged              | test_exec_command_not_logged                       | FIXED         | Phase 2 / CONF-03   |
| TLS/logging defaults in example config          | test_example_config_safe_defaults                  | FIXED         | Phase 2 / CONF-04   |
| Duplicated tool registration                    | test_stdio_http_tool_sets_identical                | FIXED         | Phase 3 / SRV-01    |
| Connection setup at construction time           | test_proxmox_connect_is_lazy                       | FIXED         | Phase 3 / SRV-04    |
| Known Bugs: blocking calls inside async path    | test_execute_command_does_not_block_loop           | FIXED         | Phase 3 / SRV-04    |
| Inconsistent error semantics (delete_vm)        | test_delete_vm_not_found_not_substring_matched     | FIXED         | Phase 4 / TECH-02   |
"""
import ast
import json
import logging
import re
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "proxmox_mcp"


SCAN_FILES = ["tools/vm.py", "tools/console/manager.py"]


def _function_source(path: Path, name: str) -> str:
    text = path.read_text()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"function {name} not found in {path}")


# --------------------------------------------------------------------------
# Fixed in Phase 1 (green)
# --------------------------------------------------------------------------

def test_console_script_main_exists():
    """CONCERNS packaging/entrypoint: console script must resolve to a callable main."""
    from proxmox_mcp import server

    assert callable(server.main)
    text = (ROOT / "pyproject.toml").read_text()
    scripts = text.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    assert "proxmox_mcp.server:main" in scripts


def test_stdio_server_imports_on_fastmcp4():
    """CONCERNS fastmcp import path: stdio server imports FastMCP from the fastmcp package."""
    from proxmox_mcp import app, server

    assert callable(server.main)
    assert app.FastMCP.__module__.split(".")[0] == "fastmcp"


def test_middleware_has_no_silent_fallback():
    """CONCERNS Dependencies at Risk: auth/middleware.py removed (Django/Yartu gone)."""
    assert not (SRC / "auth" / "middleware.py").exists()


def test_packaging_single_source():
    """CONCERNS Packaging/config drift: pyproject is the only manifest, no git+ dependencies."""
    assert not (ROOT / "setup.py").exists()
    assert not list(ROOT.glob("requirements*.in"))
    assert "git+" not in (ROOT / "pyproject.toml").read_text()


# --------------------------------------------------------------------------
# Fixed in later phases (green)
# --------------------------------------------------------------------------

def test_http_auth_not_hardcoded_off():
    """CONCERNS Security: server_http must not hardcode use_django_auth = False."""
    text = (SRC / "server_http.py").read_text()
    assert "self.use_django_auth = False" not in text


def test_health_reports_real_auth_state():
    """CONCERNS Known Bugs: /health 'auth' must not derive from use_django_auth alone."""
    text = (SRC / "app.py").read_text()
    payload_values = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "auth":
                    payload_values.append(ast.get_source_segment(text, value) or "")
    assert payload_values, "health payload has no 'auth' key"
    assert all("use_django_auth" not in v for v in payload_values)


def test_verify_ssl_typo_rejected(monkeypatch):
    """CONCERNS Security: PROXMOX_VERIFY_SSL=ture must raise, not silently disable TLS."""
    from proxmox_mcp.config.loader import load_config

    for k, v in {
        "PROXMOX_HOST": "test.proxmox.com",
        "PROXMOX_USER": "test@pve",
        "PROXMOX_TOKEN_NAME": "test_token",
        "PROXMOX_TOKEN_VALUE": "test_value",
        "PROXMOX_VERIFY_SSL": "ture",
    }.items():
        monkeypatch.setenv(k, v)
    try:
        cfg = load_config()
    except Exception:
        return
    raise AssertionError(f"typo accepted, verify_ssl={cfg.proxmox.verify_ssl}")


def test_token_value_not_in_repr():
    """CONCERNS Security: token value must not leak through repr/model_dump string."""
    from proxmox_mcp.config.models import AuthConfig

    secret = "sentinel-token-value-123"
    auth = AuthConfig(user="u@pve", token_name="t", token_value=secret)
    assert secret not in repr(auth)
    assert secret not in str(auth.model_dump())


@pytest.mark.asyncio
async def test_path_traversal_node_rejected(server, api):
    """CONCERNS Security: node '../x' must be rejected before any proxmoxer call."""
    api.nodes.reset_mock()
    try:
        await server.mcp.call_tool("get_node_status", {"node": "../x"})
    except Exception:
        pass
    assert not api.nodes.called, "unvalidated node reached proxmoxer"


@pytest.mark.asyncio
async def test_exec_command_not_logged(server, api, caplog):
    """CONCERNS Security: guest command text must not be written to logs."""
    from unittest.mock import MagicMock

    sentinel = "SENTINEL_CMD_9f3a"
    api.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "status": "running"
    }
    exec_ep = MagicMock()
    exec_ep.post.return_value = {"pid": 1}
    status_ep = MagicMock()
    status_ep.get.return_value = {"out-data": "x", "err-data": "", "exitcode": 0, "exited": 1}
    agent = MagicMock()
    agent.side_effect = lambda p: exec_ep if p == "exec" else status_ep
    api.nodes.return_value.qemu.return_value.agent = agent

    # make sure records reach caplog regardless of logger propagation settings
    for name in ("proxmox-mcp", "proxmox-mcp.vm-console"):
        logging.getLogger(name).propagate = True
    with caplog.at_level(logging.DEBUG):
        with patch("asyncio.sleep", return_value=None):
            await server.mcp.call_tool(
                "execute_vm_command", {"node": "n", "vmid": "100", "command": sentinel}
            )
    assert sentinel not in caplog.text


def test_example_config_safe_defaults():
    """CONCERNS Security: example config must default to verify_ssl true and non-DEBUG logs."""
    cfg = json.loads((ROOT / "proxmox-config" / "config.example.json").read_text())
    assert cfg["proxmox"]["verify_ssl"] is True
    assert cfg["logging"]["level"].upper() != "DEBUG"


@pytest.mark.asyncio
async def test_stdio_http_tool_sets_identical(mock_env_vars, mock_proxmox):
    """CONCERNS Tech Debt: stdio and HTTP servers must register the same tools."""
    from proxmox_mcp.server import ProxmoxMCPServer
    from proxmox_mcp.server_http import ProxmoxMCPHTTPServer
    from tests.test_tool_schema_snapshot import EXPECTED_TOOL_COUNT, build_snapshot

    stdio = ProxmoxMCPServer()
    with patch("proxmox_mcp.server_http.setup_logging", lambda cfg: logging.getLogger("x")):
        http = ProxmoxMCPHTTPServer(api_key_digests=["a" * 64])
    stdio_snap = await build_snapshot(stdio)
    http_snap = await build_snapshot(http)
    assert stdio_snap == http_snap
    assert len(stdio_snap) == EXPECTED_TOOL_COUNT
    for module in ("server.py", "server_http.py"):
        assert ".tool(" not in (SRC / module).read_text()


def test_proxmox_connect_is_lazy():
    """CONCERNS Fragile Areas: constructing ProxmoxManager must not touch the network."""
    from proxmox_mcp.config.models import AuthConfig, ProxmoxConfig
    from proxmox_mcp.core.proxmox import ProxmoxManager

    with patch("proxmox_mcp.core.proxmox.ProxmoxAPI") as mock_api:
        ProxmoxManager(
            ProxmoxConfig(host="h"), AuthConfig(user="u@pve", token_name="t", token_value="v")
        )
        mock_api.return_value.version.get.assert_not_called()


def test_execute_command_does_not_block_loop():
    """CONCERNS Known Bugs: async execute_command must offload sync proxmoxer calls."""
    src = _function_source(SRC / "tools" / "console" / "manager.py", "_execute_command")
    assert "to_thread" in src or "run_in_executor" in src
    assert "time.sleep" not in src
    assert src.count("to_thread") >= 3


def _text_membership_tests(path: Path):
    """``in`` / ``not in`` comparisons whose comparator is built from an error's text."""
    tree = ast.parse(path.read_text())
    bound = {n.name for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler) and n.name}

    def stringy(node: ast.AST) -> bool:
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "str"
            ):
                return True
            if isinstance(sub, ast.Name) and sub.id in bound:
                return True
        return False

    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops)
        and any(stringy(c) for c in node.comparators)
    ]


def test_delete_vm_not_found_not_substring_matched():
    """FIXED (Phase 4 / TECH-02): VM existence is never decided by error-text membership."""
    for rel in SCAN_FILES:
        assert _text_membership_tests(SRC / rel) == [], rel


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------

def test_catalog_covers_known_bug_section():
    """Every bold heading under CONCERNS '## Known Bugs' needs a catalog row."""
    concerns = ROOT / ".planning" / "codebase" / "CONCERNS.md"
    if not concerns.exists():
        pytest.skip("planning docs not present")
    section = concerns.read_text().split("## Known Bugs", 1)[1].split("\n## ", 1)[0]
    headings = re.findall(r"^\*\*(.+?):?\*\*", section, flags=re.M)
    assert headings, "no Known Bugs headings found"
    catalog = (__doc__ or "").lower()
    keys = {"/health": "/health", "blocking calls": "blocking calls"}
    for h in headings:
        key = next((k for k in keys if k in h.lower()), None)
        assert key is not None, f"no catalog key defined for Known Bug: {h}"
        assert keys[key] in catalog, f"Known Bug not in catalog: {h}"


def test_startup_error_is_redacted_and_on_stderr(monkeypatch, capsys):
    import sys

    import proxmox_mcp.server_http as sh
    from proxmox_mcp.utils.redaction import register_secret

    register_secret("super-secret-token-xyz")

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("bad config super-secret-token-xyz")

    monkeypatch.setattr(sh, "ProxmoxMCPHTTPServer", Boom)
    monkeypatch.setattr(sys, "argv", ["x"])
    with pytest.raises(SystemExit) as ei:
        sh.main()
    assert ei.value.code == 1
    out = capsys.readouterr()
    assert "super-secret-token-xyz" not in out.err and "Error:" in out.err
    assert out.out == ""
