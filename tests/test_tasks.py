"""Task polling core: strict OK semantics, bounded waits, redaction, UPID safety."""
import json

import pytest

from proxmox_mcp.tools.pve_compat import describe_task_result
from proxmox_mcp.tools.tasks import (
    TaskTools,
    classify_task,
    fetch_task_outcome,
    poll_task,
    task_result_text,
)
from proxmox_mcp.utils.redaction import register_secret
from proxmox_mcp.validators import InputValidationError

UPID = "UPID:pve1:0000ABCD:00123456:65A1B2C3:qmstart:100:monitor@pve!mcp:"
UPID2 = "UPID:pve2:0000ABCD:00123456:65A1B2C3:qmstop:101:root@pam:"
STATUS = "nodes/*/tasks/*/status"
LOG = "nodes/*/tasks/*/log"


class Clock:
    """Fake monotonic clock; ``sleep`` advances it and records each delay."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.parametrize("status,expected", [
    ({"status": "stopped", "exitstatus": "OK"}, "ok"),
    ({"status": "stopped", "exitstatus": "WARNINGS: 2"}, "warnings"),
    ({"status": "stopped", "exitstatus": "command failed"}, "failed"),
    ({"status": "stopped", "exitstatus": ""}, "failed"),
    ({"status": "stopped", "exitstatus": None}, "failed"),
    ({"status": "stopped"}, "failed"),
    ({"status": "stopped", "exitstatus": "ok"}, "failed"),
    ({"status": "running"}, "running"),
    ({"status": "weird"}, "running"),
    ({}, "running"),
    (None, "running"),
])
def test_classify_task(status, expected):
    assert classify_task(status) == expected


@pytest.mark.parametrize("bad", ["", "UPID:", "../x", UPID + "/x", UPID[:-1], None, 5])
def test_invalid_upid_zero_calls(fake_pve, bad):
    with pytest.raises(InputValidationError):
        fetch_task_outcome(fake_pve, bad)
    with pytest.raises(InputValidationError):
        poll_task(fake_pve, bad, 5, sleep=lambda s: None)
    with pytest.raises(InputValidationError):
        task_result_text(fake_pve, UPID, True, 0)  # bad timeout is rejected as well
    assert fake_pve.calls == []


def test_bad_node_in_upid_zero_calls(fake_pve):
    with pytest.raises(InputValidationError):
        fetch_task_outcome(fake_pve, "UPID:..:0000ABCD:00123456:65A1B2C3:qmstart:100:root@pam:")
    assert fake_pve.calls == []


def test_node_comes_from_upid_not_config(fake_pve):
    outcome = fetch_task_outcome(fake_pve, UPID2)
    assert outcome.node == "pve2" and outcome.success
    assert [c.path for c in fake_pve.calls] == [f"nodes/pve2/tasks/{UPID2}/status"]


def test_ok_reads_status_once_and_no_log(fake_pve):
    outcome = fetch_task_outcome(fake_pve, UPID)
    assert outcome.state == "ok" and outcome.log_tail == []
    assert len(fake_pve.calls) == 1


def test_failed_reads_log_with_limit_and_tail(fake_pve):
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "boom"})
    fake_pve.set("GET", LOG, [{"n": i, "t": f"line {i}"} for i in range(1, 31)])
    outcome = fetch_task_outcome(fake_pve, UPID)
    assert outcome.state == "failed" and not outcome.success
    assert outcome.log_tail == [f"line {i}" for i in range(21, 31)]
    log_call = fake_pve.calls[-1]
    assert log_call.path == f"nodes/pve1/tasks/{UPID}/log" and log_call.params == {"limit": 200}


def test_log_failure_is_swallowed_and_long_lines_cut(fake_pve):
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "boom"})
    fake_pve.fail("GET", LOG, RuntimeError("log gone"))
    assert fetch_task_outcome(fake_pve, UPID).log_tail == []
    fake_pve._errors.clear()
    fake_pve.set("GET", LOG, [{"n": 1, "t": "x" * 1000}, {"n": 2}, "junk"])
    assert fetch_task_outcome(fake_pve, UPID).log_tail == ["x" * 300]


def test_non_dict_status_response(fake_pve):
    fake_pve.set("GET", STATUS, None)
    with pytest.raises(RuntimeError, match="unexpected task status response"):
        fetch_task_outcome(fake_pve, UPID)


def test_poll_running_then_stopped(fake_pve):
    seq = iter([{"status": "running"}, {"status": "running"},
                {"status": "stopped", "exitstatus": "OK"}])
    fake_pve.set("GET", STATUS, lambda p, s: next(seq))
    clock = Clock()
    outcome = poll_task(fake_pve, UPID, 30, sleep=clock.sleep, clock=clock)
    assert outcome.success and not outcome.timed_out
    assert clock.sleeps == [1.0, 2.0]


def test_poll_timeout_returns_running_and_is_bounded(fake_pve):
    fake_pve.set("GET", STATUS, {"status": "running"})
    clock = Clock()
    outcome = poll_task(fake_pve, UPID, 12, sleep=clock.sleep, clock=clock)
    assert outcome.state == "running" and outcome.timed_out and not outcome.success
    assert clock.sleeps == [1.0, 2.0, 3.0, 5.0, 1.0]  # last sleep capped to the remaining time
    assert clock.now == 12 and len(fake_pve.calls) == 6


def test_poll_backoff_caps_at_five(fake_pve):
    fake_pve.set("GET", STATUS, {"status": "running"})
    clock = Clock()
    poll_task(fake_pve, UPID, 300, sleep=clock.sleep, clock=clock)
    assert clock.sleeps[:6] == [1.0, 2.0, 3.0, 5.0, 5.0, 5.0]
    assert max(clock.sleeps) == 5.0 and sum(clock.sleeps) == 300


def test_warnings_state_and_text(fake_pve):
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "WARNINGS: 2"})
    outcome = fetch_task_outcome(fake_pve, UPID)
    assert outcome.state == "warnings" and not outcome.success
    text = task_result_text(fake_pve, UPID, True, 5, sleep=lambda s: None)
    assert "finished with warnings" in text and "not counted as success" in text
    assert "Task finished: OK" not in text


def test_failed_secret_is_redacted_everywhere(fake_pve):
    secret = "s3cr3t-sentinel-value"
    register_secret(secret)
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": f"failed {secret}"})
    fake_pve.set("GET", LOG, [{"n": 1, "t": f"token={secret}"}])
    outcome = fetch_task_outcome(fake_pve, UPID)
    assert secret not in repr(outcome)
    with pytest.raises(RuntimeError) as exc:
        task_result_text(fake_pve, UPID, True, 5, sleep=lambda s: None)
    msg = str(exc.value)
    assert secret not in msg and "[REDACTED]" in msg and UPID in msg and "failed" in msg


def test_task_result_text_combinations(fake_pve):
    for result in (UPID, None, "", {"a": 1}):
        assert task_result_text(fake_pve, result, False, 30) == describe_task_result(result)
    assert fake_pve.calls == []
    for result in (None, ""):
        text = task_result_text(fake_pve, result, True, 30)
        assert text == describe_task_result(result) + "\nWait skipped: no task id was returned"
    assert fake_pve.calls == []
    assert task_result_text(fake_pve, UPID, True, 30, sleep=lambda s: None) == (
        describe_task_result(UPID) + "\nTask finished: OK"
    )


def test_task_result_text_timeout_and_failure(fake_pve):
    fake_pve.set("GET", STATUS, {"status": "running"})
    clock = Clock()
    text = task_result_text(fake_pve, UPID, True, 3, sleep=clock.sleep, clock=clock)
    assert text.startswith(describe_task_result(UPID))
    assert "Task still running after 3s" in text and "get_task_status" in text
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "command failed"})
    with pytest.raises(RuntimeError) as exc:
        task_result_text(fake_pve, UPID, True, 3, sleep=clock.sleep, clock=clock)
    assert UPID in str(exc.value) and "command failed" in str(exc.value)
    assert "TASK OK" in str(exc.value)  # fixture log tail is included


def _payload(content):
    assert len(content) == 1
    return json.loads(content[0].text)


def test_get_task_status_payload(fake_pve):
    data = _payload(TaskTools(fake_pve).get_task_status(UPID))
    assert data["upid"] == UPID and data["node"] == "pve1"
    assert (data["type"], data["id"], data["user"]) == ("qmstart", "100", "monitor@pve!mcp")
    assert data["state"] == "ok" and data["success"] is True and data["exitstatus"] == "OK"
    assert data["status"] == "stopped" and data["log_tail"] == []
    assert data["starttime"] == 0x65A1B2C3
    assert data["starttime_utc"] == "2024-01-12T21:44:35Z"


def test_get_task_status_failed_not_success(fake_pve):
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "oops"})
    data = _payload(TaskTools(fake_pve).get_task_status(UPID))
    assert data["state"] == "failed" and data["success"] is False and data["log_tail"]


def test_get_task_status_bad_upid_zero_calls(fake_pve):
    with pytest.raises(ValueError):
        TaskTools(fake_pve).get_task_status("../etc")
    assert fake_pve.calls == []


def test_wait_for_task_ok_and_timeout(fake_pve):
    tools = TaskTools(fake_pve)
    data = _payload(tools.wait_for_task(UPID, 5))
    assert data["success"] is True and data["timed_out"] is False
    fake_pve.set("GET", STATUS, {"status": "running"})
    clock = Clock()
    tools._sleep, tools._clock = clock.sleep, clock
    data = _payload(tools.wait_for_task(UPID, 4))
    assert data["state"] == "running" and data["timed_out"] is True
    assert data["success"] is False and "still running" in data["message"]
    assert sum(clock.sleeps) == 4


@pytest.mark.parametrize("timeout", [0, 301, -1, True, "5", 1.5])
def test_wait_for_task_bad_timeout_zero_calls(fake_pve, timeout):
    with pytest.raises(ValueError):
        TaskTools(fake_pve).wait_for_task(UPID, timeout)
    assert fake_pve.calls == []


# -- MCP level (registered tools through the full app, policy wrap included) ------------------

from fastmcp.exceptions import ToolError, ValidationError  # noqa: E402


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_task_tools_listed_and_work_on_both_transports(policy_app, fake_pve, transport):
    app = policy_app(transport, read_only=True)  # read risk: allowed even when read-only
    tools = {t.name: t for t in await app.mcp.list_tools()}
    assert {"get_task_status", "wait_for_task"} <= set(tools)
    props = tools["wait_for_task"].parameters["properties"]
    assert props["timeout"]["minimum"] == 1 and props["timeout"]["maximum"] == 300
    assert props["timeout"]["default"] == 30
    result = await app.mcp.call_tool("get_task_status", {"upid": UPID})
    assert json.loads(result.content[0].text)["success"] is True
    result = await app.mcp.call_tool("wait_for_task", {"upid": UPID, "timeout": 5})
    assert json.loads(result.content[0].text)["state"] == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [
    {"upid": "../x"}, {"upid": UPID + "/y"}, {"upid": UPID, "timeout": 0},
    {"upid": UPID, "timeout": 301}, {"upid": UPID, "timeout": -1},
])
async def test_task_tools_reject_bad_input_with_zero_calls(policy_app, fake_pve, args):
    app = policy_app()
    for name in ("get_task_status", "wait_for_task"):
        if name == "get_task_status" and "timeout" in args:
            continue
        with pytest.raises((ToolError, ValidationError)):
            await app.mcp.call_tool(name, args)
    assert fake_pve.calls == []


@pytest.mark.asyncio
async def test_wait_for_task_running_timeout_via_mcp(policy_app, fake_pve):
    app = policy_app()
    clock = Clock()
    app.task_tools._sleep, app.task_tools._clock = clock.sleep, clock
    fake_pve.set("GET", STATUS, {"status": "running"})
    result = await app.mcp.call_tool("wait_for_task", {"upid": UPID, "timeout": 7})
    data = json.loads(result.content[0].text)
    assert data["state"] == "running" and data["timed_out"] is True
    assert "still running" in data["message"] and sum(clock.sleeps) == 7


_PATH_UNSAFE = [
    UPID.replace("monitor@pve!mcp", "root@pam?x=1"),
    UPID.replace("monitor@pve!mcp", "root@pam#frag"),
    UPID.replace("monitor@pve!mcp", "a%2F..%2Fb#"),
    UPID.replace("monitor@pve!mcp", ".."),
]


@pytest.mark.parametrize("bad", _PATH_UNSAFE)
def test_path_unsafe_upid_never_reaches_api_path(fake_pve, bad):
    from proxmox_mcp.tools.pve_compat import is_upid, wait_task_stopped

    assert is_upid(bad) is False
    with pytest.raises(InputValidationError):
        fetch_task_outcome(fake_pve, bad)
    with pytest.raises(InputValidationError):
        poll_task(fake_pve, bad, 5, sleep=lambda s: None)
    with pytest.raises(ValueError):
        wait_task_stopped(fake_pve, "pve1", bad)
    assert fake_pve.calls == []


def test_poll_error_after_mutation_keeps_upid(fake_pve):
    def boom(*a, **k):
        raise TimeoutError("read timed out token=abc")

    fake_pve.set("GET", STATUS, boom)
    text = task_result_text(fake_pve, UPID, True, 5, sleep=lambda s: None)
    assert text.startswith(describe_task_result(UPID)) and UPID in text
    assert "Wait failed" in text and "get_task_status" in text


def test_concurrent_wait_cap_fails_fast_and_releases(fake_pve):
    from proxmox_mcp.tools import tasks as t

    fake_pve.set("GET", STATUS, {"status": "running"})
    held = [t._WAIT_SLOTS.acquire(blocking=False) for _ in range(t.MAX_CONCURRENT_WAITS)]
    try:
        assert all(held)
        with pytest.raises(t.TooManyWaitsError):
            poll_task(fake_pve, UPID, 5, sleep=lambda s: None)
        assert fake_pve.calls == []
        # task_result_text keeps the UPID instead of failing the whole call
        text = task_result_text(fake_pve, UPID, True, 5, sleep=lambda s: None)
        assert UPID in text and "too many concurrent waits" in text
    finally:
        for _ in range(sum(held)):
            t._WAIT_SLOTS.release()
    fake_pve.set("GET", STATUS, {"status": "stopped", "exitstatus": "OK"})
    assert poll_task(fake_pve, UPID, 5, sleep=lambda s: None).success
    # a failing poll must still release its slot
    for _ in range(t.MAX_CONCURRENT_WAITS + 2):
        poll_task(fake_pve, UPID, 5, sleep=lambda s: None)
