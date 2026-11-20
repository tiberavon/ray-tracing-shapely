"""
Python-specific module: test spline mirror
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
SplineMirror: an exact mirror through designed points and normals
===============================================================================
Through points of the parabola y = x^2/4 with its normals, the mirror sends
rays parallel to the axis to the focus (0, 1): exactly where a ray meets it
at one of its points, and between them to the spline's interpolation, which
shrinks as the cube of the spacing. Both faces reflect. Exported as a sheet
profile and rebuilt, it is the same mirror; a spline crossing the axis
without a point on it is refused, since its half-section would not start on
one of its points.
===============================================================================
"""

from __future__ import annotations

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.mirrors import SplineMirror, mirrors_from_sheet_profile
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_sheet_profile

AXIS = {"kind": "revolve", "axis": {"point": [0.0, 0.0], "direction": [0.0, 1.0]}}


def _parabola(spacing):
    xs = [-2.0 + spacing * k for k in range(int(round(4.0 / spacing)) + 1)]
    return [(x, x * x / 4.0) for x in xs], [(-x / 2.0, 1.0) for x in xs]


def _miss(points, normals, x0, from_above=True):
    """How far the reflected ray passes from the focus, and whether it went back the way it came."""
    scene = Scene()
    scene.add_object(SplineMirror(scene, points, normals, name="P"))
    y0, dy = (5.0, -1.0) if from_above else (-5.0, 1.0)
    scene.add_object(SingleRay(scene, {"p1": {"x": x0, "y": y0}, "p2": {"x": x0, "y": y0 + dy}}))
    (out,) = [g for g in Simulator(scene, max_rays=5).run_with_result(name="p").segments if g.parent_uuid]
    a, d = (out.p1["x"], out.p1["y"]), (out.p2["x"] - out.p1["x"], out.p2["y"] - out.p1["y"])
    return abs(-a[0] * d[1] - (1.0 - a[1]) * d[0]) / math.hypot(*d), d[1] * dy < 0.0


def test_at_its_points_the_reflection_is_exact_from_either_face():
    points, normals = _parabola(0.5)
    for x0 in (-1.5, -0.5, 1.0, 1.5):
        for above in (True, False):
            miss, back = _miss(points, normals, x0, above)
            assert miss < 1e-12 and back


def test_between_its_points_the_error_falls_as_the_cube_of_the_spacing():
    xs = [-1.9 + 0.0371 * k for k in range(100)]
    worst = [max(_miss(*_parabola(h), x0)[0] for x0 in xs) for h in (0.5, 0.25)]
    assert worst[0] < 2e-3 and 6.0 < worst[0] / worst[1] < 10.0           # 1.4e-3, then 1.8e-4


def test_a_sheet_profile_rebuilds_the_same_mirror():
    points, normals = _parabola(0.5)
    mirror = SplineMirror(Scene(), points, normals, name="P")
    profile = export_sheet_profile([mirror], symmetry=AXIS, physical_params={}, numerical_params={})
    (span,) = profile["spans"]
    assert span["curve"]["type"] == "spline" and span["mechanism"] == "reflect"
    assert span["curve"]["points"][0] == [0.0, 0.0]                           # the half-section starts on the axis
    (back,) = mirrors_from_sheet_profile(Scene(), profile)
    assert isinstance(back, SplineMirror) and back.name == "P"
    assert len(back.curve.points) == len(points)
    for p, q in zip(sorted(back.curve.points), sorted(points)):
        assert math.dist(p, q) < 1e-12
    for k, p in enumerate(back.curve.points):                      # the same normal at the same point
        j = min(range(len(points)), key=lambda i: math.dist(points[i], p))
        a, b = back.normal_at(float(k)), mirror.normal_at(float(j))
        assert abs(a[0] * b[1] - a[1] * b[0]) < 1e-12


def test_a_spline_crossing_the_axis_between_its_points_is_refused():
    points, normals = _parabola(0.5)
    shifted = [(x + 0.25, y) for x, y in points]
    with pytest.raises(ValueError):
        # not symmetric about the axis, so refused before its crossing is looked at
        export_sheet_profile([SplineMirror(Scene(), shifted, normals, name="P")], symmetry=AXIS,
                             physical_params={}, numerical_params={})
    xs = [-1.75 + 0.5 * k for k in range(8)]                                   # no point at x = 0
    mirror = SplineMirror(Scene(), [(x, x * x / 4.0) for x in xs], [(-x / 2.0, 1.0) for x in xs], name="P")
    with pytest.raises(NotImplementedError, match="on the axis"):
        export_sheet_profile([mirror], symmetry=AXIS, physical_params={}, numerical_params={})


def test_bad_input_is_refused():
    with pytest.raises(ValueError):
        SplineMirror(Scene(), [(0.0, 0.0), (1.0, 0.0)], [(0.0, 1.0)])
    with pytest.raises(ValueError):
        SplineMirror(Scene(), [(0.0, 0.0), (1.0, 0.0)], [(0.0, 1.0), (0.0, 0.0)])
    with pytest.raises(ValueError):
        SplineMirror(Scene(), [(0.0, 0.0), (0.0, 0.0)], [(0.0, 1.0), (0.0, 1.0)])
