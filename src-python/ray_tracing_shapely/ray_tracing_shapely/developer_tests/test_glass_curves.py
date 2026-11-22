"""
Python-specific module: test glass curves
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

Exact conic and spline edges on glass.

The witness is a property with an exact answer: a plano-convex lens whose
convex face is a hyperbola of conic constant K = -n^2 focuses collimated
light from inside the glass to one point in air, R/(n - 1) from its vertex.
A polyline facets the face and puts a slope error into every refraction; a
sphere has spherical aberration; the exact conic has neither. A spline
through exact points with exact tangents converges to the conic.
"""

import math
import random

import pytest

from ray_tracing_shapely.analysis.glass_geometry import EdgeType, get_edge_descriptions, glass_to_polygon
from ray_tracing_shapely.core.glass_curves import ConicCurve, SplineCurve, curve_from_descriptor
from ray_tracing_shapely.core.glass_spans import glass_spans
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.optical_elements.curved_glass import CurvedGlass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_profile
from ray_tracing_shapely.optical_elements.roles import Mechanism, Role

N = 1.5
R, T, H = 20.0, 12.0, 10.0
X0, Y0 = 100.0, 30.0
FOCUS = X0 + T + R / (N - 1)
HEIGHTS = [k * 0.9 for k in (-9, -7, -5, -3, -1, 1, 2, 4, 6, 8, 9)]


def _face(conic=-N * N):
    """The convex face: vertex at x0 + T, axis into the glass (-x)."""
    return ConicCurve((X0 + T, Y0), (-1.0, 0.0), R, conic, 0.0, 1.0)


def _spline_desc(knots):
    """The hyperbola as a spline: exact points, exact tangents, from y0 - h up to y0 + h."""
    c = _face()
    ss = [H - 2 * H * k / (knots - 1) for k in range(knots)]   # s = -(y - y0)
    pts = [list(c.point(s)) for s in ss]
    tans = [[-c.deriv(s)[0], -c.deriv(s)[1]] for s in ss]      # travel towards decreasing s
    return {"type": "spline", "points": pts, "tangents": tans}


class _PlanoAsphere(BasePrism):
    """Flat face S1 at x0, convex face S2 a conic or spline, rims at y0 +- h."""

    _edge_roles = [("S1", "Flat Face", Role.ENTRANCE), ("RIM", "Edge", Role.BLOCKER),
                   ("S2", "Convex Face", Role.EXIT), ("RIM", "Edge", Role.BLOCKER)]
    _edge_mechanisms = {"S1": Mechanism.REFRACT, "RIM": None, "S2": Mechanism.REFRACT}

    def __init__(self, scene, *, conic=-N * N, spline_knots=None):
        self._conic, self._knots = conic, spline_knots
        super().__init__(scene, size=H, n=N)

    def _compute_path(self):
        c = _face(self._conic)
        lo, hi = c.point(H), c.point(-H)               # y0 - h and y0 + h on the face
        desc = _spline_desc(self._knots) if self._knots else c.descriptor()
        return [{"x": X0, "y": Y0 + H, "arc": False},
                {"x": X0, "y": Y0 - H, "arc": False},
                {"x": lo[0], "y": lo[1], "arc": False, "curve": desc},
                {"x": hi[0], "y": hi[1], "arc": False}]


def _axis_crossings(glass, heights=HEIGHTS, ray_x=X0 - 20.0, axis_y=Y0):
    """Where each collimated ray, after the convex face, crosses the axis y = axis_y."""
    scene = glass.scene
    scene.add_object(glass)
    for y in heights:
        scene.add_object(SingleRay(scene, {"p1": {"x": ray_x, "y": axis_y + y}, "p2": {"x": ray_x + 1, "y": axis_y + y}}))
    segs = Simulator(scene, max_rays=10000).run_with_result(name="curves").segments
    out = []
    for sg in segs:
        dx, dy = sg.p2["x"] - sg.p1["x"], sg.p2["y"] - sg.p1["y"]
        if sg.p1["x"] > X0 + 1.0 and dx > 0 and abs(dy) > 1e-12 and sg.total_brightness > 0.5:
            out.append(sg.p1["x"] + (axis_y - sg.p1["y"]) / dy * dx)
    return out


# --- the curves ---------------------------------------------------------------------------

