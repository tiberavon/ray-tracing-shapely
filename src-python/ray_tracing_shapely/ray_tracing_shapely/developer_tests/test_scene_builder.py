"""
Python-specific module: test scene builder
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
The scene builder, driven by messages, with no browser
===============================================================================
- Mouse: the click extent follows the zoom; grid and direction snapping, and
  the direction lock, as Mouse.js.
- The editing hooks, against outcomes worked by hand from the JavaScript
  simulator's rules: a line's endpoint with ctrl (mirrored about the middle)
  and shift (snapped to a direction), the whole line; a glass vertex and the
  whole glass; a point source; a spherical lens kept symmetric.
- SceneEditor: every palette primitive constructed by pointer messages; a
  designed element placed from its arguments and moved by its placement only;
  properties set through key paths; a refused change leaves the scene as it
  was; ctrl leaves a copy; undo, redo, save and open; the state is JSON.
- What the page needs beyond the drawing: a point object's position (picked
  within the click extent, its dot being smaller), and each object's designed
  element and recipe (the scene's tree).
===============================================================================
"""

import json
import math

import pytest

from ray_tracing_shapely.analysis import scene_file as sf
from ray_tracing_shapely.builder import PALETTE_PRIMITIVES, SceneEditor
from ray_tracing_shapely.core.mouse import Mouse, MousePoint
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror

SINGLET = {"radius_front": 30, "radius_back": -30, "thickness": 4, "semi_diameter": 8}


def _editor():
    e = SceneEditor(quick_max_rays=500)
    e.scene.scale = 10.0                      # 10 px a unit: a click reaches 1 unit
    return e


def _send(e, kind, x=None, y=None, **keys):
    m = {"type": kind, **keys}
    if x is not None:
        m.update(x=x, y=y)
    s = e.handle(m)
    assert s["error"] is None, s["error"]
    return s


def _build(e, tool, a, b):
    _send(e, "tool", name=tool)
    _send(e, "press", *a)
    return _send(e, "release", *b)


def _drag(e, a, b, **keys):
    _send(e, "press", *a)
    return _send(e, "release", *b, **keys)


# --- Mouse --------------------------------------------------------------------

def test_the_click_extent_is_ten_screen_pixels_whatever_the_zoom():
    scene = Scene()
    scene.scale = 10.0
    assert Mouse({"x": 0, "y": 0}, scene).get_click_extent(True) == pytest.approx(1.0)
    assert Mouse({"x": 0.9, "y": 0}, scene).is_on_point({"x": 0, "y": 0})
    scene.scale = 2.0
    assert Mouse({"x": 4.9, "y": 0}, scene).is_on_point({"x": 0, "y": 0})
    assert Mouse({"x": 3, "y": 4.9}, scene).is_on_segment(Mirror(scene, {"p1": {"x": 0, "y": 0},
                                                                          "p2": {"x": 10, "y": 0}}))


def test_snapping_to_the_grid_and_to_directions_with_the_lock():
    scene = Scene()
    scene.snap_to_grid, scene.grid_size = True, 5.0
    assert Mouse({"x": 7.4, "y": -2.6}, scene).get_pos_snapped_to_grid() == {"x": 5.0, "y": -5.0}
    assert Mouse({"x": 7.4, "y": -2.6}, scene, override_grid=1).get_pos_snapped_to_grid() == {"x": 7.4, "y": -2.6}
    scene.snap_to_grid, scene.scale = False, 1.0
    dirs = [{"x": 1, "y": 0}, {"x": 0, "y": 1}]
    ctx = {}
    p = Mouse({"x": 40, "y": 3}, scene).get_pos_snapped_to_direction({"x": 0, "y": 0}, dirs, ctx)
    assert p == {"x": 40, "y": 0} and ctx == {"locked": True, "i0": 0}       # beyond 30 px: locked
    p = Mouse({"x": 3, "y": 40}, scene).get_pos_snapped_to_direction({"x": 0, "y": 0}, dirs, ctx)
    assert p == {"x": 3, "y": 0}                                              # still horizontal


def test_a_mouse_point_is_a_dict_and_has_attributes():
    p = MousePoint(1.5, -2.0)
    assert p == {"x": 1.5, "y": -2.0} and (p.x, p.y) == (1.5, -2.0)
    assert json.loads(json.dumps(p)) == {"x": 1.5, "y": -2.0}


# --- the hooks, as upstream's ------------------------------------------------------

