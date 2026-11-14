"""
Python-specific module: test singlet lens profile
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

Span-aware BasePrism, SingletLens, profile.json 1.1 export
(curve descriptors, sampled arcs, the revolve half-section) and
BasePrism.from_profile reading arcs back.

The test lens: R1 = 60, R2 = -20 (Optiland's convention: biconvex), centre
thickness 5, semi-diameter 10, n = 1.5 -- the SphericalLens of
test_spherical_lens.py, with light along +x.
"""

import copy
import json
import math

import pytest
from shapely.geometry import Point

from ray_tracing_shapely.analysis.glass_geometry import glass_to_polygon
from ray_tracing_shapely.core.glass_spans import glass_spans
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.spherical_lens import SphericalLens
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.lenses import SingletLens
from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
from ray_tracing_shapely.optical_elements.prisms.equilateral import EquilateralPrism
from ray_tracing_shapely.optical_elements.prisms.profile_export import (
    DEFAULT_CURVE_SAMPLES,
    PROFILE_SCHEMA_VERSION,
    export_profile,
)
from ray_tracing_shapely.optical_elements.prisms.refractometer import RefractometerPrism

EXTRUDE = {"kind": "extrude", "plane_axes": ["x", "z"], "extrude_axis": "y", "length": 10.0}


def _singlet(scene=None, r1=60.0, r2=-20.0, t=5.0, h=10.0, **kw):
    return SingletLens(scene or Scene(), radius_front=r1, radius_back=r2, thickness=t,
                       semi_diameter=h, n=1.5, **kw)


def _spherical(scene=None):
    return SphericalLens(scene or Scene(), {
        "p1": {"x": 0, "y": 10}, "p2": {"x": 0, "y": -10}, "def_by": "DR1R2",
        "params": {"d": 5.0, "r1": 20.0, "r2": -60.0}, "refIndex": 1.5, "cauchyB": 0.0,
    })


def _revolve(lens):
    return export_profile(lens, symmetry={"kind": "revolve", "axis": lens.revolve_axis()},
                          physical_params={}, numerical_params={})


def _extrude(prism, **kw):
    return export_profile(prism, symmetry=EXTRUDE, physical_params={}, numerical_params={}, **kw)


def _focus_distance(lens, height=0.25):
    """Trace one collimated ray along the lens axis at ``height``; distance from
    the back vertex, along the axis, to where it crosses the axis."""
    scene = Scene()
    lens.scene = scene
    scene.add_object(lens)
    (ux, uy), (vx, vy) = lens.axis_direction, lens.front_vertex
    nx, ny = -uy, ux
    start = (vx - 40 * ux + height * nx, vy - 40 * uy + height * ny)
    scene.add_object(SingleRay(scene, {"p1": {"x": start[0], "y": start[1]},
                                       "p2": {"x": start[0] + ux, "y": start[1] + uy}}))
    result = Simulator(scene, max_rays=100).run_with_result(name="singlet")
    bx, by = lens.back_vertex
    for seg in result.segments:
        (x1, y1), (x2, y2) = (seg.p1["x"], seg.p1["y"]), (seg.p2["x"], seg.p2["y"])
        along1 = (x1 - bx) * ux + (y1 - by) * uy
        if seg.interaction_type != "refract" or along1 < -1.0:   # leaving the back face
            continue
        h1, h2 = (x1 - bx) * nx + (y1 - by) * ny, (x2 - bx) * nx + (y2 - by) * ny
        if h1 > 0 > h2 or h1 < 0 < h2:
            along2 = (x2 - bx) * ux + (y2 - by) * uy
            return along1 + h1 * (along2 - along1) / (h1 - h2)
    raise AssertionError("the ray never crossed the axis behind the lens")


# --- SingletLens ---------------------------------------------------------------------

def test_spans_labels_roles_and_mechanisms():
    lens = _singlet()
    assert [s.kind for s in lens.spans] == ["arc", "line", "arc", "line"]
    labels = [lens.get_functional_label(i)[0] for i in range(4)]
    assert labels == ["S1", "RIM", "S2", "RIM"]
    assert [lens.get_edge_role(i).value for i in range(4)] == ["entrance", "blocker", "exit", "blocker"]
    assert lens._edge_mechanisms["S1"].value == "refract" and lens._edge_mechanisms["RIM"] is None


