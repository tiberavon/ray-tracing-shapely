"""
Python-specific module: test flow executors
Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

===============================================================================
A flow's long step: a job, an executor, a handle, and the run's fixed ends
===============================================================================
A job ends done, failed, cancelled or timed out, and its executor says which,
also when the worker dies without saying so. A handle written to the run
record is followed by an executor made from the handle alone. A flow whose
long box submits a job ends in `done` with the job's result, or in one of the
three failure states with the reason recorded; a run's record and reality
are reconciled by the run list. Nothing here looks at the process list.
===============================================================================
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

pytest.importorskip("transitions")

from ray_tracing_shapely.flows import (Handle, InProcessExecutor, Job, LocalProcessExecutor,  # noqa: E402
                                       ObservableFlow, estimate_s, executor_for, format_duration,
                                       list_runs, over_budget_question, persistence)
from ray_tracing_shapely.flows import agentic as flow_tools  # noqa: E402
from ray_tracing_shapely.flows.flow_base import FAILURE_STATES  # noqa: E402

JOBS = "ray_tracing_shapely.developer_tests._flow_jobs"


def _wait_ended(ex, handle, timeout=30.0):
    deadline = time.time() + timeout
    st = ex.status(handle)
    while not st.ended and time.time() < deadline:
        time.sleep(0.05)
        st = ex.status(handle)
    return st


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def test_in_process_ends_and_a_foreign_handle_is_unknown():
    ex = InProcessExecutor()
    ok = ex.submit(Job(f"{JOBS}:count", {"n": 3}))
    assert ex.status(ok).state == "done" and ex.result(ok)["counted"] == 3
    assert ex.status(ok).progress["done"] == 3
    bad = ex.submit(Job(f"{JOBS}:boom", {"why": "on purpose"}))
    st = ex.status(bad)
    assert st.state == "failed" and "ValueError: on purpose" in st.error
    with pytest.raises(RuntimeError, match="no result"):
        ex.result(bad)
    other = Handle("in_process", ok.job_id, {"pid": ok.where["pid"] + 1})
    assert ex.status(other).state == "unknown"
    misnamed = ex.status(ex.submit(Job("no_colon")))
    assert misnamed.state == "failed" and "package.module:function" in misnamed.error


def test_local_process_runs_at_low_priority_and_is_followed_from_its_handle(tmp_path):
    ex = LocalProcessExecutor(tmp_path / "jobs")
    h = ex.submit(Job(f"{JOBS}:count", {"n": 5, "step_s": 0.02}, label="count"))
    assert _wait_ended(ex, h).state == "done"
    out = ex.result(h)
    assert out["counted"] == 5
    if hasattr(os, "nice"):
        assert out["nice"] >= 10
    # a fresh executor, made from the handle as read back from a record, knows nothing else
    again = executor_for(Handle.from_dict(json.loads(json.dumps(h.to_dict()))))
    assert again is not ex and again.status(h).state == "done" and again.result(h) == out
    st = again.status(h)
    assert st.progress["done"] == 5 and st.finished_at >= st.started_at


def test_local_process_given_a_relative_root(tmp_path, monkeypatch):
    # the worker runs from its own job folder, where a relative root does not resolve
    monkeypatch.chdir(tmp_path)
    ex = LocalProcessExecutor("jobs")
    h = ex.submit(Job(f"{JOBS}:count", {"n": 2}))
    assert _wait_ended(ex, h).state == "done" and ex.result(h)["counted"] == 2
    assert flow_tools.set_runs_root("runs") == tmp_path / "runs"
    flow_tools.set_runs_root(None)


def test_local_process_failure_and_a_worker_that_dies(tmp_path):
    ex = LocalProcessExecutor(tmp_path)
    h = ex.submit(Job(f"{JOBS}:boom"))
    st = _wait_ended(ex, h)
    assert st.state == "failed" and "ValueError: boom" in st.error and "ValueError" in ex.logs(h)
    gone = ex.submit(Job(f"{JOBS}:vanish"))
    st = _wait_ended(ex, gone)
    assert st.state == "failed" and "without recording an end" in st.error


def test_cancel_cooperative_and_not(tmp_path):
    ex = LocalProcessExecutor(tmp_path, grace_s=1.0)
    h = ex.submit(Job(f"{JOBS}:count", {"n": 10_000, "step_s": 0.01}))
    while ex.status(h).state != "running":
        time.sleep(0.02)
    assert ex.cancel(h).state == "cancelled"
    deaf = ex.submit(Job(f"{JOBS}:deaf", {"s": 60}))
    while ex.status(deaf).state != "running":
        time.sleep(0.02)
    t0 = time.time()
    assert ex.cancel(deaf).state == "cancelled"
    assert time.time() - t0 < 10.0 and not ex._alive(deaf)


def test_a_hard_limit_times_out(tmp_path):
    ex = LocalProcessExecutor(tmp_path, grace_s=1.0)
    h = ex.submit(Job(f"{JOBS}:count", {"n": 10_000, "step_s": 0.01}, limit_s=0.5))
    st = _wait_ended(ex, h)
    assert st.state == "timed_out" and "limit" in st.error


def test_budgets():
    assert estimate_s("simulate_2d_ray", 50_000) == pytest.approx(1000.0)
    assert format_duration(1000.0) == "about 17 minutes" and format_duration(30) == "about 30 seconds"
    q = over_budget_question("simulate_2d_ray", 50_000)
    assert "about 17 minutes" in q and "3,000 rays instead" in q
    assert over_budget_question("simulate_2d_ray", 1_000) is None
    assert estimate_s("simulate_2d_ray", 10, rates={"simulate_2d_ray": 1.0}) == 10.0
    with pytest.raises(ValueError, match="no rate"):
        estimate_s("anneal", 1)


# ---------------------------------------------------------------------------
# A flow with a long box
# ---------------------------------------------------------------------------

class TraceFlow(ObservableFlow):
    """start -> tracing (a job) -> done."""

    def __init__(self, base_dir, executor, job, **kw):
        self.executor, self.job_spec, self.kw = executor, job, kw
        super().__init__("trace", ["start", "tracing", "done"], [
            {"trigger": "begin", "source": "start", "dest": "tracing"},
            {"trigger": "traced", "source": "tracing", "dest": "done"},
            {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
        ], "start", base_dir, render_svg=False)

    def on_enter_tracing(self, *_a, **_k):
        self.submit_step(self.executor, self.job_spec, on_done="traced", **self.kw)

    def on_enter_done(self, result, *_a, **_k):
        self.finish(result)


def test_a_long_box_ends_done_with_its_result(tmp_path):
    flow = TraceFlow(tmp_path, InProcessExecutor(), Job(f"{JOBS}:count", {"n": 4}, budget_s=10.0))
    assert set(FAILURE_STATES) <= set(flow.machine.states) and flow.terminal_states[0] == "done"
    flow.begin()
    assert flow.state == "done" and flow.job is None
    assert persistence.read_result(tmp_path, flow.run_id)["result"]["counted"] == 4
    assert persistence.read_heartbeats(tmp_path)[flow.run_id]["terminal"] is True

    local = TraceFlow(tmp_path, LocalProcessExecutor(tmp_path / "jobs"),
                      Job(f"{JOBS}:count", {"n": 20, "step_s": 0.02}, budget_s=30.0, label="count"))
    local.begin()
    assert local.state == "tracing" and local.job["state"] in ("queued", "running")
    hb = persistence.read_heartbeats(tmp_path)[local.run_id]
    assert hb["detail"]["job"]["handle"]["executor"] == "local_process" and hb["terminal"] is False
    out = local.wait(30.0, poll_s=0.05)
    assert out == {**out, "state": "done", "waiting": False, "finished": True}
    events = [e["message"] for e in persistence.read_events(tmp_path, local.run_id)]
    assert events[0].startswith("submitted count") and "done in" in events[-1]
    assert local.run_id != flow.run_id            # two runs of one flow in the same second


def test_run_ids_do_not_repeat():
    ids = [persistence.make_run_id("trace") for _ in range(1000)]
    assert len(set(ids)) == 1000 and ids == sorted(ids, key=lambda r: int(r.rsplit("-", 1)[1]))


def test_failure_cancel_and_reset(tmp_path):
    bad = TraceFlow(tmp_path, InProcessExecutor(), Job(f"{JOBS}:boom", {"why": "bad lens"}))
    bad.begin()
    assert bad.state == "failed" and bad.is_finished
    res = persistence.read_result(tmp_path, bad.run_id)
    assert res["status"] == "failed" and res["from_state"] == "tracing" and "bad lens" in res["reason"]
    last = persistence.read_events(tmp_path, bad.run_id)[-1]
    assert last["state"] == "failed" and "Traceback" in last["traceback"]
    assert persistence.read_manifest(tmp_path)[-1]["result"] == "failed"
    bad.job_spec = Job(f"{JOBS}:count", {"n": 1})
    bad.reset()
    bad.begin()
    assert bad.state == "done" and bad.attempt == 2

    slow = TraceFlow(tmp_path, LocalProcessExecutor(tmp_path / "jobs", grace_s=1.0),
                     Job(f"{JOBS}:count", {"n": 10_000, "step_s": 0.01}))
    slow.begin()
    handle = Handle.from_dict(slow.job["handle"])
    assert slow.cancel("enough") == "cancelled"
    assert executor_for(handle).status(handle).state == "cancelled"
    assert persistence.read_result(tmp_path, slow.run_id)["reason"] == "enough"
    assert slow.cancel() == "cancelled"          # a finished run is left as it is

    again = TraceFlow(tmp_path, LocalProcessExecutor(tmp_path / "jobs", grace_s=1.0),
                      Job(f"{JOBS}:count", {"n": 10_000, "step_s": 0.01}))
    again.begin()
    handle = Handle.from_dict(again.job["handle"])
    again.reset()                                 # an abandoned attempt's job is stopped
    assert executor_for(handle).status(handle).state == "cancelled" and again.state == "start"


class GroupFlow(ObservableFlow):
    """start -> tracing (several jobs, one step) -> done."""

    def __init__(self, base_dir, executor, jobs):
        self.executor, self.jobs = executor, jobs
        super().__init__("group", ["start", "tracing", "done"], [
            {"trigger": "begin", "source": "start", "dest": "tracing"},
            {"trigger": "traced", "source": "tracing", "dest": "done"},
            {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
        ], "start", base_dir, render_svg=False)

    def on_enter_tracing(self, *_a, **_k):
        self.submit_group(self.executor, self.jobs, on_done="traced", label="counts")

    def on_enter_done(self, results, *_a, **_k):
        self.finish({"counted": [r["counted"] for r in results]})


def test_a_group_of_jobs_is_one_step(tmp_path):
    jobs = [Job(f"{JOBS}:count", {"n": n, "step_s": 0.02}, budget_s=30.0) for n in (5, 3, 8)]
    flow = GroupFlow(tmp_path, LocalProcessExecutor(tmp_path / "jobs"), jobs)
    flow.begin()
    assert flow.state == "tracing" and len(flow.job["group"]) == 3
    assert flow.job["progress"]["total"] == 3 and flow.job["handle"] == flow.job["group"][0]
    hb = persistence.read_heartbeats(tmp_path)[flow.run_id]
    assert hb["detail"]["job"]["handle"]["executor"] == "local_process"      # read as any job's record
    out = flow.wait(30.0, poll_s=0.05)
    assert out["state"] == "done" and flow.job is None
    assert persistence.read_result(tmp_path, flow.run_id)["result"]["counted"] == [5, 3, 8]   # in the jobs' order
    assert "3 jobs done" in persistence.read_events(tmp_path, flow.run_id)[-1]["message"]


def test_a_group_fails_with_its_first_failure_and_cancels_the_rest(tmp_path):
    ex = LocalProcessExecutor(tmp_path / "jobs", grace_s=1.0)
    jobs = [Job(f"{JOBS}:count", {"n": 10_000, "step_s": 0.01}), Job(f"{JOBS}:boom", {"why": "bad chunk"})]
    flow = GroupFlow(tmp_path, ex, jobs)
    flow.begin()
    handles = [Handle.from_dict(h) for h in flow.job["group"]]
    out = flow.wait(30.0, poll_s=0.05)
    assert out["state"] == "failed" and "job 2 of 2" in flow.explain_current_state()
    assert "bad chunk" in persistence.read_result(tmp_path, flow.run_id)["reason"]
    assert ex.status(handles[0]).state == "cancelled"

    slow = GroupFlow(tmp_path, ex, [Job(f"{JOBS}:count", {"n": 10_000, "step_s": 0.01}) for _ in range(2)])
    slow.begin()
    handles = [Handle.from_dict(h) for h in slow.job["group"]]
    assert slow.cancel("enough") == "cancelled"
    assert [ex.status(h).state for h in handles] == ["cancelled", "cancelled"]


def test_an_estimate_over_the_limit_is_asked_first(tmp_path):
    job = Job(f"{JOBS}:count", {"n": 2}, budget_s=estimate_s("simulate_2d_ray", 50_000), label="2D trace")
    flow = TraceFlow(tmp_path, InProcessExecutor(), job)
    flow.begin()
    assert flow.state == "tracing" and flow.job is None
    assert "about 17 minutes" in flow.explain_current_state()
    assert flow.submit_step(flow.executor, job, on_done="traced", confirmed=True) is not None
    assert flow.state == "done"


def test_over_budget_is_flagged_and_the_run_goes_on(tmp_path):
    flow = TraceFlow(tmp_path, LocalProcessExecutor(tmp_path / "jobs"),
                     Job(f"{JOBS}:count", {"n": 100, "step_s": 0.02}, budget_s=0.1))
    flow.begin()
    deadline = time.time() + 30.0
    while time.time() < deadline and flow.poll() == "tracing" and flow.job["state"] != "running":   # the worker starts
        time.sleep(0.02)
    time.sleep(0.05)
    flow.poll()
    assert flow.job["over_budget"] and flow.state == "tracing" and flow.job["state"] == "running"
    assert any(r["flags"] == ["hung"] for r in list_runs([tmp_path]) if r["run_id"] == flow.run_id)
    assert flow.wait(30.0, poll_s=0.05)["state"] == "done"
    assert any(e["message"].startswith("over budget") for e in persistence.read_events(tmp_path, flow.run_id))


# ---------------------------------------------------------------------------
# The run list: record against reality
# ---------------------------------------------------------------------------

def _dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_the_run_list_flags_what_the_record_gets_wrong(tmp_path):
    done = TraceFlow(tmp_path, InProcessExecutor(), Job(f"{JOBS}:count", {"n": 1}))
    done.begin()
    waiting = TraceFlow(tmp_path, LocalProcessExecutor(tmp_path / "jobs"), Job(f"{JOBS}:count", {"n": 1}))
    waiting.begin()
    h = Handle.from_dict(waiting.job["handle"])
    _wait_ended(executor_for(h), h)               # it ended; nobody has polled the run

    # a run whose process died mid-step, and one whose record was started and never finished
    dead = _dead_pid()
    persistence.append_manifest(tmp_path, "trace-crashed", standard="trace", started_at=time.time())
    persistence.update_heartbeat(tmp_path, "trace-crashed", fsm_name="trace", state="tracing", terminal=False)
    hb = persistence.read_heartbeats(tmp_path)
    hb["trace-crashed"]["pid"] = dead
    (tmp_path / "heartbeats.json").write_text(json.dumps(hb))

    rows = {r["run_id"]: r for r in list_runs([tmp_path])}
    assert rows[done.run_id]["flags"] == [] and rows[done.run_id]["finished"]
    assert rows[waiting.run_id]["flags"] == ["uncollected"] and rows[waiting.run_id]["job"]["state"] == "done"
    assert rows["trace-crashed"]["flags"] == ["crashed", "never_finished"]
    waiting.poll()
    assert {r["run_id"]: r for r in list_runs([tmp_path])}[waiting.run_id]["flags"] == []


def test_the_three_tools(tmp_path):
    flow = TraceFlow(tmp_path, LocalProcessExecutor(tmp_path / "jobs", grace_s=1.0),
                     Job(f"{JOBS}:count", {"n": 10_000, "step_s": 0.01}))
    flow.begin()
    out = flow_tools.flow_wait(flow.run_id, timeout_s=0.2)
    assert out["status"] == "ok" and out["data"]["waiting"] and out["data"]["state"] == "tracing"
    listed = flow_tools.flow_list(str(tmp_path))
    assert listed["status"] == "ok" and listed["data"]["runs"][0]["run_id"] == flow.run_id
    assert flow_tools.flow_cancel(flow.run_id)["data"]["state"] == "cancelled"
    assert flow_tools.flow_wait("nope")["status"] == "error"
    assert "nope" in flow_tools.flow_cancel("nope")["message"]
    json.dumps(listed)


def test_register_adds_the_three_tools_once(monkeypatch):
    from ray_tracing_shapely.analysis import tool_registry
    # the lists are process-wide: restore them afterwards, as test_tool_lists does
    monkeypatch.setattr(tool_registry, '_REGISTRY', list(tool_registry._REGISTRY))
    monkeypatch.setattr(tool_registry, '_EXTERNAL_TOOLS', [])
    monkeypatch.delitem(sys.modules, 'ray_tracing_shapely.analysis.mcp_server', raising=False)
    names = {fn.__name__ for fn, _, _ in flow_tools.TOOLS}
    before = {t["name"] for t in tool_registry.get_agentic_tools()}
    added = flow_tools.register()
    after = {t["name"] for t in tool_registry.get_agentic_tools()}
    assert names <= after and added == (not names <= before)
    assert flow_tools.register() is False
    assert names <= {fn.__name__ for fn in tool_registry.get_exposed_tools()}
    assert tool_registry.check_tool_lists() == []
