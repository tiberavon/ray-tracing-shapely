"""
Python-specific module: test graph runner
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
The graph runner: the compiled cells, re-run only where stale (KA10)
===============================================================================
- a full run gives each node's outputs equal to the compiled script run;
- after an edit, only the edited node and what is downstream of it run, and
  every node's outputs equal a full run of the edited graph's script;
- a rayfile changed on disk makes the nodes reading it stale;
- a node taken out of the graph leaves the store;
- a node that fails stops the run, with the node and the reason, and what
  is downstream stays stale;
- a long node is refused with its estimate when there is no executor, before
  anything runs; with one, it goes as a job (in process, and in a worker
  process) and its outputs come back equal to the kernel's.
===============================================================================
"""

import copy
import os
import time

import pytest

pytest.importorskip("pint")

from ray_tracing_shapely.developer_tests.test_graph import _run_compiled, chain_graph, write_led  # noqa: E402
from ray_tracing_shapely.graph import GraphRunner, RunnerError  # noqa: E402


@pytest.fixture()
def rayfile(tmp_path):
    return write_led(tmp_path)


def _node(doc, nid):
    return next(n for n in doc["nodes"] if n["id"] == nid)


def _values(runner, doc):
    """Every node's outputs in their JSON form, the trace left out, as `_run_compiled` gives them."""
    out = {}
    for node in doc["nodes"]:
        values = runner.values(doc, node["id"])
        out[node["id"]] = {k: v for k, v in values.items() if node["block"] != "trace"}
    return out


def test_a_full_run_equals_the_compiled_script(rayfile):
    doc = chain_graph(rayfile)
    runner = GraphRunner(inline_limit_s=None)
    report = runner.run(doc)
    assert report.done and report.ran() == report.order and report.kept() == []
    assert _values(runner, doc) == _run_compiled(doc)
    assert runner.stale(doc) == []
    again = runner.run(doc)
    assert again.ran() == [] and again.kept() == again.order


def test_after_an_edit_only_what_is_downstream_runs_and_equals_a_full_run(rayfile):
    doc = chain_graph(rayfile)
    runner = GraphRunner(inline_limit_s=None)
    runner.run(doc)

    edited = copy.deepcopy(doc)
    _node(edited, "weighted")["inputs"]["hazard"] = "ir"
    _node(edited, "group")["inputs"] = {"alpha": "5 mrad", "ir": {"from": "weighted.weighted"}}
    assert runner.stale(edited) == ["weighted", "group"]
    report = runner.run(edited)
    assert report.ran() == ["weighted", "group"] and "traced" in report.kept()
    assert _values(runner, edited) == _run_compiled(edited)

    wider = copy.deepcopy(edited)
    _node(wider, "det")["inputs"]["binSize"] = "5 mm"
    stale = runner.stale(wider)
    assert set(stale) == {"det", "scene", "traced", "reading", "irr", "weighted", "group"}
    report = runner.run(wider)
    assert set(report.kept()) == {"slice", "led", "tir"}
    assert _values(runner, wider) == _run_compiled(wider)


def test_a_rayfile_changed_on_disk_makes_its_readers_stale(rayfile):
    doc = chain_graph(rayfile)
    runner = GraphRunner(inline_limit_s=None)
    runner.run(doc)
    st = os.stat(rayfile)
    os.utime(rayfile, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    stale = runner.stale(doc)
    assert stale[0] == "slice" and "weighted" in stale and "tir" not in stale and "det" not in stale


def test_a_node_taken_out_leaves_the_store(rayfile):
    doc = chain_graph(rayfile)
    runner = GraphRunner(inline_limit_s=None)
    runner.run(doc)
    smaller = copy.deepcopy(doc)
    smaller["nodes"] = [n for n in smaller["nodes"] if n["id"] != "group"]
    report = runner.run(smaller)
    assert report.ran() == [] and "group" not in runner.namespace
    with pytest.raises(RunnerError, match="no result for 'group'"):
        runner.outputs("group")


def test_a_failing_node_stops_the_run_with_the_reason(rayfile, tmp_path):
    doc = chain_graph(rayfile)
    broken = copy.deepcopy(doc)
    missing = str(tmp_path / "gone.tm25")
    _node(broken, "slice")["inputs"]["rayfile"] = missing
    runner = GraphRunner(inline_limit_s=None)
    with pytest.raises(RunnerError, match=r"slice: BlockTypeError: .*gone\.tm25"):
        runner.run(broken)
    report = runner.report
    assert report.done and report.nodes["slice"].state == "failed"
    assert report.nodes["led"].state == "skipped" and report.nodes["led"].error == "not run: slice failed"
    assert "group" not in runner.namespace
    assert runner.stale(broken)[0] == "slice"
    report = runner.run(doc)
    assert "slice" in report.ran() and "led" in report.ran() and "tir" in report.kept()
    assert _values(runner, doc) == _run_compiled(doc)


def test_a_long_node_is_refused_with_its_estimate_without_an_executor(rayfile):
    doc = chain_graph(rayfile)                 # the trace's default max_rays: 100,000 segments
    runner = GraphRunner()
    with pytest.raises(RunnerError, match=r"traced: trace is estimated at about 75 seconds .*executor"):
        runner.run(doc)
    assert list(runner.namespace) == ["call_block"]          # refused before anything ran
    _node(doc, "traced")["inputs"]["max_rays"] = 20000
    assert runner.estimate_s(_node(doc, "traced")) == pytest.approx(15.0)
    assert runner.run(doc).done


def _small_chain(rayfile, runs):
    doc = chain_graph(rayfile)
    _node(doc, "traced")["inputs"]["runs_dir"] = str(runs)
    return doc


def test_a_long_node_goes_to_an_executor_and_comes_back_equal(rayfile, tmp_path):
    from ray_tracing_shapely.flows.executors import InProcessExecutor
    runs = tmp_path / "runs"
    runs.mkdir()
    doc = _small_chain(rayfile, runs)
    no_folder = copy.deepcopy(doc)
    del _node(no_folder, "traced")["inputs"]["runs_dir"]
    runner = GraphRunner(executor=InProcessExecutor(tmp_path / "jobs"))
    with pytest.raises(RunnerError, match="traced: a trace run by an executor comes back as its run folder"):
        runner.run(no_folder)
    report = runner.run(doc)
    assert report.nodes["traced"].where == "in_process" and report.nodes["traced"].state == "ran"
    assert report.nodes["slice"].state == "kept" and report.nodes["reading"].where == "kernel"  # slice ran before the refusal
    assert _values(runner, doc) == _run_compiled(doc)
    assert runner.outputs("traced")["trace"].folder.parent.parent == runs


def test_a_long_node_runs_in_a_worker_process(rayfile, tmp_path):
    from ray_tracing_shapely.flows.executors import LocalProcessExecutor
    runs = tmp_path / "runs"
    runs.mkdir()
    doc = _small_chain(rayfile, runs)
    runner = GraphRunner(executor=LocalProcessExecutor(tmp_path / "jobs", nice=0), poll_s=0.2)
    first = runner.start(doc)
    assert not first.done and runner.waiting == ["traced"]
    assert first.nodes["traced"].state == "submitted" and first.nodes["reading"].state == "waiting"
    assert first.nodes["traced"].estimate_s == pytest.approx(75.0)
    deadline, report = time.time() + 120, first
    while not report.done:                    # the job followed by its executor's record
        assert time.time() < deadline, runner.waiting
        time.sleep(0.2)
        report = runner.advance()
    assert report.nodes["traced"].where == "local_process" and report.failed() is None
    assert _values(runner, doc) == _run_compiled(doc)
