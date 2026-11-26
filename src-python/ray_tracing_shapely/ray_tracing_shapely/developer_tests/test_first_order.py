"""
Python-specific module: test first order
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
The first-order change of a designed surface's rays, against a re-trace
===============================================================================
On the Example 9.1 RR lens (Chaves), baked to a plain curved glass so an edit
survives the scene's copy, a point source at E1 cut into 8 flux tubes:

- C-SCULPT-02: a handle moved by delta and by 2 delta (a point along its
  normal, a tangent turned): the predicted change of S, against the re-traced
  S brought to the old end point, has a residual that quadruples when delta
  doubles (second order), and a relative error within the bound measured;
- the outgoing direction at the moved surface likewise, the curvature term
  included (without it the error would be first order);
- a flat mirror tilted by dphi turns the reflected ray by 2 dphi; a flat glass
  face tilted by dphi turns the refracted ray by dphi (1 - n1 cos t1 / (n2
  cos t2)): finite differences of real traces against `turn_factor`;
- handles: every interior point of each spline edge, in both kinds, named by
  the edge's label; the outward normal points out of the glass; an end point,
  a straight edge, an unknown glass or kind is refused with the reason;
- an arrival that does not meet the moved edge is predicted unchanged.
===============================================================================
"""

import copy
import math

import pytest

from ray_tracing_shapely.analysis import first_order as fo
from ray_tracing_shapely.analysis import flux_tubes as ft
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.curved_glass import CurvedGlass
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens

E1, E2, R1, R2 = (-1.0, 2.0), (1.0, 2.0), (-0.5, -2.0), (0.5, -2.0)
#: Measured on this lens (top-surface handle 26): relative error of the predicted S change per unit
#: drag ratio, 12 for a point moved, 11 for a tangent turned. The bound tested leaves a margin.
OPL_BOUND = 15.0


def _rr_path():
    return copy.deepcopy(RRLens(Scene(), E1, E2, R1, R2, seed_n_angle_deg=303.3, seed_x_angle_deg=42.7,
                                n=1.5, etendue=1.0, n_points_per_section=5, name="lens").path)


PATH = _rr_path()


def scene_with(path):
    scene = Scene()
    glass = CurvedGlass(scene, {"path": copy.deepcopy(path), "refIndex": 1.5})
    glass.name = "lens"
    scene.add_object(glass)
    src = PointSource(scene, {"x": E1[0], "y": E1[1], "brightness": 0.5})
    src.name = "E1"
    scene.add_object(src)
    det = Detector(scene, {"p1": {"x": -0.6, "y": -2.0}, "p2": {"x": 0.6, "y": -2.0}})
    det.name = "R"
    scene.add_object(det)
    scene.ray_density = 2.0
    return scene


@pytest.fixture(scope="module")
def lens():
    scene = scene_with(PATH)
    return scene, ft.partition(scene, "R", ft.TubeSettings(tubes=8))


def _direct(arrival):
    return len(arrival.route) == 3


def _compare(scene, tubes, handle, delta):
    """Per direct arrival meeting the edge: (predicted, re-traced) change of S and of the first turn."""
    pred = fo.predict(scene, tubes, handle, delta)
    new = ft.replay(scene_with(fo.edited_path(scene, handle, delta)), tubes)
    out = []
    for t in tubes.tubes:
        moved = {(a.seed, a.route): a for a in new.tubes[t.tube_id].arrivals}
        for a, c in zip(t.arrivals, pred[t.tube_id]):
            b = moved.get((a.seed, a.route))
            if not c.hits or not _direct(a) or b is None:
                continue
            turn = math.remainder(math.atan2(*b.hits[0].p_out[::-1]) - math.atan2(*a.hits[0].p_out[::-1]), 2 * math.pi)
            first_on_edge = a.hits[0].surface == handle.glass and a.hits[0].edge == handle.edge
            out.append((c.dopl, fo.opl_at_old_end(b, a) - a.opl,
                        c.hits[0].dtheta * delta if first_on_edge else None, turn if first_on_edge else None))
    assert len(out) > 30, "the handle should move many of the lens's direct rays"
    return out


