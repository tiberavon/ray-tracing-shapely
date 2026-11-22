"""
Python-specific module: test asphere curve
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
An exact even-asphere edge: the conic plus a polynomial, in 2D
===============================================================================
With no coefficients the asphere must be the conic, point for point, and
focus as the conic does. With coefficients, a ray leaving through the face
must bend by Snell's law at the face's own slope, computed here from a sag
written out independently. A line crossing the face twice inside one search
sub-interval must be found twice. The descriptor, moves and scaling carry
the exact curve, and the analysis layer names it. Through ``profile.json``
(schema 1.5) it comes back as the same asphere, its two halves joined when
the profile is a revolve half-section, and a sample off it is refused.
===============================================================================
"""

from __future__ import annotations

import json
import math
import random

import pytest

from ray_tracing_shapely.analysis.glass_geometry import EdgeType, get_edge_descriptions
from ray_tracing_shapely.core.glass_curves import (ASPHERE_INTERVALS, AsphereCurve, ConicCurve,
                                                   curve_from_descriptor, transform_descriptor)
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.optical_elements.curved_glass import CurvedGlass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
from ray_tracing_shapely.optical_elements.prisms.profile_export import PROFILE_SCHEMA_VERSION, export_profile
from ray_tracing_shapely.optical_elements.roles import Mechanism, Role

N = 1.5
R, T, H = 20.0, 12.0, 10.0
X0, Y0 = 100.0, 30.0
#: The ACL25416U's first surface (Thorlabs' .zmx): R, K and A2 .. A10, the r**2 term 0.
ACL = dict(radius=8.818197, conic=-0.99917152,
           coefficients=[0.0, 8.6821674e-5, 6.3760123e-8, 2.4073084e-9, -1.7189021e-11])


def _sag(s, radius, conic, coefficients):
    """The even asphere's sag, written out here independently of the class."""
    c = 1.0 / radius
    z = c * s * s / (1.0 + math.sqrt(1.0 - (1.0 + conic) * c * c * s * s))
    return z + sum(a * s ** (2 * i) for i, a in enumerate(coefficients, start=1))


def _lens(scene, desc, face):
    """Flat face at x0, the curve ``face`` (vertex at x0 + T, axis -x) from y0 - h to y0 + h."""
    lo, hi = face.point(H), face.point(-H)
    return CurvedGlass(scene, {"path": [{"x": X0, "y": Y0 + H, "arc": False},
                                  {"x": X0, "y": Y0 - H, "arc": False},
                                  {"x": lo[0], "y": lo[1], "arc": False, "curve": desc},
                                  {"x": hi[0], "y": hi[1], "arc": False}],
                         "refIndex": N, "notDone": False})


def _exits(face, heights):
    """Each collimated ray's direction after the curved face, by height above the axis."""
    scene = Scene()
    scene.add_object(_lens(scene, face.descriptor(), face))
    for y in heights:
        scene.add_object(SingleRay(scene, {"p1": {"x": X0 - 20.0, "y": Y0 + y}, "p2": {"x": X0 - 19.0, "y": Y0 + y}}))
    segs = Simulator(scene, max_rays=10_000).run_with_result(name="asphere").segments
    out = {}
    for sg in segs:
        dx, dy = sg.p2["x"] - sg.p1["x"], sg.p2["y"] - sg.p1["y"]
        if sg.p1["x"] > X0 + 1.0 and dx > 0 and sg.total_brightness > 0.5:
            norm = math.hypot(dx, dy)
            out[round(sg.p1["y"] - Y0, 6)] = (sg.p1["x"], sg.p1["y"], dx / norm, dy / norm)
    return out