@pytest.mark.parametrize("rotation", [0.0, 90.0, -37.0])
def test_radii_follow_optilands_sign_convention(rotation):
    """Positive: centre of curvature downstream of the vertex (along the light)."""
    lens = _singlet(rotation=rotation, position=(3.0, -2.0))
    ux, uy = lens.axis_direction
    s1, s2 = lens.spans[0], lens.spans[2]
    for span, vertex, radius in ((s1, lens.front_vertex, 60.0), (s2, lens.back_vertex, -20.0)):
        downstream = (span.center[0] - vertex[0]) * ux + (span.center[1] - vertex[1]) * uy
        assert downstream == pytest.approx(radius)
        assert math.dist(span.midpoint, vertex) == pytest.approx(0.0, abs=1e-12)


def test_a_flat_face_is_a_straight_span():
    lens = _singlet(r1=40.0, r2=math.inf)
    assert [s.kind for s in lens.spans] == ["arc", "line", "line", "line"]
    assert _singlet(r1=None, r2=-40.0).spans[0].kind == "line"


@pytest.mark.parametrize("kw, match", [
    ({"r1": 9.0}, "must exceed the semi-diameter"),
    ({"t": 1.0}, "edge thickness"),
    ({"t": 0.0}, "thickness must be positive"),
    ({"r1": 0.0}, "radius of 0"),
])
def test_impossible_lenses_raise(kw, match):
    with pytest.raises(ValueError, match=match):
        _singlet(**kw)


@pytest.mark.parametrize("rotation", [0.0, 30.0])
def test_traced_focus_matches_the_thick_lens_back_focal_length(rotation):
    lens = _singlet(rotation=rotation, position=(1.0, 2.0))
    assert lens.effective_focal_length() == pytest.approx(30.6383, abs=1e-4)
    assert _focus_distance(lens) == pytest.approx(lens.back_focal_length(), abs=0.01)


def test_from_spherical_lens_is_the_same_outline_and_optics():
    sph = _spherical()
    singlet = SingletLens.from_spherical_lens(sph)
    assert (singlet.radius_front, singlet.radius_back) == pytest.approx((60.0, -20.0))
    assert (singlet.thickness, singlet.semi_diameter) == pytest.approx((5.0, 10.0))
    key = lambda s: (s.kind, round(s.radius or 0, 9), round(s.midpoint[0], 9), round(s.midpoint[1], 9))
    assert sorted(map(key, glass_spans(sph.path))) == sorted(map(key, singlet.spans))
    # Light the other way meets the R = 20 face first: the radii swap and change sign.
    reverse = SingletLens.from_spherical_lens(sph, first_surface="r1")
    assert (reverse.radius_front, reverse.radius_back) == pytest.approx((20.0, -60.0))
    assert reverse.axis_direction == pytest.approx((-1.0, 0.0))
    assert reverse.effective_focal_length() == pytest.approx(singlet.effective_focal_length())


# --- span-aware BasePrism ------------------------------------------------------------

def test_edge_methods_measure_spans():
    lens = _singlet()
    s1 = lens.spans[0]
    assert lens.get_edge_endpoints(0) == (s1.start, s1.end)
    assert lens.get_edge_length(0) == pytest.approx(s1.length) and s1.length > math.dist(s1.start, s1.end)
    assert lens.get_span_curve(0)["type"] == "circle" and lens.get_span_curve(1) == {"type": "line"}
    assert lens.get_span(4) is None and lens.get_edge_endpoints(4) is None
    assert lens.signed_area() == pytest.approx(glass_to_polygon(lens).area, rel=1e-9)


def test_straight_prism_edges_are_unchanged():
    prism = RefractometerPrism.from_critical_ray_path(Scene(), n_prism=1.72, n_target=1.33,
                                                      ray_path_length=20.0)
    n = len(prism.path)
    for i in range(n):
        a, b = prism.path[i], prism.path[(i + 1) % n]
        assert prism.get_edge_endpoints(i) == ((a["x"], a["y"]), (b["x"], b["y"]))


# --- export: schema 1.1 --------------------------------------------------------------

def test_extrude_export_samples_each_arc_on_its_curve():
    lens = _singlet()
    profile = _extrude(lens)
    assert profile["schema_version"] == PROFILE_SCHEMA_VERSION == "1.5"
    assert profile["body"] == "solid"
    assert profile["construction_params"]["numerical_params"]["curve_samples"] == DEFAULT_CURVE_SAMPLES
    poly = glass_to_polygon(lens)
    arcs = [s for s in profile["spans"] if s["curve"]["type"] == "circle"]
    assert [s["short_label"] for s in arcs] == ["S1", "S2"]
    for span in arcs:
        center, radius = span["curve"]["center"], span["curve"]["radius"]
        assert span["index_end"] - span["index_start"] == DEFAULT_CURVE_SAMPLES
        for k in range(span["index_start"], span["index_end"]):
            (px, py), (nx, ny) = profile["points"][k], profile["normals"][k]
            assert math.dist((px, py), center) == pytest.approx(radius, abs=1e-12)
            assert math.hypot(nx, ny) == pytest.approx(1.0)
            # radial, and pointing out of the glass
            assert abs(nx * (py - center[1]) - ny * (px - center[0])) < 1e-9
            assert not poly.contains(Point(px + 1e-3 * nx, py + 1e-3 * ny))
            assert poly.contains(Point(px - 1e-3 * nx, py - 1e-3 * ny))
    json.dumps(profile)


