"""Static guards for the container files (no docker needed)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _instructions() -> list[str]:
    """Dockerfile instruction lines with comments removed and continuations joined."""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    text = re.sub(r"\\\n", " ", text)
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_base_image_is_pinned_by_digest() -> None:
    froms = [i for i in _instructions() if i.startswith("FROM ")]
    assert len(froms) >= 2, "multi-stage build expected"
    for line in froms:
        assert re.match(r"FROM python:3\.12-slim@sha256:[0-9a-f]{64}( AS \w+)?$", line), line


def test_runs_as_non_root_with_healthcheck() -> None:
    ins = _instructions()
    users = [i.split(None, 1)[1] for i in ins if i.startswith("USER ")]
    assert users
    assert users[-1].isdigit() and users[-1] != "0"
    assert any(i.startswith("HEALTHCHECK ") for i in ins)


def test_no_forbidden_instructions() -> None:
    body = "\n".join(_instructions())
    for forbidden in ("apt-get", "apt install", "pip install", "COPY . .", "COPY . /"):
        assert forbidden not in body, forbidden
    assert not re.search(r"\b(git|curl|wget)\b", body)
    assert "uv sync --locked --no-dev" in body
    assert "config.json" not in re.sub(r"PROXMOX_MCP_CONFIG=\S+", "", body)


def test_dockerignore_keeps_credentials_out() -> None:
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    entries = {x.strip() for x in lines if x.strip() and not x.startswith("#")}
    assert {"proxmox-config/config.json", ".git", ".venv", ".planning", "tests"} <= entries


def test_compose_is_hardened() -> None:
    raw = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    svc = yaml.safe_load(raw)["services"]["proxmox-mcp-extended"]
    assert svc["ports"] == ["127.0.0.1:8812:8812"]
    assert svc["read_only"] is True
    assert svc["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in svc["security_opt"]
    assert any(
        e.startswith("PROXMOX_MCP_API_KEY_HASHES=${PROXMOX_MCP_API_KEY_HASHES:?")
        for e in svc["environment"]
    )
    assert "0.0.0.0:" not in raw
    assert "privileged" not in svc
    assert "cap_add" not in svc
    assert not any(str(e).startswith("HTTP_") for e in svc["environment"])


def test_logs_go_to_the_docker_driver_not_tmpfs() -> None:
    raw = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    svc = yaml.safe_load(raw)["services"]["proxmox-mcp-extended"]
    assert not any(str(e).startswith("LOG_FILE") for e in svc["environment"])
    assert svc["logging"]["driver"] == "json-file"
    assert svc["logging"]["options"] == {"max-size": "10m", "max-file": "5"}
    (tmp,) = svc["tmpfs"]
    assert tmp.startswith("/tmp:") and "noexec" in tmp
    assert "LOG_FILE" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "LOG_FILE" not in (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
