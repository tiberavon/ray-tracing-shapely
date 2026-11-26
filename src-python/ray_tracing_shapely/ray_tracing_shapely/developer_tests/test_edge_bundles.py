"""
Python-specific module: test edge bundles
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
Map A, the edge bundles of the Example 9.1 RR lens (Chaves), against the design
===============================================================================
- KD5: on the unedited lens, a ray from E1 aimed through a designed point of
  the N surface that leaves by a designed point of the X surface has the
  design's S to R2 (|R2 - X| + S_XE1, from the book's S_XE1) and passes
  through R2, to round-off; likewise E2 to R1. Between the points, the
  spline's interpolation error; near the axis, the waist the book notes;
- the two bundles are mirror images: one mean, one spread;
- the fan rays through the seed point's corner have the design's S and miss
  the target: S alone does not see it, the miss does;
- C-SCULPT-05: a segment that carries no index is reported, and its ray is
  out of the mean, not counted with n = 1;
- the first order of S to the target, against a re-trace: second order in the
  move, for a point moved and a tangent turned, on the entrance and the exit;
- the scene's own sources are left out, the caller's scene untouched; the set
  round-trips through JSON; the refusals say why.
===============================================================================
"""

import copy
import json
import math

import pytest

from ray_tracing_shapely.analysis import edge_bundles as eb
from ray_tracing_shapely.analysis import first_order as fo
from ray_tracing_shapely.analysis import flux_tubes as ft
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.optical_elements.curved_glass import CurvedGlass
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens

E1, E2, R1, R2 = (-1.0, 2.0), (1.0, 2.0), (-0.5, -2.0), (0.5, -2.0)
#: Measured on this lens: the first-order error of S to the target, relative to the largest change,
#: per unit drag ratio. Entrance (N): 4-29 for a point moved, 9-92 for a tangent turned (the inside
#: ray turns, and the lens's thickness is its lever arm); exit (X): 0.1-0.6. The bounds leave a margin.
ENTRANCE_BOUND, EXIT_BOUND = 120.0, 1.0


def _lens(scene=None):
    return RRLens(scene or Scene(), E1, E2, R1, R2, seed_n_angle_deg=303.3, seed_x_angle_deg=42.7,
                  n=1.5, etendue=1.0, n_points_per_section=5, name="lens")


LENS = _lens()
SPECS = eb.rr_bundles(LENS)
#: The design's S along an edge ray, E1 to R2 (and E2 to R1 by symmetry): Chaves Ch. 9's S_RE1.
S_DESIGN = math.dist(R2, LENS.seed_X) + LENS.S_XE1


def baked(path=None):
    scene = Scene()
    glass = CurvedGlass(scene, {"path": copy.deepcopy(path or LENS.path), "refIndex": 1.5})
    glass.name = "lens"
    scene.add_object(glass)
    return scene


@pytest.fixture(scope="module")
def bundles():
    scene = Scene()
    scene.add_object(_lens(scene))
    src = PointSource(scene, {"x": 0.0, "y": 3.0, "brightness": 0.5})
    src.name = "P"
    scene.add_object(src)
    return eb.edge_bundles(scene, SPECS)


@pytest.fixture(scope="module")
def baked_bundles():
    return eb.edge_bundles(baked(), SPECS)


def test_rays_through_designed_points_have_the_designs_s(bundles):
    for b in bundles.bundles:
        exact = [r for r in b.counted if r.knot and r.exit_knot]
        assert len(exact) >= 40, b.bundle_id
        assert max(abs(r.opl - S_DESIGN) for r in exact) < 1e-12
        assert max(abs(r.miss) for r in exact) < 1e-10
        # between the designed points: the spline's interpolation, away from the axis's waist
        between = [r for r in b.counted if not r.knot and abs(r.entry[0]) > 0.3]
        assert max(abs(r.opl - S_DESIGN) for r in between) < 2e-7
        # the waist: designed points near the axis whose ray does not leave by a designed point
        waist = [r for r in b.counted if r.knot and not r.exit_knot]
        assert waist and all(abs(r.entry[0]) < 0.3 for r in waist)
        assert 1e-4 < b.spread < 3e-4


def test_the_two_bundles_are_mirror_images(bundles):
    a, b = bundles.map_a()
    assert abs(a["mean"] - b["mean"]) < 1e-12
    assert abs(a["spread"] - b["spread"]) < 1e-12
    assert a["counted"] == b["counted"]


def test_the_fan_through_the_corner_has_the_designs_s_and_misses_the_target(bundles):
    b = bundles.bundle("E1->R2")
    corner = [r for r in b.counted if math.dist(r.exit, LENS.seed_X) < 1e-6]
    assert len(corner) >= 4
    assert max(abs(r.opl - S_DESIGN) for r in corner) < 1e-7      # S says nothing is wrong
    assert max(abs(r.miss) for r in corner) > 0.1                  # the miss does
    assert bundles.map_a()[0]["max_miss"] > 0.1