def test_curve_samples_is_configurable_and_bounded():
    profile = _extrude(_singlet(), curve_samples=9)
    assert profile["spans"][0]["index_end"] - profile["spans"][0]["index_start"] == 9
    with pytest.raises(ValueError, match="at least 3"):
        _extrude(_singlet(), curve_samples=2)


def test_straight_export_says_every_span_is_a_line():
    profile = _extrude(EquilateralPrism(Scene(), side_length=50.0))
    assert {s["curve"]["type"] for s in profile["spans"]} == {"line"}
    assert "curve_samples" not in profile["construction_params"]["numerical_params"]


def test_revolve_export_is_the_half_section_from_axis_to_axis():
    lens = _singlet()
    profile = _revolve(lens)
    spans = profile["spans"]
    assert [s["short_label"] for s in spans] == ["S2", "RIM", "S1"]
    points = profile["points"]
    assert points[spans[0]["index_start"]] == pytest.approx([lens.back_vertex[0], 0.0], abs=1e-12)
    assert points[spans[-1]["index_end"] - 1] == pytest.approx([lens.front_vertex[0], 0.0], abs=1e-12)
    assert points[spans[0]["index_start"]][1] == points[spans[-1]["index_end"] - 1][1] == 0.0  # exactly on it
    assert all(y >= 0.0 for _, y in points)            # left of +x is +y
    assert profile["symmetry"]["axis"] == {"point": [0.0, 0.0], "direction": [1.0, 0.0]}
    # Each half-face is still one span sampled on its full circle.
    assert spans[0]["curve"]["radius"] == pytest.approx(20.0)
    assert spans[0]["index_end"] - spans[0]["index_start"] == DEFAULT_CURVE_SAMPLES


def test_revolve_export_of_a_rotated_lens_stays_left_of_its_axis():
    lens = _singlet(rotation=37.0, position=(2.0, 5.0))
    profile = _revolve(lens)
    (px, py), (ux, uy) = profile["symmetry"]["axis"]["point"], profile["symmetry"]["axis"]["direction"]
    assert all(ux * (y - py) - uy * (x - px) >= -1e-12 for x, y in profile["points"])


def test_revolve_rejects_an_outline_not_symmetric_about_the_axis():
    lens = _singlet()
    with pytest.raises(ValueError, match="mirror-symmetric"):
        export_profile(lens, symmetry={"kind": "revolve", "axis": {"point": [0, 0.5], "direction": [1, 0]}},
                       physical_params={}, numerical_params={})


@pytest.mark.parametrize("axis", [[0, 0], {"point": [0, 0]}, {"point": [0, 0], "direction": [0, 0]}])
def test_revolve_rejects_a_malformed_axis(axis):
    with pytest.raises(ValueError, match="axis"):
        export_profile(_singlet(), symmetry={"kind": "revolve", "axis": axis},
                       physical_params={}, numerical_params={})


# --- from_profile: reading arcs and half-sections back --------------------------------

def _cyclic_key(prism):
    return sorted(
        (prism.get_functional_label(s.index)[0], s.kind, round(s.radius or 0.0, 9),
         round(s.midpoint[0], 9), round(s.midpoint[1], 9))
        for s in prism.spans
    )


def test_extrude_round_trip_keeps_the_path_and_labels():
    lens = _singlet(rotation=20.0, position=(1.0, -3.0))
    profile = _extrude(lens)
    rebuilt = BasePrism.from_profile(Scene(), profile, n=1.5)
    assert type(rebuilt) is BasePrism
    assert len(rebuilt.path) == len(lens.path)
    for a, b in zip(rebuilt.path, lens.path):
        assert a["arc"] == b["arc"] and (a["x"], a["y"]) == pytest.approx((b["x"], b["y"]), abs=1e-12)
    again = _extrude(rebuilt)
    for a, b in zip(again["spans"], profile["spans"]):
        assert {k: v for k, v in a.items() if k != "curve"} == {k: v for k, v in b.items() if k != "curve"}
        assert a["curve"]["type"] == b["curve"]["type"]
        if a["curve"]["type"] == "circle":
            assert a["curve"]["radius"] == pytest.approx(b["curve"]["radius"], abs=1e-9)
            assert a["curve"]["center"] == pytest.approx(b["curve"]["center"], abs=1e-9)
    for a, b in zip(again["points"], profile["points"]):
        assert a == pytest.approx(b, abs=1e-9)


