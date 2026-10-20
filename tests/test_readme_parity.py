"""README.md and README.tr.md stay structurally identical and match the generated tool table."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN = (ROOT / "README.md").read_text(encoding="utf-8")
TR = (ROOT / "README.tr.md").read_text(encoding="utf-8")
FENCE = re.compile(r"^```[^\n]*\n.*?^```\n", re.M | re.S)
TABLE = re.compile(r"<!-- tools:start -->\n(.*?)\n<!-- tools:end -->", re.S)
LOCAL_LINK = re.compile(r"\]\((?!https?:|#)([^)#]+)")


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_tool_table", ROOT / "scripts/gen_tool_table.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tool_table_matches_generator_in_both_readmes() -> None:
    expected = _generator().render()
    for text in (EN, TR):
        match = TABLE.search(text)
        assert match, "tools markers missing"
        assert match.group(1) == expected
    assert expected.count("\n| `") == 27


def test_code_blocks_and_structure_are_identical() -> None:
    assert FENCE.findall(EN) == FENCE.findall(TR)
    assert len(re.findall(r"^#{1,3} ", EN, re.M)) == len(re.findall(r"^#{1,3} ", TR, re.M))

    # the language switch legitimately differs, every other local link must match
    def links(text: str) -> list[str]:
        return sorted(x for x in set(LOCAL_LINK.findall(text)) if not x.startswith("README"))

    assert links(EN) == links(TR)


def test_no_stale_content() -> None:
    for text in (EN, TR):
        for stale in (
            "requirements.in",
            "pip install -e",
            "mcpo",
            "Python 3.9",
            "35 tools",
            "black .",
        ):
            assert stale not in text, stale