def test_without_coefficients_it_is_the_conic():
    conic = ConicCurve((X0 + T, Y0), (-1.0, 0.0), R, -N * N, -H, H)
    asphere = AsphereCurve((X0 + T, Y0), (-1.0, 0.0), R, -N * N, [], -H, H)
    for s in (-H, -3.3, 0.0, 4.1, H):
        assert math.dist(conic.point(s), asphere.point(s)) < 1e-12
        assert math.dist(conic.deriv(s), asphere.deriv(s)) < 1e-12
        assert math.dist(conic.deriv2(s), asphere.deriv2(s)) < 1e-12
    rng = random.Random(3)
    for _ in range(200):
        o = (X0 + rng.uniform(-10, 30), Y0 + rng.uniform(-15, 15))
        a = rng.uniform(0, 2 * math.pi)
        d = (math.cos(a), math.sin(a))
        want, got = conic.line_hits(o, d), asphere.line_hits(o, d)
        assert len(want) == len(got)
        assert all(abs(t1 - t2) < 1e-9 and abs(p1 - p2) < 1e-9 for (t1, p1), (t2, p2) in zip(want, got))
    # the hyperbola K = -n^2 focuses collimated light exactly; so must the asphere that is it
    focus = X0 + T + R / (N - 1)
    for ray in _exits(asphere, [k * 0.9 for k in (-9, -5, -1, 2, 6, 9)]).values():
        x, y, dx, dy = ray
        assert abs(x + (Y0 - y) / dy * dx - focus) < 1e-9


def test_a_ray_leaving_through_the_polynomial_bends_at_its_own_slope():
    coefficients = [0.0, 2.0e-4, -1.5e-6]
    face = AsphereCurve((X0 + T, Y0), (-1.0, 0.0), R, -1.2, coefficients, -H, H)
    heights = [-8.5, -4.0, -1.0, 0.7, 3.3, 7.9]
    exits = _exits(face, heights)
    assert len(exits) == len(heights)
    h = 1e-6
    for y, (x, y_hit, dx, dy) in exits.items():
        s = -(y_hit - Y0)                                     # the axis is -x, so s runs along -y
        slope = (_sag(s + h, R, -1.2, coefficients) - _sag(s - h, R, -1.2, coefficients)) / (2 * h)
        assert x == pytest.approx(X0 + T - _sag(s, R, -1.2, coefficients), abs=1e-9)
        # the face's outward normal, in (x, y): the surface is x = x0 + T - z(s), y = y0 - s
        nx, ny = 1.0, -slope                                  # from dx/ds = -z', dy/ds = -1
        norm = math.hypot(nx, ny)
        nx, ny = nx / norm, ny / norm
        cos_i = nx                                            # the ray arrives along +x
        sin_t = N * math.sqrt(max(0.0, 1.0 - cos_i * cos_i))
        cos_t = math.sqrt(1.0 - sin_t * sin_t)
        want = (N * 1.0 + (cos_t - N * cos_i) * nx, (cos_t - N * cos_i) * ny)
        want_norm = math.hypot(*want)
        assert (dx, dy) == pytest.approx((want[0] / want_norm, want[1] / want_norm), abs=1e-9)


def test_a_line_crossing_twice_inside_one_subinterval_is_found():
    a1 = 0.05
    lo, hi = -10.0, 9.3                                       # 0 is not a sub-interval edge
    face = AsphereCurve((0.0, 0.0), (1.0, 0.0), None, 0.0, [a1], lo, hi)     # z = a1 s^2
    width = (hi - lo) / ASPHERE_INTERVALS
    s_cross = 0.2 * width                                     # both crossings well inside one sub-interval
    z_line = a1 * s_cross ** 2
    hits = face.line_hits((z_line, -5.0), (0.0, 1.0))        # the line z = z_line, along +s
    assert [round(p, 12) for _, p in hits] == [round(-s_cross, 12), round(s_cross, 12)]
    for t, p in hits:
        assert math.dist(face.point(p), (z_line, -5.0 + t)) < 1e-12
    # the ACL25416U's face: every hit lies on the face
    acl = AsphereCurve((0.0, 0.0), (1.0, 0.0), ACL["radius"], ACL["conic"], ACL["coefficients"], -12.7, 12.7)
    rng = random.Random(5)
    for _ in range(100):
        o = (rng.uniform(-5, 15), rng.uniform(-15, 15))
        a = rng.uniform(0, 2 * math.pi)
        d = (math.cos(a), math.sin(a))
        for t, p in acl.line_hits(o, d):
            assert math.dist(acl.point(p), (o[0] + t * d[0], o[1] + t * d[1])) < 1e-9


