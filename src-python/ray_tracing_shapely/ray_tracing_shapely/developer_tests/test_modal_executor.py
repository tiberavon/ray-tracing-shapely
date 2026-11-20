"""
Python-specific module: test modal executor
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
The Modal executor, and the safeguards a remote job needs, without Modal
===============================================================================
A stand-in for the Modal client (`_fake_modal`) runs `remote_run` where the deployed function
would, or never starts the call (a container failing on import), or starts it
and never ends it. Checked:
- a job's result, progress and files come back; a failing procedure is the
  job's status, with its output;
- a handle is followed by a new executor, as after a restart;
- a job that never starts is cancelled at its start limit: the run ends
  failed, wait returns at once with the log, and the run list flags it
  not_started before anyone waits;
- a running job past its hard limit is cancelled and reported timed_out;
- wait returns early, once, when a job goes over its budget;
- many queued jobs of one function share its statistics: Modal is asked no more
  often than for one job (it rate-limits those calls).
===============================================================================
"""

from __future__ import annotations

import itertools
import json
import sys
import time
import types

import pytest

pytest.importorskip("transitions")

from ray_tracing_shapely.flows import Job, ObservableFlow, executor_for, list_runs, persistence  # noqa: E402
from ray_tracing_shapely.flows import modal_executor  # noqa: E402
from ray_tracing_shapely.flows.modal_executor import ModalExecutor, remote_run  # noqa: E402
from ray_tracing_shapely.developer_tests._fake_modal import FakeModal, reset  # noqa: E402

JOBS = "ray_tracing_shapely.developer_tests._flow_jobs"


# --- a stand-in for the Modal client ---------------------------------------------------

