#!/usr/bin/env python3
"""Local, offline scanner for secrets and AI labels in a git repository (stdlib only).

Secrets mode scans the added lines of EVERY commit reachable from ANY ref (``git log --all -p``),
plus the working tree and untracked, non-ignored files (``git ls-files -co --exclude-standard``,
so git-ignored files such as ``proxmox-config/config.json`` are never opened). It also flags every
commit that touched ``proxmox-config/config.json``.

Labels mode scans commit messages, author and committer identities for AI tool labels and, for
information only, lists tracked files that mention such labels, counted per top-level entry.

The scanner NEVER prints, logs or writes a matched value. Output rows carry the rule id, the short
commit, the path, the line number and the length of the match only.

Exit status: 0 when there is no non-informational finding, 1 otherwise, 2 on a usage or git error.

Usage:
    uv run python scripts/scan_history.py --mode all --report /path/to/report.md
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess  # noqa: S404 - runs git with a fixed argv, never a shell
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCANNER_VERSION = "1.0.0"
MAX_LINE = 20000  # characters of one line that are inspected (guards against minified blobs)
MAX_FILE = 2_000_000  # bytes; larger working-tree files are skipped
WORKTREE = "WORKTREE"
CONFIG_PATH = "proxmox-config/config.json"
SELF_PATHS = ("scripts/scan_history.py", "tests/test_scan_history.py")

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

PLACEHOLDER_SUBSTRINGS = (
    "your",
    "example",
    "placeholder",
    "changeme",
    "change-me",
    "change_me",
    "fake",
    "dummy",
    "sample",
    "redacted",
    "replace",
    "not-a-real",
    "token_value",
    "token-value",
    "secret_value",
    "<",
    ">",
    "{",
    "}",
    "%s",
    "xxx",
)
PLACEHOLDER_WORDS = {"none", "null", "nil", "true", "false", "todo", "secret", "token", "password"}


# --------------------------------------------------------------------------------------------
# data model
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    rule: str
    commit: str
    path: str
    line: int
    length: int
    informational: bool = False

    def row(self) -> str:
        path = self.path.replace("\t", " ").replace("\n", " ")
        return f"{self.rule}\t{self.commit[:10]}\t{path}\t{self.line}\t{self.length}"


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    commits_scanned: int = 0
    files_scanned: int = 0
    informational: Counter[str] = field(default_factory=Counter)
    suppressed: Counter[str] = field(default_factory=Counter)
    authors: Counter[tuple[str, str]] = field(default_factory=Counter)
    committers: Counter[str] = field(default_factory=Counter)
    tree_labels: dict[str, list[int]] = field(default_factory=dict)  # group -> [files, matches]
    _seen: set[tuple[str, str, str, int]] = field(default_factory=set)

    def add(self, finding: Finding) -> None:
        key = (finding.rule, finding.commit, finding.path, finding.line)
        if key in self._seen:
            return
        self._seen.add(key)
        if finding.informational:
            self.informational[finding.rule] += 1
        else:
            self.findings.append(finding)


class Allowlist:
    """Placeholder substrings (case-insensitive) and ``sha256:<prefix>`` value fingerprints."""

    def __init__(self, entries: list[str] | None = None) -> None:
        self.substrings: list[str] = []
        self.fingerprints: list[str] = []
        self.rule_paths: set[tuple[str, str]] = set()
        for entry in entries or []:
            entry = entry.strip()
            if not entry or entry.startswith("#"):
                continue
            head, _, tail = entry.partition(":")
            if head == "sha256":
                self.fingerprints.append(tail.lower())
            elif tail and head in RULE_IDS:
                self.rule_paths.add((head, tail))
            else:
                self.substrings.append(entry.lower())

    @classmethod
    def from_file(cls, path: str | None) -> Allowlist:
        if not path:
            return cls()
        return cls(Path(path).read_text(encoding="utf-8").splitlines())

    def suppresses(self, rule: str, path: str) -> bool:
        return (rule, path) in self.rule_paths

    def allows(self, value: str) -> bool:
        lowered = value.lower()
        if any(s in lowered for s in self.substrings):
            return True
        digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
        return any(digest.startswith(f) for f in self.fingerprints if f)


def is_placeholder(value: str, allow: Allowlist) -> bool:
    v = value.strip()
    if not v or not any(c.isalnum() for c in v):
        return True
    if re.fullmatch(r"[A-Z_]+", v):  # TOKEN_VALUE, YOUR_API_KEY
        return True
    lowered = v.lower()
    if set(lowered) <= set("x*-._#"):
        return True
    if lowered in PLACEHOLDER_WORDS:
        return True
    if any(s in lowered for s in PLACEHOLDER_SUBSTRINGS):
        return True
    if re.fullmatch(UUID, v) and len(set(v.replace("-", "").lower())) <= 2:
        return True  # 0000..., aaaa...
    return allow.allows(v)


# --------------------------------------------------------------------------------------------
# secret rules
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    value: Callable[[re.Match[str]], str]
    accept: Callable[[str, str, Allowlist], bool]  # (value, path, allowlist) -> is a finding
    informational: bool = False
    description: str = ""


def _whole(m: re.Match[str]) -> str:
    return m.group(0)


def _group(name: str) -> Callable[[re.Match[str]], str]:
    def get(m: re.Match[str]) -> str:
        return m.group(name)

    return get


def _token_value(m: re.Match[str]) -> str:
    for name in ("dq", "sq", "bare"):
        if m.group(name) is not None:
            return str(m.group(name))
    return ""


def _accept_token_value(value: str, path: str, allow: Allowlist) -> bool:
    if re.search(r"""[\s'"`()]""", value):
        return False  # string concatenation or a call expression in source code, not a literal
    if is_placeholder(value, allow):
        return False
    bare_code_like = not any(c.isdigit() for c in value)
    # An unquoted value without a digit is a code expression or a type name, not a token. A quoted
    # literal is checked with the placeholder rules only, so short fake secrets are caught too.
    return not (bare_code_like and re.fullmatch(r"[A-Za-z_][\w.\[\]()]*", value) is not None)


def _accept_if_not_placeholder(value: str, path: str, allow: Allowlist) -> bool:
    return not is_placeholder(value, allow)


def _accept_always(value: str, path: str, allow: Allowlist) -> bool:
    return True


def _pveapitoken_secret(m: re.Match[str]) -> str:
    raw = m.group("v")
    return raw.rsplit("=", 1)[-1] if "=" in raw else ""


def _accept_bearer(value: str, path: str, allow: Allowlist) -> bool:
    if path.startswith("tests/") or "/tests/" in path:
        return False
    return not is_placeholder(value, allow)


def _accept_digest(value: str, path: str, allow: Allowlist) -> bool:
    return True


RULES: tuple[Rule, ...] = (
    Rule(
        "pve-token-uuid",
        re.compile(rf"(?i)(?:token|secret|api[_-]?key)[^\n]{{0,40}}?\b(?P<v>{UUID})\b"),
        _group("v"),
        _accept_if_not_placeholder,
        description="UUID within 40 characters after a token/secret/api key word",
    ),
    Rule(
        "pve-token-uuid",
        re.compile(rf"(?i)\b(?P<v>{UUID})\b[^\n]{{0,20}}?(?:token|secret)"),
        _group("v"),
        _accept_if_not_placeholder,
        description="UUID followed closely by a token/secret word",
    ),
    Rule(
        "pve-token-value",
        re.compile(
            r"""(?ix)
            (?:["']?token[_-]?value["']?|PROXMOX_TOKEN_VALUE|PVE_TOKEN_VALUE)
            \s*[:=]\s*
            (?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s,;}\])\#"'`]+))
            """
        ),
        _token_value,
        _accept_token_value,
        description="token_value / PROXMOX_TOKEN_VALUE assignment with a non-placeholder value",
    ),
    Rule(
        "pveapitoken-header",
        re.compile(r"PVEAPIToken=(?P<v>[^\s\"'`,;]+)"),
        _pveapitoken_secret,
        _accept_if_not_placeholder,
        description="PVEAPIToken=user@realm!name=secret header with a real-looking secret",
    ),
    Rule(
        "pem-private-key",
        re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
        _whole,
        _accept_always,
        description="PEM / OpenSSH private key header",
    ),
    Rule(
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
        _whole,
        _accept_always,
        description="GitHub personal access / app token",
    ),
    Rule(
        "aws-access-key",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        _whole,
        _accept_always,
        description="AWS access key id",
    ),
    Rule(
        "generic-bearer",
        re.compile(r"\bBearer\s+(?P<v>[A-Za-z0-9._~+/=-]{20,})"),
        _group("v"),
        _accept_bearer,
        description="Long bearer credential outside tests",
    ),
    Rule(
        "sha256-digest-allowed",
        re.compile(r"\b[0-9a-fA-F]{64}\b"),
        _whole,
        _accept_digest,
        informational=True,
        description="64-hex digest (documented API key digests are not secrets); counted only",
    ),
)


RULE_IDS = frozenset(r.id for r in RULES)


def scan_text(
    text: str, path: str, commit: str, line: int, allow: Allowlist, result: Result
) -> None:
    text = text[:MAX_LINE]
    for rule in RULES:
        for m in rule.pattern.finditer(text):
            value = rule.value(m)
            if rule.accept(value, path, allow):
                if allow.suppresses(rule.id, path):
                    result.suppressed[rule.id] += 1
                    break
                result.add(Finding(rule.id, commit, path, line, len(value), rule.informational))
                break  # one finding per rule and line is enough


# --------------------------------------------------------------------------------------------
# git plumbing
# --------------------------------------------------------------------------------------------


class GitError(RuntimeError):
    pass


def git_cmd(repo: str, *args: str) -> list[str]:
    git = shutil.which("git")
    if git is None:
        raise GitError("git executable not found")
    return [git, "-C", repo, "-c", "core.quotepath=false", *args]


def git_run(repo: str, *args: str) -> bytes:
    proc = subprocess.run(  # noqa: S603 - fixed argv, absolute git path, no shell
        git_cmd(repo, *args), capture_output=True, check=False, timeout=600
    )
    if proc.returncode != 0:
        raise GitError(f"git {args[0]} failed with status {proc.returncode}")
    return proc.stdout


def git_stream(repo: str, *args: str) -> Iterator[str]:
    """Yield decoded lines of a git command without loading the whole output."""
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, absolute git path, no shell
        git_cmd(repo, *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdout is not None  # noqa: S101 - PIPE was requested above
    try:
        for raw in proc.stdout:
            yield raw.decode("utf-8", errors="replace").rstrip("\n")
    finally:
        proc.stdout.close()
        status = proc.wait()
    if status != 0:
        raise GitError(f"git {args[0]} failed with status {status}")


DIFF_RE = re.compile(r"^diff --git a/(?P<a>.+) b/(?P<b>.+)$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,\d+)? @@")


def _is_config(path: str) -> bool:
    return path == CONFIG_PATH or path.endswith("/" + CONFIG_PATH)


def scan_history(repo: str, allow: Allowlist, result: Result) -> None:
    commit = ""
    path: str | None = None
    in_hunk = False
    lineno = 0
    for line in git_stream(
        repo,
        "log",
        "--all",
        "--full-history",
        "-p",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--format=%x01%H",
    ):
        if line.startswith("\x01"):
            commit = line[1:]
            path = None
            in_hunk = False
            result.commits_scanned += 1
            continue
        if line.startswith("diff --git "):
            in_hunk = False
            path = None
            m = DIFF_RE.match(line)
            if m:
                for candidate in (m.group("a"), m.group("b")):
                    if _is_config(candidate):
                        result.add(Finding("tracked-config-json", commit, candidate, 0, 0))
            continue
        if not in_hunk:
            if line.startswith("+++ "):
                target = line[4:]
                path = target[2:] if target.startswith("b/") else None
            elif line.startswith("@@"):
                m2 = HUNK_RE.match(line)
                if m2:
                    in_hunk = True
                    lineno = int(m2.group("start")) - 1
            continue
        if line.startswith("@@"):
            m2 = HUNK_RE.match(line)
            if m2:
                lineno = int(m2.group("start")) - 1
            continue
        if line.startswith("+") and path is not None:
            lineno += 1
            scan_text(line[1:], path, commit, lineno, allow, result)


def scan_worktree(repo: str, allow: Allowlist, result: Result) -> None:
    listing = git_run(repo, "ls-files", "-z", "-c", "-o", "--exclude-standard")
    root = Path(repo)
    for name in listing.split(b"\0"):
        if not name:
            continue
        rel = name.decode("utf-8", errors="replace")
        if _is_config(rel):
            result.add(Finding("tracked-config-json", WORKTREE, rel, 0, 0))
        full = root / rel
        try:
            if full.is_symlink() or not full.is_file() or full.stat().st_size > MAX_FILE:
                continue
            data = full.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8000]:
            continue
        result.files_scanned += 1
        for idx, text in enumerate(data.decode("utf-8", errors="replace").splitlines(), start=1):
            scan_text(text, rel, WORKTREE, idx, allow, result)


# --------------------------------------------------------------------------------------------
# AI labels
# --------------------------------------------------------------------------------------------

AI_NAMES = (
    r"claude|anthropic|copilot|chatgpt|openai|\bgpt\b|gpt-\d|codex|gemini|cursor|devin|aider"
    r"|windsurf"
)
MESSAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("co-authored-by", re.compile(rf"(?im)^\s*co-authored-by:.*(?:{AI_NAMES})")),
    (
        "generated-with",
        re.compile(
            r"(?i)\bgenerated (?:with|by|using)\b\W{0,3}"
            r"(?:claude|chatgpt|gpt|copilot|gemini|codex|cursor|devin|aider|an? ai\b|ai\b)"
        ),
    ),
    ("claude-code", re.compile(r"(?i)\bclaude[ -]code\b")),
    (
        "ai-branch-name",
        re.compile(
            r"(?i)(?:\bfrom\s+\S*?|\bbranch\s+'?)\b"
            r"(?:codex|copilot|claude|cursor|devin|gemini|aider|openai)/[\w.-]+"
        ),
    ),
    ("noreply-anthropic", re.compile(r"(?i)noreply@anthropic\.com")),
    ("robot-emoji", re.compile("\U0001f916")),
)
IDENTITY_RE = re.compile(rf"(?i)(?:{AI_NAMES})")
TREE_RE = re.compile(rf"(?i)(?:{AI_NAMES})|generated (?:with|by)\b|co-authored-by|\U0001f916")