def test_a_segment_without_an_index_is_reported_not_counted(monkeypatch):
    from ray_tracing_shapely.core.ray_lineage import RayLineage
    original = RayLineage.get_full_path

    def stripped(self, uuid):
        path = original(self, uuid)
        if len(path) > 1 and 0.3 < path[0].p2["x"] < 0.45:        # the rays entering there: inside, no index
            path[1].__dict__.pop("medium_index", None)
        return path

    monkeypatch.setattr(RayLineage, "get_full_path", stripped)
    got = eb.edge_bundles(baked(), SPECS[:1], eb.BundleSettings(per_span=1))
    b = got.bundles[0]
    reported = [r for r in b.rays if r.unindexed]
    assert reported and all(r.opl is None for r in reported)
    assert all(r.seed not in b.deviations() for r in reported)
    assert got.map_a()[0]["unindexed"] == [r.seed for r in reported]


def _check_first_order(base_set, handle, delta, bound):
    scene = baked()
    residuals, largest = [], 0.0
    for d in (delta, 2 * delta):
        new = eb.trace_bundles(baked(fo.edited_path(scene, handle, d)), base_set)
        pred = eb.predict(scene, base_set, handle, d)
        worst = 0.0
        for b, nb in zip(base_set.bundles, new.bundles):
            old, now = {r.seed: r.opl for r in b.counted}, {r.seed: r.opl for r in nb.counted}
            for seed, dp in pred[b.bundle_id].items():
                if seed in now:
                    worst = max(worst, abs(now[seed] - old[seed] - dp))
                    if d == delta:
                        largest = max(largest, abs(now[seed] - old[seed]))
        residuals.append(worst)
    assert largest > 0.0
    assert 3.8 < residuals[1] / residuals[0] < 4.2                 # second order
    assert residuals[0] / largest < bound * fo.drag_ratio(scene, handle, delta)


@pytest.mark.parametrize("edge,index,kind,delta,bound", [
    (0, 12, "position", 1e-5, ENTRANCE_BOUND), (0, 12, "normal", 0.005, ENTRANCE_BOUND),
    (2, 20, "position", 1e-5, EXIT_BOUND), (2, 20, "normal", 0.005, EXIT_BOUND),
])
def test_the_first_order_of_s_to_the_target_is_right(baked_bundles, edge, index, kind, delta, bound):
    handle = next(h for h in fo.handles(baked(), "lens") if (h.edge, h.index, h.kind) == (edge, index, kind))
    _check_first_order(baked_bundles, handle, delta, bound)


def test_the_scene_is_untouched_and_the_set_round_trips(bundles):
    scene = baked()
    before = [o.name for o in scene.objs]
    eb.edge_bundles(scene, SPECS[:1], eb.BundleSettings(per_span=1))
    assert [o.name for o in scene.objs] == before
    data = json.loads(json.dumps(bundles.to_dict()))
    again = eb.BundleSet.from_dict(data)
    assert again.map_a() == bundles.map_a()
    assert again.bundles[0].rays == bundles.bundles[0].rays
    knots_only = eb.edge_bundles(baked(), SPECS[:1], eb.BundleSettings(per_span=1))
    assert all(r.knot for r in knots_only.bundles[0].rays)
    assert len(knots_only.bundles[0].rays) == len(LENS.path[0]["curve"]["points"])


def test_refusals_say_why():
    from ray_tracing_shapely.core.scene_objs.base_grin_glass import BaseGrinGlass

    class Grin(BaseGrinGlass):
        type = "test_grin"

    with pytest.raises(eb.EdgeBundleError, match="takes an RRLens"):
        eb.rr_bundles(baked().objs[0])
    with pytest.raises(eb.EdgeBundleError, match="no object named 'other'"):
        eb.edge_bundles(baked(), [eb.BundleSpec("B", "other", E1, R2, 0, 2)])
    with pytest.raises(eb.EdgeBundleError, match="not a designed spline"):
        eb.edge_bundles(baked(), [eb.BundleSpec("B", "lens", E1, R2, 1, 2)])
    with pytest.raises(eb.EdgeBundleError, match="share an id"):
        eb.edge_bundles(baked(), [SPECS[0], SPECS[0]])
    with pytest.raises(eb.EdgeBundleError, match="per_span"):
        eb.BundleSettings(per_span=0)
    scene = baked()
    grin = Grin(scene, {"refIndexFn": "1.5", "absorptionFn": "0", "origin": {"x": 5, "y": 5},
                        "stepSize": 0.1, "intersectTol": 0.001})
    grin.name = "grin"
    scene.add_object(grin)
    with pytest.raises(ft.FluxTubeError, match="gradient-index glass"):
        eb.edge_bundles(scene, SPECS)
