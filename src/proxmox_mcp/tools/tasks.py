"""Asynchronous Proxmox task tracking (UPID status, bounded waiting).

Success semantics are strict: a task succeeded ONLY when ``status == "stopped"`` and
``exitstatus == "OK"``. ``WARNINGS...`` is its own state and is never counted as success,
any other (or missing) exitstatus on a stopped task is a failure (fail closed), and any
other status value means the task is still running.

The node used in every API path is the node encoded in the UPID itself (second field),
never the configured one, and the UPID is validated before the first API call.

``poll_task`` differs deliberately from ``pve_compat.wait_task_stopped``: that helper keeps
raise-on-timeout semantics for the force-delete path, whereas ``poll_task`` is bounded by a
monotonic deadline and returns a ``running`` outcome (``timed_out=True``) instead of raising.

Task log lines and exitstatus text are untrusted external data: they are redacted and
truncated before being returned, and are never interpolated into logger calls.
"""

import json
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from mcp.types import TextContent as Content

from ..utils.redaction import redact
from ..validators import InputValidationError, upid_node, validate_wait_timeout
from .base import ProxmoxTool
from .pve_compat import TaskFailedError, describe_task_result, is_upid

# Global cap on concurrent blocking waits. Each wait holds one worker thread for up to 300 s
# (time.sleep); without a bound, ~40 waits would exhaust the threadpool and stall every other
# sync tool. When the cap is reached a wait fails fast instead of queueing.
MAX_CONCURRENT_WAITS = 8
_WAIT_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_WAITS)

LOG_LIMIT = 200
LOG_MAX_PAGES = 50  # at most 10000 log lines are read per failed task
LOG_TAIL_LINES = 10
LOG_LINE_MAX = 300
_STATUS_KEYS = ("status", "exitstatus", "starttime", "type", "id", "user", "node")


class TooManyWaitsError(ValueError):
    """The global concurrent-wait cap (MAX_CONCURRENT_WAITS) is exhausted."""


@dataclass(frozen=True)
class TaskOutcome:
    """Result of one task status read (``exitstatus`` and ``log_tail`` are redacted)."""

    upid: str
    node: str
    state: str  # "ok" | "warnings" | "failed" | "running"
    exitstatus: str | None = None
    status: dict[str, Any] = field(default_factory=dict)
    log_tail: list[str] = field(default_factory=list)
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.state == "ok"


def _clip(text: Any, limit: int = LOG_LINE_MAX) -> str:
    return redact(str(text))[:limit]


def classify_task(status: Any) -> str:
    """Map a task status dict to ``ok`` / ``warnings`` / ``failed`` / ``running``."""
    if not isinstance(status, dict) or status.get("status") != "stopped":
        return "running"
    exitstatus = status.get("exitstatus")
    if exitstatus == "OK":
        return "ok"
    if isinstance(exitstatus, str) and exitstatus.startswith("WARNINGS"):
        return "warnings"
    return "failed"


def _log_tail(api: Any, node: str, upid: str) -> list[str]:
    """Last lines of the task log; best effort (any error yields an empty tail).

    The log API returns pages from ``start`` (at most ``LOG_LIMIT`` lines), so the log is
    read page by page and only the final ``LOG_TAIL_LINES`` lines are kept. Reading stops at
    the first short or empty page, or after ``LOG_MAX_PAGES`` pages; in the latter case the
    tail is marked as not being the true end of the log.
    """
    tail: deque[str] = deque(maxlen=LOG_TAIL_LINES)
    start = 0
    capped = False
    try:
        for page_no in range(LOG_MAX_PAGES):
            entries = api.nodes(node).tasks(upid).log.get(start=start, limit=LOG_LIMIT)
            if not isinstance(entries, list) or not entries:
                break
            tail.extend(
                e["t"] for e in entries if isinstance(e, dict) and isinstance(e.get("t"), str)
            )
            start += len(entries)
            if len(entries) < LOG_LIMIT:
                break
            capped = page_no == LOG_MAX_PAGES - 1
    except Exception:
        return []
    lines = [_clip(line) for line in tail]
    if capped and lines:
        lines.insert(0, f"[log longer than {start} lines; showing lines before that point]")
    return lines


def fetch_task_outcome(api: Any, upid: str) -> TaskOutcome:
    """Read the task status once (plus its log tail when it failed or has warnings)."""
    node = upid_node(upid)  # validates the UPID (single entry point) before any API call
    status = api.nodes(node).tasks(upid).status.get()
    if not isinstance(status, dict):
        raise RuntimeError("unexpected task status response")
    state = classify_task(status)
    subset: dict[str, Any] = {}
    for key in _STATUS_KEYS:
        if key in status:
            value = status[key]
            subset[key] = _clip(value) if isinstance(value, str) else value
    exitstatus = status.get("exitstatus")
    tail = _log_tail(api, node, upid) if state in ("failed", "warnings") else []
    return TaskOutcome(
        upid=upid,
        node=node,
        state=state,
        exitstatus=None if exitstatus is None else _clip(exitstatus),
        status=subset,
        log_tail=tail,
    )


