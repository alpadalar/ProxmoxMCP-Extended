"""Tests for scripts/scan_history.py (secret and AI-label history scanner).

Every secret-shaped value is generated at runtime so no secret-looking literal is committed, and
the scanner is run in a subprocess against throw-away git repositories. The central property is
that no matched value ever reaches stdout, stderr or a report file.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import string
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_history.py"
REPO_ALLOWLIST = Path(__file__).resolve().parents[1] / "scripts" / "scan_allowlist.txt"
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(GIT is None, reason="git is required")


def _env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        HOME=str(home),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_AUTHOR_NAME="Test Author",
        GIT_AUTHOR_EMAIL="author@example.invalid",
        GIT_COMMITTER_NAME="Test Author",
        GIT_COMMITTER_EMAIL="author@example.invalid",
    )
    return env


def _git(repo: Path, *args: str) -> str:
    assert GIT is not None
    done = subprocess.run(  # noqa: S603 - fixed argv, absolute git path, throw-away repo
        [GIT, "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        capture_output=True,
        text=True,
        check=True,
        env=_env(repo.parent),
        timeout=60,
    )
    return done.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    return path


def commit(
    repo: Path,
    files: dict[str, str | None],
    message: str = "change",
    author: str | None = None,
) -> str:
    """Write (or delete, for None) files and commit them; returns the short sha."""
    for name, content in files.items():
        target = repo / name
        if content is None:
            _git(repo, "rm", "-q", "-f", "--", name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _git(repo, "add", "--", name)
    extra = ["--author", author] if author else []
    _git(repo, "commit", "-q", "--allow-empty", "-m", message, *extra)
    return _git(repo, "rev-parse", "--short", "HEAD").strip()


def scan(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv: our own script under test
        [sys.executable, str(SCRIPT), "--repo", str(repo), *extra],
        capture_output=True,
        text=True,
        env=_env(repo.parent),
        timeout=120,
    )


def rows(proc: subprocess.CompletedProcess[str]) -> list[list[str]]:
    """Finding rows (tab separated: rule, commit, path, line, length)."""
    return [ln.split("\t") for ln in proc.stdout.splitlines() if ln.count("\t") == 4]


def rules(proc: subprocess.CompletedProcess[str]) -> set[str]:
    return {r[0] for r in rows(proc)}


def alnum(n: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


# --- Test 1: history, not only HEAD; value never printed -------------------------------------


def test_removed_token_value_is_found_in_history_and_never_printed(repo: Path, tmp_path: Path):
    value = str(uuid.uuid4())
    first = commit(repo, {"cfg.json": '{\n  "token_value": "' + value + '"\n}\n'}, "add config")
    commit(repo, {"cfg.json": '{\n  "token_value": "REDACTED_VALUE"\n}\n'}, "scrub config")
    report = tmp_path / "report.md"

    proc = scan(repo, "--mode", "secrets", "--report", str(report))

    assert proc.returncode == 1
    assert "pve-token-value" in rules(proc)
    hit = [r for r in rows(proc) if r[0] == "pve-token-value"][0]
    assert hit[1].startswith(first[:7])
    assert hit[2] == "cfg.json"
    assert hit[4] == str(len(value))
    for blob in (proc.stdout, proc.stderr, report.read_text(encoding="utf-8")):
        assert value not in blob
        assert value.replace("-", "") not in blob
    # the secret is gone from HEAD but the report still names the offending commit
    assert first[:7] in report.read_text(encoding="utf-8")


def test_clean_repo_exits_zero(repo: Path):
    commit(repo, {"a.txt": "nothing to see\n"})
    proc = scan(repo, "--mode", "all")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert rows(proc) == []


# --- Test 2: placeholders are not findings -----------------------------------------------------


def test_placeholders_are_not_findings(repo: Path):
    lines = [
        '"token_value": "your-token-value"',
        'token_value = "TOKEN_VALUE"',
        '"token_value": "**********"',
        "PROXMOX_TOKEN_VALUE=YOUR_API_KEY",
        '"token_value": "fake-not-a-real-secret"',
        'headers = {"Authorization": "Bearer YOUR_API_KEY"}',
        "token_value=self.config.auth.token_value",
        "token_value: SecretStr",
        '"token_value": "<your token>"',
        'token = "00000000-0000-0000-0000-000000000000"',
    ]
    commit(repo, {"docs.md": "\n".join(lines) + "\n"})
    proc = scan(repo, "--mode", "secrets", "--allowlist", str(REPO_ALLOWLIST))
    assert proc.returncode == 0, proc.stdout
    assert rows(proc) == []


def test_no_builtin_word_suppression_and_words_match_whole_words_only(repo: Path, tmp_path: Path):
    real = "ab9K" + alnum(20)
    # placeholder words inside a longer, secret-looking value must not hide it
    commit(
        repo,
        {
            "a.json": '{"token_value": "' + real + "example" + alnum(6) + '"}\n',
            "b.json": '{"token_value": "xfake' + alnum(24) + '"}\n',
            "c.json": '{"token_value": "example-' + alnum(24) + '"}\n',
        },
    )
    # no allowlist: nothing is suppressed by wording alone
    assert {r[2] for r in rows(scan(repo, "--mode", "secrets"))} == {"a.json", "b.json", "c.json"}
    allow = tmp_path / "allow.txt"
    allow.write_text("fake\nexample\n", encoding="utf-8")
    got = {r[2] for r in rows(scan(repo, "--mode", "secrets", "--allowlist", str(allow)))}
    assert got == {"a.json", "b.json"}  # only the delimited word "example-" is suppressed


def test_value_entry_matches_the_whole_value_only(repo: Path, tmp_path: Path):
    word = "pass" + "word"
    commit(
        repo,
        {
            "a.json": '{"token_value": "' + word + '"}\n',
            "b.json": '{"token_value": "' + word + "123" + alnum(6) + '"}\n',
        },
    )
    allow = tmp_path / "allow.txt"
    allow.write_text(f"value:{word}\n", encoding="utf-8")
    got = {r[2] for r in rows(scan(repo, "--mode", "secrets", "--allowlist", str(allow)))}
    assert got == {"b.json"}


def test_allowlist_file_suppresses_a_substring_and_a_fingerprint(repo: Path, tmp_path: Path):
    value = "zzq-" + alnum(24)
    commit(repo, {"x.json": '{"token_value": "' + value + '"}\n'})
    assert scan(repo, "--mode", "secrets").returncode == 1

    by_substring = tmp_path / "allow_sub.txt"
    by_substring.write_text("# comment\nzzq-\n", encoding="utf-8")
    assert scan(repo, "--mode", "secrets", "--allowlist", str(by_substring)).returncode == 0

    digest = hashlib.sha256(value.encode()).hexdigest()[:16]
    by_fingerprint = tmp_path / "allow_fp.txt"
    by_fingerprint.write_text(f"sha256:{digest}\n", encoding="utf-8")
    assert scan(repo, "--mode", "secrets", "--allowlist", str(by_fingerprint)).returncode == 0


def test_rule_path_allowlist_is_scoped_to_one_rule_and_file(repo: Path, tmp_path: Path):
    header = "-----BEGIN " + "RSA PRIVATE KEY-----"
    commit(repo, {"docs/a.md": f"the header is `{header}`\n", "docs/b.md": f"{header}\n"})
    allow = tmp_path / "allow.txt"
    allow.write_text("pem-private-key:docs/a.md\n", encoding="utf-8")
    proc = scan(repo, "--mode", "secrets", "--allowlist", str(allow))
    assert proc.returncode == 1
    assert {r[2] for r in rows(proc) if r[0] == "pem-private-key"} == {"docs/b.md"}


def test_code_expressions_are_not_token_values(repo: Path):
    lines = [
        "p.write_text('{\"token_value\": \"' + SENTINEL + '\"}')",
        "cfg = dict(token_value=get_secret_value())",
        "token_value: str = Field(min_length=1)",
    ]
    commit(repo, {"src/code.py": "\n".join(lines) + "\n"})
    assert scan(repo, "--mode", "secrets").returncode == 0


# --- Test 3: token header, PEM, GitHub token ---------------------------------------------------


def test_pveapitoken_header_pem_and_github_token_are_detected(repo: Path):
    token_uuid = str(uuid.uuid4())
    header = "Authorization: PVEAPIToken=" + "ci@pve!deploy=" + token_uuid
    pem = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    gh = "gh" + "p_" + alnum(36)
    commit(repo, {"notes.txt": f"{header}\n{pem}\nkey={gh}\n"})
    report_out = scan(repo, "--mode", "secrets")
    assert report_out.returncode == 1
    found = rules(report_out)
    assert {"pveapitoken-header", "pem-private-key", "github-token"} <= found
    for secret in (token_uuid, gh):
        assert secret not in report_out.stdout + report_out.stderr


def test_aws_key_and_bearer_are_detected_outside_tests_only(repo: Path):
    aws = (
        "AK"
        + "IA"
        + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    )
    bearer = "Bearer " + alnum(40)
    short = "Bearer " + alnum(24)
    commit(
        repo,
        {
            "src/a.py": f'k = "{aws}"\nh = "{bearer}"\n',
            "tests/t.py": f'h = "{short}"\n',
            "tests/long.py": f'h = "{bearer}"\n',
        },
    )
    proc = scan(repo, "--mode", "secrets")
    got = {(r[0], r[2]) for r in rows(proc)}
    assert ("aws-access-key", "src/a.py") in got
    assert ("generic-bearer", "src/a.py") in got
    assert ("generic-bearer", "tests/t.py") not in got  # short fixture token
    assert ("generic-bearer", "tests/long.py") in got  # a long credential is reported anywhere


def test_sha256_digests_are_informational_only(repo: Path):
    digest = "".join(secrets.choice("0123456789abcdef") for _ in range(64))
    commit(repo, {"env.txt": f"PROXMOX_MCP_API_KEY_HASHES={digest}\n"})
    proc = scan(repo, "--mode", "secrets")
    assert proc.returncode == 0
    assert rows(proc) == []
    assert "informational" in proc.stdout.lower()
    assert digest not in proc.stdout + proc.stderr


# --- Test 4: tracked config.json ---------------------------------------------------------------


def test_tracked_proxmox_config_json_is_flagged_even_with_clean_content(repo: Path):
    sha = commit(repo, {"proxmox-config/config.json": '{"auth": {"user": "u@pve"}}\n'})
    commit(repo, {"proxmox-config/config.json": None}, "stop tracking")
    proc = scan(repo, "--mode", "secrets")
    assert proc.returncode == 1
    hit = [r for r in rows(proc) if r[0] == "tracked-config-json"]
    assert hit, proc.stdout
    assert {h[1][:7] for h in hit} >= {sha[:7]}  # the adding commit and the removing commit
    assert {h[2] for h in hit} == {"proxmox-config/config.json"}


def test_example_config_is_not_flagged(repo: Path):
    commit(repo, {"proxmox-config/config.example.json": '{"auth": {"user": "u@pve"}}\n'})
    assert scan(repo, "--mode", "secrets").returncode == 0


# --- Test 5: AI labels -------------------------------------------------------------------------


def _co_author(name: str, email: str) -> str:
    return "Co-Authored-By: " + name + " <" + email + ">"


@pytest.mark.parametrize(
    "message",
    [
        "feat: x\n\n" + _co_author("Cla" + "ude", "noreply@anth" + "ropic.com"),
        "feat: x\n\nGenerated " + "with Cla" + "ude Code",
        "feat: " + chr(0x1F916) + " add things",
        "feat: x\n\n" + _co_author("Copi" + "lot", "copi" + "lot@example.invalid"),
        "feat: x\n\n" + _co_author("Co" + "dex", "co" + "dex@example.invalid"),
        "feat: x\n\n" + _co_author("Gem" + "ini", "gem" + "ini@example.invalid"),
        "Merge pull request #5 from fork/co" + "dex/fix-things",
    ],
)
def test_ai_labels_in_commit_messages_are_reported(repo: Path, message: str):
    sha = commit(repo, {"a.txt": "a\n"}, message)
    proc = scan(repo, "--mode", "labels")
    assert proc.returncode == 1
    hits = [r for r in rows(proc) if r[0] == "ai-label"]
    assert hits and hits[0][1].startswith(sha[:7])


def test_normal_commit_message_is_not_an_ai_label(repo: Path):
    commit(repo, {"a.txt": "a\n"}, "fix(auth): reject empty digest list\n\nPlain body.")
    proc = scan(repo, "--mode", "labels")
    assert proc.returncode == 0, proc.stdout
    assert rows(proc) == []


def test_mcp_client_names_in_messages_are_not_labels(repo: Path):
    commit(repo, {"a.txt": "a\n"}, "docs: examples for Cla" + "ude Desktop/Cur" + "sor/Cline")
    proc = scan(repo, "--mode", "labels")
    assert proc.returncode == 0, proc.stdout
    assert "ai-tool-name-mention-in-message=1" in proc.stdout


def test_ai_author_identity_is_reported(repo: Path):
    sha = commit(
        repo,
        {"a.txt": "a\n"},
        "chore: bot change",
        author="Cla" + "ude <noreply@anth" + "ropic.com>",
    )
    proc = scan(repo, "--mode", "labels")
    assert proc.returncode == 1
    hits = [r for r in rows(proc) if r[0] == "ai-identity"]
    assert hits and hits[0][1].startswith(sha[:7])
    assert "noreply@anth" + "ropic.com" not in proc.stdout


def test_tree_labels_are_informational_and_counted_by_directory(repo: Path, tmp_path: Path):
    word = "Cla" + "ude"
    commit(repo, {"docs/a.md": f"written with {word}\n", "docs/b.md": f"{word} again\n"})
    report = tmp_path / "labels.md"
    proc = scan(repo, "--mode", "labels", "--report", str(report))
    assert proc.returncode == 0, proc.stdout
    text = report.read_text(encoding="utf-8")
    assert "docs" in text and "tree" in text.lower()


# --- Test 6: worktree and untracked files; ignored files never opened -------------------------


def test_untracked_files_are_scanned_but_ignored_files_are_not(repo: Path):
    ignored_secret = str(uuid.uuid4())
    commit(repo, {".gitignore": "proxmox-config/config.json\n"}, "ignore real config")
    (repo / "proxmox-config").mkdir()
    (repo / "proxmox-config" / "config.json").write_text(
        '{"token_value": "' + ignored_secret + '"}\n', encoding="utf-8"
    )
    proc = scan(repo, "--mode", "secrets")
    assert proc.returncode == 0, proc.stdout
    assert rows(proc) == []

    visible = str(uuid.uuid4())
    (repo / "scratch.env").write_text("PROXMOX_TOKEN_VALUE=" + visible + "\n", encoding="utf-8")
    proc = scan(repo, "--mode", "secrets")
    assert proc.returncode == 1
    hit = [r for r in rows(proc) if r[0] == "pve-token-value"]
    assert hit and hit[0][1] == "WORKTREE" and hit[0][2] == "scratch.env"
    for blob in (proc.stdout, proc.stderr):
        assert visible not in blob
        assert ignored_secret not in blob


def test_uncommitted_modification_in_tracked_file_is_scanned(repo: Path):
    commit(repo, {"a.txt": "clean\n"})
    (repo / "a.txt").write_text("token_value = '" + str(uuid.uuid4()) + "'\n", encoding="utf-8")
    proc = scan(repo, "--mode", "secrets")
    assert proc.returncode == 1
    assert any(r[1] == "WORKTREE" for r in rows(proc))


# --- all refs ----------------------------------------------------------------------------------


def test_secret_on_a_non_head_branch_is_found(repo: Path):
    commit(repo, {"a.txt": "clean\n"})
    _git(repo, "checkout", "-q", "-b", "side")
    value = str(uuid.uuid4())
    commit(repo, {"b.txt": 'api_token = "' + value + '"\n'}, "side work")
    _git(repo, "checkout", "-q", "main")
    proc = scan(repo, "--mode", "secrets")
    assert proc.returncode == 1
    assert "pve-token-uuid" in rules(proc)
    assert value not in proc.stdout + proc.stderr