def test_the_descriptor_and_transforms_carry_the_exact_curve():
    face = AsphereCurve((3.0, 4.0), (0.6, 0.8), ACL["radius"], ACL["conic"], ACL["coefficients"], -12.0, 11.0)
    rebuilt = curve_from_descriptor(face.descriptor(), face.start, face.end)
    assert isinstance(rebuilt, AsphereCurve) and math.dist(rebuilt.point(5.0), face.point(5.0)) < 1e-12
    k = 2.5                                                    # scaled about the origin
    scaled = transform_descriptor(face.descriptor(), lambda q: (k * q[0], k * q[1]), lambda v: v, scale=k)
    big = curve_from_descriptor(scaled, (k * face.start[0], k * face.start[1]), (k * face.end[0], k * face.end[1]))
    for s in (-12.0, -4.0, 0.0, 7.5, 11.0):
        assert math.dist(big.point(k * s), (k * face.point(s)[0], k * face.point(s)[1])) < 1e-9
    flat = AsphereCurve((0.0, 0.0), (1.0, 0.0), None, 0.0, [0.01, 1e-4], -5.0, 5.0)
    assert flat.descriptor()["radius"] is None and flat.point(2.0) == pytest.approx((0.01 * 4 + 1e-4 * 16, 2.0))


def test_what_an_asphere_refuses_and_the_analysis_layer_names_it():
    with pytest.raises(ValueError, match="non-zero"):
        AsphereCurve((0, 0), (1, 0), 0.0, 0.0, [1e-3], -1, 1)
    with pytest.raises(ValueError, match="is a line"):
        AsphereCurve((0, 0), (1, 0), None, 0.0, [0.0, 0.0], -1, 1)
    with pytest.raises(ValueError, match="equator"):
        AsphereCurve((0, 0), (1, 0), 5.0, 0.0, [1e-3], -6.0, 1.0)
    with pytest.raises(ValueError, match="finite"):
        AsphereCurve((0, 0), (1, 0), 5.0, 0.0, [float("nan")], -1, 1)
    face = AsphereCurve((X0 + T, Y0), (-1.0, 0.0), R, -1.2, [0.0, 2.0e-4], -H, H)
    kinds = [d.edge_type for d in get_edge_descriptions(_lens(Scene(), face.descriptor(), face))]
    assert kinds.count(EdgeType.ASPHERE) == 1


# --- profile.json, schema 1.5 ------------------------------------------------------------------

FACE = dict(radius=R, conic=-1.2, coefficients=[0.0, 2.0e-4, -1.5e-6])


class _PlanoAsphereLens(BasePrism):
    """Flat face S1 at x0, the asphere S2 (vertex at x0 + T, axis -x), rims at y0 +- h."""

    _edge_roles = [("S1", "Flat Face", Role.ENTRANCE), ("RIM", "Edge", Role.BLOCKER),
                   ("S2", "Aspheric Face", Role.EXIT), ("RIM", "Edge", Role.BLOCKER)]
    _edge_mechanisms = {"S1": Mechanism.REFRACT, "RIM": None, "S2": Mechanism.REFRACT}

    def __init__(self, scene, face=FACE):
        self._face = face
        super().__init__(scene, size=H, n=N)

    def _compute_path(self):
        c = AsphereCurve((X0 + T, Y0), (-1.0, 0.0), self._face["radius"], self._face["conic"],
                         self._face["coefficients"], -H, H)
        lo, hi = c.point(H), c.point(-H)
        return [{"x": X0, "y": Y0 + H, "arc": False}, {"x": X0, "y": Y0 - H, "arc": False},
                {"x": lo[0], "y": lo[1], "arc": False, "curve": c.descriptor()}, {"x": hi[0], "y": hi[1], "arc": False}]


