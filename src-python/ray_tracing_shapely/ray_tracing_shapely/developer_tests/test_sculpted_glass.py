"""
Python-specific module: test sculpted glass
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
A sculpted glass: a designed recipe and its edits, as one recipe
===============================================================================
On the Example 9.1 RR lens (Chaves):

- C-SCULPT-03: with no edits the glass is its base: the same outline, labels,
  roles, mechanisms and profile;
- an edit moves one Hermite point by delta along the outward normal, or turns
  its tangent, exactly as the first-order estimate's edit does; edits apply
  in order; a handle id names the same edit;
- the scene file holds the base and the edits, not the outline, and rebuilds
  the same glass; changing a delta in the file changes the shape (a sweep);
- C-SCULPT-04: an edit that breaks the outline, or names no handle, is
  refused with the reason, and a refused change in the builder leaves the
  scene as it was;
- the builder moves a sculpted glass whole by its base's placement, the edits
  unchanged;
- baked, it is a plain glass with the same outline and labels;
- flux tubes cut on a sculpted lens replay exactly: the edits survive the
  tubes' copy of the scene.
===============================================================================
"""

import json
import math

import pytest

from ray_tracing_shapely.analysis import first_order as fo
from ray_tracing_shapely.analysis import flux_tubes as ft
from ray_tracing_shapely.analysis import scene_file as sf
from ray_tracing_shapely.analysis.sculpted_glass import SculptError, SculptedGlass
from ray_tracing_shapely.builder import SceneEditor
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_profile
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens

ARGS = {"e1": [-1.0, 2.0], "e2": [1.0, 2.0], "r1": [-0.5, -2.0], "r2": [0.5, -2.0],
        "seed_n_angle_deg": 303.3, "seed_x_angle_deg": 42.7}
BASE = {"recipe": "RRLens", "args": ARGS}
EDITS = [{"edge": "N", "index": 26, "kind": "position", "delta": 0.002},
         {"edge": "X", "index": 20, "kind": "normal", "delta": -0.3}]


def _rr(scene=None):
    return RRLens(scene or Scene(), *(tuple(ARGS[k]) for k in ("e1", "e2", "r1", "r2")),
                  seed_n_angle_deg=303.3, seed_x_angle_deg=42.7, name="lens")


def _profile(glass):
    return json.dumps(export_profile(glass, symmetry={"kind": "free"}, physical_params={}, numerical_params={}),
                      sort_keys=True, default=str)


def _shifted(path, dx, dy):
    out = []
    for v in path:
        w = dict(v, x=v["x"] + dx, y=v["y"] + dy)
        if v.get("curve"):
            w["curve"] = dict(v["curve"], points=[[x + dx, y + dy] for x, y in v["curve"]["points"]])
        out.append(w)
    return out


def _close(a, b, tol=1e-9):
    assert len(a) == len(b)
    for u, v in zip(a, b):
        assert abs(u["x"] - v["x"]) < tol and abs(u["y"] - v["y"]) < tol
        cu, cv = u.get("curve"), v.get("curve")
        assert (cu is None) == (cv is None)
        if cu:
            for key in ("points", "tangents"):
                for p, q in zip(cu[key], cv[key]):
                    assert math.dist(p, q) < tol


def test_with_no_edits_the_glass_is_its_base():
    base = _rr()
    glass = SculptedGlass(Scene(), BASE, [], name="lens")
    assert glass.path == base.path
    assert glass._functional_labels == base._functional_labels
    assert glass._edge_role_tags == base._edge_role_tags
    assert glass._edge_mechanisms == base._edge_mechanisms
    assert glass.refIndex == base.refIndex
    assert _profile(glass) == _profile(base)


def test_an_edit_moves_one_point_as_the_estimate_s_edit_does():
    scene = Scene()
    scene.add_object(SculptedGlass(scene, BASE, [], name="lens"))
    for edit in EDITS:
        handle = next(h for h in fo.handles(scene, "lens") if h.label == edit["edge"]
                      and (h.index, h.kind) == (edit["index"], edit["kind"]))
        expected = fo.edited_path(scene, handle, edit["delta"])
        got = SculptedGlass(Scene(), BASE, [edit], name="lens")
        assert got.path == expected
    one = SculptedGlass(Scene(), BASE, [EDITS[0]]).path[0]["curve"]["points"]
    before = _rr().path[0]["curve"]["points"]
    assert math.dist(one[26], before[26]) == pytest.approx(0.002, abs=1e-15)
    assert all(one[i] == before[i] for i in range(len(one)) if i != 26)
    # in order: two moves of one point along its (unchanged) normal add up
    twice = SculptedGlass(Scene(), BASE, [EDITS[0], EDITS[0]]).path
    once = SculptedGlass(Scene(), BASE, [dict(EDITS[0], delta=0.004)]).path
    _close(twice, once, 1e-15)
    by_id = SculptedGlass(Scene(), BASE, [{"handle_id": "renamed/N/26", "kind": "position", "delta": 0.002}])
    assert by_id.path == SculptedGlass(Scene(), BASE, [EDITS[0]]).path
    assert by_id.edits == [EDITS[0]]


