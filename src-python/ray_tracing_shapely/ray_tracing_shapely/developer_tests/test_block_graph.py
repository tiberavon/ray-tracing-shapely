"""
Python-specific module: test block graph
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
An agent's kept values written as a graph document (KA10, C-GRAPH-02)
===============================================================================
- the store records each call: its block, its inputs as given, its outputs;
- the chain built through block_run, written by block_graph, is a checked
  graph whose compiled script gives every value the agent kept, exactly;
- with refs, only those values and what they were made from: a run tried and
  dropped is left out; without, every call;
- a node is named after its object's name input, or its block;
- what the graph cannot say is refused with the reason (a list mixing
  handles and literals), as are nothing kept and an unknown handle;
- the written graph opens in the graph editor and runs with the runner.
===============================================================================
"""

import copy
import json

import pytest

pytest.importorskip("pint")

from ray_tracing_shapely.blocks import agentic as tools  # noqa: E402
from ray_tracing_shapely.developer_tests.test_graph import DETECTOR, _run_compiled, write_led  # noqa: E402
from ray_tracing_shapely.graph import GraphRunner, load_graph  # noqa: E402


@pytest.fixture()
def rayfile(tmp_path):
    return write_led(tmp_path)


@pytest.fixture(autouse=True)
def _fresh_store():
    tools.clear_values()
    yield
    tools.clear_values()


def _ok(reply):
    assert reply["status"] == "ok", reply
    return reply["data"]


def _run(name, inputs):
    """block_run, answering with the handle of each output."""
    return {p: o["ref"] for p, o in _ok(tools.block_run(name, inputs))["outputs"].items() if o}


def build_chain(rayfile):
    """The example chain as an agent builds it, by handle; with one run tried and dropped."""
    sl = _run("slice_rayfile", {"rayfile": rayfile, "position": [0, 0], "direction_deg": "0 deg",
                                "max_offset_mm": "0.5 mm"})["slice"]
    led = _run("source_from_slice", {"slice": {"ref": sl}, "name": "led"})["entry"]
    tir = _run("TIRCollimator", {"name": "tir"})["entry"]
    det = _run("Detector", DETECTOR)["entry"]
    scene = _run("assemble", {"entries": [{"ref": led}, {"ref": tir}, {"ref": det}]})["scene"]
    trace = _run("trace", {"scene": {"ref": scene}})["trace"]
    reading = _run("detector_reading", {"trace": {"ref": trace}, "detector": "det", "profile": True})["reading"]
    irr = _run("physical_reading", {"reading": {"ref": reading}, "calibration": "1 W/m",
                                    "detector_length": "80 mm"})["irradiance"]
    _run("hazard_weighted", {"irradiance": {"ref": irr}, "rayfile": rayfile, "hazard": "ir"})    # tried, dropped
    weighted = _run("hazard_weighted", {"irradiance": {"ref": irr}, "rayfile": rayfile,
                                        "hazard": "blue_light"})["weighted"]
    group = _run("classify_iec62471", {"alpha": "5 mrad", "blue_light_irradiance": {"ref": weighted}})
    return group["classification"]


def _kept_json(ref):
    kept = tools._STORE[ref]
    return kept["type"].format(kept["live"])


def test_the_store_records_each_call(rayfile):
    build_chain(rayfile)
    calls = list(tools._CALLS.values())
    assert [c["block"] for c in calls][:3] == ["slice_rayfile", "source_from_slice", "TIRCollimator"]
    assert calls[1]["inputs"] == {"slice": {"ref": "v1"}, "name": "led"} and calls[1]["outputs"] == {"entry": "v2"}
    assert tools._STORE["v2"]["call"] == "c2" and tools._STORE["v2"]["port"] == "entry"


def test_the_agents_chain_as_a_graph_compiles_to_its_own_numbers(rayfile, tmp_path):
    group = build_chain(rayfile)
    path = tmp_path / "chain.graph.json"
    data = _ok(tools.block_graph(str(path), refs=[group], notes="The chain."))
    doc = load_graph(path)                                     # checked as it is read
    ids = [n["id"] for n in data["nodes"]]
    assert ids == ["slice_rayfile", "led", "tir", "det", "assemble", "trace", "detector_reading",
                   "physical_reading", "hazard_weighted", "classify_iec62471"]       # the dropped run left out
    assert _node(doc, "assemble")["inputs"]["entries"] == [{"from": "led.entry"}, {"from": "tir.entry"},
                                                           {"from": "det.entry"}]
    assert _node(doc, "hazard_weighted")["inputs"]["hazard"] == "blue_light" and doc["notes"] == "The chain."
    got = _run_compiled(doc)
    compared = 0
    for ref, end in data["values"].items():
        node, port = end.split(".")
        if node != "trace":
            assert got[node][port] == _kept_json(ref), end
            compared += 1
    assert compared == len(data["values"]) - 1 and data["values"][group] == "classify_iec62471.classification"


def test_without_refs_every_call_is_a_node(rayfile, tmp_path):
    build_chain(rayfile)
    data = _ok(tools.block_graph(str(tmp_path / "all.graph.json")))
    ids = [n["id"] for n in data["nodes"]]
    assert "hazard_weighted_2" in ids and len(ids) == 11
    doc = load_graph(tmp_path / "all.graph.json")
    assert _node(doc, "hazard_weighted")["inputs"]["hazard"] == "ir"
    assert _node(doc, "hazard_weighted_2")["inputs"]["irradiance"] == {"from": "physical_reading.irradiance"}


def test_what_the_graph_cannot_say_is_refused_with_the_reason(rayfile, tmp_path):
    out = str(tmp_path / "g.graph.json")
    assert "nothing is kept yet" in tools.block_graph(out)["message"]
    det = _run("Detector", DETECTOR)["entry"]
    tir = _run("TIRCollimator", {"name": "tir"})["entry"]
    _run("assemble", {"entries": [{"ref": tir}, _kept_json(det)]})       # a handle and a literal in one list
    reply = tools.block_graph(out)
    assert reply["status"] == "error" and "mixes them" in reply["message"]
    assert "no kept value 'v99'" in tools.block_graph(out, refs=["v99"])["message"]
    assert "refs must be a list" in tools.block_graph(out, refs="v1")["message"]
    assert _ok(tools.block_graph(out, refs=[det]))["nodes"] == [{"id": "det", "block": "Detector"}]


def test_the_graph_opens_in_the_editor_and_runs(rayfile, tmp_path):
    from ray_tracing_shapely.graph import GraphEditor
    group = build_chain(rayfile)
    path = tmp_path / "chain.graph.json"
    _ok(tools.block_graph(str(path), refs=[group]))
    editor = GraphEditor(path=str(path))
    state = editor.state()
    assert not state["missing"] and all(n["at"] for n in editor.doc["nodes"])      # laid out by its wires
    runner = GraphRunner(inline_limit_s=None)
    doc = copy.deepcopy(editor.doc)
    assert runner.run(doc).done
    assert json.loads(json.dumps(runner.values(doc, "classify_iec62471")["classification"])) == _kept_json(group)


def _node(doc, nid):
    return next(n for n in doc["nodes"] if n["id"] == nid)
