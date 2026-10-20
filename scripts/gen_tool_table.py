"""Print the README tool table (markdown) from tests/golden/tools.json and RISK_CLASSES.

Usage: uv run python scripts/gen_tool_table.py

The output is pasted verbatim between the ``tools:start`` / ``tools:end`` markers of README.md
and README.tr.md; scripts/verify_docs_commands.sh checks that both copies match.
"""

from __future__ import annotations

import json
from pathlib import Path

from proxmox_mcp.tools.registry import RISK_CLASSES

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "tools.json"
ORDER = ("read", "write", "destructive", "exec")

GATES = {
    "read": "always available",
    "write": "blocked by `read_only`",
    "destructive": "needs `allow_destructive`; blocked by `read_only`",
    "exec": "needs `allow_exec`; blocked by `read_only`",
}


def _gate(risk: str, params: list[dict[str, object]]) -> str:
    gate = GATES[risk]
    if any(p["name"] == "confirm" for p in params):
        gate += "; `confirm=true` to execute (otherwise a preview)"
    return gate


def _params(params: list[dict[str, object]]) -> str:
    parts = [f"**{p['name']}**" if p["required"] else f"{p['name']}" for p in params]
    return ", ".join(parts)


def render() -> str:
    tools = {t["name"]: t for t in json.loads(GOLDEN.read_text(encoding="utf-8"))}
    risk_of = {name: risk for risk, names in RISK_CLASSES.items() for name in names}
    missing = set(tools) ^ set(risk_of)
    if missing:
        raise SystemExit(f"golden and RISK_CLASSES disagree: {sorted(missing)}")
    rows = ["| Tool | Risk class | Gate | Parameters |", "|---|---|---|---|"]
    for risk in ORDER:
        for name in sorted(n for n, r in risk_of.items() if r == risk):
            params = tools[name]["params"]
            rows.append(f"| `{name}` | {risk} | {_gate(risk, params)} | {_params(params)} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(render())
