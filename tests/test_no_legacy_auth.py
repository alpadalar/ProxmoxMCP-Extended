"""Guard: the legacy Django/Yartu auth stack and default tokens stay gone (T-03-04).

Forbidden words are assembled at runtime so this file does not match itself;
tests/ is deliberately not part of the scan set.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "proxmox_mcp"

FORBIDDEN = re.compile(
    "|".join(
        [
            "dja" + "ngo",
            "yar" + "tu",
            "scope" + "rbac",
            "simple" + "token" + "auth",
            "management" + "/commands",
        ]
    ),
    re.IGNORECASE,
)
SKIP_DIRS = {"__pycache__", ".venv", ".git"}
SCAN_FILES = [
    "README.md",
    "README.tr.md",
    "HTTP_MCP_GUIDE.md",
    "Dockerfile",
    "docker-compose.yml",
    "pyproject.toml",
    "proxmox-config/config.example.json",
]
SCAN_DIRS = ["src", "examples"]


def _files():
    for name in SCAN_FILES:
        p = ROOT / name
        if p.is_file():
            yield p
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            parts = set(p.relative_to(ROOT).parts)
            if not p.is_file() or parts & SKIP_DIRS:
                continue
            if any(part.endswith(".egg-info") for part in p.relative_to(ROOT).parts):
                continue
            yield p


def test_management_package_removed():
    assert not (SRC / "management").exists()


def test_auth_package_contents():
    names = {p.name for p in (SRC / "auth").iterdir() if p.name != "__pycache__"}
    assert names == {"__init__.py", "apikey.py", "hostguard.py", "policy.py"}


def test_no_legacy_words_in_repo():
    offenders = []
    for p in _files():
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        m = FORBIDDEN.search(text)
        if m:
            offenders.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert not offenders, offenders


def test_lockfile_has_no_legacy_packages():
    # pyjwt is a legitimate transitive dependency of fastmcp, so it is not banned.
    lock = ROOT / "uv.lock"
    if not lock.is_file():
        return
    names = set(re.findall(r'^name = "([^"]+)"', lock.read_text(), re.MULTILINE))
    banned = {"dja" + "ngo", "dja" + "ngorestframework", "asgiref"}
    assert not (names & {n.lower() for n in banned})
