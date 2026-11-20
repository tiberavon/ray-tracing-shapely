"""
Python-specific module: test curved glass analysis
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

The analysis layer on glass with circular arcs.

Before: a lens's outline was a polygon through its arcs' through-points
(area -16%, points inside the lens reported outside), each arc counted as two
edges (one "circular", one "line"), hits mid-arc were not located on any
surface, and concave faces were drawn bulging outward. After: one edge per
physical surface (core.glass_spans), the true curve everywhere, and nothing
changed for straight glass.
"""

import math
import re

import pytest
from shapely.geometry import Point

from ray_tracing_shapely.analysis import agentic_db
from ray_tracing_shapely.analysis.agentic_db import create_database
from ray_tracing_shapely.analysis.bidirectional import _locate_on_surface
from ray_tracing_shapely.analysis.glass_geometry import (
    EdgeType,
    edge_outward_normal,
    get_edge_descriptions,
    glass_to_polygon,
)
from ray_tracing_shapely.analysis.ray_geometry_queries import (
    find_rays_crossing_edge,
    interpolate_along_edge,
    normal_along_edge,
)
from ray_tracing_shapely.core.glass_spans import glass_spans
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.spherical_lens import SphericalLens
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.svg_renderer import SVGRenderer
from ray_tracing_shapely.optical_elements.prisms.equilateral import EquilateralPrism
from ray_tracing_shapely.optical_elements.prisms.refractometer import RefractometerPrism


def _lens(scene=None, r1=20.0, r2=-60.0):
    return SphericalLens(scene or Scene(), {
        "p1": {"x": 0, "y": 10}, "p2": {"x": 0, "y": -10}, "def_by": "DR1R2",
        "params": {"d": 5.0, "r1": r1, "r2": r2}, "refIndex": 1.5, "cauchyB": 0.0,
    })


def _true_area(r_minus_x=60.0, r_plus_x=20.0, d=5.0, half_aperture=10.0, n=20001):
    """Area of the biconvex test lens, integrated across the aperture."""
    total, h = 0.0, 2 * half_aperture / (n - 1)
    for k in range(n):
        y = -half_aperture + k * h
        xl = -d / 2 + (r_minus_x - math.sqrt(r_minus_x ** 2 - y * y))
        xr = d / 2 - (r_plus_x - math.sqrt(r_plus_x ** 2 - y * y))
        w = 0.5 if k in (0, n - 1) else 1.0
        total += w * (xr - xl) * h
    return total


# --- spans ------------------------------------------------------------------------

@pytest.mark.parametrize("prism", [
    EquilateralPrism(Scene(), side_length=50.0),
    RefractometerPrism.from_critical_ray_path(Scene(), n_prism=1.72, n_target=1.33, ray_path_length=20.0),
])
def test_straight_glass_spans_are_exactly_its_path_edges(prism):
    spans = glass_spans(prism.path)
    n = len(prism.path)
    assert len(spans) == n
    for i, s in enumerate(spans):
        assert s.kind == "line" and s.index == i and s.path_indices == (i, (i + 1) % n)
        assert s.start == (prism.path[i]["x"], prism.path[i]["y"])
    # Edge descriptions and cardinal labels are therefore unchanged for straight glass.
    assert [e.index for e in get_edge_descriptions(prism)] == list(range(n))
    assert prism._get_edge_count() == n


def test_a_lens_has_one_span_per_physical_surface():
    spans = glass_spans(_lens().path)
    assert [s.kind for s in spans] == ["line", "arc", "line", "arc"]
    assert sorted(round(s.radius, 9) for s in spans if s.is_arc) == [20.0, 60.0]


def test_arc_midpoint_and_length_are_on_the_curve():
    arcs = [s for s in glass_spans(_lens().path) if s.is_arc]
    for s in arcs:
        assert math.dist(s.midpoint, s.center) == pytest.approx(s.radius)
        half_chord = math.dist(s.start, s.end) / 2
        assert s.length == pytest.approx(2 * s.radius * math.asin(half_chord / s.radius))


# --- the outline ------------------------------------------------------------------

def test_polygon_has_the_true_area():
    assert glass_to_polygon(_lens()).area == pytest.approx(_true_area(), abs=1e-3)


def test_a_point_between_the_arc_and_its_chord_is_inside():
    # (1.5, 5): right of the old chord from (-0.18, 10) to (2.5, 0), left of the true +x face.
    assert glass_to_polygon(_lens()).contains(Point(1.5, 5.0))


