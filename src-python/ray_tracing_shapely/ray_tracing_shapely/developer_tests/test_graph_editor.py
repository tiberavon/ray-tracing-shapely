"""
Python-specific module: test graph editor
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
The graph editor, driven by its messages with no browser (C-GRAPH-02)
===============================================================================
- the example chain built by the canvas's own messages is the document
  written by hand, and compiles to the same script;
- a wire is refused at once, with the reason, when its type does not fit or
  it would close a cycle, and the document stays as it was; so is a literal
  its type refuses;
- an output's targets are the inputs that accept it, less those feeding it;
- deleting or renaming a node takes its wires with it; undo and redo;
- a graph is saved unfinished and opened again, a node without a place laid
  out by its wires; it compiles only when finished;
- Run runs the stale nodes and each node says whether it is fresh, stale,
  running or failed; a long node is refused with its estimate, or goes to
  the runner's executor and is taken on by a poll;
- the widget applies the same messages, opens a computed scene in the scene
  builder, and its page module is valid JavaScript whose helpers give a
  field's JSON.
===============================================================================
"""

import json
import shutil
import subprocess

import pytest

pytest.importorskip("pint")

from ray_tracing_shapely.developer_tests.test_graph import DETECTOR, chain_graph, write_led  # noqa: E402
from ray_tracing_shapely.graph import GraphEditor, GraphRunner, check_graph, compile_script  # noqa: E402

RAYFILE = "led.tm25"
NOTEBOOK = ".ipynb"                  # a compiled notebook's suffix


def _send(e, kind, **fields):
    return e.handle({"type": kind, **fields})


def _ok(e, kind, **fields):
    s = _send(e, kind, **fields)
    assert s["error"] is None, s["error"]
    return s


def build_chain(e):
    """The example chain, as a person draws it: add each block, name it, fill its form, wire it."""
    for block, nid in [("slice_rayfile", "slice"), ("source_from_slice", "led"), ("TIRCollimator", "tir"),
                       ("Detector", "det"), ("assemble", "scene"), ("trace", "traced"),
                       ("detector_reading", "reading"), ("physical_reading", "irr"),
                       ("hazard_weighted", "weighted"), ("classify_iec62471", "group")]:
        s = _ok(e, "add", block=block, at=[0, 0])
        _ok(e, "rename", id=s["selected"], to=nid)
    for nid, values in {
        "slice": {"rayfile": RAYFILE, "position": [0, 0], "direction_deg": "0 deg", "max_offset_mm": "0.5 mm"},
        "led": {"name": "led"}, "tir": {"name": "tir"}, "det": DETECTOR,
        "reading": {"detector": "det", "profile": True},
        "irr": {"calibration": "1 W/m", "detector_length": "80 mm"},
        "weighted": {"rayfile": RAYFILE, "hazard": "blue_light"}, "group": {"alpha": "5 mrad"},
    }.items():
        for name, value in values.items():
            _ok(e, "set", id=nid, input=name, value=value)
    for src, dst in [("slice.slice", "led.slice"), ("led.entry", "scene.entries"), ("tir.entry", "scene.entries"),
                     ("det.entry", "scene.entries"), ("scene.scene", "traced.scene"), ("traced.trace", "reading.trace"),
                     ("reading.reading", "irr.reading"), ("irr.irradiance", "weighted.irradiance"),
                     ("weighted.weighted", "group.blue_light_irradiance")]:
        _ok(e, "connect", **{"from": src, "to": dst})
    return e.state()


def _by_id(doc):
    return {n["id"]: {"block": n["block"], "inputs": n.get("inputs", {})} for n in doc["nodes"]}


def test_the_chain_drawn_by_messages_is_the_document_written_by_hand():
    e = GraphEditor()
    s = build_chain(e)
    want = chain_graph(RAYFILE)
    assert _by_id(e.document()) == _by_id(want)
    assert s["missing"] == [] and s["order"] == check_graph(e.document())
    want["nodes"] = sorted(want["nodes"], key=lambda n: s["order"].index(n["id"]))
    drawn = e.document()
    drawn["nodes"] = sorted(drawn["nodes"], key=lambda n: s["order"].index(n["id"]))
    assert compile_script(drawn) == compile_script(want)
    json.dumps(s)
    assert {"from": "tir.entry", "to": "scene.entries", "index": 1} in s["wires"]