@pytest.fixture
def fake_modal(monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", FakeModal)
    reset()
    monkeypatch.setattr(modal_executor, "QUEUE_STATS_AFTER_S", 0.0)
    monkeypatch.setattr(ModalExecutor, "_modal_logs", lambda self, h: f"ImportError: no module named common ({self.app_name})")
    return FakeModal


class TraceFlow(ObservableFlow):
    def __init__(self, base_dir, executor, job):
        self.executor, self.job_spec = executor, job
        super().__init__("trace", ["start", "tracing", "done"], [
            {"trigger": "begin", "source": "start", "dest": "tracing"},
            {"trigger": "traced", "source": "tracing", "dest": "done"},
        ], "start", base_dir, render_svg=False)

    def on_enter_tracing(self, *_a, **_k):
        self.submit_step(self.executor, self.job_spec, on_done="traced", ask_over_s=None)

    def on_enter_done(self, result, *_a, **_k):
        self.finish(result)


# --- the executor ------------------------------------------------------------------------

def test_a_job_runs_there_and_its_handle_is_followed_from_here(fake_modal, tmp_path):
    data = tmp_path / "in" / "numbers.json"
    data.parent.mkdir()
    data.write_text(json.dumps([1, 2, 3]))
    ex = ModalExecutor("run")
    h = ex.submit(Job(f"{JOBS}:count", {"n": 3, "source": str(data)}, files={"numbers": str(data)}))
    assert ex.status(h).state == "queued"                                     # the first look, without a round trip
    st = ex.status(h)
    assert st.state == "done" and ex.result(h)["counted"] == 3 and st.progress["done"] == 3
    assert set(st.telemetry) >= {"commit", "run_s", "cost_usd_est"} and st.telemetry["cost_usd_est"] >= 0.0
    assert h.job_id not in fake_modal.dicts[modal_executor.STATE_DICT]           # its record is cleaned up
    assert h.executor == "modal" and h.where["app"] == "run" and h.where["call_id"].startswith("fc-")
    again = executor_for(type(h).from_dict(json.loads(json.dumps(h.to_dict()))))   # a fresh process
    assert isinstance(again, ModalExecutor) and again.result(h)["counted"] == 3

    failing = ex.submit(Job(f"{JOBS}:boom", {"why": "a bad input"}))
    ex.status(failing)
    st = ex.status(failing)
    assert st.state == "failed" and "ValueError: a bad input" in st.error
    ex._modal_logs = lambda handle: "x" * 50_000             # however long Modal's logs are
    tail = ex.logs(failing)
    assert len(tail) <= 4000 and tail.rstrip().endswith("ValueError: a bad input")
    assert tail[-2000:].count("a bad input") >= 1             # what a flow keeps of it


def test_remote_run_points_the_inputs_at_the_files_it_was_sent(tmp_path):
    state = {}
    out = remote_run("j1", "json:loads", '"x"', {}, state)          # json.loads('"x"', ctx) fails: a status
    assert out["state"] == "failed" and state["j1"]["ended"] == "failed"
    seen = {}

    def spy(inputs, ctx):
        seen.update(inputs=inputs, files=ctx.files)
        return open(inputs["profiles"][0]["path"]).read()

    mod = types.ModuleType("_spy_jobs")
    mod.spy = spy
    sys.modules["_spy_jobs"] = mod
    try:
        out = remote_run("j2", "_spy_jobs:spy", {"profiles": [{"path": "/far/away/profile.json", "n": 1.5}]},
                         {"lens": {"path": "/far/away/profile.json", "data": b"{\"a\": 1}"}}, state)
    finally:
        del sys.modules["_spy_jobs"]
    assert out["state"] == "done" and out["result"] == "{\"a\": 1}"
    assert seen["inputs"]["profiles"][0]["path"] == seen["files"]["lens"] != "/far/away/profile.json"


def test_a_job_that_never_starts_is_cancelled_at_its_start_limit(fake_modal, tmp_path):
    ex = ModalExecutor("never", default_start_limit_s=0.2)
    flow = TraceFlow(tmp_path, ex, Job(f"{JOBS}:count", {"n": 1}, label="count"))
    flow.begin()
    assert flow.job["start_limit_s"] == 0.2 and flow.job["state"] == "queued"
    time.sleep(0.3)
    rows = {r["run_id"]: r for r in list_runs([tmp_path])}
    assert rows[flow.run_id]["flags"] == ["not_started"]                       # seen before anyone waits
    t0 = time.time()
    out = flow.wait(60.0, poll_s=0.05)
    assert time.time() - t0 < 5.0                                               # not the 60 s
    assert out["state"] == "failed" and out["attention"] == ["failed"]
    assert "ImportError" in out["log_tail"]
    (call,) = fake_modal.calls.values()
    assert call.cancelled
    assert any("did not start within" in e["message"] for e in persistence.read_events(tmp_path, flow.run_id))


def test_a_running_job_past_its_limit_is_cancelled_and_timed_out(fake_modal):
    ex = ModalExecutor("slow")
    h = ex.submit(Job(f"{JOBS}:count", {"n": 1}, limit_s=10.0))
    ex.status(h)
    st = ex.status(h)
    assert st.state == "timed_out" and "10.0 s limit" in st.error
    (call,) = fake_modal.calls.values()
    assert call.cancelled and fake_modal.dicts[modal_executor.STATE_DICT][f"cancel:{h.job_id}"] is True
    assert ex.cancel(h).state == "timed_out"                                    # an ended job stays ended
    call.error = RuntimeError("Function call was cancelled by user or a failure.")   # as Modal says it later
    ModalExecutor._ended.pop(h.job_id)                                           # another process knows nothing
    assert ModalExecutor("slow").status(h).state == "cancelled"                  # seen from another process


def test_wait_returns_once_when_a_job_goes_over_its_budget(fake_modal, tmp_path):
    flow = TraceFlow(tmp_path, ModalExecutor("slow", default_start_limit_s=None),
                     Job(f"{JOBS}:count", {"n": 1}, budget_s=0.1))
    flow.begin()
    time.sleep(0.15)
    t0 = time.time()
    first = flow.wait(30.0, poll_s=0.05)
    assert first["attention"] == ["over_budget"] and first["waiting"] and time.time() - t0 < 5.0
    second = flow.wait(0.2, poll_s=0.05)
    assert second["attention"] == [] and second["waiting"]                      # it said so once


def test_a_queued_job_over_its_budget_is_not_hung(fake_modal, tmp_path):
    flow = TraceFlow(tmp_path, ModalExecutor("never", default_start_limit_s=60.0),
                     Job(f"{JOBS}:count", {"n": 1}, budget_s=0.1))
    flow.begin()
    time.sleep(0.15)
    flow.poll()
    assert flow.job["over_budget"] and flow.job["state"] == "queued"
    assert {r["run_id"]: r for r in list_runs([tmp_path])}[flow.run_id]["flags"] == []
    over = [e["message"] for e in persistence.read_events(tmp_path, flow.run_id) if "over budget" in e["message"]]
    assert over and over[0].endswith("still queued: not started yet")
    flow.cancel("done with it")


def test_containers_failing_to_start_fail_the_job_before_its_start_limit(fake_modal, tmp_path):
    ex = ModalExecutor("never", default_start_limit_s=600.0, fail_after_container_errors=3)
    flow = TraceFlow(tmp_path, ex, Job(f"{JOBS}:count", {"n": 1}, label="count"))
    flow.begin()
    flow.poll()
    assert flow.job["state"] == "queued" and flow.job["telemetry"]["queue"]["backlog"] == 1
    fake_modal.container_errors = 3
    modal_executor.STATS_EVERY_S, every = 0.0, modal_executor.STATS_EVERY_S
    try:
        out = flow.wait(30.0, poll_s=0.05)
    finally:
        modal_executor.STATS_EVERY_S = every
    assert out["state"] == "failed"
    assert any("failed to start 3 times" in e["message"] for e in persistence.read_events(tmp_path, flow.run_id))
    (call,) = fake_modal.calls.values()
    assert call.cancelled


def test_many_queued_jobs_share_their_functions_statistics(fake_modal, tmp_path):
    ex = ModalExecutor("never", default_start_limit_s=600.0)
    handles = ex.submit_many([Job(f"{JOBS}:count", {"n": k}) for k in range(60)])
    for h in handles:
        ex.status(h)                                              # the first look needs no round trip
    for _ in range(3):
        states = [ex.status(h) for h in handles]
        assert all(st.state == "queued" for st in states)
        assert all(st.telemetry["queue"]["backlog"] == 1 for st in states)
    assert fake_modal.stats_calls <= 2 * 2                        # one window of submissions (two at a boundary)
    for h in handles:
        ex.cancel(h)


def test_wait_all_follows_many_runs_and_reports_each_end_once(fake_modal, tmp_path):
    from ray_tracing_shapely.flows import wait_all
    ex = ModalExecutor("run")
    flows = [TraceFlow(tmp_path, ex, Job(f"{JOBS}:count", {"n": k + 1})) for k in range(5)]
    flows.append(TraceFlow(tmp_path, ModalExecutor("never", default_start_limit_s=0.2), Job(f"{JOBS}:count", {"n": 1})))
    for f in flows:
        f.begin()
    seen = []
    t0 = time.time()
    last = wait_all(flows, 30.0, poll_s=0.1, on_change=lambda f, out: seen.append((f.run_id, out["state"])))
    assert time.time() - t0 < 10.0
    assert [last[f.run_id]["state"] for f in flows] == ["done"] * 5 + ["failed"]
    assert sorted(seen) == sorted((f.run_id, f.state) for f in flows)             # each end reported once


def test_submit_many_sends_jobs_ahead_and_flows_pick_up_their_handles(fake_modal, tmp_path):
    from ray_tracing_shapely.flows import wait_all
    ex = ModalExecutor("run")
    jobs = [Job(f"{JOBS}:count", {"n": k + 1}) for k in range(6)]
    handles = ex.submit_many(jobs, max_workers=3)
    assert len({h.job_id for h in handles}) == 6 and len(fake_modal.calls) == 6
    flows = [TraceFlow(tmp_path, ex, j) for j in jobs]
    for f in flows:
        f.begin()
    assert len(fake_modal.calls) == 6                                         # nothing sent twice
    assert [f.job["handle"]["job_id"] for f in flows if f.job] in ([h.job_id for h in handles], [])
    last = wait_all(flows, 10.0, poll_s=0.05)
    assert [last[f.run_id]["state"] for f in flows] == ["done"] * 6
    assert [persistence.read_result(tmp_path, f.run_id)["result"]["counted"] for f in flows] == [1, 2, 3, 4, 5, 6]
    other = Job(f"{JOBS}:count", {"n": 1})                                   # not sent ahead: sent at submit
    assert ex.submit(other).job_id not in {h.job_id for h in handles} and len(fake_modal.calls) == 7
