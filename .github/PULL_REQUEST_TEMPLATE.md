## What and why

<!-- Describe the change and the reason. Link the issue if there is one. -->

## Checklist

- [ ] `uv run ruff check src tests scripts` is clean
- [ ] `uv run ruff format --check src tests scripts` is clean
- [ ] `uv run mypy src` is clean
- [ ] `uv run pytest -q` passes (mock harness only, no real Proxmox)
- [ ] If a tool name or parameter changed: `tests/golden/tools.json`, the exact-delta test and `CHANGELOG.md` are updated, and the README table is regenerated (`uv run python scripts/gen_tool_table.py`)
- [ ] New or changed tools have an explicit risk class, validators, and policy matrix and path-injection tests
- [ ] No secrets, tokens or secret-shaped literals; `proxmox-config/config.json` is not included
- [ ] Documentation updated (README, SECURITY.md if the threat surface changed)
- [ ] Commit messages have no AI attribution trailers
