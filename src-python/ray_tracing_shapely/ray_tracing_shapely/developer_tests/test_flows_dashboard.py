"""
Python-specific module: test flows dashboard
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
The flow runs dashboard: what it shows, and how it starts and stops
===============================================================================
- a folder that does not exist is refused at start, naming the ones that do;
- a busy port is said so, and Ctrl-C stops it without a traceback;
- with no folder given, a folder made after it started appears on the next
  page;
- each run's and experiment's estimated cost, and the spend card's billed
  spend against the monthly credit;
- the page shows a failed run's reason first and its log tail folded and
  escaped; an experiment's cases against the ends they were meant to reach
  (a run meant to fail that fails is a pass, and is not listed as ended
  badly); a page per run with every event; the history filtered by state.
===============================================================================
"""

from __future__ import annotations

import socket

import pytest

pytest.importorskip("transitions")

from ray_tracing_shapely.flows import InProcessExecutor, Job, ObservableFlow, dashboard  # noqa: E402

JOBS = "ray_tracing_shapely.developer_tests._flow_jobs"


class OneJob(ObservableFlow):
    def __init__(self, base_dir, executor, job):
        self.executor, self.job_spec = executor, job
        super().__init__("one_job", ["start", "working", "done"], [
            {"trigger": "begin", "source": "start", "dest": "working"},
            {"trigger": "worked", "source": "working", "dest": "done"},
        ], "start", base_dir, render_svg=False)

    def on_enter_working(self, *_a, **_k):
        self.submit_step(self.executor, self.job_spec, on_done="worked", ask_over_s=None)

    def on_enter_done(self, result, *_a, **_k):
        self.finish(result)


def test_a_missing_folder_is_refused_with_the_ones_that_exist(tmp_path, capsys):
    OneJob(tmp_path / "flow_runs" / "17p6c_e3", InProcessExecutor(), Job(f"{JOBS}:count", {"n": 1})).begin()
    code = dashboard.main(["--root", str(tmp_path / "flow_runs"),
                           "--base-dir", str(tmp_path / "flow-runs" / "17p6c-e3"), "--port", "0", "--no-spend"])
    err = capsys.readouterr().err
    assert code == 2 and "no folder" in err and "did you mean" in err and "17p6c_e3" in err
    assert dashboard.run_folders(tmp_path / "flow_runs") == [tmp_path / "flow_runs" / "17p6c_e3"]


