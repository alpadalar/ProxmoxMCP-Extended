"""Guard tests for packaging invariants (STAB-01, STAB-05)."""

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _all_dependency_strings() -> list:
    data = _pyproject()
    deps = list(data["project"].get("dependencies", []))
    for group in data["project"].get("optional-dependencies", {}).values():
        deps.extend(group)
    for group in data.get("dependency-groups", {}).values():
        deps.extend(item for item in group if isinstance(item, str))
    return deps


def test_no_legacy_manifests():
    for name in ("setup.py", "requirements.in", "requirements-dev.in"):
        assert not (ROOT / name).exists(), f"{name} must not exist"


def test_no_git_dependency():
    for dep in _all_dependency_strings():
        assert "git+" not in dep, dep
        assert " @ " not in dep, dep


def test_fastmcp_bounded():
    data = _pyproject()
    assert data["project"]["requires-python"] == ">=3.10"
    matches = [
        d for d in data["project"]["dependencies"] if d.replace(" ", "").startswith("fastmcp>=4.1.2")
    ]
    assert matches and "<5" in matches[0].replace(" ", "")


def test_lock_committed():
    assert (ROOT / "uv.lock").is_file()


def test_live_scripts_not_collected():
    assert not (ROOT / "test_scripts").exists()
    assert (ROOT / "scripts" / "live" / "README.md").is_file()
    ini = _pyproject()["tool"]["pytest"]["ini_options"]
    assert ini["testpaths"] == ["tests"]
