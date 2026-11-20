"""
Python-specific module: test rx concentrator
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
RXConcentrator: the RX of Chaves Ch. 9, eq. 9.34
===============================================================================
The construction's own checks. The chain grown from Q1 returns to P0 exactly:
by symmetry, it is r1's path mirrored, so it ties the seed, the path length S
and both kinds of step together. The receiver lies inside the glass, between
the top and the mirror. Each surface is one curve, its points in order from
the axis outward, labelled R (refracting) and X (mirror-coated). Calls in the
old form (a point P0 and its normal) are refused, not reinterpreted.

What the RX claims of its rays is tested in test_sms_claims.py.
===============================================================================
"""

from __future__ import annotations

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.optical_elements.prisms.rx_concentrator import RXConcentrator

R1, R2 = (-0.5, 0.0), (0.5, 0.0)


def _rx(**kw):
    return RXConcentrator(Scene(), R1, R2, theta_deg=2.0, **kw)


def _inside(point, polygon):
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def test_the_chain_from_q1_returns_to_p0():
    rx = _rx()
    assert min(math.dist(q.p, rx.P0) for q in rx.lens_points) < 1e-9


def test_the_receiver_is_inside_the_glass_between_the_surfaces():
    rx = _rx(edges="polyline")
    assert rx.P0[1] > R1[1] > max(q.p[1] for q in rx.mirror_points)
    for p in (R1, R2, (0.0, 0.0)):
        assert _inside(p, rx.polyline_vertices)


def test_each_surface_runs_outward_from_the_axis():
    rx = _rx()
    for points in (rx.lens_points, rx.mirror_points):
        xs = [q.p[0] for q in points]
        assert all(b < a for a, b in zip(xs, xs[1:])) and xs[0] <= 0.0
    # the top falls from P0 to its rim; the rim lies above the mirror's edge
    assert rx.lens_points[-1].p[1] < rx.P0[1] and rx.lens_points[-1].p[1] > rx.mirror_points[-1].p[1]


def test_r_refracts_and_x_is_mirror_coated():
    rx = _rx()
    labels = {rx.get_functional_label(s.index)[0]: s for s in rx.spans}
    assert set(labels) == {"R", "X", "RIM"}
    assert labels["R"].kind == labels["X"].kind == "spline"
    assert rx._edge_mechanisms["R"].value == "refract" and rx._edge_mechanisms["X"].value == "reflect"
    reflects = [s.index for s in rx.spans if rx.edge_reflects(s.index)]
    assert reflects == [labels["X"].index]


def test_the_old_form_is_refused():
    with pytest.raises(TypeError):
        RXConcentrator(Scene(), R1, R2, theta_deg=2.0, p0=(0.0, -4.0), n0=(0.0, -1.0))
    with pytest.raises(ValueError, match="mirror"):
        _rx(top_height=2.0, mirror_depth=1.0)
    with pytest.raises(ValueError, match="r1 left of r2"):
        RXConcentrator(Scene(), R2, R1, theta_deg=2.0)