def scan_commit_labels(repo: str, result: Result) -> None:
    out = git_run(
        repo, "log", "--all", "--format=%x01%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B", "--no-color"
    ).decode("utf-8", errors="replace")
    for chunk in out.split("\x01"):
        if not chunk.strip():
            continue
        parts = chunk.split("\x00", 5)
        if len(parts) < 6:
            continue
        sha, an, ae, cn, ce, body = parts
        sha = sha.strip()
        result.authors[(an, ae)] += 1
        result.committers[cn] += 1
        for who, name, email in (("author", an, ae), ("committer", cn, ce)):
            if IDENTITY_RE.search(name) or IDENTITY_RE.search(email):
                result.add(Finding("ai-identity", sha, f"({who})", 0, len(name) + len(email)))
        matched = False
        for kind, pattern in MESSAGE_PATTERNS:
            m = pattern.search(body)
            if m:
                matched = True
                line_no = body.count("\n", 0, m.start()) + 1
                result.add(
                    Finding("ai-label", sha, f"(commit-message:{kind})", line_no, len(m.group(0)))
                )
        if not matched and IDENTITY_RE.search(body):
            # e.g. "Claude Desktop" or "Cursor" as MCP client names: counted, not a label
            result.informational["ai-tool-name-mention-in-message"] += 1