def test_a_wrong_wire_is_refused_at_once_with_the_reason_and_changes_nothing():
    e = GraphEditor()
    build_chain(e)
    before = e.document()
    s = _send(e, "connect", **{"from": "led.entry", "to": "traced.scene"})
    assert s["error"] == "traced.scene: wire from 'led.entry': scene_entry cannot feed scene"
    assert e.document() == before
    s = _send(e, "connect", **{"from": "group.classification", "to": "slice.max_offset_mm"})
    assert "cannot feed" in s["error"] and e.document() == before
    s = _send(e, "connect", **{"from": "irr.irradiance", "to": "irr.reading"})
    assert "its own input" in s["error"]
    s = _send(e, "set", id="irr", input="calibration", value="1 mm")
    assert "irr.calibration" in s["error"] and e.document() == before
    s = _send(e, "connect", **{"from": "led.entry", "to": "scene.entries"})
    assert "already wired" in s["error"] and e.document() == before


def test_a_wire_that_closes_a_cycle_is_refused():
    e = GraphEditor()
    for b in ("Detector", "assemble", "trace"):
        _ok(e, "add", block=b)
    _ok(e, "connect", **{"from": "detector.entry", "to": "assemble.entries"})
    s = _ok(e, "connect", **{"from": "assemble.scene", "to": "trace.scene"})
    nodes = {n["id"]: n for n in s["nodes"]}
    # settings is JSON, which accepts any wire (the blocks' rule; KW-BLOCKS-03), so it is a target too
    assert nodes["detector"]["outputs"][0]["targets"] == ["assemble.entries", "assemble.settings"]
    assert nodes["assemble"]["outputs"][0]["targets"] == ["trace.scene"]
    assert nodes["trace"]["outputs"][0]["targets"] == []         # nothing it could feed without a cycle
    s = _send(e, "connect", **{"from": "assemble.scene", "to": "assemble.settings"})
    assert "its own input" in s["error"]


def test_an_output_s_targets_are_the_inputs_that_accept_it():
    e = GraphEditor()
    s = build_chain(e)
    nodes = {n["id"]: n for n in s["nodes"]}
    out = nodes["slice"]["outputs"][0]["targets"]
    assert out == ["led.slice", "scene.settings"]
    irr = next(o for o in nodes["irr"]["outputs"] if o["name"] == "irradiance")["targets"]
    assert "weighted.irradiance" in irr and "irr.reading" not in irr and "reading.trace" not in irr
    shown = {p["name"] for p in nodes["scene"]["inputs"] if p["shown"]}
    assert shown == {"entries"}                                  # settings (JSON) only once given
    assert nodes["scene"]["inputs"][0]["wired"] == ["led.entry", "tir.entry", "det.entry"]


def test_delete_rename_undo_and_redo_keep_the_wires_in_step():
    e = GraphEditor()
    build_chain(e)
    _ok(e, "rename", id="tir", to="collimator")
    assert e.document()["nodes"][4]["inputs"]["entries"][1] == {"from": "collimator.entry"}
    s = _send(e, "rename", id="collimator", to="call_block")
    assert "call_block" in s["error"]
    _ok(e, "delete", id="collimator")
    assert e.document()["nodes"][3]["inputs"]["entries"] == [{"from": "led.entry"}, {"from": "det.entry"}]
    _ok(e, "delete", id="slice")
    s = e.state()
    assert "led needs slice" in s["missing"] and s["order"] is None
    _ok(e, "disconnect", to="scene.entries", index=0)
    assert e.document()["nodes"][2]["inputs"]["entries"] == [{"from": "det.entry"}]
    _ok(e, "undo")
    _ok(e, "undo")
    s = _ok(e, "undo")
    assert any(n["id"] == "collimator" for n in s["nodes"]) and s["can_redo"]
    _ok(e, "redo")
    assert not any(n["id"] == "collimator" for n in e.state()["nodes"])
    s = _ok(e, "set", id="led", input="name", value=None)
    assert "name" not in e.document()["nodes"][0]["inputs"]


