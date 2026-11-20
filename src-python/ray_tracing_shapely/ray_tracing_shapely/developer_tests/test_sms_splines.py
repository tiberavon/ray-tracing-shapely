"""
Python-specific module: test sms splines
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
The SMS elements' designed surfaces as exact splines through the chain
===============================================================================
Each designed surface is one spline edge through the chain's points, with the
chain's normals there; a surface with a corner (the direct RXI's top at C) is
split at it. Checked: the knots and normals; the spline at the book's density
closer to a ten times denser chain than the polyline; each spline monotonic in
r on each half (a revolved spline needs it); the polyline kept as an option.
And Curve.nearest on a spline of many uneven knots (the dense chain's 108 intervals).
===============================================================================
"""

from __future__ import annotations

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens
from ray_tracing_shapely.optical_elements.prisms.rx_concentrator import RXConcentrator
from ray_tracing_shapely.optical_elements.prisms.rxi_direct import RXIOpticDirect


def _rr(n_points=5, edges="spline"):
    return RRLens(Scene(), (-1.0, 2.0), (1.0, 2.0), (-0.5, -2.0), (0.5, -2.0), seed_n_angle_deg=303.3,
                  seed_x_angle_deg=42.7, n_points_per_section=n_points, edges=edges)


def _rx(edges="spline"):
    return RXConcentrator(Scene(), (-0.5, 0.0), (0.5, 0.0), theta_deg=2.0, n=1.5, edges=edges)


def _spans(element):
    return {element.get_functional_label(s.index)[0]: s for s in element.spans}


def _on_outline(element, points):
    """The chain points the outline is built from (those it kept, with their mirror images)."""
    kept = {(round(x, 9), round(y, 9)) for x, y in element.polyline_vertices}
    out = []
    for q in points:
        for mx in (1.0, -1.0):
            p, n = (mx * q.p[0], q.p[1]), (mx * q.n[0], q.n[1])
            if (round(p[0], 9), round(p[1], 9)) in kept:
                out.append((p, n))
    return out


@pytest.mark.parametrize("make, surfaces", [
    (_rr, (("N", "n_surface_points"), ("X", "x_surface_points"))),
    (_rx, (("R", "lens_points"), ("X", "mirror_points"))),
])
def test_the_knots_are_the_chain_points_with_their_normals(make, surfaces):
    element = make()
    spans = _spans(element)
    for label, attr in surfaces:
        assert spans[label].kind == "spline"
        shape = spans[label].shape
        pairs = _on_outline(element, getattr(element, attr))
        assert len(pairs) >= 3
        for p, n in pairs:
            d, t = shape.nearest(p)
            ln = shape.left_normal(t)
            assert d < 1e-12, (label, p, d)
            assert abs(ln[0] * n[1] - ln[1] * n[0]) / math.hypot(*n) < 1e-9, (label, p)


def test_the_spline_is_closer_to_a_denser_chain_than_the_polyline():
    """Where the book's density has points; across the axis, between its innermost points
    (x = +-0.037), the spline bridges what the chains do not reach (the book's central zone)."""
    coarse, dense, poly = _rr(5), _rr(50), _rr(5, edges="polyline")
    shape = _spans(coarse)["X"].shape
    inner = min(q.p[0] for q in coarse.x_surface_points)
    everywhere = [p for p, _ in _on_outline(dense, dense.x_surface_points)]
    reference = [q for q in everywhere if abs(q[0]) >= inner]
    bridge = [q for q in everywhere if abs(q[0]) < inner]
    assert bridge and max(shape.nearest(q)[0] for q in bridge) < 1e-4          # 6.6e-5 mm
    ring = poly.polyline_vertices

    def to_polyline(q):
        best = math.inf
        for a, b in zip(ring, ring[1:] + ring[:1]):
            ab = (b[0] - a[0], b[1] - a[1])
            t = max(0.0, min(1.0, ((q[0] - a[0]) * ab[0] + (q[1] - a[1]) * ab[1]) / (ab[0] ** 2 + ab[1] ** 2)))
            best = min(best, math.hypot(q[0] - a[0] - t * ab[0], q[1] - a[1] - t * ab[1]))
        return best
    spline_dev = max(shape.nearest(q)[0] for q in reference)
    poly_dev = max(to_polyline(q) for q in reference)
    assert spline_dev < poly_dev / 1000.0, (spline_dev, poly_dev)        # 1.6e-7 against 2.6e-4 mm


@pytest.mark.parametrize("make", [_rr, _rx, lambda: _rr(50),
                                  lambda: RXIOpticDirect(Scene(), (-1.0, 0.0), (1.0, 0.0), theta_deg=10.0, n=1.5)])
def test_every_spline_is_monotonic_in_r_on_each_half(make):
    element = make()
    splines = [s for s in element.spans if s.kind == "spline"]
    assert splines
    for s in splines:
        pts = s.shape.coords(1e-4)
        for side in (1.0, -1.0):
            r = [side * x for x, _ in pts if side * x > 1e-9]
            steps = [b - a for a, b in zip(r, r[1:])]
            assert all(v >= -1e-12 for v in steps) or all(v <= 1e-12 for v in steps), \
                element.get_functional_label(s.index)


def test_a_corner_is_kept_and_the_polyline_stays_an_option():
    rr = _rr()
    corners = [s for s in rr.spans if s.kind == "line"]
    assert corners and all(rr.get_functional_label(s.index)[0] == "RIM" for s in corners)   # the rim kept straight
    poly = _rr(edges="polyline")
    assert not any("curve" in e for e in poly.path) and len(poly.path) == len(poly.polyline_vertices)
    assert {poly.get_functional_label(s.index)[0] for s in poly.spans} >= {"N1", "X1", "RIM"}
    with pytest.raises(ValueError, match="spline' or 'polyline"):
        _rr(edges="bezier")


def test_nearest_on_a_spline_of_many_uneven_knots():
    """The dense chain's N surface: 108 knot intervals, dense near the rim, sparse at the axis.
    Seeded from 64 trial points, Newton settled 1.13 away from points on the curve."""
    shape = _spans(_rr(50))["N"].shape
    on_curve = [(-x, y) for x, y in shape.coords(1e-3)]          # the mirror images: points of the curve
    assert max(shape.nearest(p)[0] for p in on_curve) < 1e-12
