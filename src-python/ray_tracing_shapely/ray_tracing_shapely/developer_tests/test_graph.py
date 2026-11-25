"""
Python-specific module: test graph
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
The graph document and its compiler (KA10, C-GRAPH-01, C-GRAPH-02)
===============================================================================
- the example chain as a graph document, compiled and executed, gives each
  node's outputs equal to the blocks run directly, exactly (KD5);
- the nodes run in the wires' order whatever order the document lists them;
- the notebook's code cells are the script's, and the notebook is valid;
- the document round-trips through a file;
- refused, with the node, the input and the reason: no version, a version
  not read, an unknown block or input, a missing required input, a wire from
  no node or no output, a wire of a type the input refuses, a list of wires
  into a single input, a literal its type refuses, a duplicate or unusable
  id, a cycle.
===============================================================================
"""

import copy
import json

import numpy as np
import pytest

pytest.importorskip("pint")

from ray_tracing_shapely.blocks import get_block, run_block  # noqa: E402
from ray_tracing_shapely.graph import (GraphError, check_graph, compile_graph, compile_script, load_graph,  # noqa: E402
                                       save_graph)

SPECTRUM = [(400.0, 0.0), (450.0, 1.0), (500.0, 0.2), (550.0, 0.6), (650.0, 0.3), (750.0, 0.0)]
DETECTOR = {"p1": [80, -40], "p2": [80, 40], "irradMap": True, "binSize": "10 mm", "name": "det"}


def write_led(folder):
    """A small synthetic LED rayfile in ``folder``: 300 rays, a blue-peaked spectrum; its path."""
    from ray_tracing_shapely.optical_elements.sources.rayfile import write_tm25
    rng = np.random.default_rng(1)
    n = 300
    th, ph = rng.uniform(-1.3, 1.3, n), rng.uniform(-0.05, 0.05, n)
    dirs = np.c_[np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]
    pos = np.c_[rng.uniform(-0.4, 0.4, n), rng.uniform(-0.4, 0.4, n), np.zeros(n)]
    return str(write_tm25(folder / "led.tm25", pos, dirs, np.cos(th) * 1e-3, spectrum_nm=SPECTRUM))


@pytest.fixture(scope="module")
def rayfile_path(tmp_path_factory):
    return write_led(tmp_path_factory.mktemp("led"))


def _w(source):
    return {"from": source}


def chain_graph(rayfile):
    """The example chain, rayfile to risk group, listed backwards: the wires give the order."""
    nodes = [
        {"id": "group", "block": "classify_iec62471",
         "inputs": {"alpha": "5 mrad", "blue_light_irradiance": _w("weighted.weighted")}},
        {"id": "weighted", "block": "hazard_weighted",
         "inputs": {"irradiance": _w("irr.irradiance"), "rayfile": rayfile, "hazard": "blue_light"}},
        {"id": "irr", "block": "physical_reading",
         "inputs": {"reading": _w("reading.reading"), "calibration": "1 W/m", "detector_length": "80 mm"}},
        {"id": "reading", "block": "detector_reading",
         "inputs": {"trace": _w("traced.trace"), "detector": "det", "profile": True}},
        {"id": "traced", "block": "trace", "inputs": {"scene": _w("scene.scene")}},
        {"id": "scene", "block": "assemble",
         "inputs": {"entries": [_w("led.entry"), _w("tir.entry"), _w("det.entry")]}},
        {"id": "det", "block": "Detector", "inputs": DETECTOR},
        {"id": "tir", "block": "TIRCollimator", "inputs": {"name": "tir"}},
        {"id": "led", "block": "source_from_slice", "inputs": {"slice": _w("slice.slice"), "name": "led"}},
        {"id": "slice", "block": "slice_rayfile",
         "inputs": {"rayfile": rayfile, "position": [0, 0], "direction_deg": "0 deg", "max_offset_mm": "0.5 mm"}},
    ]
    return {"graph_version": 1, "nodes": nodes, "notes": "The example chain."}


