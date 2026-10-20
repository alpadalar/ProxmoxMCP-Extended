"""Entry point and import smoke tests (fastmcp 4 / mcp 2 migration)."""

import ast
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LEGACY = "mcp.server.fastmcp"


def _imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_import_server_module():
    importlib.import_module("proxmox_mcp.server")


def test_console_script_target_exists():
    server = importlib.import_module("proxmox_mcp.server")
    assert callable(getattr(server, "main", None))


def test_main_help_exits_zero(capsys):
    from proxmox_mcp.server import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "--config" in capsys.readouterr().out


def test_main_requires_config(monkeypatch, capsys):
    from unittest.mock import patch

    from proxmox_mcp import server

    monkeypatch.delenv("PROXMOX_MCP_CONFIG", raising=False)
    with patch("proxmox_mcp.app.ProxmoxManager") as manager:
        with pytest.raises(SystemExit) as exc:
            server.main([])
        manager.assert_not_called()
    assert exc.value.code not in (0, None)
    assert "Traceback" not in capsys.readouterr().err


def test_no_legacy_fastmcp_imports():
    offenders = []
    for base in ("src", "tests"):
        for path in (ROOT / base).rglob("*.py"):
            for module in _imported_modules(path):
                if module == LEGACY or module.startswith(LEGACY + "."):
                    offenders.append(f"{path.relative_to(ROOT)}: {module}")
    assert not offenders, offenders
