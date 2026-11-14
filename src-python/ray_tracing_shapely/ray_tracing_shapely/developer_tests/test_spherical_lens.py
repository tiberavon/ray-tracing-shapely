"""
Python-specific module: test spherical lens
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

Pins SphericalLens (core/scene_objs/glass/spherical_lens.py): its optics
against the thick-lens formula, and its radius convention.

The test lens: aperture line from p1 = (0, 10) to p2 = (0, -10), centre
thickness 5, n = 1.5 with dispersion off. Light travels along +x.
"""

import math

import pytest

from ray_tracing_shapely.core.glass_spans import glass_spans
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.spherical_lens import SphericalLens
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator

N = 1.5
D = 5.0


def _lens(scene, r1, r2, d=D):
    return SphericalLens(scene, {
        "p1": {"x": 0, "y": 10}, "p2": {"x": 0, "y": -10}, "def_by": "DR1R2",
        "params": {"d": d, "r1": r1, "r2": r2}, "refIndex": N, "cauchyB": 0.0,
    })


def _axis_crossings(r1, r2, heights):
    """Trace a collimated ray at each height along +x; return {height: x where it crosses y = 0}."""
    scene = Scene()
    lens = _lens(scene, r1, r2)
    scene.add_object(lens)
    for h in heights:
        scene.add_object(SingleRay(scene, {"p1": {"x": -40, "y": h}, "p2": {"x": -39, "y": h}}))
    result = Simulator(scene, max_rays=1000).run_with_result(name="lens")
    back = max(p["x"] for p in lens.path)
    crossings = {}
    for seg in result.segments:
        x1, y1, x2, y2 = seg.p1["x"], seg.p1["y"], seg.p2["x"], seg.p2["y"]
        # the transmitted ray leaving the back surface, heading on along +x
        if seg.interaction_type != "refract" or x2 <= back or x1 < -0.5 or abs(y2 - y1) < 1e-12:
            continue
        root = seg
        while root.parent_uuid:
            root = result.lineage.get_segment(root.parent_uuid)
        crossings[round(root.p1["y"], 6)] = x1 - y1 * (x2 - x1) / (y2 - y1)
    return crossings


def _thick_lens_back_focus(R1, R2, d=D, n=N):
    """Back focal point, from the back vertex, for light meeting R1 first (Cartesian signs)."""
    f = 1.0 / ((n - 1) * (1 / R1 - 1 / R2 + (n - 1) * d / (n * R1 * R2)))
    return f * (1 - (n - 1) * d / (n * R1))


def test_r1_is_the_surface_on_the_plus_x_side():
    """With p1 above p2, r1 shapes the +x face and r2 the -x face, whichever way the light goes."""
    lens = _lens(Scene(), r1=20.0, r2=-60.0)
    arcs = [s for s in glass_spans(lens.path) if s.is_arc]
    by_side = {("+x" if s.midpoint[0] > 0 else "-x"): s.radius for s in arcs}
    assert by_side["+x"] == pytest.approx(20.0)
    assert by_side["-x"] == pytest.approx(60.0)
    # Centre thickness d sits between the two vertices on the axis.
    vertices = sorted(s.midpoint[0] for s in arcs)
    assert vertices[1] - vertices[0] == pytest.approx(D)


def test_positive_radii_make_a_biconvex_lens_from_both_sides():
    """r1 > 0 bulges the +x face outward (+x); r2 < 0 bulges the -x face outward (-x)."""
    lens = _lens(Scene(), r1=20.0, r2=-60.0)
    arcs = {("+x" if s.midpoint[0] > 0 else "-x"): s for s in glass_spans(lens.path) if s.is_arc}
    assert arcs["+x"].center[0] < arcs["+x"].midpoint[0]   # centre of curvature inside the lens
    assert arcs["-x"].center[0] > arcs["-x"].midpoint[0]


def test_paraxial_focus_matches_the_thick_lens_formula():
    # Light along +x meets the -x face first: radius 60 with its centre on +x (R1 = +60),
    # then the +x face, radius 20 with its centre on -x (R2 = -20).
    expected = D / 2 + _thick_lens_back_focus(60.0, -20.0)
    crossing = _axis_crossings(20.0, -60.0, [0.25])[0.25]
    assert crossing == pytest.approx(expected, abs=0.01)


def test_spherical_aberration_grows_as_height_squared():
    heights = [0.5, 1.0, 2.0]
    paraxial = D / 2 + _thick_lens_back_focus(60.0, -20.0)
    crossings = _axis_crossings(20.0, -60.0, heights)
    lsa = {h: crossings[h] - paraxial for h in heights}
    assert all(v < 0 for v in lsa.values())          # marginal rays focus short: undercorrected
    assert lsa[1.0] / lsa[0.5] == pytest.approx(4.0, rel=0.05)
    assert lsa[2.0] / lsa[1.0] == pytest.approx(4.0, rel=0.05)


def test_dr1r2_parameters_round_trip():
    lens = _lens(Scene(), r1=20.0, r2=-60.0)
    params = lens.get_dr1r2()
    assert params["d"] == pytest.approx(D)
    assert params["r1"] == pytest.approx(20.0)
    assert params["r2"] == pytest.approx(-60.0)


def test_negative_radii_build_a_biconcave_lens():
    lens = _lens(Scene(), r1=-20.0, r2=60.0)
    arcs = {("+x" if s.midpoint[0] > 0 else "-x"): s for s in glass_spans(lens.path) if s.is_arc}
    assert arcs["+x"].center[0] > arcs["+x"].midpoint[0]   # centres of curvature outside the lens
    assert arcs["-x"].center[0] < arcs["-x"].midpoint[0]
    assert math.isclose(arcs["+x"].radius, 20.0) and math.isclose(arcs["-x"].radius, 60.0)