@pytest.mark.parametrize("kind, delta", [("position", 2e-5), ("normal", 0.02)])
def test_the_change_of_s_is_right_to_first_order(lens, kind, delta):
    """C-SCULPT-02."""
    scene, tubes = lens
    handle = fo.Handle("lens", 0, 26, kind)
    once, twice = _compare(scene, tubes, handle, delta), _compare(scene, tubes, handle, 2 * delta)
    res1 = max(abs(p - a) for p, a, _, _ in once)
    res2 = max(abs(p - a) for p, a, _, _ in twice)
    assert 3.8 < res2 / res1 < 4.2, f"the residual should be second order: x{res2 / res1:.2f} for delta doubled"
    rel = res1 / max(abs(a) for _, a, _, _ in once)
    assert rel < OPL_BOUND * fo.drag_ratio(scene, handle, delta), (rel, fo.drag_ratio(scene, handle, delta))


def test_the_turn_of_the_outgoing_ray_is_right_to_first_order_curvature_included(lens):
    scene, tubes = lens
    handle = fo.Handle("lens", 0, 26, "position")
    once = [(p, a) for _, _, p, a in _compare(scene, tubes, handle, 2e-5) if p is not None]
    twice = [(p, a) for _, _, p, a in _compare(scene, tubes, handle, 4e-5) if p is not None]
    res1, res2 = max(abs(p - a) for p, a in once), max(abs(p - a) for p, a in twice)
    assert 3.8 < res2 / res1 < 4.2
    assert res1 / max(abs(a) for _, a in once) < 1e-3       # measured 2.7e-4; 2e-2 without the curvature


def _traced_turn(scene_fn, angle, delta):
    """The outgoing direction's change, per radian of tilt, by central difference of two traces."""
    def out(a):
        scene = scene_fn(a)
        sim = Simulator(scene, max_rays=100, record_surface_hits=True)
        sim.run()
        root = sim.lineage.get_roots()[0]
        child = max(sim.lineage.get_children(root.uuid), key=lambda c: c.brightness_s + c.brightness_p)
        return root, child, math.atan2(child.p2["y"] - child.p1["y"], child.p2["x"] - child.p1["x"])
    root, child, _ = out(angle)
    (_, _, plus), (_, _, minus) = out(angle + delta), out(angle - delta)
    return root, child, math.remainder(plus - minus, 2 * math.pi) / (2 * delta)


def _p(seg):
    d = (seg.p2["x"] - seg.p1["x"], seg.p2["y"] - seg.p1["y"])
    length = math.hypot(*d)
    return (seg.medium_index * d[0] / length, seg.medium_index * d[1] / length)


def test_a_flat_mirror_tilted_turns_the_reflection_by_twice_the_tilt():
    def scene_fn(a):
        scene = Scene()
        m = Mirror(scene, {"p1": {"x": -math.cos(a), "y": -math.sin(a)}, "p2": {"x": math.cos(a), "y": math.sin(a)}})
        scene.add_object(m)
        ray = SingleRay(scene, {"p1": {"x": -0.3, "y": 1.0}, "p2": {"x": -0.2, "y": 0.0}, "brightness": 1.0})
        scene.add_object(ray)
        return scene
    root, child, traced = _traced_turn(scene_fn, 0.1, 1e-6)
    assert child.interaction_type == "reflect"
    factor = fo.turn_factor(_p(root), _p(child), (root.hit_normal["x"], root.hit_normal["y"]), "reflect")
    assert factor == 2.0 and abs(traced - 2.0) < 1e-6