def test_a_conic_curve_lies_on_its_conic_and_meets_lines_exactly():
    rng = random.Random(1)
    c = ConicCurve((10.0, 5.0), (math.cos(0.3), math.sin(0.3)), -20.0, -2.5, -12.0, 15.0)
    for _ in range(500):
        p = rng.uniform(-12, 15)
        o = (c.point(p)[0] - 10.0, c.point(p)[1] - 5.0)
        z, s = o[0] * c.axis[0] + o[1] * c.axis[1], o[0] * c.left[0] + o[1] * c.left[1]
        assert abs(s * s - 2 * c.radius * z + (1 + c.conic) * z * z) < 1e-11
    for _ in range(200):
        o = (rng.uniform(-30, 40), rng.uniform(-30, 40))
        a = rng.uniform(0, 2 * math.pi)
        d = (math.cos(a), math.sin(a))
        hits = c.line_hits(o, d)
        nrm = (-d[1], d[0])
        vals = [(c.point(-12 + 27 * k / 4000)[0] - o[0]) * nrm[0] + (c.point(-12 + 27 * k / 4000)[1] - o[1]) * nrm[1]
                for k in range(4001)]
        assert len(hits) == sum(1 for x, y in zip(vals[:-1], vals[1:]) if (x > 0) != (y > 0))
        for t, p in hits:
            assert math.dist(c.point(p), (o[0] + t * d[0], o[1] + t * d[1])) < 1e-9


def test_a_spline_passes_its_points_with_its_tangents_and_meets_lines_exactly():
    rng = random.Random(2)
    angles = [k * 0.2 for k in range(11)]
    sp = SplineCurve([(math.cos(a), math.sin(a)) for a in angles],
                     [(-math.sin(a), math.cos(a)) for a in angles], 0.0, 10.0)
    for k, a in enumerate(angles):
        assert math.dist(sp.point(k), (math.cos(a), math.sin(a))) < 1e-15
        tx, ty = sp.tangent(k)
        assert abs(tx + math.sin(a)) < 1e-14 and abs(ty - math.cos(a)) < 1e-14
    for _ in range(200):
        o = (rng.uniform(-2, 2), rng.uniform(-2, 2))
        a = rng.uniform(0, 2 * math.pi)
        d = (math.cos(a), math.sin(a))
        hits = sp.line_hits(o, d)
        nrm = (-d[1], d[0])
        vals = [(sp.point(10 * k / 4000)[0] - o[0]) * nrm[0] + (sp.point(10 * k / 4000)[1] - o[1]) * nrm[1]
                for k in range(4001)]
        assert len(hits) == sum(1 for x, y in zip(vals[:-1], vals[1:]) if (x > 0) != (y > 0))
        for t, p in hits:
            assert math.dist(sp.point(p), (o[0] + t * d[0], o[1] + t * d[1])) < 1e-13


def test_arc_length_and_sampling_along_a_curve():
    sp = SplineCurve([(math.cos(k * 0.2), math.sin(k * 0.2)) for k in range(11)],
                     [(-math.sin(k * 0.2), math.cos(k * 0.2)) for k in range(11)], 10.0, 0.0)
    fine = 100_000
    poly = sum(math.dist(sp.point(10 - 10 * k / fine), sp.point(10 - 10 * (k + 1) / fine)) for k in range(fine))
    assert sp.length == pytest.approx(poly, abs=1e-10)
    for f in (0.1, 0.37, 0.5, 0.93):
        assert sp.fraction_of(sp.param_at(f)) == pytest.approx(f, abs=1e-13)


# --- the engine ------------------------------------------------------------------------------

def test_a_hyperbolic_face_focuses_collimated_light_exactly():
    xs = _axis_crossings(_PlanoAsphere(Scene()))
    assert len(xs) == len(HEIGHTS)
    assert max(abs(x - FOCUS) for x in xs) < 1e-9
    sphere = _axis_crossings(_PlanoAsphere(Scene(), conic=0.0))
    assert max(sphere) - min(sphere) > 1.0          # the sphere's aberration, for contrast


def test_a_spline_face_converges_to_the_conic_and_a_polyline_does_not():
    spreads = {}
    for knots in (9, 33, 65):
        xs = _axis_crossings(_PlanoAsphere(Scene(), spline_knots=knots))
        assert len(xs) == len(HEIGHTS)
        spreads[knots] = max(xs) - min(xs)
    assert spreads[9] > spreads[33] > spreads[65] and spreads[65] < 1e-3
    pts = _spline_desc(65)["points"]
    scene = Scene()
    poly = Glass(scene, {"path": [{"x": X0, "y": Y0 + H, "arc": False}, {"x": X0, "y": Y0 - H, "arc": False}]
                         + [{"x": p[0], "y": p[1], "arc": False} for p in pts], "refIndex": N, "notDone": False})
    xs = _axis_crossings(poly)
    assert max(xs) - min(xs) > 1.0                  # the same 65 points, faceted


