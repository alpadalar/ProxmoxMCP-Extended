"""Docs are locked to the code: tool coverage, flags, defaults, links, attribution, no secrets."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess  # noqa: S404 - fixed git argv, no shell
from pathlib import Path

import pytest

from proxmox_mcp import server, server_http
from proxmox_mcp.config.models import PolicyConfig

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / "tests" / "golden" / "tools.json").read_text(encoding="utf-8"))
TOOL_NAMES = sorted(t["name"] for t in GOLDEN)
README = (ROOT / "README.md").read_text(encoding="utf-8")
README_TR = (ROOT / "README.tr.md").read_text(encoding="utf-8")
GUIDE = (ROOT / "HTTP_MCP_GUIDE.md").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
TABLE = re.compile(r"<!-- tools:start -->\n(.*?)\n<!-- tools:end -->", re.S)
MD_LINK = re.compile(r"\]\((?!https?:|mailto:|#)([^)#\s]+)")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
GIT = shutil.which("git")


def _tracked_files() -> list[Path]:
    if GIT is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(  # noqa: S603 - fixed argv, absolute git path
        [GIT, "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout.decode("utf-8")
    return [Path(p) for p in out.split("\0") if p]


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_tool_table", ROOT / "scripts" / "gen_tool_table.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _help_options(main, prog_args: list[str]) -> set[str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        main(prog_args)
    return set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", buf.getvalue()))


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_tool_is_documented_in_both_readmes(name: str) -> None:
    assert f"`{name}`" in README
    assert f"`{name}`" in README_TR


def test_tool_count_matches_golden() -> None:
    assert len(TOOL_NAMES) == 27


def test_embedded_tool_table_equals_generator() -> None:
    expected = _generator().render()
    for text in (README, README_TR):
        match = TABLE.search(text)
        assert match, "tools:start/tools:end markers missing"
        assert match.group(1) == expected


def test_every_cli_flag_is_documented() -> None:
    stdio = _help_options(server.main, ["--help"])
    http = _help_options(lambda argv: server_http.build_parser().parse_args(argv), ["--help"])
    flags = stdio | http
    assert {"--config", "--host", "--port", "--path", "--no-auth", "--allow-exec"} <= flags
    docs = README + GUIDE
    for flag in sorted(flags - {"--help"}):
        assert flag in docs, f"{flag} is not documented in README.md or HTTP_MCP_GUIDE.md"


def test_documented_defaults_match_code() -> None:
    args = server_http.build_parser().parse_args([])
    assert (args.host, args.port, args.path) == ("127.0.0.1", 8812, "/proxmox-mcp")
    policy = PolicyConfig()
    assert (policy.read_only, policy.allow_destructive, policy.allow_exec) == (False,) * 3
    for text in (README, README_TR):
        assert "127.0.0.1" in text
        assert "8812" in text
        assert "/proxmox-mcp" in text
        for key in ("read_only", "allow_destructive", "allow_exec"):
            assert key in text


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        "README.tr.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "HTTP_MCP_GUIDE.md",
    ],
)
def test_relative_links_resolve(name: str) -> None:
    path = ROOT / name
    for target in MD_LINK.findall(path.read_text(encoding="utf-8")):
        assert (path.parent / target).exists(), f"{name}: broken link {target}"


def test_changelog_only_claims_existing_paths() -> None:
    # "Removed" lists deleted files on purpose; every other section must name real paths
    kept = CHANGELOG.split("### Removed")[0]
    claimed = re.findall(r"`((?:scripts|\.github|examples|tests)/[^`\s]*)`", kept)
    assert claimed
    for rel in claimed:
        assert (ROOT / rel.rstrip("/")).exists(), f"CHANGELOG names missing path {rel}"
    for rel in (
        ".github/workflows/ci.yml",
        ".github/workflows/security.yml",
        ".github/workflows/release.yml",
        ".github/dependabot.yml",
    ):
        assert (ROOT / rel).is_file(), rel


@pytest.mark.parametrize(
    "name", ["claude_desktop_config.json", "cursor_mcp_config.json", "cline_mcp_settings.json"]
)
def test_examples_hold_only_placeholders(name: str) -> None:
    raw = (ROOT / "examples" / name).read_text(encoding="utf-8")
    data = json.loads(raw)
    assert not re.search(r"\b[0-9a-fA-F]{64}\b", raw)
    assert not UUID.search(raw)
    for match in re.finditer(r"Bearer (\S+)", raw):
        assert match.group(1).strip('"') in {"YOUR_API_KEY", "${PROXMOX_MCP_API_KEY}"}, match.group(
            0
        )
    for entry in data["mcpServers"].values():
        if "command" in entry:
            assert entry["command"] in {"uv", "proxmox-mcp", "npx"}


def test_license_and_notice_keep_attribution() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Kevin" in license_text
    assert "Alperen Adalar" in license_text
    assert "canvrno/ProxmoxMCP" in notice
    assert "RekklesNA/ProxmoxMCP-Plus" in notice
    for text in (README, README_TR):
        assert "canvrno" in text
        assert "RekklesNA" in text


@pytest.mark.parametrize(
    "keyword",
    [
        "allow_destructive",
        "allow_exec",
        "confirm",
        "127.0.0.1",
        "API_KEY_HASHES",
        "fastmcp",
        "Python 3.10",
        "update_vm",
        "get_containers",
        "/health",
        "extra=forbid",
        "HTTP_PORT",
        "ENTRYPOINT",
        "/config",
        "proxmox-network",
    ],
)
def test_changelog_names_every_breaking_change(keyword: str) -> None:
    assert keyword in CHANGELOG


def test_no_secret_shapes_in_tracked_docs() -> None:
    files = _tracked_files()
    assert Path("proxmox-config/config.json") not in files
    assert Path(".env") not in files
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    copies = [ln for ln in dockerfile.splitlines() if ln.strip().upper().startswith("COPY")]
    assert not any("proxmox-config/config.json" in ln for ln in copies)
    for rel in files:
        if rel.parts[0] in {"tests", ".planning"} or rel.name == "uv.lock":
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        assert not re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text), rel
        for line in text.splitlines():
            if "PVEAPIToken=" in line:
                assert not UUID.search(line), f"{rel}: token-shaped value"
            if re.search(r"token|secret|password", line, re.I):
                assert not UUID.search(line), f"{rel}: uuid next to a secret word"


@pytest.mark.parametrize(
    "stale",
    [
        "black .",
        "requirements.in",
        "pip install -e",
        "Django",
        "Yartu",
        "mcpo",
        "35 tools",
        "Python 3.9",
    ],
)
def test_no_stale_claims_in_readmes(stale: str) -> None:
    assert stale not in README
    assert stale not in README_TR


PLANNING = ROOT / ".planning"
SUMMARY_FILES = {
    "04-04": "phases/04-tool-layer-security-pve-api-uyumu/04-04-SUMMARY.md",
    "05-02": "phases/05-new-features/05-02-SUMMARY.md",
    "05-03": "phases/05-new-features/05-03-SUMMARY.md",
    "05-04": "phases/05-new-features/05-04-SUMMARY.md",
}


def _human_test_items(text: str) -> list[int]:
    match = re.search(r"^## For HUMAN-TESTS[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert match, "no '## For HUMAN-TESTS' section"
    return [int(n) for n in re.findall(r"^(\d+)\. ", match.group(1), re.M)]


@pytest.mark.parametrize("plan", sorted(SUMMARY_FILES))
def test_human_tests_cover_every_summary_item(plan: str) -> None:
    human = PLANNING / "HUMAN-TESTS.md"
    summary = PLANNING / SUMMARY_FILES[plan]
    if not human.is_file() or not summary.is_file():
        pytest.skip(".planning is not part of this checkout")
    items = _human_test_items(summary.read_text(encoding="utf-8"))
    assert items == list(range(1, len(items) + 1))
    text = human.read_text(encoding="utf-8")
    for n in items:
        assert f"Kaynak: {plan}#{n}" in text, f"HUMAN-TESTS.md misses {plan}#{n}"
    assert "Kaynak: " in text