def test_a_flat_glass_face_tilted_turns_the_refraction_as_snell_says():
    def scene_fn(a):
        scene = Scene()
        c, s = math.cos(a), math.sin(a)
        corners = [(-2, -2), (2, -2), (2, 0), (-2, 0)]        # the top face y = 0, tilted by a about the origin
        g = Glass(scene, {"path": [{"x": c * x - s * y, "y": s * x + c * y, "arc": False} for x, y in corners],
                          "refIndex": 1.5})
        scene.add_object(g)
        ray = SingleRay(scene, {"p1": {"x": -0.8, "y": 1.0}, "p2": {"x": -0.4, "y": 0.0}, "brightness": 1.0})
        scene.add_object(ray)
        return scene
    root, child, traced = _traced_turn(scene_fn, 0.05, 1e-6)
    assert child.interaction_type == "refract" and abs(child.medium_index - 1.5) < 1e-12
    factor = fo.turn_factor(_p(root), _p(child), (root.hit_normal["x"], root.hit_normal["y"]), "refract")
    assert abs(traced - factor) < 1e-6 and 0 < factor < 1


def test_handles_are_the_interior_points_of_each_spline_edge():
    scene = scene_with(PATH)
    hs = fo.handles(scene, "lens")
    assert len(hs) == 2 * 50 * 2 and {h.edge for h in hs} == {0, 2} and {h.kind for h in hs} == set(fo.KINDS)
    assert hs[0].handle_id == "lens/0/1"
    labelled = Scene()
    labelled.add_object(RRLens(labelled, E1, E2, R1, R2, seed_n_angle_deg=303.3, seed_x_angle_deg=42.7,
                               n=1.5, etendue=1.0, n_points_per_section=5, name="lens"))
    assert fo.handles(labelled, "lens", kinds=("position",))[0].handle_id == "lens/N/1"
    glass = scene.objs[0]
    cx = sum(v["x"] for v in glass.path) / 4
    cy = sum(v["y"] for v in glass.path) / 4
    for edge in (0, 2):
        span = fo._span(glass, edge)
        desc = glass.path[span.path_indices[0]]["curve"]
        nx, ny = fo.outward_normal(glass, span, 26)
        x, y = desc["points"][26]
        assert (x - cx) * nx + (y - cy) * ny > 0, f"edge {edge}'s normal should point out of the glass"
    moved = fo.edited_path(scene, fo.Handle("lens", 0, 26, "position"), 1e-3)
    before, after = glass.path[0]["curve"]["points"], moved[0]["curve"]["points"]
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [26]
    assert abs(math.dist(before[26], after[26]) - 1e-3) < 1e-15
    assert abs(fo.drag_ratio(scene, fo.Handle("lens", 0, 26, "normal"), 1.0) - math.radians(1.0)) < 1e-15


def test_refusals_say_why():
    scene = scene_with(PATH)
    with pytest.raises(fo.FirstOrderError, match="not interior"):
        fo.edited_path(scene, fo.Handle("lens", 0, 0, "position"), 1e-3)
    with pytest.raises(fo.FirstOrderError, match="not a spline"):
        fo.edited_path(scene, fo.Handle("lens", 1, 1, "position"), 1e-3)
    with pytest.raises(fo.FirstOrderError, match="no object named"):
        fo.handles(scene, "nowhere")
    with pytest.raises(fo.FirstOrderError, match="not a glass"):
        fo.handles(scene, "R")
    with pytest.raises(fo.FirstOrderError, match="not 'twist'"):
        fo.edited_path(scene, fo.Handle("lens", 0, 26, "twist"), 1.0)


def test_an_arrival_that_misses_the_edge_is_unchanged(lens):
    scene, tubes = lens
    pred = fo.predict(scene, tubes, fo.Handle("lens", 0, 26, "position"), 1e-4)
    changes = [c for cs in pred.values() for c in cs]
    assert any(not c.hits and c.dopl == 0.0 for c in changes)
    assert any(c.hits for c in changes)
