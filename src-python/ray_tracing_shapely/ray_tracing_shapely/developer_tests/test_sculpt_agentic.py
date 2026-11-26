"""
Python-specific module: test sculpt agentic
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
The agent's sculpt tools, on the Example 9.1 RR lens (Chaves)
===============================================================================
- register() adds the eight tools to the three lists once, in agreement
  (KA7, C-AGENT-02); the MCP server publishes them and they run through it;
- every answer is a plain dict, JSON as it is (KA3); errors are values, and a
  name not found says which tool lists the names (KA2, KA4); every argument
  is checked (KA9); the handle list is capped and says so (KA8);
- a session: start, the tubes, a tube's crossings with the handles near them,
  those handles crossed by it, a preview that changes nothing, an apply, the
  report with its drawing on disk, undo;
- a builder widget attached is refreshed after each change (KD7);
- the tools are enough: a scripted coordinate descent (preview the handles a
  perturbation touched, apply the best) brings a perturbed lens's spread back
  down.
===============================================================================
"""

import asyncio
import importlib
import json
import math
import sys

import pytest

from ray_tracing_shapely.builder import agentic as tools
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens


def _scene():
    scene = Scene()
    scene.ray_density = 2.0
    scene.add_object(RRLens(scene, (-1.0, 2.0), (1.0, 2.0), (-0.5, -2.0), (0.5, -2.0),
                            seed_n_angle_deg=303.3, seed_x_angle_deg=42.7, name="lens"))
    src = PointSource(scene, {"x": -1.0, "y": 2.0, "brightness": 0.5})
    src.name = "E1"
    scene.add_object(src)
    det = Detector(scene, {"p1": {"x": -0.6, "y": -2.0}, "p2": {"x": 0.6, "y": -2.0}})
    det.name = "R"
    scene.add_object(det)
    return scene


def _ok(out):
    json.dumps(out)                                          # KA3: plain data, as it is
    assert out["status"] == "ok", out.get("message")
    return out["data"]


def _err(out, *words):
    json.dumps(out)
    assert out["status"] == "error"
    for w in words:
        assert w in out["message"], out["message"]
    return out["message"]


@pytest.fixture
def session():
    tools.attach(_scene())
    _ok(tools.sculpt_start("lens"))
    yield
    tools.detach()


def test_register_adds_the_sculpt_tools_once_in_agreement(monkeypatch):
    from ray_tracing_shapely.analysis import tool_registry
    monkeypatch.setattr(tool_registry, "_REGISTRY", list(tool_registry._REGISTRY))
    monkeypatch.setattr(tool_registry, "_EXTERNAL_TOOLS", [])
    monkeypatch.delitem(sys.modules, "ray_tracing_shapely.analysis.mcp_server", raising=False)
    assert tools.register() is True
    assert tools.register() is False
    names = {t["name"] for t in tool_registry.get_agentic_tools()}
    assert {fn.__name__ for fn, _, _ in tools.TOOLS} <= names
    assert {fn.__name__ for fn, _, _ in tools.TOOLS} <= {fn.__name__ for fn in tool_registry.get_exposed_tools()}
    assert tool_registry.check_tool_lists() == []
    assert len(tools.TOOLS) == 8


@pytest.mark.skipif(importlib.util.find_spec("mcp") is None, reason="mcp not installed (the agentic extra)")
def test_the_mcp_server_publishes_the_tools_and_they_run_through_it(monkeypatch):
    from ray_tracing_shapely import analysis
    from ray_tracing_shapely.analysis import tool_registry
    monkeypatch.setattr(tool_registry, "_REGISTRY", list(tool_registry._REGISTRY))
    monkeypatch.setattr(tool_registry, "_EXTERNAL_TOOLS", [])
    name = "ray_tracing_shapely.analysis.mcp_server"
    prior_module, prior_attr = sys.modules.pop(name, None), analysis.__dict__.pop("mcp_server", None)
    try:
        assert tools.register()
        server = importlib.import_module(name)
        published = {t.name for t in asyncio.run(server.mcp.list_tools())}
        assert {fn.__name__ for fn, _, _ in tools.TOOLS} <= published

        def call(tool, args):
            out = asyncio.run(server.mcp.call_tool(tool, args))
            content = out[0] if isinstance(out, tuple) else out
            return json.loads(content[0].text)

        tools.attach(_scene())
        assert _ok(call("sculpt_start", {"glass": "lens", "bundles": False}))["tubes"] == 8
        assert _ok(call("list_flux_tubes", {}))["tubes"][0]["tube_id"] == "E1/T0"
    finally:
        tools.detach()
        sys.modules.pop(name, None)
        analysis.__dict__.pop("mcp_server", None)
        if prior_module is not None:
            sys.modules[name] = prior_module
        if prior_attr is not None:
            analysis.mcp_server = prior_attr