def test_a_line_endpoint_with_ctrl_is_mirrored_about_the_middle_and_with_shift_snapped():
    e = _editor()
    _build(e, "Mirror", (0, 0), (10, 0))
    _drag(e, (10, 0), (12, 2), ctrl=True)            # midpoint (5, 0) stays: p1 = 2*(5, 0) - (12, 2)
    m = e._obj("Mirror1")
    assert (m.p1, m.p2) == ({"x": -2, "y": -2}, {"x": 12, "y": 2})
    # from p1 (-2, -2) the pointer is (22, 20) away: of 0°, 90°, ±45° and the mirror's own
    # direction (14, 4), 45° is nearest (squared distances 2 against 228 and more)
    _drag(e, (12, 2), (20, 18), shift=True)
    assert m.p2["x"] - m.p1["x"] == pytest.approx(m.p2["y"] - m.p1["y"])     # 45°


def test_dragging_a_line_s_middle_moves_it_by_the_pointer_s_displacement():
    e = _editor()
    _build(e, "Blocker", (0, 0), (10, 0))
    _drag(e, (5, 0), (8, 4))
    b = e._obj("Blocker1")
    assert (b.p1, b.p2) == ({"x": 3, "y": 4}, {"x": 13, "y": 4})


def test_a_glass_is_built_by_clicks_and_closed_on_its_first_vertex_then_dragged():
    e = _editor()
    _send(e, "tool", name="Glass")
    for x, y in [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]:
        _send(e, "press", x, y)
        s = _send(e, "release", x, y)
    assert not s["constructing"]
    g = e._obj("Glass1")
    assert [(p["x"], p["y"]) for p in g.path] == [(0, 0), (10, 0), (10, 10), (0, 10)]
    _drag(e, (10, 10), (12, 13))                     # a vertex
    assert (g.path[2]["x"], g.path[2]["y"]) == (12, 13)
    _drag(e, (5, 0), (9, 1), shift=True)             # an edge: the whole glass, snapped horizontal
    assert [(p["x"], p["y"]) for p in g.path] == [(4, 0), (14, 0), (16, 13), (4, 10)]


def test_a_point_source_is_placed_by_a_click_and_dragged():
    e = _editor()
    _build(e, "PointSource", (1, 2), (1, 2))
    _drag(e, (1, 2), (-3, 5))
    p = e._obj("PointSource1")
    assert (p.x, p.y) == (-3, 5)


def test_a_spherical_lens_rim_drag_keeps_it_symmetric_about_its_axis():
    e = _editor()
    _build(e, "SphericalLens", (0, -20), (0, 20))
    lens = e._obj("SphericalLens1")
    path = lens.path
    before_axis = [(p["x"] + q["x"]) / 2 for p, q in ((path[0], path[1]), (path[4], path[3]))]
    _drag(e, (path[0]["x"], path[0]["y"]), (path[0]["x"] - 3, path[0]["y"]))   # the rim, outwards
    path = lens.path
    half = [abs(path[1]["x"] - path[0]["x"]) / 2, abs(path[3]["x"] - path[4]["x"]) / 2]
    assert half[0] == pytest.approx(half[1])                 # both rims the same thickness
    assert [(p["x"] + q["x"]) / 2 for p, q in ((path[0], path[1]), (path[4], path[3]))] == \
        pytest.approx(before_axis)                           # on the same axis
    assert lens.serialize()["path"]                          # still a lens that saves


# --- the editor -------------------------------------------------------------------

@pytest.mark.parametrize("tool", PALETTE_PRIMITIVES)
def test_every_palette_primitive_is_built_by_pointer_messages_and_saves(tool):
    e = _editor()
    if tool == "Glass":
        _send(e, "tool", name=tool)
        for x, y in [(0, 0), (10, 0), (10, 10), (0, 0)]:
            _send(e, "press", x, y)
            _send(e, "release", x, y)
    else:
        _build(e, tool, (0, 0), (0, 0) if tool == "PointSource" else (0, 20))
    s = e.state()
    assert [o["name"] for o in s["objects"]] == [f"{tool}1"] and s["selected"]["name"] == f"{tool}1"
    assert sf.scene_from_dict(sf.scene_to_dict(e.scene)).objs[0].name == f"{tool}1"