def test_a_graph_is_saved_unfinished_opened_and_compiled_when_finished(tmp_path):
    e = GraphEditor()
    _ok(e, "add", block="slice_rayfile")
    s = _ok(e, "save", path=str(tmp_path / "draft.graph.json"))
    assert "not finished: slice_rayfile needs rayfile, position, direction_deg" in s["notice"]
    s = _send(e, "compile", path=str(tmp_path / ("draft" + NOTEBOOK)))
    assert "slice_rayfile needs" in s["error"] and not (tmp_path / ("draft" + NOTEBOOK)).exists()

    done = GraphEditor()
    build_chain(done)
    _ok(done, "save", path=str(tmp_path / "chain.graph.json"))
    s = _ok(done, "compile")
    assert (tmp_path / ("chain" + NOTEBOOK)).exists() and "10 nodes" in s["notice"]
    nb = json.loads((tmp_path / ("chain" + NOTEBOOK)).read_text())
    assert nb["metadata"]["ray_tracing_shapely"]["graph_version"] == 1

    again = GraphEditor(path=str(tmp_path / "chain.graph.json"))
    assert again.document() == done.document() and not again.state()["can_undo"]

    bare = chain_graph(RAYFILE)                    # as an agent would write it: no places
    s = GraphEditor(bare).state()
    at = {n["id"]: n["at"] for n in s["nodes"]}
    assert at["slice"][0] < at["led"][0] < at["scene"][0] < at["traced"][0] < at["group"][0]
    assert at["det"][0] == at["slice"][0] and at["det"][1] != at["slice"][1]

    (tmp_path / "v2.graph.json").write_text(json.dumps({"graph_version": 2, "nodes": []}))
    s = _send(done, "open", path=str(tmp_path / "v2.graph.json"))
    assert "graph_version 2" in s["error"] and len(s["nodes"]) == 10


def test_unknown_messages_and_blocks_are_answered_not_raised():
    e = GraphEditor()
    assert "no message type" in _send(e, "frobnicate")["error"]
    assert "no block" in _send(e, "add", block="NoSuchBlock")["error"]
    assert "no node" in _send(e, "move", id="ghost", at=[1, 2])["error"]
    assert "'<node>.<port>'" in _send(e, "connect", **{"from": "x", "to": "y.z"})["error"]
    assert e.state()["nodes"] == []