def test_errors_are_values_and_say_where_the_names_are():
    tools.detach()
    _err(tools.sculpt_start("lens"), "no scene attached", "attach")
    _err(tools.list_flux_tubes(), "no scene attached")
    tools.attach(_scene())
    try:
        _err(tools.list_flux_tubes(), "not sculpting", "sculpt_start")
        _err(tools.sculpt_start("nope"), "no object named 'nope'", "can be sculpted: lens")
        _err(tools.sculpt_start("R"), "not a designed element")
        _err(tools.sculpt_start("lens", tubes=1), "tubes is 2 to 20")
        _ok(tools.sculpt_start("lens"))
        _err(tools.describe_flux_tube("T9"), "no tube 'T9'", "list_flux_tubes")
        _err(tools.preview_handle_move("lens/N/0", 1e-4), "no handle", "list_sculpt_handles")
        _err(tools.preview_handle_move("lens/N/12", "far"), "delta must be a number")
        _err(tools.preview_handle_move("lens/N/12", float("nan")), "finite")
        _err(tools.preview_handle_move("lens/N/12", 1e-4, kind="spin"), "kind is 'position'")
        _err(tools.list_sculpt_handles(edge="Q"), "no edge 'Q'", "N, X")
        _err(tools.list_sculpt_handles(tube_id="T9"), "list_flux_tubes")
        _err(tools.list_sculpt_handles(max_items=0), "max_items")
        refused = tools.apply_handle_move("lens/N/26", -1.0)
        _err(refused, "no longer a simple closed curve")
        assert [e["kind"] for e in refused["events"]] == ["outline_refused"]
    finally:
        tools.detach()


def test_a_session_from_start_to_report(session, tmp_path):
    tubes = _ok(tools.list_flux_tubes())["tubes"]
    assert len(tubes) == 8 and all(0 < t["delivered_fraction"] <= 1 for t in tubes)
    tube = _ok(tools.describe_flux_tube("E1/T3"))
    crossings = [c for c in tube["crossings"] if c.get("handles")]
    assert [c["edge"] for c in crossings] == ["N", "X"]
    crossed = {h["handle_id"] for h in _ok(tools.list_sculpt_handles(tube_id="E1/T3", max_items=100))["handles"]}
    assert set(crossings[0]["handles"]) & crossed and set(crossings[1]["handles"]) & crossed
    listed = _ok(tools.list_sculpt_handles())
    assert listed["shown"] == tools.MAX_HANDLES and listed["truncated"] and listed["total"] == 100
    x = _ok(tools.list_sculpt_handles(edge="X", max_items=100))["handles"]
    assert len(x) == 50 and all(h["edge"] == "X" for h in x)

    before = _ok(tools.sculpt_report(str(tmp_path / "a.svg")))
    preview = _ok(tools.preview_handle_move("lens/X/20", 1e-4))
    assert preview["trusted"] and len(preview["bundles"]) == 2
    assert _ok(tools.sculpt_report(str(tmp_path / "b.svg")))["edits"] == before["edits"] == []
    applied = _ok(tools.apply_handle_move("lens/X/20", 1e-4))
    assert applied["edits"] == 1
    for b, p in zip(applied["map_a"], preview["bundles"]):
        assert b["spread"] == pytest.approx(p["spread_after"], rel=0.02)    # the preview, borne out
    report = _ok(tools.sculpt_report(str(tmp_path / "c.svg")))
    assert report["edits"] == [{"edge": "X", "index": 20, "kind": "position", "delta": 1e-4}]
    assert report["map_a"]["start"] != report["map_a"]["now"]
    assert report["svg"]["bytes"] > 10_000 and report["svg"]["elements"]["sculpt-bundle-ray"] > 0
    assert (tmp_path / "c.svg").read_text().startswith("<svg")
    undone = _ok(tools.undo_handle_move())
    assert undone["sculpting"] and undone["edits"] == []
    assert undone["map_a"] == report["map_a"]["start"]


def test_an_attached_builder_is_refreshed_after_each_change():
    from ray_tracing_shapely.builder import SceneEditor

    class Builder:                                             # a widget's two members the tools use
        def __init__(self):
            self.editor, self.refreshed = SceneEditor(_scene(), quick_max_rays=0), 0

        def refresh(self):
            self.refreshed += 1

    builder = Builder()
    assert tools.attach(builder) is builder.editor
    try:
        _ok(tools.sculpt_start("lens", bundles=False))
        _ok(tools.preview_handle_move("lens/X/20", 1e-4))
        assert builder.refreshed == 2 and builder.editor.sculpt.preview is not None
    finally:
        tools.detach()


def test_a_coordinate_descent_by_the_tools_restores_a_perturbed_lens(session):
    def worst():
        return max(b["spread"] for b in _ok(tools.list_flux_tubes()) and tools._map_a(tools._editor().state()))
    start = worst()
    _ok(tools.apply_handle_move("lens/X/20", 0.002))                # the perturbation
    perturbed = worst()
    assert perturbed > 3 * start
    for _ in range(2):
        best = None
        for h in ("lens/X/19", "lens/X/20", "lens/X/21"):
            limit = next(x for x in _ok(tools.list_sculpt_handles(edge="X", max_items=100))["handles"]
                         if x["handle_id"] == h)["limit_position"]
            for delta in (k * limit for k in (-1, -0.5, -0.3, -0.15, 0.15, 0.3, 0.5, 1)):
                p = _ok(tools.preview_handle_move(h, delta))
                after = max(b["spread_after"] for b in p["bundles"])
                if p["trusted"] and (best is None or after < best[0]):
                    best = (after, h, delta)
        _ok(tools.apply_handle_move(best[1], best[2]))
    assert worst() < perturbed / 2 and math.isfinite(worst())