def _direct(rayfile, runs_dir):
    sl = run_block("slice_rayfile", {"rayfile": rayfile, "position": [0, 0], "direction_deg": "0 deg",
                                     "max_offset_mm": "0.5 mm"})["slice"]
    entries = [run_block("source_from_slice", {"slice": sl, "name": "led"})["entry"],
               run_block("TIRCollimator", {"name": "tir"})["entry"], run_block("Detector", DETECTOR)["entry"]]
    scene = run_block("assemble", {"entries": entries})["scene"]
    trace = run_block("trace", {"scene": scene, "runs_dir": str(runs_dir)})["trace"]
    reading = run_block("detector_reading", {"trace": trace, "detector": "det", "profile": True})["reading"]
    irr = run_block("physical_reading", {"reading": reading, "calibration": "1 W/m", "detector_length": "80 mm"})
    weighted = run_block("hazard_weighted", {"irradiance": irr["irradiance"], "rayfile": rayfile,
                                             "hazard": "blue_light"})["weighted"]
    group = run_block("classify_iec62471", {"alpha": "5 mrad", "blue_light_irradiance": weighted})
    return {"slice": {"slice": sl}, "scene": {"scene": scene}, "reading": {"reading": reading}, "irr": irr,
            "weighted": {"weighted": weighted}, "group": group}


def _run_compiled(doc):
    """Execute the compiled script; each node's outputs in their JSON form."""
    namespace = {}
    exec(compile_script(doc), namespace)  # noqa: S102 -- the compiled notebook's own code
    out = {}
    for node in doc["nodes"]:
        block = get_block(node["block"])
        live = namespace[node["id"]]
        out[node["id"]] = {p.name: (None if live.get(p.name) is None else p.type.format(live[p.name]))
                           for p in block.outputs if p.type.name != "trace"}
    return out


def test_the_compiled_chain_equals_the_blocks_run_directly(rayfile_path, tmp_path):
    doc = chain_graph(rayfile_path)
    got = _run_compiled(doc)
    want = _direct(rayfile_path, tmp_path)
    for node, outputs in want.items():
        assert got[node] == outputs, node
    assert got["group"]["classification"]["group"] in ("Exempt", "RG1", "RG2", "RG3")


def test_the_wires_give_the_order(rayfile_path):
    order = check_graph(chain_graph(rayfile_path))
    assert order[-1] == "group" and order.index("slice") < order.index("led")
    assert order.index("led") < order.index("scene") < order.index("traced")
    assert order.index("det") < order.index("scene") and order.index("tir") < order.index("scene")


def test_the_notebook_is_the_script_in_cells(rayfile_path):
    doc = chain_graph(rayfile_path)
    nb = compile_graph(doc, "The example chain")
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    assert "\n\n".join(code) + "\n" == compile_script(doc)
    assert any(c.startswith("# slice: slice_rayfile (ray_tracing_shapely.blocks.chain:") for c in code)
    led = next(c for c in code if c.startswith("# led:"))
    assert "led = call_block('source_from_slice', {\n    'name': 'led',\n}, wired={\n    'slice': slice['slice'],\n})" in led
    assert nb["metadata"]["ray_tracing_shapely"] == {"graph_version": 1}
    nbformat = pytest.importorskip("nbformat")
    nbformat.validate(nbformat.from_dict(nb))


def test_the_document_round_trips(rayfile_path, tmp_path):
    doc = chain_graph(rayfile_path)
    path = save_graph(doc, tmp_path / "chain.graph.json")
    assert load_graph(path) == doc


def _with(doc, node_id, **change):
    doc = copy.deepcopy(doc)
    node = next(n for n in doc["nodes"] if n["id"] == node_id)
    for key, value in change.items():
        if key == "inputs":
            node["inputs"].update(value)
        else:
            node[key] = value
    return doc