def test_a_busy_port_is_said_and_ctrl_c_stops_cleanly(tmp_path, capsys, monkeypatch):
    OneJob(tmp_path / "runs", InProcessExecutor(), Job(f"{JOBS}:count", {"n": 1})).begin()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        busy = s.getsockname()[1]
        assert dashboard.main(["--base-dir", str(tmp_path / "runs"), "--port", str(busy), "--no-spend"]) == 2
    assert "is in use" in capsys.readouterr().err

    def interrupted(self, *a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(dashboard.HTTPServer, "serve_forever", interrupted)
    assert dashboard.main(["--base-dir", str(tmp_path / "runs"), "--port", "0", "--no-spend"]) == 0
    assert "stopped" in capsys.readouterr().out


def test_the_page_shows_jobs_failures_and_flags(tmp_path):
    base = tmp_path / "runs"
    OneJob(base, InProcessExecutor(), Job(f"{JOBS}:count", {"n": 2}, label="two")).begin()
    OneJob(base, InProcessExecutor(), Job(f"{JOBS}:boom", {"why": "<frozen> broke"}, label="boom")).begin()
    html = dashboard.page_html([base])
    assert "<title>Flow runs</title>" in html and "eye_safety" not in html
    assert "Ended badly" in html and "&lt;frozen&gt; broke" in html and "<frozen>" not in html
    assert "<details><summary>log tail" in html                                 # folded, not open
    assert "History" in html and "one_job" in html
    rows = dashboard.list_runs([base])
    assert {r["state"] for r in rows} == {"done", "failed"}


def test_experiments_runs_and_filters(tmp_path):
    base = tmp_path / "runs"
    cases = (("done", f"{JOBS}:count", {"n": 1}, "done"), ("failing", f"{JOBS}:boom", {"why": "meant"}, "failed"),
             ("wrong", f"{JOBS}:boom", {"why": "not meant"}, "done"))
    flows = {}
    for case, proc, inputs, expected in cases:
        f = OneJob(base, InProcessExecutor(), Job(proc, inputs, label=case))
        f.label_experiment("E9", case, expected)
        f.begin()
        flows[case] = f
    html = dashboard.page_html([base])
    assert "E9: " in html and "2 of 3 cases ended as expected" in html
    ended_badly = html.split("<h2>Ended badly</h2>")[1].split("<h2")[0]
    assert flows["wrong"].run_id in ended_badly and flows["failing"].run_id not in ended_badly
    page = dashboard.run_page_html(base, flows["failing"].run_id)
    assert "case <b>failing</b>" in page and "as expected" in page and "Events (" in page and "meant" in page
    only_failed = dashboard.page_html([base], query={"state": "failed"})
    hist = only_failed.split('id="history"')[1]
    assert "History (2 of 3)" in only_failed and flows["done"].run_id not in hist
    assert f'/run/runs/{flows["done"].run_id}' in html


def _page(handler_cls, path="/"):
    """A handler's page for ``path``, without a socket."""
    import io
    h = object.__new__(handler_cls)
    h.path, h.wfile = path, io.BytesIO()
    h.send_response = lambda code: None
    h.send_header = lambda *a: None
    h.end_headers = lambda: None
    h.do_GET()
    return h.wfile.getvalue().decode()


def test_a_folder_made_later_appears_on_the_next_page(tmp_path):
    root = tmp_path / "flow_runs"
    handler = dashboard.make_handler(None, root=root)
    assert "no folders of runs" in _page(handler)
    OneJob(root / "e9", InProcessExecutor(), Job(f"{JOBS}:count", {"n": 1})).begin()
    first = _page(handler)
    assert "1 runs in" in first and "e9" in first
    OneJob(root / "e10", InProcessExecutor(), Job(f"{JOBS}:count", {"n": 1})).begin()
    assert "2 runs in" in _page(handler) and "e10" in _page(handler)


def test_costs_per_run_and_experiment_and_the_spend_card(tmp_path):
    base = tmp_path / "runs"
    local = OneJob(base, InProcessExecutor(), Job(f"{JOBS}:count", {"n": 1}))
    local.label_experiment("E9", "here", "done")
    local.begin()
    remote = OneJob(base, InProcessExecutor(), Job(f"{JOBS}:count", {"n": 1}))
    remote.label_experiment("E9", "there", "done")
    remote.begin()
    remote.emit_event(message="as a Modal job reports it", executor="modal",
                      telemetry={"cost_usd_est": 0.0025, "run_s": 3.0})
    assert dashboard.run_cost(base, remote.run_id)["usd"] == 0.0025
    assert dashboard.run_cost(base, local.run_id)["usd"] is None

    class Spend:
        latest = {"last_hours": 24, "recent": {"total_usd": 0.07, "latest_hour": "18:00"},
                  "month": {"total_usd": 1.5, "by_object": {"rts-jobs": 1.4}, "latest_hour": "18:00"}}
        error, checked_at = None, 0.0
    html = dashboard.page_html([base], spend=Spend(), monthly_credit=30.0)
    assert "estimated compute $0.0025" in html and '<span class="dim">local</span>' in html
    assert "this month (UTC) <b>$1.5000</b>" in html and "<b>$28.50</b> left" in html and "rts-jobs $1.4000" in html

    class NoSpend:
        latest, error, checked_at = None, "ModuleNotFoundError: No module named 'modal'", None
    assert "No module named" in dashboard.page_html([base], spend=NoSpend(), monthly_credit=30.0)
    assert "estimated compute cost: $0.00250" in dashboard.run_page_html(base, remote.run_id)
