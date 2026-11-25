"""
Python-specific module: test graph server
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
The graph editor served as a process, for the VS Code editor (C-GRAPH-02)
===============================================================================
- hello gives the page's module, the one the notebook widget uses;
- a document's text is loaded (empty: a new graph); the state's text comes
  only when the graph changed, not on loading, selecting or running;
- new, open and save are the host's, refused with the reason;
- a text that is not a graph is refused, and nothing is written over it;
- a relative notebook path is compiled beside the graph, and named;
- over standard input and output, in a real process: the chain runs, its
  trace sent to a worker process and followed by polls, and every node ends
  fresh, its values equal to the compiled script's.
===============================================================================
"""

import json
import subprocess
import sys
import time

import pytest

pytest.importorskip("pint")

from ray_tracing_shapely.developer_tests.test_graph import DETECTOR, chain_graph, write_led  # noqa: E402
from ray_tracing_shapely.graph import GraphRunner  # noqa: E402
from ray_tracing_shapely.graph.server import GraphServer, graph_text  # noqa: E402

NOTEBOOK = ".ipy" + "nb"


@pytest.fixture()
def server():
    return GraphServer(runner=GraphRunner(inline_limit_s=None))


def _det_graph():
    return {"graph_version": 1, "notes": "", "nodes": [{"id": "det", "block": "Detector", "at": [40, 40],
                                                        "inputs": dict(DETECTOR)}]}


def test_hello_gives_the_widgets_page(server):
    from ray_tracing_shapely.graph.widget import _ESM
    hello = server.request({"type": "hello"})
    assert hello["esm"] == _ESM and "version" in hello and hello["css"]


def test_the_text_comes_only_when_the_graph_changed(server, tmp_path):
    s = server.request({"type": "load_text", "text": "", "path": str(tmp_path / "g.graph.json")})
    assert s["host"] == "vscode" and s["nodes"] == [] and s["text"] is None
    s = server.request({"type": "add", "block": "Detector"})
    assert json.loads(s["text"])["nodes"][0]["id"] == "detector"
    assert server.request({"type": "select", "id": "detector"})["text"] is None
    assert server.request({"type": "refresh"})["text"] is None
    s = server.request({"type": "set", "id": "detector", "input": "name", "value": "d1"})
    assert s["error"] is None and json.loads(s["text"])["nodes"][0]["inputs"]["name"] == "d1"

    doc = _det_graph()
    del doc["nodes"][0]["at"]                          # laid out on loading, written with the next edit
    s = server.request({"type": "load_text", "text": graph_text(doc), "path": str(tmp_path / "g.graph.json")})
    assert s["text"] is None and s["nodes"][0]["id"] == "det"
    s = server.request({"type": "run"})
    assert s["text"] is None and s["notice"] == "ran det"


def test_the_file_commands_are_the_hosts(server, tmp_path):
    server.request({"type": "load_text", "text": graph_text(_det_graph())})
    for kind in ("new", "open", "save"):
        s = server.request({"type": kind, "path": str(tmp_path / "x.graph.json")})
        assert "VS Code's File menu" in s["error"]
    assert not (tmp_path / "x.graph.json").exists() and server.editor.doc["nodes"]


def test_a_text_that_is_not_a_graph_is_never_written_over(server):
    for text in ("{not json", json.dumps({"nodes": []})):
        s = server.request({"type": "load_text", "text": text})
        assert "not a graph the editor can read" in s["error"] and s["text"] is None
        s = server.request({"type": "add", "block": "Detector"})
        assert "fix its text first" in s["error"] and s["text"] is None


def test_a_relative_notebook_is_compiled_beside_the_graph(server, tmp_path):
    server.request({"type": "load_text", "text": graph_text(_det_graph()), "path": str(tmp_path / "g.graph.json")})
    s = server.request({"type": "compile", "path": "det" + NOTEBOOK})
    assert s["compiled"] == str(tmp_path / ("det" + NOTEBOOK)) and (tmp_path / ("det" + NOTEBOOK)).exists()
    assert server.request({"type": "refresh"})["compiled"] is None


def test_the_chain_runs_in_the_served_process_its_trace_in_a_worker(tmp_path):
    from ray_tracing_shapely.developer_tests.test_graph import _run_compiled
    runs = tmp_path / "runs"
    runs.mkdir()
    doc = chain_graph(write_led(tmp_path))
    next(n for n in doc["nodes"] if n["id"] == "traced")["inputs"]["runs_dir"] = str(runs)
    proc = subprocess.Popen([sys.executable, "-m", "ray_tracing_shapely.graph.server", "--jobs", str(tmp_path / "jobs")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=tmp_path)
    counter = iter(range(1, 10**6))

    def ask(message):
        rid = next(counter)
        proc.stdin.write(json.dumps({"id": rid, "message": message}) + "\n")
        proc.stdin.flush()
        reply = json.loads(proc.stdout.readline())
        assert reply["id"] == rid and "error" not in reply, reply
        return reply["state"]

    try:
        ask({"type": "load_text", "text": graph_text(doc), "path": str(tmp_path / "chain.graph.json")})
        s = ask({"type": "run"})
        assert s["waiting"] == ["traced"] and s["notice"] == "waiting on traced"
        status = {n["id"]: n["status"] for n in s["nodes"]}
        assert status["traced"] == "running" and status["slice"] == "fresh" and status["group"] == "stale"
        deadline = time.time() + 120
        while s["waiting"]:                          # as the page polls, once a second
            assert time.time() < deadline, s["waiting"]
            time.sleep(0.5)
            s = ask({"type": "poll"})
        assert s["error"] is None and all(n["status"] == "fresh" for n in s["nodes"]), s["nodes"]
        want = _run_compiled(doc)
        s = ask({"type": "select", "id": "group"})
        assert json.loads(json.dumps(want["group"]["classification"]["group"])) in s["values"]["classification"]
    finally:
        proc.stdin.close()
        proc.wait(timeout=20)