# --- edge descriptions and labels -------------------------------------------------

def test_edge_descriptions_report_each_arc_once():
    lens = _lens()
    edges = get_edge_descriptions(lens)
    assert [e.edge_type for e in edges] == [EdgeType.LINE, EdgeType.CIRCULAR, EdgeType.LINE, EdgeType.CIRCULAR]
    assert [e.index for e in edges] == [0, 1, 2, 3]
    for e in edges:
        if e.edge_type is EdgeType.CIRCULAR:
            assert math.dist((e.midpoint.x, e.midpoint.y), e.span.center) == pytest.approx(e.span.radius)
            assert e.length == pytest.approx(e.span.length)


def test_cardinal_labels_follow_the_physical_surfaces():
    lens = _lens()
    lens.auto_label_cardinal()
    labels = [lens.get_edge_label(i)[0] for i in range(lens._get_edge_count())]
    assert labels == ["N", "W", "S", "E"]


# --- locating hits ----------------------------------------------------------------

def test_a_hit_mid_arc_is_located_on_the_arc():
    lens = _lens()
    arc = next(s for s in glass_spans(lens.path) if s.is_arc and s.midpoint[0] > 0)
    point = arc.point_at(0.3)
    located = _locate_on_surface(lens, {"x": point[0], "y": point[1]})
    assert located is not None, "before spans, a hit mid-arc was farther than tol from every chord"
    edge_index, along, edge_len = located
    assert edge_index == arc.index
    assert along == pytest.approx(0.3 * arc.length, abs=1e-9)
    assert edge_len == pytest.approx(arc.length)


# --- normals and positions along an edge -----------------------------------------

@pytest.mark.parametrize("r1, r2", [(20.0, -60.0), (-20.0, 60.0)])
def test_arc_normals_point_out_of_the_glass(r1, r2):
    lens = _lens(r1=r1, r2=r2)
    poly = glass_to_polygon(lens)
    for e in get_edge_descriptions(lens):
        if e.edge_type is not EdgeType.CIRCULAR:
            continue
        for f in (0.1, 0.5, 0.9):
            px, py = e.span.point_at(f)
            nx, ny = edge_outward_normal(e, poly, (px, py))
            assert math.hypot(nx, ny) == pytest.approx(1.0)
            assert not poly.contains(Point(px + 1e-3 * nx, py + 1e-3 * ny))
            assert poly.contains(Point(px - 1e-3 * nx, py - 1e-3 * ny))


def test_interpolate_and_normal_along_a_curved_edge():
    lens = _lens()
    arc_edge = next(e for e in get_edge_descriptions(lens) if e.edge_type is EdgeType.CIRCULAR and e.midpoint.x > 0)
    x, y = interpolate_along_edge(lens, str(arc_edge.index), 0.5)
    assert (x, y) == pytest.approx((arc_edge.midpoint.x, arc_edge.midpoint.y))
    (bx, by), (tx, ty) = normal_along_edge(lens, str(arc_edge.index), 0.5, length=1.0)
    assert (tx - bx, ty - by) == pytest.approx((1.0, 0.0), abs=1e-9)   # the +x vertex faces +x


# --- crossings and the per-run database ---------------------------------------------

def _traced_lens_scene(heights=(1.0, 4.0, 8.0), record_surface_hits=False):
    scene = Scene()
    lens = _lens(scene)
    lens.name = "lens"
    scene.add_object(lens)
    for h in heights:
        scene.add_object(SingleRay(scene, {"p1": {"x": -40, "y": h}, "p2": {"x": -39, "y": h}}))
    result = Simulator(scene, max_rays=1000, record_surface_hits=record_surface_hits).run_with_result(name="lens")
    return scene, lens, result.segments


def test_rays_crossing_a_curved_edge_are_found_on_the_curve():
    scene, lens, segments = _traced_lens_scene()
    front = next(e for e in get_edge_descriptions(lens) if e.edge_type is EdgeType.CIRCULAR and e.midpoint.x < 0)
    crossing = find_rays_crossing_edge(segments, lens, str(front.index))
    # Each incoming ray ends on the front face; at h = 8 that point is 0.2 mm off the old chord.
    roots = [s for s in segments if s.parent_uuid is None]
    assert {s.uuid for s in roots} <= {s.uuid for s in crossing}


