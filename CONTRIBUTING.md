# Contributing

Thanks for helping. This server can power off and delete virtual machines, so changes are reviewed
with safety first. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Security
problems go through [SECURITY.md](SECURITY.md), not public issues.

## Setup

Python 3.10 or newer and [uv](https://docs.astral.sh/uv/) are required.

```bash
git clone https://github.com/alpadalar/ProxmoxMCP-Extended.git
cd ProxmoxMCP-Extended
uv sync
```

## Checks (all must pass before you open a pull request)

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest -q
```

Use `uv run ruff format src tests scripts` to apply formatting. Ruff replaces black; the rule sets are
`E, F, B, I, UP, S` with a line length of 100 (see `pyproject.toml`). Security (`S`) findings need a
fix or a line-level `# noqa: Sxxx` with a reason after it. Test files have a small, documented
per-file ignore list.

### mypy policy

`mypy src` runs with the strict-ish settings from `pyproject.toml` (typed defs, typed decorators,
unreachable-code warnings). The only override is `ignore_missing_imports` for `proxmoxer` and
`proxmoxer.*`, because that library ships no type information. Do not add `ignore_errors`, relax
global flags or sprinkle `# type: ignore` to get green; fix the types, or discuss a justified,
narrowly scoped override in the pull request.

## Tests

- No real Proxmox in tests, ever. Tests run against the fixture-driven fake in `tests/harness`
  (PVE 8 and PVE 9 canned data; an unmocked route raises `UnmockedCallError`).
- `scripts/live/` contains manual scripts that need a real cluster. They are not collected by pytest
  and never run in CI.
- Do not commit secrets or secret-shaped literals. Generate keys and tokens at runtime in tests.
- Never commit `proxmox-config/config.json` (it is git-ignored); start from
  `proxmox-config/config.example.json`.

## Golden snapshot rule

`tests/golden/tools.json` freezes the public tool surface (tool names, parameter names, required
flags and simple types). Existing MCP client configurations depend on it. A deliberate change must,
in the same pull request:

1. update `tests/golden/tools.json`,
2. update the exact-delta test in `tests/test_tool_schema_snapshot.py` (and
   `tests/test_phase5_surface.py` when the count changes),
3. add a `CHANGELOG.md` entry (a renamed or removed tool or parameter is a breaking change),
4. regenerate the README table: `uv run python scripts/gen_tool_table.py`.

## Adding a tool

1. Implement it in the matching module under `src/proxmox_mcp/tools/`. Validate every user-supplied
   identifier with `src/proxmox_mcp/validators.py` before any API call, and map errors through
   `pve_compat.translate_pve_error` (add the operation to `OPERATION_PRIVILEGES`).
2. Register it with a `ToolSpec` in `tools/registry.py` with an explicit risk class (`read`, `write`,
   `destructive` or `exec`; there is no default) and MCP annotations. Destructive tools take
   `confirm` and return a preview unless it is true.
3. Extend the policy matrix test and the path-injection tests so the new tool is covered, and add mock
   tests in the harness.
4. Update the golden snapshot (see above) and the README table.

## Commits and pull requests

- Imperative subject line (for example `fix(auth): reject empty digest list`), a short body if the why
  is not obvious. One logical change per commit.
- Do not add AI attribution lines or tool-generated trailers (for example `Co-Authored-By` lines for
  assistants or "Generated with" footers) to commit messages or pull request descriptions.
- Fill in the pull request template; the checklist mirrors this page.
- Keep unrelated formatting changes out of the diff.
