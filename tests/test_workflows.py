"""Static guards for the GitHub Actions workflows (they are written, never run here).

The checks inspect parsed YAML, not raw text, so comments cannot cause false hits.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml"))

PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
UNTRUSTED = re.compile(
    r"\$\{\{\s*(?:github\.event[.\[]|inputs\.|github\.head_ref|github\.ref_name|github\.actor)"
)
LATEST = "latest=${{ github.event_name == 'push' && 'auto' || 'false' }}"
LINT_COMMANDS = [
    "uv run ruff check src tests scripts",
    "uv run ruff format --check src tests scripts",
    "uv run mypy src",
]
# Keep in sync with requires-python and the CI matrix in .github/workflows/ci.yml.
PYTHON_MATRIX = ["3.10", "3.11", "3.12", "3.13", "3.14"]


def load(path: Path) -> dict[Any, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def triggers(doc: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 parses the bare key `on` as boolean True.
    raw = doc.get("on", doc.get(True))
    if isinstance(raw, str):
        return {raw: None}
    if isinstance(raw, list):
        return {name: None for name in raw}
    assert isinstance(raw, dict)
    return raw


def steps(doc: dict[Any, Any]) -> list[dict[str, Any]]:
    return [s for job in doc["jobs"].values() for s in job.get("steps", [])]


def uses_values(doc: dict[Any, Any]) -> list[str]:
    return [s["uses"] for s in steps(doc) if "uses" in s and not s["uses"].startswith("./")]


def unpinned(doc: dict[Any, Any], text: str) -> list[str]:
    bad = []
    for value in uses_values(doc):
        if not PINNED.match(value):
            bad.append(value)
            continue
        comment = r"\s+#\s*v\d+\.\d+\.\d+\S*\s*$"
        line = re.compile(rf"^\s*(?:-\s+)?uses:\s*{re.escape(value)}{comment}", re.M)
        if not line.search(text):
            bad.append(f"{value} (missing # vX.Y.Z comment)")
    return bad


def write_permissions(doc: dict[Any, Any]) -> list[str]:
    found = []
    blocks = [("top-level", doc.get("permissions"))]
    blocks += [(name, job.get("permissions")) for name, job in doc["jobs"].items()]
    for where, perms in blocks:
        if isinstance(perms, str) and "write" in perms:
            found.append(f"{where}: {perms}")
        elif isinstance(perms, dict):
            found += [f"{where}: {k}: {v}" for k, v in perms.items() if v == "write"]
    return found


def run_injections(doc: dict[Any, Any]) -> list[str]:
    return [s["run"] for s in steps(doc) if "run" in s and UNTRUSTED.search(str(s["run"]))]


def bad_triggers(doc: dict[Any, Any]) -> bool:
    return "pull_request_target" in triggers(doc)


def test_workflow_files_exist() -> None:
    names = {p.name for p in WORKFLOWS}
    assert {"ci.yml", "security.yml", "release.yml"} <= names


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
class TestEveryWorkflow:
    def test_parses_and_has_jobs(self, path: Path) -> None:
        doc = load(path)
        assert doc["jobs"]
        assert triggers(doc)

    def test_actions_pinned_to_sha_with_version_comment(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert uses_values(load(path))
        assert unpinned(load(path), text) == []

    def test_top_level_permissions_and_no_write(self, path: Path) -> None:
        doc = load(path)
        assert "permissions" in doc
        assert write_permissions(doc) == []

    def test_no_pull_request_target(self, path: Path) -> None:
        assert not bad_triggers(load(path))

    def test_no_untrusted_context_in_run(self, path: Path) -> None:
        assert run_injections(load(path)) == []

    def test_jobs_have_timeouts(self, path: Path) -> None:
        for name, job in load(path)["jobs"].items():
            assert "timeout-minutes" in job, name


def test_release_is_a_dry_run() -> None:
    doc = load(WORKFLOW_DIR / "release.yml")
    build = [s for s in steps(doc) if s.get("uses", "").startswith("docker/build-push-action@")]
    assert len(build) == 1
    assert build[0]["with"]["push"] is False
    assert build[0]["with"]["load"] is True
    assert not [u for u in uses_values(doc) if u.startswith("docker/login-action@")]
    meta = [s for s in steps(doc) if s.get("uses", "").startswith("docker/metadata-action@")]
    assert len(meta) == 1
    assert LATEST in meta[0]["with"]["flavor"]
    tags = meta[0]["with"]["tags"]
    assert "type=sha,prefix={{branch}}-" not in tags
    assert "type=sha,prefix=sha-" in tags
    assert "${{ secrets." not in (WORKFLOW_DIR / "release.yml").read_text(encoding="utf-8")


def test_ci_commands_and_matrix() -> None:
    doc = load(WORKFLOW_DIR / "ci.yml")
    runs = [s["run"] for s in steps(doc) if "run" in s]
    for command in LINT_COMMANDS:
        assert command in runs
    assert "uv sync --locked" in runs
    strategy = doc["jobs"]["test"]["strategy"]
    assert strategy["fail-fast"] is False
    assert strategy["matrix"]["python-version"] == PYTHON_MATRIX
    assert "uv run pytest -q" in runs


def test_ci_matrix_matches_requires_python() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in pyproject


def test_dependabot() -> None:
    doc = load(ROOT / ".github" / "dependabot.yml")
    assert doc["version"] == 2
    ecosystems = {u["package-ecosystem"]: u for u in doc["updates"]}
    assert {"github-actions", "uv", "docker"} <= set(ecosystems)
    for update in ecosystems.values():
        assert update["schedule"]["interval"] == "weekly"


def _parse(text: str) -> dict[Any, Any]:
    return load_text(text)


def load_text(text: str) -> dict[Any, Any]:
    data = yaml.safe_load(text)
    assert isinstance(data, dict)
    return data


class TestGuardsHaveTeeth:
    def test_flags_unpinned_action(self) -> None:
        text = "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n"
        assert unpinned(_parse(text), text) == ["actions/checkout@v4"]

    def test_flags_missing_version_comment(self) -> None:
        text = f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{'a' * 40}\n"
        assert len(unpinned(_parse(text), text)) == 1

    def test_accepts_pinned_with_comment(self) -> None:
        text = f"jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{'a' * 40} # v1.2.3\n"
        assert unpinned(_parse(text), text) == []

    def test_flags_pull_request_target(self) -> None:
        assert bad_triggers(_parse("on:\n  pull_request_target:\njobs:\n  a: {}\n"))

    def test_flags_event_input_in_run(self) -> None:
        text = (
            "jobs:\n  a:\n    steps:\n"
            "      - run: echo ${{ github.event.inputs.x }}\n"
            "      - run: echo ${{ inputs.y }}\n"
            "      - run: echo ${{ github.head_ref }}\n"
        )
        assert len(run_injections(_parse(text))) == 3

    def test_env_passthrough_is_allowed(self) -> None:
        text = (
            "jobs:\n  a:\n    steps:\n"
            "      - env:\n          X: ${{ github.event.inputs.x }}\n"
            '        run: echo "$X"\n'
        )
        assert run_injections(_parse(text)) == []

    def test_flags_write_permissions(self) -> None:
        text = (
            "permissions:\n  contents: read\njobs:\n  a:\n    permissions:\n      packages: write\n"
        )
        assert write_permissions(_parse(text)) == ["a: packages: write"]

    def test_comments_do_not_trigger_guards(self) -> None:
        text = "# packages: write and pull_request_target in a comment\non: push\njobs:\n  a: {}\n"
        doc = _parse(text)
        assert write_permissions(doc) == []
        assert not bad_triggers(doc)


def test_release_smoke_checks_auth_and_tag() -> None:
    text = (WORKFLOW_DIR / "release.yml").read_text(encoding="utf-8")
    assert 'test "$code" = "200"' in text  # authenticated request must succeed
    assert 'test "$code" = "401"' in text
    assert 'rm -f "${RUNNER_TEMP}/smoke-key"' in text
    assert 'test "${REF_NAME#v}" = "$version"' in text