def test_the_scene_file_holds_the_edits_and_rebuilds_the_glass():
    scene = Scene()
    scene.add_object(SculptedGlass(scene, BASE, EDITS, name="lens"))
    data = json.loads(json.dumps(sf.scene_to_dict(scene)))
    entry = data["objects"][0]
    assert entry["recipe"] == "SculptedGlass"
    assert entry["args"]["base"]["recipe"] == "RRLens" and entry["args"]["edits"] == EDITS
    assert "path" not in json.dumps(entry["args"])
    rebuilt = sf.scene_from_dict(data).objs[0]
    assert isinstance(rebuilt, SculptedGlass) and rebuilt.path == scene.objs[0].path
    entry["args"]["edits"][0]["delta"] = 0.004                      # a sweep varies a delta
    swept = sf.scene_from_dict(data).objs[0]
    assert swept.path != rebuilt.path
    assert swept.path == SculptedGlass(Scene(), BASE, [dict(EDITS[0], delta=0.004), EDITS[1]]).path


@pytest.mark.parametrize("edits,reason", [
    ([{"edge": "N", "index": 26, "kind": "position", "delta": -1.0}], "no longer a simple closed curve"),
    ([{"edge": "N", "index": 26, "kind": "normal", "delta": 179.0}], "no longer a simple closed curve"),
    ([{"edge": "N", "index": 0, "kind": "position", "delta": 0.1}], "not interior"),
    ([{"edge": "Q", "index": 3, "kind": "position", "delta": 0.1}], "no edge labelled 'Q'"),
    ([{"edge": "RIM", "index": 1, "kind": "position", "delta": 0.1}], "not a spline"),
    ([{"edge": "N", "index": 3, "kind": "spin", "delta": 0.1}], "position or normal"),
    ([{"edge": "N", "index": 3, "kind": "position", "delta": float("nan")}], "finite"),
    ([{"edge": "N", "kind": "position", "delta": 0.1}], "missing index"),
])
def test_an_edit_that_breaks_the_outline_or_names_no_handle_is_refused(edits, reason):
    scene = Scene()
    with pytest.raises(SculptError, match=reason):
        SculptedGlass(scene, BASE, edits)
    assert scene.objs == []


def test_a_base_that_is_not_a_designed_glass_is_refused():
    with pytest.raises(SculptError, match="no recipe 'Nothing'"):
        SculptedGlass(Scene(), {"recipe": "Nothing", "args": {}})
    with pytest.raises(SculptError, match="not another sculpted glass"):
        SculptedGlass(Scene(), {"recipe": "SculptedGlass", "args": {"base": BASE}})
    with pytest.raises(SculptError, match="could not be built"):
        SculptedGlass(Scene(), {"recipe": "RRLens", "args": {"e1": [0, 0]}})
    with pytest.raises(SculptError, match="not a glass"):
        SculptedGlass(Scene(), {"recipe": "ConicMirror", "args": {"vertex": [0, 0], "axis": [0, 1], "radius": 5, "semi_diameter": 2}})


def _editor_with_sculpted():
    scene = Scene()
    scene.add_object(SculptedGlass(scene, BASE, EDITS, name="lens"))
    e = SceneEditor(scene, quick_max_rays=500)
    e.scene.scale = 10.0
    return e


def test_a_refused_edit_in_the_builder_leaves_the_scene_as_it_was():
    e = _editor_with_sculpted()
    before = sf.scene_to_dict(e.scene)
    s = e.handle({"type": "set", "name": "lens", "key": "edits",
                  "value": [{"edge": "N", "index": 26, "kind": "position", "delta": -1.0}]})
    assert "no longer a simple closed curve" in s["error"]
    assert sf.scene_to_dict(e.scene) == before
    s = e.handle({"type": "set", "name": "lens", "key": "edits", "value": EDITS[:1]})
    assert s["error"] is None
    assert e._obj("lens").edits == EDITS[:1]


def test_the_builder_moves_a_sculpted_glass_whole_by_its_base():
    e = _editor_with_sculpted()
    before = e._obj("lens").path
    v = before[1]
    s = e.handle({"type": "press", "x": v["x"], "y": v["y"]})
    assert s["error"] is None and s["drag"]["whole"] is True
    s = e.handle({"type": "release", "x": v["x"] + 2, "y": v["y"] + 1})
    assert s["error"] is None, s["error"]
    moved = e._obj("lens")
    args = moved._construction_args
    assert args["base"]["args"]["e1"] == pytest.approx([1.0, 3.0])
    assert list(args["edits"]) == EDITS
    _close(moved.path, _shifted(before, 2.0, 1.0))


def test_baked_it_is_a_plain_glass_with_the_same_outline_and_labels():
    glass = SculptedGlass(Scene(), BASE, EDITS, name="lens")
    baked = glass.bake()
    assert type(baked) is BasePrism and baked.name == "lens"
    assert baked._functional_labels == glass._functional_labels
    _close(baked.path, glass.path)


def test_tubes_cut_on_a_sculpted_lens_replay_exactly():
    scene = Scene()
    scene.ray_density = 2.0
    scene.add_object(SculptedGlass(scene, BASE, EDITS, name="lens"))
    src = PointSource(scene, {"x": -1.0, "y": 2.0, "brightness": 0.5})
    src.name = "E1"
    scene.add_object(src)
    det = Detector(scene, {"p1": {"x": -0.6, "y": -2.0}, "p2": {"x": 0.6, "y": -2.0}})
    det.name = "R"
    scene.add_object(det)
    tubes = ft.partition(scene, "R")
    again = ft.replay(scene, tubes)
    for t in tubes.tubes:
        a = sorted((x.seed, x.route, round(x.opl, 9)) for x in t.arrivals)
        b = sorted((x.seed, x.route, round(x.opl, 9)) for x in again.tubes[t.tube_id].arrivals)
        assert a == b