def test_a_ray_that_enters_through_a_curve_leaves_through_it():
    """The arc-exit defect (test_glass_arc_exit), for curves: the root at the ray's own
    start is skipped per root, so the far side is found."""
    c = ConicCurve((0.0, 3.0), (0.0, -1.0), 3.0, -0.5, 0.0, 1.0)     # a dome, vertex up
    left, right = c.point(-2.9), c.point(2.9)                          # s left of (0, -1) is +x
    for x0 in (0.0, 0.5, 3.0, 30.0, 300.0):
        scene = Scene()
        dome = CurvedGlass(scene, {"path": [{"x": right[0] + x0, "y": right[1], "arc": False,
                                       "curve": {**c.descriptor(), "vertex": [x0, 3.0]}},
                                      {"x": left[0] + x0, "y": left[1], "arc": False}],
                             "refIndex": 1.5, "notDone": False})
        scene.add_object(dome)
        # enters the curve near its left end, crosses the dome, must leave by the same curve
        scene.add_object(SingleRay(scene, {"p1": {"x": x0 - 20.0, "y": 2.4}, "p2": {"x": x0 - 19.0, "y": 2.36}}))
        sim = Simulator(scene, max_rays=50)
        sim.record_surface_hits = True
        segs = sim.run_with_result(name="dome").segments
        root = next(sg for sg in segs if sg.parent_uuid is None)
        leaving = max((sg for sg in segs if sg is not root
                       and math.dist((sg.p1["x"], sg.p1["y"]), (sg.p2["x"], sg.p2["y"])) > 1000.0),
                      key=lambda sg: sg.total_brightness)
        start = (leaving.p1["x"] - x0, leaving.p1["y"])
        # the brightest light leaves through the curve's far side, refracted there
        assert start[0] > 0.0 and curve_from_descriptor(c.descriptor(), right, left).nearest(start)[0] < 1e-9


def test_moving_rotating_and_scaling_carry_the_curve():
    for op in ("move", "rotate", "scale"):
        lens = _PlanoAsphere(Scene())
        if op == "move":
            lens.move(5.0, -3.0)
            assert glass_spans(lens.path)[2].shape.vertex == pytest.approx((X0 + T + 5.0, Y0 - 3.0))
        elif op == "rotate":
            lens.rotate(math.radians(90.0), {"x": X0, "y": Y0})
            spans = glass_spans(lens.path)
            assert spans[2].shape.axis == pytest.approx((0.0, -1.0), abs=1e-15)
            assert spans[2].shape.vertex == pytest.approx((X0, Y0 + T), abs=1e-12)
        else:
            lens.scale(2.0, {"x": X0, "y": Y0})
            assert glass_spans(lens.path)[2].shape.radius == pytest.approx(2 * R)
            assert glass_spans(lens.path)[2].shape.vertex == pytest.approx((X0 + 2 * T, Y0))
    lens = _PlanoAsphere(Scene())
    lens.move(0.0, 7.0)
    xs = _axis_crossings(lens, axis_y=Y0 + 7.0)                      # still focuses, on the moved axis
    assert len(xs) == len(HEIGHTS) and max(abs(x - FOCUS) for x in xs) < 1e-9


# --- profile.json --------------------------------------------------------------------------

@pytest.mark.parametrize("knots", [None, 17])
def test_export_and_rebuild_keep_the_exact_curve(knots):
    lens = _PlanoAsphere(Scene(), spline_knots=knots)
    profile = export_profile(lens, symmetry={"kind": "free"}, physical_params={}, numerical_params={})
    assert profile["schema_version"] == "1.5"
    s2 = next(sp for sp in profile["spans"] if sp["short_label"] == "S2")
    assert s2["curve"]["type"] == ("spline" if knots else "conic")
    assert s2["index_end"] - s2["index_start"] == profile["construction_params"]["numerical_params"]["curve_samples"]
    rebuilt = BasePrism.from_profile(Scene(), profile, n=N)
    assert [sp.kind for sp in rebuilt.spans] == [sp.kind for sp in lens.spans]
    assert rebuilt.get_functional_label(2)[0] == "S2"
    a, b = _axis_crossings(lens), _axis_crossings(rebuilt)
    assert a == pytest.approx(b, abs=1e-12)


