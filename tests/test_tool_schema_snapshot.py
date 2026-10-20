"""Golden snapshot of the stdio tool contract (names, params, required, simple types).

The snapshot deliberately stores only a simplified, Python/pydantic-version independent
view of each tool: sorted parameter names, a required flag and a simple type. Titles,
descriptions, defaults, bounds and ``anyOf`` nesting are ignored.

Regenerate after an intentional, reviewed contract change with::

    UPDATE_GOLDEN=1 uv run pytest tests/test_tool_schema_snapshot.py -q
"""
import copy
import difflib
import json
import os
from pathlib import Path

import pytest
import pytest_asyncio

GOLDEN_PATH = Path(__file__).parent / "golden" / "tools.json"
# tools_phase3.json is the frozen pre-Phase-4 tool surface; tools.json may differ from it
# only by DOCUMENTED_ADDITIONS below (deliberate, additive, optional parameters).
BASELINE_PATH = Path(__file__).parent / "golden" / "tools_phase3.json"
DOCUMENTED_ADDITIONS = {
    "delete_vm": {"confirm": "boolean"},
    "stop_vm": {"confirm": "boolean"},
    "reset_vm": {"confirm": "boolean"},
    "rollback_snapshot": {"confirm": "boolean"},
}
SIMPLE_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


def _simple_type(prop: dict) -> str:
    """Reduce a JSON-schema property to a simple type name."""
    members = prop.get("anyOf") or prop.get("oneOf")
    if members:
        names = set()
        for member in members:
            if member.get("type") == "null":
                continue
            names.add(_simple_type(member))
        return "|".join(sorted(names)) if names else "null"
    ptype = prop.get("type")
    if isinstance(ptype, list):
        ptype = "|".join(sorted(t for t in ptype if t != "null"))
    return ptype if ptype else "any"


def normalize_schema(name: str, schema: dict) -> dict:
    """Normalize a tool name and its JSON schema into the golden shape."""
    required = set(schema.get("required", []))
    params = [
        {"name": p, "required": p in required, "type": _simple_type(prop)}
        for p, prop in schema.get("properties", {}).items()
    ]
    params.sort(key=lambda x: x["name"])
    return {"name": name, "params": params}


def normalize_tool(tool) -> dict:
    """Normalize a fastmcp tool object."""
    return normalize_schema(tool.name, tool.parameters)


def diff_snapshots(expected: list, actual: list) -> str:
    """Return a unified diff of two snapshots, empty string when equal."""
    if expected == actual:
        return ""
    a = json.dumps(expected, indent=2, sort_keys=True).splitlines()
    b = json.dumps(actual, indent=2, sort_keys=True).splitlines()
    return "\n".join(difflib.unified_diff(a, b, "golden", "actual", lineterm=""))


async def build_snapshot(server) -> list:
    tools = await server.mcp.list_tools()
    return sorted((normalize_tool(t) for t in tools), key=lambda t: t["name"])


def _load_golden() -> list:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest_asyncio.fixture
async def snapshot(server):
    snap = await build_snapshot(server)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(
            json.dumps(snap, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return snap


@pytest.mark.asyncio
async def test_tool_names_match_golden(snapshot):
    """The sorted tool-name list equals the golden list."""
    expected = [t["name"] for t in _load_golden()]
    actual = [t["name"] for t in snapshot]
    assert actual == expected, diff_snapshots(
        [{"name": n} for n in expected], [{"name": n} for n in actual]
    )
    assert len(actual) == 18


@pytest.mark.asyncio
async def test_tool_params_match_golden(snapshot):
    """Every tool's normalized parameter list equals the golden entry."""
    golden = {t["name"]: t for t in _load_golden()}
    for tool in snapshot:
        assert tool == golden[tool["name"]], diff_snapshots(
            [golden[tool["name"]]], [tool]
        )


def test_snapshot_normalizer_ignores_anyOf_shape():
    """anyOf-with-null and a plain type normalize to the same simple type."""
    nullable = {"properties": {"a": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                     "default": None, "title": "A"}}}
    plain = {"properties": {"a": {"type": "string", "description": "x"}}}
    assert normalize_schema("t", nullable)["params"][0]["type"] == "string"
    assert normalize_schema("t", plain)["params"][0]["type"] == "string"


def test_mismatch_is_reported():
    """Dropping a parameter from a copy yields a non-empty readable diff."""
    golden = _load_golden()
    mutated = copy.deepcopy(golden)
    victim = next(t for t in mutated if t["params"])
    dropped = victim["params"].pop()
    diff = diff_snapshots(golden, mutated)
    assert diff
    assert dropped["name"] in diff


def test_golden_is_phase3_plus_documented_additions():
    """The current surface is the frozen Phase 3 baseline plus exactly the documented extras."""
    expected = {t["name"]: {p["name"]: p for p in t["params"]}
                for t in json.loads(BASELINE_PATH.read_text(encoding="utf-8"))}
    for tool, extras in DOCUMENTED_ADDITIONS.items():
        for pname, ptype in extras.items():
            assert pname not in expected[tool], f"{tool}.{pname} already in baseline"
            expected[tool][pname] = {"name": pname, "required": False, "type": ptype}
    actual = {t["name"]: {p["name"]: p for p in t["params"]} for t in _load_golden()}
    assert actual == expected