def test_a_designed_element_is_placed_from_its_arguments_and_moved_by_its_placement_only(tmp_path):
    e = _editor()
    s = e.handle({"type": "tool", "name": "SingletLens"})
    assert "needs radius_front" in s["error"]
    _send(e, "tool", name="SingletLens", args=SINGLET)
    _send(e, "press", 20, 5)
    s = _send(e, "release", 20, 5)
    assert s["selected"]["kind"] == "recipe" and s["selected"]["handles"] == []
    lens = e._obj("SingletLens1")
    v = lens.path[0]
    s = _send(e, "press", v["x"], v["y"])                    # on a vertex: still the whole element
    assert s["drag"]["whole"] is True
    _send(e, "release", v["x"] + 10, v["y"] + 3)
    assert e._obj("SingletLens1")._construction_args["position"] == pytest.approx([30, 8])
    path = tmp_path / "lens.scene.json"
    _send(e, "save", path=str(path))
    entry = json.loads(path.read_text())["objects"][0]
    assert entry["recipe"] == "SingletLens" and entry["args"]["position"] == pytest.approx([30, 8])


def test_a_refused_change_leaves_the_scene_as_it_was():
    e = _editor()
    _send(e, "tool", name="SingletLens", args=SINGLET)
    _send(e, "press", 0, 0)
    _send(e, "release", 0, 0)
    before = sf.scene_to_dict(e.scene)
    s = e.handle({"type": "set", "name": "SingletLens1", "key": "thickness", "value": -1})
    assert "thickness must be positive" in s["error"]
    assert sf.scene_to_dict(e.scene) == before
    s = e.handle({"type": "set", "name": "SingletLens1", "key": "no_such", "value": 1})
    assert "no argument 'no_such'" in s["error"]
    _send(e, "set", name="SingletLens1", key="thickness", value=6)
    assert e._obj("SingletLens1")._construction_args["thickness"] == 6


def test_a_primitive_s_properties_are_set_by_key_path():
    e = _editor()
    _build(e, "Beam", (0, 0), (0, 20))
    _send(e, "set", name="Beam1", key="emisAngle", value=15)
    _send(e, "set", name="Beam1", key="p2.y", value=30)
    beam = e._obj("Beam1")
    assert beam.emisAngle == 15 and beam.p2["y"] == 30
    s = e.handle({"type": "set", "name": "Beam1", "key": "bogus", "value": 1})
    assert "no property 'bogus'" in s["error"]


def test_ctrl_on_a_whole_object_drag_leaves_a_copy_and_a_click_only_selects():
    e = _editor()
    _build(e, "Mirror", (0, 0), (10, 0))
    undo_depth = len(e._undo)
    _drag(e, (5, 0), (5, 0))                               # a click
    assert len(e._undo) == undo_depth and e.selected == "Mirror1"
    _drag(e, (5, 0), (5, 10), ctrl=True)
    names = {o.name: (o.p1, o.p2) for o in e.scene.objs}
    assert names["Mirror1"] == ({"x": 0, "y": 10}, {"x": 10, "y": 10})
    assert names["Mirror2"] == ({"x": 0, "y": 0}, {"x": 10, "y": 0})


def test_undo_redo_save_and_open(tmp_path):
    e = _editor()
    _build(e, "Mirror", (0, 0), (10, 0))
    _build(e, "PointSource", (5, 5), (5, 5))
    assert [o["name"] for o in _send(e, "undo")["objects"]] == ["Mirror1"]
    assert [o["name"] for o in _send(e, "redo")["objects"]] == ["Mirror1", "PointSource1"]
    _send(e, "settings", snap_to_grid=True, grid_size=2.5)
    path = tmp_path / "s.scene.json"
    _send(e, "save", path=str(path))
    other = SceneEditor()
    s = other.handle({"type": "open", "path": str(path)})
    assert s["error"] is None and [o["name"] for o in s["objects"]] == ["Mirror1", "PointSource1"]
    assert s["settings"]["snap_to_grid"] is True and s["settings"]["grid_size"] == 2.5
    assert sf.scene_to_dict(other.scene)["objects"] == sf.scene_to_dict(e.scene)["objects"]


def test_the_state_is_json_and_the_view_zooms_about_a_point():
    e = _editor()
    _build(e, "Beam", (0, -5), (0, 5))
    _build(e, "Detector", (30, -10), (30, 10))
    s = e.state()
    json.dumps(s)
    assert all(o["uuid"] in s["svg"] for o in s["objects"])      # the page finds them in the drawing
    assert s["trace"]["segments"] > 0
    vb = s["view"]["viewbox"]
    s = _send(e, "view", zoom=2, x=vb[0], y=vb[1])
    assert s["view"]["viewbox"][:2] == pytest.approx(vb[:2]) and s["view"]["viewbox"][2] == pytest.approx(vb[2] / 2)