def test_revolve_round_trip_rebuilds_the_full_section():
    lens = _singlet(r1=40.0, r2=math.inf, rotation=-15.0)
    rebuilt = BasePrism.from_profile(Scene(), _revolve(lens), n=1.5)
    assert len(rebuilt.spans) == 4, "each face cut at the axis is one surface again"
    assert _cyclic_key(rebuilt) == _cyclic_key(lens)
    assert _focus_distance_rebuilt(rebuilt, lens) == pytest.approx(lens.back_focal_length(), abs=0.01)


def _focus_distance_rebuilt(rebuilt, lens):
    """The rebuilt BasePrism has no axis attributes; borrow the lens's."""
    rebuilt.axis_direction, rebuilt.front_vertex, rebuilt.back_vertex = (
        lens.axis_direction, lens.front_vertex, lens.back_vertex)
    return _focus_distance(rebuilt)


def test_revolve_round_trip_of_a_cone_keeps_two_sides():
    """A triangle about its apex axis: the base, cut at the axis, joins back;
    the apex is a point on the axis, so the two sides stay two spans."""
    prism = EquilateralPrism(Scene(), side_length=50.0)
    base = prism.spans[prism.find_edge_by_functional_label("B")]
    apex = next(p for p in (s.start for s in prism.spans) if p not in (base.start, base.end))
    mid = base.midpoint
    axis = {"point": list(mid), "direction": [apex[0] - mid[0], apex[1] - mid[1]]}
    profile = export_profile(prism, symmetry={"kind": "revolve", "axis": axis},
                             physical_params={}, numerical_params={})
    assert len(profile["spans"]) == 2
    rebuilt = BasePrism.from_profile(Scene(), profile, n=1.5)
    labels = sorted(rebuilt.get_functional_label(i)[0] for i in range(len(rebuilt.spans)))
    assert len(labels) == 3 and labels.count("B") == 1
    assert rebuilt.signed_area() == pytest.approx(prism.signed_area())


def test_a_profile_without_curves_still_reads_as_straight():
    profile = _extrude(EquilateralPrism(Scene(), side_length=50.0))
    for span in profile["spans"]:
        del span["curve"]
    del profile["body"]
    profile["schema_version"] = "1.0"
    assert len(BasePrism.from_profile(Scene(), profile, n=1.5).spans) == 3


def test_from_profile_rejects_a_sample_off_its_circle():
    profile = _extrude(_singlet())
    k = profile["spans"][0]["index_start"] + 5
    profile["points"][k] = [profile["points"][k][0] + 1e-6, profile["points"][k][1]]
    with pytest.raises(ValueError, match="from its circle"):
        BasePrism.from_profile(Scene(), profile, n=1.5)


def test_from_profile_rejects_a_wrong_normal_on_an_arc():
    profile = _extrude(_singlet())
    k = profile["spans"][2]["index_start"] + 7
    nx, ny = profile["normals"][k]
    profile["normals"][k] = [-nx, -ny]
    with pytest.raises(ValueError, match="stored normal"):
        BasePrism.from_profile(Scene(), profile, n=1.5)


def test_from_profile_rejects_sheets_and_unknown_curves():
    profile = _extrude(_singlet())
    sheet = dict(profile, body="sheet")
    with pytest.raises(ValueError, match="sheet"):
        BasePrism.from_profile(Scene(), sheet, n=1.5)
    unknown = copy.deepcopy(profile)
    unknown["spans"][0]["curve"] = {"type": "bezier", "points": [[0, 0], [1, 1]]}
    with pytest.raises(NotImplementedError, match="bezier"):
        BasePrism.from_profile(Scene(), unknown, n=1.5)
    # a conic is rebuilt since schema 1.2, but only if its samples lie on it
    conic = copy.deepcopy(profile)
    conic["spans"][0]["curve"] = {"type": "conic", "vertex": [0, 0], "axis": [1, 0], "radius": 60, "conic": -1}
    with pytest.raises(ValueError, match="conic"):
        BasePrism.from_profile(Scene(), conic, n=1.5)


def test_from_profile_rejects_a_half_section_off_the_axis():
    profile = _revolve(_singlet())
    profile["symmetry"]["axis"]["point"] = [0.0, -0.5]
    with pytest.raises(ValueError, match="on the axis"):
        BasePrism.from_profile(Scene(), profile, n=1.5)