def poll_task(
    api: Any,
    upid: str,
    timeout: int,
    interval: float = 1.0,
    max_interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> TaskOutcome:
    """Poll until the task is no longer running or the monotonic deadline passes.

    Sleeps 1, 2, 3, 5, 5, ... seconds (``interval`` multiples, capped at ``max_interval``)
    and never past the remaining time. At the deadline the last outcome is returned with
    ``timed_out=True`` (state ``running``); this function does not raise for a timeout.
    """
    validate_wait_timeout(timeout)
    upid_node(upid)
    if not _WAIT_SLOTS.acquire(blocking=False):
        raise TooManyWaitsError(
            f"too many concurrent waits (max {MAX_CONCURRENT_WAITS}); "
            f"task {upid} is unaffected, use get_task_status to check it"
        )
    try:
        return _poll_loop(api, upid, timeout, interval, max_interval, sleep, clock)
    finally:
        _WAIT_SLOTS.release()


def _poll_loop(
    api: Any,
    upid: str,
    timeout: int,
    interval: float,
    max_interval: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> TaskOutcome:
    deadline = clock() + timeout
    attempt = 0
    while True:
        outcome = fetch_task_outcome(api, upid)
        if outcome.state != "running":
            return outcome
        remaining = deadline - clock()
        if remaining <= 0:
            return TaskOutcome(
                upid=outcome.upid,
                node=outcome.node,
                state="running",
                exitstatus=outcome.exitstatus,
                status=outcome.status,
                log_tail=outcome.log_tail,
                timed_out=True,
            )
        attempt += 1
        delay = min(interval * attempt, max_interval) if attempt <= 3 else max_interval
        sleep(max(0.0, min(delay, remaining)))


def task_result_text(
    api: Any,
    result: Any,
    wait: bool,
    timeout: int,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """Text for an async PVE call result, optionally waiting for the task to finish.

    ``wait`` False returns exactly ``describe_task_result(result)``.
    """
    text = describe_task_result(result)
    if not wait:
        return text
    if not is_upid(result):
        return text + "\nWait skipped: no task id was returned"
    try:
        outcome = poll_task(api, result, timeout, sleep=sleep, clock=clock)
    except InputValidationError:
        raise
    except Exception as e:
        # The mutation already started this task: keep the UPID so the caller does not retry.
        return text + (
            f"\nWait failed ({_clip(e)}); the task may be running or finished, "
            "check it with get_task_status"
        )
    if outcome.timed_out:
        return text + (
            f"\nTask still running after {timeout}s (UPID above); "
            "check it with get_task_status or wait_for_task"
        )
    if outcome.state == "ok":
        return text + "\nTask finished: OK"
    if outcome.state == "warnings":
        return text + (
            f"\nTask finished with warnings (exitstatus: {outcome.exitstatus}); "
            "not counted as success"
        )
    detail = f"Task {outcome.upid} failed (exitstatus: {outcome.exitstatus})"
    if outcome.log_tail:
        detail += "\nLast log lines:\n" + "\n".join(outcome.log_tail)
    raise TaskFailedError(detail)


def _starttime(upid: str, status: dict[str, Any]) -> int | None:
    value = status.get("starttime")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(upid.split(":")[4], 16)
    except (IndexError, ValueError):
        return None


def _payload(outcome: TaskOutcome) -> dict[str, Any]:
    parts = outcome.upid.split(":")
    started = _starttime(outcome.upid, outcome.status)
    data: dict[str, Any] = {
        "upid": outcome.upid,
        "node": outcome.node,
        "type": parts[5],
        "id": parts[6],
        "user": parts[7],
        "starttime": started,
        "status": outcome.status.get("status", "running"),
        "state": outcome.state,
        "exitstatus": outcome.exitstatus,
        "success": outcome.success,
        "log_tail": outcome.log_tail,
    }
    if started is not None:
        data["starttime_utc"] = (
            datetime.fromtimestamp(started, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        )
    return data


class TaskTools(ProxmoxTool):
    """Read-only task tracking tools (``get_task_status``, ``wait_for_task``)."""

    def __init__(self, proxmox_api: Any):
        super().__init__(proxmox_api)
        self._sleep: Callable[[float], None] = time.sleep
        self._clock: Callable[[], float] = time.monotonic

    def get_task_status(self, upid: str) -> list[Content]:
        """Return the current status of a task; success only when exitstatus is OK."""
        node: str | None = None
        try:
            node = upid_node(upid)
            outcome = fetch_task_outcome(self.proxmox, upid)
            return [Content(type="text", text=json.dumps(_payload(outcome), indent=2))]
        except Exception as e:
            self._handle_error("get task status", e, "get_task_status", node=node)
            return []

    def wait_for_task(self, upid: str, timeout: int = 30) -> list[Content]:
        """Wait (bounded, 1..300 s) for a task; a timeout reports state running."""
        node: str | None = None
        try:
            node = upid_node(upid)
            validate_wait_timeout(timeout)
            outcome = poll_task(self.proxmox, upid, timeout, sleep=self._sleep, clock=self._clock)
            data = _payload(outcome)
            data["timed_out"] = outcome.timed_out
            if outcome.timed_out:
                data["message"] = f"still running after {timeout}s; call wait_for_task again"
            else:
                data["message"] = f"task finished: {outcome.state}"
            return [Content(type="text", text=json.dumps(data, indent=2))]
        except Exception as e:
            self._handle_error("wait for task", e, "wait_for_task", node=node)
            return []