def test_the_widget_applies_messages_with_no_browser():
    pytest.importorskip("anywidget")
    from ray_tracing_shapely.builder import scene_builder
    w = scene_builder(quick_max_rays=200)
    w.handle({"type": "tool", "name": "Mirror"})
    w.handle({"type": "press", "x": 0, "y": 0})
    s = w.handle({"type": "release", "x": 10, "y": 0})
    assert s["error"] is None and [o["name"] for o in s["objects"]] == ["Mirror1"]
    assert "files" in w.state and w.scene is w.editor.scene
    assert math.isfinite(w.state["view"]["scale"])


# --- the web simulator's files, the live construction, the curved mirrors -------

def test_the_builder_opens_a_web_simulator_file_and_exports_one(tmp_path):
    web = {"version": 5, "objs": [{"type": "Mirror", "p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}},
                                  {"type": "Ruler", "p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}]}
    src = tmp_path / "from_web.json"
    src.write_text(json.dumps(web))
    e = _editor()
    s = e.handle({"type": "open", "path": str(src)})
    assert s["error"] is None and [o["name"] for o in s["objects"]] == ["Mirror1"]
    assert "Left out: Ruler" in s["notice"]
    out = tmp_path / "back.web.json"
    s = _send(e, "export_web", path=str(out))
    assert json.loads(out.read_text())["objs"] == [web["objs"][0]] and "exported" in s["notice"]


def test_a_polygon_s_next_point_follows_the_pointer_between_clicks():
    e = _editor()
    _send(e, "tool", name="Glass")
    for x, y in [(0, 0), (10, 0)]:
        _send(e, "press", x, y)
        _send(e, "release", x, y)
    _send(e, "move", 7, 9)
    assert (e._constructing.path[-1]["x"], e._constructing.path[-1]["y"]) == (7, 9)


def test_a_curved_mirror_without_hooks_is_grabbed_where_drawn_and_moved_by_its_vertex_only():
    e = _editor()
    _send(e, "tool", name="CircularArcMirror", args={"vertex": [0, 0], "axis": [1, 0], "radius": 20,
                                                     "semi_diameter": 5})
    _send(e, "press", 0, 0)
    _send(e, "release", 0, 0)
    s = _send(e, "press", 0.5, 0.5, target="CircularArcMirror1")   # the page names what it drew there
    assert s["drag"]["whole"] is True
    _send(e, "release", 3.5, 4.5)
    args = e._obj("CircularArcMirror1")._construction_args
    assert list(args["vertex"]) == pytest.approx([3, 4]) and list(args["axis"]) == [1, 0]


def test_the_state_gives_point_objects_their_place_and_parts_their_element():
    from ray_tracing_shapely.optical_elements.prisms.xr_concentrator import XRConcentrator
    ed = SceneEditor()
    for m in ({"type": "tool", "name": "PointSource"}, {"type": "press", "x": 3, "y": 4},
              {"type": "release", "x": 3, "y": 4}, {"type": "tool", "name": "Mirror"},
              {"type": "press", "x": 10, "y": 0}, {"type": "release", "x": 10, "y": 20}):
        assert ed.handle(m)["error"] is None
    xr = XRConcentrator(ed.scene, (39.5, 30.0), (40.5, 30.0), theta_deg=2.0, p0=(40.0, 26.0), n0=(0.0, -1.0), n=1.5)
    ed.scene.add_object(xr)
    for m in xr.primary:
        ed.scene.add_object(m)
    ed._name_all()
    objects = {o["name"]: o for o in json.loads(json.dumps(ed.state()))["objects"]}
    src = next(o for o in objects.values() if o["type"] == "PointSource")
    assert src["at"] == [3, 4] and src["owner"] is None and src["recipe"] is None
    assert all("at" not in o for o in objects.values() if o["type"] != "PointSource")
    element = objects[xr.name]
    parts = [o for o in objects.values() if o["owner"] == xr.name]
    assert element["owner"] is None and element["recipe"] == "XRConcentrator"
    assert parts and all(p["recipe"] == "XRConcentrator" and p["type"] == "SplineMirror" for p in parts)
    assert ed.handle({"type": "select", "name": parts[0]["name"]})["selected"]["name"] == xr.name   # a part selects its element