def scan_tree_labels(repo: str, result: Result) -> None:
    listing = git_run(repo, "ls-files", "-z")
    root = Path(repo)
    for name in listing.split(b"\0"):
        if not name:
            continue
        rel = name.decode("utf-8", errors="replace")
        if rel in SELF_PATHS:
            continue
        full = root / rel
        hits = 1 if TREE_RE.search(rel) else 0
        try:
            if not full.is_symlink() and full.is_file() and full.stat().st_size <= MAX_FILE:
                data = full.read_bytes()
                if b"\0" not in data[:8000]:
                    text = data.decode("utf-8", errors="replace")
                    hits += sum(1 for ln in text.splitlines() if TREE_RE.search(ln[:MAX_LINE]))
        except OSError:
            pass
        if hits:
            group = rel.split("/", 1)[0]
            entry = result.tree_labels.setdefault(group, [0, 0])
            entry[0] += 1
            entry[1] += hits


# --------------------------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------------------------


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


def _repo_meta(repo: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        meta["head"] = git_run(repo, "rev-parse", "--short", "HEAD").decode().strip()
        refs = git_run(repo, "for-each-ref", "--format=%(refname)").decode().split()
        meta["refs"] = str(len(refs))
        meta["ref_names"] = ", ".join(sorted(r.replace("refs/", "", 1) for r in refs)) or "none"
        meta["commits"] = git_run(repo, "rev-list", "--all", "--count").decode().strip()
        meta["scanner_commit"] = (
            git_run(repo, "log", "-1", "--format=%h", "--", "scripts/scan_history.py")
            .decode()
            .strip()
            or "uncommitted"
        )
    except GitError:
        meta.setdefault("head", "unknown")
    return meta


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def _pyproject_email(repo: str) -> str | None:
    try:
        text = (Path(repo) / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"authors\s*=\s*\[[^\]]*?email\s*=\s*\"([^\"]+)\"", text)
    return m.group(1) if m else None


def render_report(result: Result, mode: str, repo: str, command: str) -> str:
    meta = _repo_meta(repo)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nonfinal = result.findings
    secret_ids = {r.id for r in RULES} | {"tracked-config-json"}
    secret_rows = [f for f in nonfinal if f.rule in secret_ids]
    label_rows = [f for f in nonfinal if f.rule in {"ai-label", "ai-identity"}]
    lines: list[str] = []
    lines.append(f"Generated by scripts/scan_history.py {SCANNER_VERSION} on {today}.")
    lines.append("")
    lines.append(
        f"- Scanner version: {SCANNER_VERSION} (file last changed in {meta['scanner_commit']})"
    )
    lines.append(f"- Repository HEAD: {meta['head']}")
    lines.append(f"- Refs scanned: {meta.get('refs', '?')} ({meta.get('ref_names', '?')})")
    lines.append(f"- Commits reachable from all refs: {meta.get('commits', '?')}")
    lines.append(f"- Commits scanned (diff stream): {result.commits_scanned}")
    lines.append(f"- Working tree files scanned: {result.files_scanned}")
    lines.append(f"- Mode: {mode}")
    lines.append(f"- Reproduce: `{command}`")
    lines.append("")
    lines.append("No matched value appears anywhere in this report: rows carry the rule id, the")
    lines.append("short commit, the path, the line number and the match length only.")
    lines.append("")
    if mode in {"secrets", "all"}:
        status = "BLOCKER" if secret_rows else "CLEAN"
        lines.append(f"## Secret scan result: {status}")
        lines.append("")
        lines.append(f"Non-informational secret findings: {len(secret_rows)}")
        lines.append("")
        lines.append("Rules:")
        lines.append("")
        lines += _table(
            ["Rule", "Kind", "Description"],
            [
                [r.id, "informational" if r.informational else "finding", r.description]
                for r in RULES
            ]
            + [["tracked-config-json", "finding", "A revision touched proxmox-config/config.json"]],
        )
        lines.append("")
        if secret_rows:
            lines += _table(
                ["Rule", "Commit", "Path", "Line", "Length"],
                [[f.rule, f.commit[:10], f.path, str(f.line), str(f.length)] for f in secret_rows],
            )
        else:
            lines.append("No findings.")
        lines.append("")
        tracked = [f for f in secret_rows if f.rule == "tracked-config-json"]
        if tracked:
            lines.append(
                f"proxmox-config/config.json WAS tracked: {len(tracked)} revision(s) touched it "
                "(see the table). Rotate any token that file ever held."
            )
        else:
            lines.append(
                "proxmox-config/config.json was never tracked in any scanned revision and is not "
                "tracked or unignored in the working tree."
            )
        lines.append("")
        info = result.informational.get("sha256-digest-allowed", 0)
        if result.suppressed:
            lines.append(
                "Allowlisted (rule:path entries from the allowlist file): "
                + ", ".join(f"{k}={v}" for k, v in sorted(result.suppressed.items()))
                + " line occurrence(s)."
            )
            lines.append("")
        lines.append(
            f"Informational: {info} occurrence(s) of 64-hex digests (sha256 API key digests and "
            "lock file hashes are not secrets). Not listed."
        )
        lines.append("")
    if mode in {"labels", "all"}:
        status = "FINDINGS" if label_rows else "CLEAN"
        lines.append(f"## AI label scan result: {status}")
        lines.append("")
        lines.append(f"Commit message / identity findings: {len(label_rows)}")
        lines.append("")
        if label_rows:
            lines += _table(
                ["Rule", "Commit", "Where", "Line", "Length"],
                [[f.rule, f.commit[:10], f.path, str(f.line), str(f.length)] for f in label_rows],
            )
        else:
            lines.append("No commit message, author or committer carries an AI label.")
        lines.append("")
        mentions = result.informational.get("ai-tool-name-mention-in-message", 0)
        lines.append(
            f"Informational: {mentions} commit message(s) mention an AI tool or MCP client name "
            "(for example Claude Desktop, Cursor) without being a label. Not listed."
        )
        lines.append("")
        lines.append("### Tree label mentions (informational, counts only)")
        lines.append("")
        if result.tree_labels:
            lines += _table(
                ["Top-level entry", "Files", "Matching lines"],
                [[g, str(v[0]), str(v[1])] for g, v in sorted(result.tree_labels.items())],
            )
            lines.append("")
            lines.append(
                "Matches are words such as Claude, Cursor or Codex in tracked files. Planning "
                "notes and MCP client documentation (Claude Desktop, Cursor) mention them "
                "legitimately; the table only shows where."
            )
        else:
            lines.append("No tracked file mentions an AI tool label.")
        lines.append("")
        lines.append("### Author identity inventory")
        lines.append("")
        by_name: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for (name, email), count in result.authors.items():
            by_name[name].append((mask_email(email), count))
        lines += _table(
            ["Author name", "Commits", "Email(s) (masked)"],
            [
                [
                    name,
                    str(sum(c for _, c in entries)),
                    ", ".join(sorted({e for e, _ in entries})),
                ]
                for name, entries in sorted(
                    by_name.items(), key=lambda kv: -sum(c for _, c in kv[1])
                )
            ],
        )
        lines.append("")
        declared = _pyproject_email(repo)
        if declared and all(e != declared for (_, e) in result.authors):
            lines.append(
                f"Note (informational): the pyproject.toml author email ({mask_email(declared)}) "
                "does not appear as a commit author email in history; commits use a different "
                "address."
            )
            lines.append("")
        lines.append("History was NOT rewritten by this scanner.")
        lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--repo", default=".", help="repository to scan (default: .)")
    parser.add_argument("--mode", choices=("secrets", "labels", "all"), default="all")
    parser.add_argument("--report", help="write a markdown report (no matched values) to PATH")
    parser.add_argument(
        "--allowlist",
        help="file with one entry per line: a placeholder substring, sha256:<digest prefix> of "
        "an accepted value, or <rule-id>:<path> to accept one rule in one file; # starts a "
        "comment",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    repo = str(Path(args.repo).resolve())
    allow = Allowlist.from_file(args.allowlist)
    result = Result()
    if args.mode in {"secrets", "all"}:
        scan_history(repo, allow, result)
        scan_worktree(repo, allow, result)
    if args.mode in {"labels", "all"}:
        scan_commit_labels(repo, result)
        scan_tree_labels(repo, result)
    for finding in result.findings:
        print(finding.row())
    info = ", ".join(f"{k}={v}" for k, v in sorted(result.informational.items())) or "none"
    tree_files = sum(v[0] for v in result.tree_labels.values())
    print(
        f"# commits={result.commits_scanned} worktree_files={result.files_scanned} "
        f"findings={len(result.findings)}"
    )
    print(f"# informational: {info}; tree-label-files={tree_files}")
    if args.report:
        parts = ["uv", "run", "python", "scripts/scan_history.py", "--mode", args.mode]
        if args.allowlist:
            parts += ["--allowlist", str(args.allowlist)]
        parts += ["--report", "<path>"]
        command = " ".join(parts)
        Path(args.report).write_text(
            render_report(result, args.mode, repo, command), encoding="utf-8"
        )
    return 1 if result.findings else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except GitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