def test_refusals_name_the_node_the_input_and_the_reason(rayfile_path):
    doc = chain_graph(rayfile_path)
    no_version = {k: v for k, v in doc.items() if k != "graph_version"}
    dropped = copy.deepcopy(doc)
    del next(n for n in dropped["nodes"] if n["id"] == "irr")["inputs"]["calibration"]
    cases = [
        (no_version, "no graph_version; this library reads versions 1 to 1"),
        ({**doc, "graph_version": 2}, "graph_version 2; this library reads versions 1 to 1"),
        (_with(doc, "tir", block="nope"), "tir: no block 'nope'"),
        (_with(doc, "tir", inputs={"wrong": 1}), "tir: TIRCollimator has no input 'wrong'"),
        (dropped, "irr: physical_reading needs 'calibration'"),
        (_with(doc, "led", inputs={"slice": _w("nobody.slice")}), "led.slice: wire from 'nobody.slice': no node"),
        (_with(doc, "led", inputs={"slice": _w("slice.nope")}), "slice_rayfile has no output 'nope'"),
        (_with(doc, "irr", inputs={"reading": _w("det.entry")}), "irr.reading: wire from 'det.entry'"),
        (_with(doc, "scene", inputs={"entries": [_w("led.entry"), _w("slice.slice")]}), "scene.entries[1]"),
        (_with(doc, "traced", inputs={"scene": [_w("scene.scene")]}), "a list of wires goes into a list input"),
        (_with(doc, "det", inputs={"binSize": 2}), "det.binSize"),
        (_with(doc, "tir", id="det"), "two nodes have the id 'det'"),
        (_with(doc, "tir", id="call_block"), "must be a Python name"),
        (_with(doc, "tir", id="class"), "must be a Python name"),
        (_with(doc, "scene", inputs={"entries": [_w("led.entry"), {"name": "x"}]}), "mixes them"),
    ]
    for bad, reason in cases:
        with pytest.raises(GraphError) as info:
            check_graph(bad)
        assert reason in str(info.value), (reason, str(info.value))
    with pytest.raises(GraphError, match="cannot feed"):
        check_graph(_with(doc, "irr", inputs={"reading": _w("det.entry")}))


def test_a_cycle_is_refused(monkeypatch):
    from ray_tracing_shapely.blocks import registry
    from ray_tracing_shapely.blocks.types import NUMBER
    echo = registry.Block("echo", "function", [registry.Port("x", NUMBER)], [registry.Port("y", NUMBER)],
                          lambda live: {"y": live["x"]})
    monkeypatch.setitem(registry._REGISTRY, "echo", echo)
    doc = {"graph_version": 1, "nodes": [{"id": "a", "block": "echo", "inputs": {"x": _w("b.y")}},
                                         {"id": "b", "block": "echo", "inputs": {"x": _w("a.y")}},
                                         {"id": "c", "block": "echo", "inputs": {"x": 1}}]}
    with pytest.raises(GraphError, match="the wires make a cycle through a, b"):
        check_graph(doc)


def test_wired_values_are_taken_live_and_not_twice():
    from ray_tracing_shapely.blocks import BlockTypeError, call_block
    out = call_block("physical_reading", {"calibration": "1 W/m", "detector_length": "80 mm"},
                     wired={"reading": {"power": 2.0, "hits": 1}})
    assert out["irradiance"] == pytest.approx(25.0)                   # 2 x 1 W/m over 0.08 m
    with pytest.raises(BlockTypeError, match="given both"):
        call_block("physical_reading", {"reading": {"power": 2.0, "hits": 1}, "calibration": "1 W/m",
                                        "detector_length": "80 mm"}, wired={"reading": {"power": 2.0, "hits": 1}})


def test_a_literal_file_is_not_opened_when_checked():
    doc = {"graph_version": 1, "nodes": [{"id": "slice", "block": "slice_rayfile",
                                          "inputs": {"rayfile": "not/here.tm25", "position": [0, 0],
                                                     "direction_deg": "0 deg", "max_offset_mm": "0.5 mm"}}]}
    assert check_graph(doc) == ["slice"]
    assert "'rayfile': 'not/here.tm25'" in compile_script(doc)
    json.dumps(compile_graph(doc))
