"""
Python-specific module: test xr concentrator
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
XRConcentrator: Chaves Ch. 9, Example 9.2
===============================================================================
Built with the book's parameters, the XR reproduces its published numbers:
the seed circle's centre C, the optical path length S, and both complete
point lists, the primary's 42 and the lens's 45, each point to the book's six
printed digits, with no point the book does not list. That holds because the
chains grow from every point of the seed circle and the surfaces end where
the book's do.

The assembly is the XR's: a dielectric bounded below by R and above by a
straight top at the receiver's level (the receiver inside it), and the
primary apart from it, in air, one spline mirror through its points and
their mirror images, with a point on the axis.

What the XR claims of its rays is tested in test_sms_claims.py.
===============================================================================
"""

from __future__ import annotations

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.optical_elements.mirrors import SplineMirror
from ray_tracing_shapely.optical_elements.prisms.xr_concentrator import XRConcentrator

R1, R2 = (-0.5, 0.0), (0.5, 0.0)
P0, N0 = (0.0, -4.0), (0.0, -1.0)

# Example 9.2's lists, every fourth point and the last (the book: 42 mirror points, 45 lens points)
BOOK_MIRROR = [(-0.372449, -13.8934), (-3.36293, -13.6643), (-6.45408, -13.0391), (-9.6786, -11.9579),
               (-12.8973, -10.4318), (-15.7396, -8.70992), (-17.8916, -7.18315), (-19.3709, -6.03937),
               (-20.3351, -5.26718), (-20.972, -4.75509), (-21.3905, -4.42431), (-21.4416, -4.38492)]
BOOK_LENS = [(0.0, -4.0), (-0.560526, -4.02071), (-1.18322, -4.07455), (-1.93955, -4.13243), (-2.88953, -4.1286),
             (-3.9971, -3.96305), (-5.07093, -3.58644), (-5.94625, -3.03872), (-6.56186, -2.37674),
             (-6.90277, -1.63261), (-6.9467, -0.808906), (-6.58436, 0.165038)]
PRINTED = 1e-4          # six printed digits, on coordinates of up to 21


def _xr(**kw):
    return XRConcentrator(Scene(), R1, R2, theta_deg=2.0, p0=P0, n0=N0, n=1.5, **kw)


def test_the_seed_and_path_length_are_the_books():
    xr = _xr()
    assert math.dist(xr.C, (0.0, 10.57)) < 1e-2
    assert abs(xr.S - 31.0467) < 1e-4
    book_seed = [(1.86052, -13.8254), (1.117, -13.8707), (0.372449, -13.8934), (-0.372449, -13.8934),
                 (-1.117, -13.8707)]
    for b in book_seed:
        assert min(math.dist(b, q.p) for q in xr.seed_points) < PRINTED


def test_both_lists_are_the_books_complete():
    xr = _xr()
    mirror = [q.p for q in xr.mirror_points[1:]]          # the first is the circle's point on the axis
    lens = [q.p for q in xr.lens_points]
    assert (len(mirror), len(lens)) == (42, 45)
    for book, ours in ((BOOK_MIRROR, mirror), (BOOK_LENS, lens)):
        for b in book:
            assert min(math.dist(b, p) for p in ours) < PRINTED, b
    # in order, from the axis outward, ending where the book's lists end
    assert math.dist(mirror[-1], BOOK_MIRROR[-1]) < PRINTED and math.dist(lens[-1], BOOK_LENS[-1]) < PRINTED
    assert xr.mirror_points[0].p == pytest.approx((0.0, xr.C[1] - math.dist(xr.P1, xr.C)))


def test_the_dielectric_holds_the_receiver_under_a_straight_top():
    xr = _xr(edges="polyline")
    top = xr.polyline_vertices[-1][1]
    assert top == pytest.approx(BOOK_LENS[-1][1], abs=PRINTED) and top > R1[1]
    assert xr.polyline_vertices[0][1] == pytest.approx(top)
    spline = _xr()
    labels = [(spline.get_functional_label(s.index)[0], s.kind) for s in spline.spans]
    assert labels == [("R2", "spline"), ("R1", "spline"), ("R2", "spline"), ("TOP", "line")]
    assert all(spline._edge_mechanisms[k].value == "refract" for k in ("R1", "R2", "TOP"))


def test_the_lens_is_cut_where_it_turns_back_toward_the_axis():
    """Revolved, a surface must be single-valued in r: R is cut where its distance from the axis
    peaks, its tangent vertical there, the three pieces one spline over narrower domains."""
    xr = _xr()
    curves = [xr.path[k]["curve"] for k in range(3)]
    assert all(c["points"] == curves[0]["points"] and c["tangents"] == curves[0]["tangents"] for c in curves)
    (a, cut1), cut2 = curves[1]["domain"], curves[2]["domain"][0]
    assert curves[0]["domain"][0] == 0.0 and curves[0]["domain"][1] == a and cut1 == cut2
    from ray_tracing_shapely.core.glass_curves import SplineCurve
    whole = SplineCurve(curves[0]["points"], curves[0]["tangents"], 0.0, len(curves[0]["points"]) - 1.0)
    for p in (a, cut1):
        dx, dy = whole.deriv(p)
        assert abs(dx) < 1e-9 * abs(dy)                       # vertical: r at its peak
    x = whole.point(a)[0]
    assert x == pytest.approx(-6.969, abs=1e-3) and min(q.p[0] for q in xr.lens_points) > x


def test_the_primary_is_one_spline_mirror_through_its_points():
    xr = _xr()
    (primary,) = xr.primary
    assert isinstance(primary, SplineMirror) and primary.name == "X" and primary.mechanism.value == "reflect"
    knots = primary.curve.points
    assert len(knots) == 2 * 43 - 1                        # both halves, sharing the point on the axis
    for q in xr.mirror_points:
        for p in (q.p, (-q.p[0], q.p[1])):
            assert min(math.dist(p, k) for k in knots) < 1e-12
    assert xr.objects() == [xr, primary]
    flat = _xr(edges="polyline").primary
    assert len(flat) == len(knots) - 1 and all(m.type == "Mirror" for m in flat)


def test_the_old_stage_count_is_refused():
    with pytest.raises(TypeError):
        _xr(n_stages=6)