def test_database_records_crossings_at_the_local_normal():
    scene, lens, segments = _traced_lens_scene()
    conn = create_database(scene, segments)
    rows = conn.execute(
        "SELECT r.p1_y, c.angle_to_normal FROM ray_edge_crossing c JOIN rays r ON r.uuid = c.ray_uuid "
        "JOIN edges e ON e.glass_uuid = c.glass_uuid AND e.edge_index = c.edge_index "
        "WHERE e.edge_type = 'circular' AND r.parent_uuid IS NULL"
    ).fetchall()
    assert rows, "no incoming ray was recorded as crossing the curved front face"
    # A ray along +x at height h meets the R = 60 face at asin(h / 60) from its normal.
    for p1_y, angle in rows:
        assert angle == pytest.approx(math.degrees(math.asin(abs(p1_y) / 60.0)), abs=1e-3)


def _crossings(scene, segments, monkeypatch, **kw):
    """The crossing rows, and how many curved-edge normals were computed from the edge."""
    calls = []
    real = agentic_db.edge_outward_normal
    monkeypatch.setattr(agentic_db, "edge_outward_normal", lambda *a, **k: calls.append(1) or real(*a, **k))
    conn = create_database(scene, segments, **kw)
    rows = sorted(conn.execute("SELECT ray_uuid, glass_uuid, edge_index, angle_to_normal FROM ray_edge_crossing"))
    return rows, len(calls)


def test_crossing_angles_reuse_the_normals_the_simulator_recorded(monkeypatch):
    scene, lens, segments = _traced_lens_scene(record_surface_hits=True)
    recorded, computed_b = _crossings(scene, segments, monkeypatch)
    recomputed, computed_a = _crossings(scene, segments, monkeypatch, recompute_angles=True)
    assert computed_a > 0 and computed_b == 0           # every curved crossing here is a recorded hit
    assert [r[:3] for r in recorded] == [r[:3] for r in recomputed]
    assert all(abs(a[3] - b[3]) <= 1e-9 for a, b in zip(recorded, recomputed))
    roots = {s.uuid: s.p1["y"] for s in segments if s.parent_uuid is None}
    front = [(roots[u], angle) for u, _, _, angle in recorded if u in roots]
    assert front and all(angle == pytest.approx(math.degrees(math.asin(abs(h) / 60.0)), abs=1e-3)
                         for h, angle in front)


def test_without_recorded_hits_the_angles_are_computed_from_the_edge(monkeypatch):
    scene, lens, segments = _traced_lens_scene(record_surface_hits=False)
    default, computed = _crossings(scene, segments, monkeypatch)
    assert computed > 0 and default == _crossings(scene, segments, monkeypatch, recompute_angles=True)[0]


def test_a_hit_at_an_edges_corner_is_not_taken_for_that_edge():
    span = next(sp for sp in glass_spans(_lens().path) if sp.is_curved)
    hit = [("glass", span.start[0], span.start[1], 1.0, 0.0)]
    assert agentic_db._recorded_normal(hit, "glass", span.start, span) is None
    mid = span.midpoint
    assert agentic_db._recorded_normal([("glass", mid[0], mid[1], 1.0, 0.0)], "glass", mid, span) == (1.0, 0.0)
    assert agentic_db._recorded_normal([("other", mid[0], mid[1], 1.0, 0.0)], "glass", mid, span) is None


# --- drawing --------------------------------------------------------------------------

@pytest.mark.parametrize("r1, r2, flags", [(20.0, -60.0, {"1"}), (-20.0, 60.0, {"0"})])
def test_svg_arcs_bend_the_way_the_glass_does(r1, r2, flags):
    """Every arc's sweep flag follows its turning direction; the old constant
    flag drew a biconcave lens biconvex."""
    scene = Scene()
    scene.add_object(_lens(scene, r1, r2))
    renderer = SVGRenderer(width=200, height=200, viewbox=(-15, -15, 30, 30))
    renderer.draw_scene(scene, [], draw_obj_labels=False, draw_edge_labels=False)
    arcs = re.findall(r"A [\d.]+,[\d.]+ 0 (\d) (\d)", renderer.to_string())
    assert len(arcs) == 2
    assert {large for large, _ in arcs} == {"0"}
    assert {sweep for _, sweep in arcs} == flags