def test_the_widget_applies_messages_with_no_browser():
    pytest.importorskip("anywidget")
    from ray_tracing_shapely.graph import graph_editor
    w = graph_editor()
    w.handle({"type": "add", "block": "Detector", "at": [10, 20]})
    s = w.handle({"type": "add", "block": "assemble"})
    s = w.handle({"type": "connect", "from": "detector.entry", "to": "assemble.entries"})
    assert s["error"] is None and s["wires"] == [{"from": "detector.entry", "to": "assemble.entries", "index": 0}]
    assert "files" in w.state and w.document()["nodes"][0]["at"] == [10.0, 20.0]
    s = w.handle({"type": "add", "block": "Detector", "at": [10, 20]})
    assert s["nodes"][-1]["at"] == [40.0, 50.0]                   # not on top of the first
    assert [g["kind"] for g in s["palette"]] == ["function", "recipe", "primitive"]


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def test_the_page_module_is_valid_javascript_and_its_fields_give_json(tmp_path):
    from ray_tracing_shapely.graph import widget
    node = _node()
    (tmp_path / "graph.mjs").write_text(widget._ESM, encoding="utf-8")
    checked = subprocess.run([node, "--check", str(tmp_path / "graph.mjs")], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    (tmp_path / "run.mjs").write_text("""
import { toValue, typeText, nodeHeight, portAt } from "./graph.mjs";
const q = {type: "quantity", unit: "mm"}, n = {type: "number"}, l = {type: "list", of: {type: "number"}};
const node = {at: [100, 50], inputs: [{name: "a", shown: true}, {name: "b", shown: false}, {name: "c", shown: true}],
              outputs: [{name: "out"}]};
console.log(JSON.stringify({
  q: toValue(q, " 0.5 mm "), empty: toValue(q, ""), n: toValue(n, "3"), bad: toValue(n, "x"),
  l: toValue(l, "[1, 2]"), opt: toValue({type: "optional", of: {type: "text"}}, "det"),
  types: [typeText(q), typeText({type: "optional", of: q}), typeText({type: "list", of: {type: "scene_entry"}})],
  h: nodeHeight(node), c: portAt(node, "in", "c"), o: portAt(node, "out", "out"),
}));
""", encoding="utf-8")
    done = subprocess.run([node, str(tmp_path / "run.mjs")], capture_output=True, text=True, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout)
    assert got["q"] == "0.5 mm" and got["empty"] is None and got["n"] == 3 and got["bad"] == "x"
    assert got["l"] == [1, 2] and got["opt"] == "det"
    assert got["types"] == ["mm", "mm?", "[scene_entry]"]
    assert got["c"]["x"] == 100 and got["c"]["y"] > 50 and got["o"]["x"] > 100


# --- running from the canvas ---------------------------------------------------------

@pytest.fixture(scope="module")
def rayfile_path(tmp_path_factory):
    return write_led(tmp_path_factory.mktemp("led"))


def _status(state):
    return {n["id"]: n["status"] for n in state["nodes"]}


def test_run_runs_the_stale_nodes_and_each_node_says_its_status(rayfile_path):
    e = GraphEditor(chain_graph(rayfile_path), runner=GraphRunner(inline_limit_s=None))
    s = _ok(e, "add", block="Detector")
    assert "not finished" in _send(e, "run")["error"]
    _ok(e, "delete", id="detector")
    assert set(_status(e.state()).values()) == {"stale"}
    s = _ok(e, "run")
    assert s["notice"] == "ran " + ", ".join(s["order"]) and set(_status(s).values()) == {"fresh"}
    s = _ok(e, "select", id="weighted")
    assert s["values"]["weighted"].endswith(' W/m^2"')               # a quantity's JSON: text with its unit
    s = _ok(e, "set", id="weighted", input="hazard", value="near_uv")
    status = _status(s)
    assert status["weighted"] == "stale" and status["group"] == "stale" and status["traced"] == "fresh"
    assert s["values"] is None
    _ok(e, "connect", **{"from": "weighted.weighted", "to": "group.near_uv"})
    _ok(e, "disconnect", to="group.blue_light_irradiance")
    s = _ok(e, "run")
    assert s["notice"] == "ran weighted, group" and set(_status(s).values()) == {"fresh"}
    assert _ok(e, "run")["notice"] == "nothing to run: every node is fresh"


def test_a_long_node_is_refused_with_its_estimate_or_sent_to_the_executor(rayfile_path, tmp_path):
    from ray_tracing_shapely.flows.executors import InProcessExecutor
    doc = chain_graph(rayfile_path)
    s = _send(GraphEditor(doc), "run")
    assert "traced: trace is estimated at about 75 seconds" in s["error"]

    next(n for n in doc["nodes"] if n["id"] == "traced")["inputs"]["runs_dir"] = str(tmp_path)
    e = GraphEditor(doc, runner=GraphRunner(executor=InProcessExecutor(tmp_path / "jobs")))
    s = _ok(e, "run")
    assert s["waiting"] == ["traced"] and _status(s)["traced"] == "running" and _status(s)["reading"] == "stale"
    assert s["notice"] == "waiting on traced"
    s = _ok(e, "poll")
    assert s["waiting"] == [] and set(_status(s).values()) == {"fresh"}
    assert s["notice"].startswith("ran ") and "traced" in s["notice"]


def test_a_failed_node_says_why(rayfile_path, tmp_path):
    doc = chain_graph(rayfile_path)
    next(n for n in doc["nodes"] if n["id"] == "slice")["inputs"]["rayfile"] = str(tmp_path / "gone.tm25")
    e = GraphEditor(doc, runner=GraphRunner(inline_limit_s=None))
    s = _send(e, "run")
    assert s["error"].startswith("slice: BlockTypeError") and "gone.tm25" in s["error"]
    node = next(n for n in s["nodes"] if n["id"] == "slice")
    assert node["status"] == "failed" and "gone.tm25" in node["error"]
    assert _status(s)["led"] == "stale" and _status(s)["tir"] == "fresh"


def test_the_widget_opens_a_computed_scene_in_the_scene_builder(rayfile_path):
    pytest.importorskip("anywidget")
    from ray_tracing_shapely.graph import graph_editor
    w = graph_editor(chain_graph(rayfile_path), runner=GraphRunner(inline_limit_s=None))
    w.handle({"type": "run"})
    builder = w.open_scene("scene", quick_max_rays=100)
    names = sorted(o["name"] for o in builder.state["objects"] if not o.get("owner"))
    assert {"led", "det"} <= set(names)
    kept = w.editor.runner.outputs("scene")["scene"]
    builder.handle({"type": "delete", "name": "det"})
    assert any(getattr(o, "name", None) == "det" for o in kept.objs)       # the runner's value is not touched