def _exits_of(glass, heights=(-8.5, -4.0, -1.0, 0.7, 3.3, 7.9)):
    scene = glass.scene
    scene.add_object(glass)
    for y in heights:
        scene.add_object(SingleRay(scene, {"p1": {"x": X0 - 20.0, "y": Y0 + y}, "p2": {"x": X0 - 19.0, "y": Y0 + y}}))
    segs = Simulator(scene, max_rays=10_000).run_with_result(name="asphere").segments
    rays = sorted((sg.p1["y"], sg.p2["x"] - sg.p1["x"], sg.p2["y"] - sg.p1["y"]) for sg in segs
                  if sg.p1["x"] > X0 + 1.0 and sg.p2["x"] > sg.p1["x"] and sg.total_brightness > 0.5)
    return [v for ray in rays for v in ray]                # flat: pytest.approx takes no nested tuples


@pytest.mark.parametrize("face", [FACE, dict(radius=None, conic=0.0, coefficients=[-0.02, 1.0e-5])])
def test_export_and_rebuild_keep_the_exact_asphere(face):
    lens = _PlanoAsphereLens(Scene(), face)
    profile = json.loads(json.dumps(export_profile(lens, symmetry={"kind": "free"}, physical_params={},
                                                   numerical_params={})))
    assert profile["schema_version"] == PROFILE_SCHEMA_VERSION == "1.5"
    s2 = next(sp for sp in profile["spans"] if sp["short_label"] == "S2")
    assert s2["curve"]["type"] == "asphere" and s2["curve"]["coefficients"] == face["coefficients"]
    assert s2["curve"]["radius"] == face["radius"]                      # None survives JSON as null
    rebuilt = BasePrism.from_profile(Scene(), profile, n=N)
    assert [sp.kind for sp in rebuilt.spans] == ["line", "line", "asphere", "line"]
    assert _exits_of(rebuilt) == pytest.approx(_exits_of(_PlanoAsphereLens(Scene(), face)), abs=1e-12)


def test_a_revolve_half_section_rebuilds_the_whole_asphere():
    profile = export_profile(_PlanoAsphereLens(Scene()), symmetry={"kind": "revolve", "axis": {
        "point": [X0, Y0], "direction": [1.0, 0.0]}}, physical_params={}, numerical_params={})
    s2 = next(sp for sp in profile["spans"] if sp["short_label"] == "S2")
    assert min(abs(p[1] - Y0) for p in profile["points"][s2["index_start"]:s2["index_end"]]) < 1e-12
    rebuilt = BasePrism.from_profile(Scene(), profile, n=N)
    assert [sp.kind for sp in rebuilt.spans].count("asphere") == 1        # the two halves are one face again
    assert _exits_of(rebuilt) == pytest.approx(_exits_of(_PlanoAsphereLens(Scene())), abs=1e-9)


def test_from_profile_refuses_a_sample_off_the_asphere_and_a_wrong_normal():
    profile = export_profile(_PlanoAsphereLens(Scene()), symmetry={"kind": "free"}, physical_params={},
                             numerical_params={})
    s2 = next(sp for sp in profile["spans"] if sp["short_label"] == "S2")
    mid = (s2["index_start"] + s2["index_end"]) // 2
    off = {**profile, "points": [list(p) for p in profile["points"]]}
    off["points"][mid][0] += 1e-6
    with pytest.raises(ValueError, match="from its asphere curve"):
        BasePrism.from_profile(Scene(), off, n=N)
    tilted = {**profile, "normals": [list(v) for v in profile["normals"]]}
    nx, ny = tilted["normals"][mid]
    tilted["normals"][mid] = [math.cos(0.01) * nx - math.sin(0.01) * ny, math.sin(0.01) * nx + math.cos(0.01) * ny]
    with pytest.raises(ValueError, match="disagrees"):
        BasePrism.from_profile(Scene(), tilted, n=N)
    other = {**profile, "spans": [dict(sp) for sp in profile["spans"]]}
    k = next(i for i, sp in enumerate(other["spans"]) if sp["short_label"] == "S2")
    other["spans"][k]["curve"] = {**other["spans"][k]["curve"], "coefficients": [0.0, 2.1e-4, -1.5e-6]}
    with pytest.raises(ValueError, match="from its asphere curve"):
        BasePrism.from_profile(Scene(), other, n=N)