@pytest.mark.parametrize("knots", [None, 33, 32])   # 32: no point at the vertex, cut mid-segment
def test_a_revolve_half_section_rebuilds_the_whole_face(knots):
    lens = _PlanoAsphere(Scene(), spline_knots=knots)
    profile = export_profile(lens, symmetry={"kind": "revolve", "axis": {"point": [X0, Y0], "direction": [1.0, 0.0]}},
                             physical_params={}, numerical_params={})
    s2 = next(sp for sp in profile["spans"] if sp["short_label"] == "S2")
    pts = profile["points"][s2["index_start"]:s2["index_end"]]
    assert min(abs(p[1] - Y0) for p in pts) < 1e-12           # cut at the vertex, on the axis
    rebuilt = BasePrism.from_profile(Scene(), profile, n=N)
    kind = "spline" if knots else "conic"
    assert [sp.kind for sp in rebuilt.spans].count(kind) == 1        # the halves joined back
    if knots:   # the joined spline is the original, knot for knot
        joined = next(sp for sp in rebuilt.spans if sp.kind == "spline")
        got, want = sorted(joined.shape.points), sorted(lens.spans[2].shape.points)
        assert max(math.dist(a, b) for a, b in zip(got, want)) < 1e-12   # the same points
        assert {joined.shape.lo, joined.shape.hi} == {0.0, float(knots - 1)}
    xs, ref = _axis_crossings(rebuilt), _axis_crossings(_PlanoAsphere(Scene(), spline_knots=knots))
    assert xs == pytest.approx(ref, abs=1e-9)


def test_from_profile_refuses_a_sample_off_its_curve_and_a_wrong_normal():
    lens = _PlanoAsphere(Scene())
    profile = export_profile(lens, symmetry={"kind": "free"}, physical_params={}, numerical_params={})
    s2 = next(sp for sp in profile["spans"] if sp["short_label"] == "S2")
    mid = (s2["index_start"] + s2["index_end"]) // 2
    off = {**profile, "points": [list(p) for p in profile["points"]]}
    off["points"][mid][0] += 1e-6
    with pytest.raises(ValueError, match="from its conic"):
        BasePrism.from_profile(Scene(), off, n=N)
    tilted = {**profile, "normals": [list(v) for v in profile["normals"]]}
    nx, ny = tilted["normals"][mid]
    tilted["normals"][mid] = [math.cos(0.01) * nx - math.sin(0.01) * ny, math.sin(0.01) * nx + math.cos(0.01) * ny]
    with pytest.raises(ValueError, match="disagrees"):
        BasePrism.from_profile(Scene(), tilted, n=N)


# --- what is refused, drawing, analysis ------------------------------------------------------

def test_what_a_curve_edge_refuses():
    c = _face()
    with pytest.raises(ValueError, match="from its conic"):
        curve_from_descriptor(c.descriptor(), c.point(5.0), (c.point(-5.0)[0] + 1e-3, c.point(-5.0)[1]))
    with pytest.raises(ValueError, match="equator"):
        ConicCurve((0.0, 0.0), (1.0, 0.0), 10.0, 0.0, 0.0, 10.0)
    with pytest.raises(ValueError, match="flat edge is a line"):
        ConicCurve((0.0, 0.0), (1.0, 0.0), math.inf, 0.0, 0.0, 1.0)
    with pytest.raises(ValueError, match="coincide"):
        SplineCurve([(0, 0), (0, 0), (1, 1)], [(1, 0), (1, 0), (0, 1)], 0.0, 2.0)
    with pytest.raises(ValueError, match="through-point"):
        glass_spans([{"x": 0.0, "y": 0.0, "curve": c.descriptor()}, {"x": 1.0, "y": 1.0, "arc": True},
                     {"x": 2.0, "y": 0.0}])


def test_the_analysis_layer_and_the_svg_renderer_see_the_true_curve():
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    lens = _PlanoAsphere(Scene())
    c = _face()
    # area: the rectangle x0..x_rim plus the cap between the rim and the conic
    x_rim = c.point(H)[0]
    steps = 200_000
    cap = sum(c.point(-H + 2 * H * (k + 0.5) / steps)[0] - x_rim for k in range(steps)) * (2 * H / steps)
    # (the analysis layer's polygon follows the curve to a sag of 1e-5: a 5e-7 deficit here)
    assert glass_to_polygon(lens).area == pytest.approx((x_rim - X0) * 2 * H + cap, rel=1e-6)
    kinds = [d.edge_type for d in get_edge_descriptions(lens)]
    assert kinds.count(EdgeType.CONIC) == 1
    svg = SVGRenderer(width=400, height=300, viewbox=(80, 10, 100, 40))
    svg.draw_glass_path(lens.path)
    assert svg.to_string().count("L ") > 50           # the curve, not its chord
