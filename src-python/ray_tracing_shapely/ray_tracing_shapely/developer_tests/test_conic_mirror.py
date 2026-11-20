"""
Python-specific module: test conic mirror
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

ConicMirror / ArcMirror, exact curved mirrors in 2D, and the
sheet export, and its inverse (mirrors_from_sheet_profile).

Every optical check is a property with an exact answer, so a sampled or
approximate curve fails it: a conic sends a ray from one focus through the
other (on axis, at z = R/(1 + e) and R/(1 - e) from the vertex, e = sqrt(-K);
a parabola's second focus is at infinity), and a sphere's marginal ray
crosses the axis at R - R/(2 cos theta).
"""

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.mirrors import ArcMirror, ConicMirror, mirrors_from_sheet_profile
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_sheet_profile
from ray_tracing_shapely.optical_elements.lenses import SingletLens
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_profile
from ray_tracing_shapely.optical_elements.roles import Role

TOL = 1e-11


def _trace(scene, start, direction, max_rays=50):
    scene.add_object(SingleRay(scene, {"p1": {"x": start[0], "y": start[1]},
                                       "p2": {"x": start[0] + direction[0],
                                              "y": start[1] + direction[1]}}))
    return Simulator(scene, max_rays=max_rays).run_with_result(name="m").segments


def _line_distance(point, seg):
    """Distance from ``point`` to the infinite line through a segment."""
    (x1, y1), (x2, y2) = (seg.p1["x"], seg.p1["y"]), (seg.p2["x"], seg.p2["y"])
    dx, dy = x2 - x1, y2 - y1
    return abs((point[0] - x1) * dy - (point[1] - y1) * dx) / math.hypot(dx, dy)


def _frame(angle_deg, origin=(3.0, -2.0)):
    """A vertex and axis at an arbitrary place and orientation, and a map from (s, z)."""
    a = math.radians(angle_deg)
    axis = (math.cos(a), math.sin(a))
    left = (-axis[1], axis[0])

    def at(s, z):
        return (origin[0] + s * left[0] + z * axis[0], origin[1] + s * left[1] + z * axis[1])
    return origin, axis, at


# --- optics -------------------------------------------------------------------------------

@pytest.mark.parametrize("angle", [0.0, 37.0, 180.0, -100.0])
def test_a_parabola_sends_every_parallel_ray_through_its_focus(angle):
    vertex, axis, at = _frame(angle)
    R = 40.0
    for h in (-14.0, -6.0, 0.5, 3.0, 12.0):
        scene = Scene()
        scene.add_object(ConicMirror(scene, vertex, axis, R, -1.0, semi_diameter=15.0, name="P"))
        segs = _trace(scene, at(h, 60.0), (-axis[0], -axis[1]))
        assert len(segs) == 2
        assert _line_distance(at(0.0, R / 2), segs[1]) < TOL


@pytest.mark.parametrize("conic", [-0.5, -0.9, -2.0, -5.0])
@pytest.mark.parametrize("angle", [0.0, 23.0])
def test_a_conic_sends_a_ray_from_one_focus_through_the_other(conic, angle):
    """Prolate ellipses (-1 < K < 0) and hyperbolas (K < -1); for a hyperbola the
    second focus is virtual, behind the vertex. (An oblate ellipse, K > 0, has
    its foci off the axis.)"""
    vertex, axis, at = _frame(angle)
    R, e = 10.0, math.sqrt(-conic)
    f1, f2 = at(0.0, R / (1 + e)), at(0.0, R / (1 - e))
    h_max = min(9.0, 0.95 * (R / math.sqrt(1 + conic) if conic > -1 else 9.0))
    for frac in (-1.0, -0.4, 0.3, 0.8):
        scene = Scene()
        mirror = ConicMirror(scene, vertex, axis, R, conic, semi_diameter=h_max * 1.01, name="C")
        scene.add_object(mirror)
        target = mirror.point_at(frac * h_max)
        segs = _trace(scene, f1, (target[0] - f1[0], target[1] - f1[1]))
        assert math.dist((segs[0].p2["x"], segs[0].p2["y"]), target) < 1e-9
        assert _line_distance(f2, segs[1]) < 1e-9


def test_a_sphere_has_exactly_its_spherical_aberration():
    vertex, axis, at = _frame(15.0)
    R = 30.0
    for h in (1.0, 8.0, 15.0, 20.0):
        scene = Scene()
        scene.add_object(ArcMirror(scene, vertex, axis, R, semi_diameter=21.0, name="S"))
        segs = _trace(scene, at(h, 50.0), (-axis[0], -axis[1]))
        theta = math.asin(h / R)
        assert _line_distance(at(0.0, R - R / (2 * math.cos(theta))), segs[1]) < TOL


def test_a_ray_reflected_twice_meets_the_mirror_twice():
    """A hemisphere: a parallel ray beyond 45 deg incidence reflects onto the
    mirror again. The first hit's own point is skipped, the second is not."""
    scene = Scene()
    mirror = ArcMirror(scene, (0.0, 0.0), (1.0, 0.0), 10.0, semi_diameter=10.0, name="H")
    scene.add_object(mirror)
    segs = _trace(scene, (20.0, 8.0), (-1.0, 0.0))
    hits = [(s.p2["x"], s.p2["y"]) for s in segs[:-1]]
    assert len(segs) >= 3
    for p in hits[:2]:
        assert abs(math.dist(p, mirror.center) - 10.0) < 1e-12
    assert math.dist(hits[0], hits[1]) > 1.0


def test_a_root_too_close_to_the_start_is_skipped_not_returned():
    """A ray starting 1e-12 off the mirror, heading across it: its first root
    is ~1e-12 away, below the simulator's minimum segment length, which would
    drop the whole object; the mirror must answer with the far crossing."""
    scene = Scene()
    mirror = ArcMirror(scene, (0.0, 0.0), (1.0, 0.0), 10.0, semi_diameter=10.0, name="H")
    p = mirror.point_at(-6.0)
    n = mirror.normal_at(-6.0)                       # towards the centre (inside)
    start = (p[0] - 1e-12 * n[0], p[1] - 1e-12 * n[1])
    target = mirror.point_at(7.0)

    class _Ray:
        p1 = {"x": start[0], "y": start[1]}
        p2 = {"x": target[0], "y": target[1]}

    hit = mirror.check_ray_intersects(_Ray())
    assert hit is not None
    assert math.dist((hit.x, hit.y), target) < 1e-9


def test_only_the_vertex_branch_within_the_extent_is_a_mirror():
    scene = Scene()
    # Ellipse R = 10, K = -0.5: the whole curve spans z in [0, 40]; the mirror is z <= 20.
    mirror = ConicMirror(scene, (0.0, 0.0), (1.0, 0.0), 10.0, -0.5, semi_diameter=14.0, name="E")
    scene.add_object(mirror)
    assert len(_trace(scene, (30.0, 0.0), (1.0, 0.0))) == 1           # the far branch: no hit
    for h, segments in ((1.0, 1), (5.0, 2)):                              # outside, inside the extent
        scene = Scene()
        scene.add_object(ConicMirror(scene, (0.0, 0.0), (1.0, 0.0), 40.0, -1.0, extent=(2.0, 10.0),
                                     name="P"))
        assert len(_trace(scene, (30.0, h), (-1.0, 0.0))) == segments


def test_hits_are_recorded_with_the_exact_normal():
    scene = Scene()
    mirror = ConicMirror(scene, (0.0, 0.0), (1.0, 0.0), 40.0, -1.0, semi_diameter=15.0, name="P")
    scene.add_object(mirror)
    scene.add_object(SingleRay(scene, {"p1": {"x": 30.0, "y": 8.0}, "p2": {"x": 29.0, "y": 8.0}}))
    sim = Simulator(scene, max_rays=10)
    sim.record_surface_hits = True
    seg = sim.run_with_result(name="m").segments[0]
    assert seg.hit_surface_uuid == mirror.uuid
    n = mirror.normal_at(8.0)
    assert (seg.hit_normal["x"], seg.hit_normal["y"]) == pytest.approx(n, abs=1e-15)
    assert seg.incident_angle == pytest.approx(math.atan(8.0 / 40.0), abs=1e-14)   # parabola: tan = s/R
    assert segs_interaction(sim) == "reflect"


def segs_interaction(sim):
    return sim.ray_segments[1].interaction_type


def test_labels_and_refusals():
    scene = Scene()
    m = ConicMirror(scene, (0, 0), (1, 0), 10.0, -1.0, semi_diameter=5.0, name="P")
    assert (m.name, m.role, m.mechanism.value) == ("P", Role.WALL, "reflect")
    for kwargs, match in [
        (dict(radius=0.0, semi_diameter=1.0), "finite and non-zero"),
        (dict(radius=math.inf, semi_diameter=1.0), "finite and non-zero"),
        (dict(radius=10.0, semi_diameter=1.0, extent=(0, 1)), "exactly one"),
        (dict(radius=10.0, extent=(1.0, 1.0)), "s_start < s_end"),
        (dict(radius=10.0, conic=-0.5, semi_diameter=14.2), "single-valued"),   # equator at 14.14
    ]:
        with pytest.raises(ValueError, match=match):
            ConicMirror(scene, (0, 0), (1, 0), **kwargs)


# --- the sheet export ----------------------------------------------------------------------

AXIS_X = {"kind": "revolve", "axis": {"point": [0.0, 0.0], "direction": [1.0, 0.0]}}


def _sheet(mirrors, symmetry=AXIS_X, **kw):
    return export_sheet_profile(mirrors, symmetry=symmetry, physical_params={},
                                numerical_params={}, **kw)


def test_a_paraboloid_exports_as_one_conic_span_from_the_axis():
    scene = Scene()
    m = ConicMirror(scene, (5.0, 0.0), (-1.0, 0.0), 40.0, -1.0, semi_diameter=15.0, name="P")
    profile = _sheet([m])
    assert profile["body"] == "sheet" and profile["schema_version"] == "1.5"
    (span,) = profile["spans"]
    assert span["mechanism"] == "reflect" and span["role"] == "wall"
    assert span["curve"] == {"type": "conic", "vertex": [5.0, 0.0], "axis": [-1.0, 0.0],
                             "radius": 40.0, "conic": -1.0}
    pts = profile["points"][span["index_start"]:span["index_end"]]
    assert pts[0] == [5.0, 0.0]                                           # from the axis out
    for p, n in zip(pts, profile["normals"][span["index_start"]:span["index_end"]]):
        assert p[1] >= 0.0                                                # left of +x is +y
        d, inside = m.on_curve(tuple(p))
        assert d < 1e-12 and inside
        assert math.hypot(*n) == pytest.approx(1.0)
    assert profile["construction_params"]["numerical_params"]["curve_samples"] == 33


def test_an_arc_mirror_exports_as_a_circle_and_a_cone_as_one_line():
    scene = Scene()
    arc = ArcMirror(scene, (0.0, 0.0), (1.0, 0.0), 30.0, semi_diameter=10.0, name="S")
    assert _sheet([arc])["spans"][0]["curve"] == {"type": "circle", "center": [30.0, 0.0], "radius": 30.0}
    upper = Mirror(scene, {"p1": {"x": 0.0, "y": 2.0}, "p2": {"x": 20.0, "y": 6.0}})
    lower = Mirror(scene, {"p1": {"x": 0.0, "y": -2.0}, "p2": {"x": 20.0, "y": -6.0}})
    upper.name, lower.name = "WALL", "WALL_MIRROR"
    profile = _sheet([upper, lower])
    (span,) = profile["spans"]
    assert span["short_label"] == "WALL" and span["curve"] == {"type": "line"}
    assert profile["points"] == [[0.0, 2.0], [20.0, 6.0]]


def test_the_sheet_export_refuses_what_a_revolve_cannot_make():
    scene = Scene()
    m = ConicMirror(scene, (0.0, 0.0), (1.0, 0.0), 40.0, -1.0, semi_diameter=10.0, name="P")
    half = ConicMirror(scene, (0.0, 0.0), (1.0, 0.0), 40.0, -1.0, extent=(0.0, 10.0), name="H")
    with pytest.raises(ValueError, match="not mirror-symmetric"):
        _sheet([half])
    tilted = ConicMirror(scene, (0.0, 0.0), (math.cos(0.1), math.sin(0.1)), 40.0, -1.0,
                         semi_diameter=10.0, name="T")
    tilted_twin = ConicMirror(scene, (0.0, 0.0), (math.cos(0.1), -math.sin(0.1)), 40.0, -1.0,
                              semi_diameter=10.0, name="T2")
    with pytest.raises(NotImplementedError, match="CPC"):
        _sheet([tilted, tilted_twin])
    unnamed = ConicMirror(scene, (0.0, 0.0), (1.0, 0.0), 40.0, -1.0, semi_diameter=10.0)
    with pytest.raises(ValueError, match="distinct name"):
        _sheet([unnamed])
    with pytest.raises(NotImplementedError, match="revolve only"):
        _sheet([m], symmetry={"kind": "extrude", "plane_axes": ["x", "z"], "extrude_axis": "y",
                              "length": 1.0})


# --- drawing --------------------------------------------------------------------------------

def test_the_svg_renderer_draws_a_conic_mirror_as_its_curve():
    import re

    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    scene = Scene()
    m = ConicMirror(scene, (0.0, 0.0), (1.0, 0.0), 40.0, -1.0, semi_diameter=15.0, name="P")
    flat = Mirror(scene, {"p1": {"x": 20.0, "y": -5.0}, "p2": {"x": 20.0, "y": 5.0}})
    scene.add_object(m)
    scene.add_object(flat)
    renderer = SVGRenderer(width=200, height=200, viewbox=(-20, -20, 60, 40))
    renderer.draw_scene(scene, [], draw_edge_labels=False)
    svg = renderer.to_string()
    (points,) = re.findall(r'<polyline[^>]*points="([^"]+)"', svg)
    drawn = [tuple(float(v) for v in pair.split(",")) for pair in points.split()]
    expected = m.sample_points()
    assert len(drawn) == len(expected)
    assert max(math.dist(a, b) for a, b in zip(drawn, expected)) < 1e-6
    assert len(re.findall(r"<line ", svg)) == 1           # the flat mirror, still a line
    assert ">P<" in svg                                    # the curved mirror's label


# --- the sheet rebuild ------------------------------------------------------------------


def _exported_sheet(mirrors, axis_point, axis, **symmetry):
    return export_sheet_profile(mirrors, symmetry={"kind": "revolve", "axis": {"point": list(axis_point),
                                                                               "direction": list(axis)},
                                                   **symmetry}, physical_params={}, numerical_params={})


@pytest.mark.parametrize("angle", [0.0, 37.0, -100.0])
def test_a_rebuilt_paraboloid_is_one_mirror_with_its_focus(angle):
    vertex, axis, at = _frame(angle)
    R = 40.0
    profile = _exported_sheet([ConicMirror(Scene(), vertex, axis, R, -1.0, semi_diameter=15.0, name="P")], vertex, axis)
    (m,) = mirrors_from_sheet_profile(Scene(), profile)
    assert type(m) is ConicMirror and m.name == "P" and m.role is Role.WALL
    assert m.extent == pytest.approx((-15.0, 15.0), abs=1e-9)
    want = ConicMirror(Scene(), vertex, axis, R, -1.0, semi_diameter=1.0).descriptor()
    got = m.descriptor()
    assert got["vertex"] == pytest.approx(want["vertex"]) and got["axis"] == pytest.approx(want["axis"])
    assert (got["radius"], got["conic"]) == pytest.approx((want["radius"], want["conic"]))
    for h in (-14.0, -6.0, 0.5, 12.0):
        scene = Scene()
        scene.add_object(mirrors_from_sheet_profile(scene, profile)[0])
        segs = _trace(scene, at(h, 60.0), (-axis[0], -axis[1]))
        assert len(segs) == 2 and _line_distance(at(0.0, R / 2), segs[1]) < TOL


def test_a_zone_comes_back_in_two_and_a_cut_sheet_in_one_half():
    vertex, axis, _ = _frame(0.0)
    zone = ConicMirror(Scene(), vertex, axis, 30.0, -0.5, extent=(4.0, 20.0), name="Z")
    image = ConicMirror(Scene(), vertex, axis, 30.0, -0.5, extent=(-20.0, -4.0), name="Z_far")
    whole = mirrors_from_sheet_profile(Scene(), _exported_sheet([zone, image], vertex, axis))
    assert [x for m in sorted(whole, key=lambda m: m.extent) for x in m.extent] == pytest.approx(
        [-20.0, -4.0, 4.0, 20.0], abs=1e-9)
    (half,) = mirrors_from_sheet_profile(Scene(), _exported_sheet([zone], vertex, axis, azimuth_deg=[-90, 90]))
    assert half.extent == pytest.approx((4.0, 20.0), abs=1e-9)


def test_a_sphere_and_a_flat_mirror_across_the_axis_are_joined():
    sphere = ArcMirror(Scene(), (40.0, 0.0), (1.0, 0.0), -40.0, semi_diameter=20.0, name="S")
    flat = Mirror(Scene(), {"p1": {"x": -5.0, "y": -3.0}, "p2": {"x": -5.0, "y": 3.0}})
    flat.name = "F"
    cone = Mirror(Scene(), {"p1": {"x": 0.0, "y": 0.0}, "p2": {"x": 10.0, "y": 5.0}})     # from the axis, slanted
    cone.name = "C"
    cone_image = Mirror(Scene(), {"p1": {"x": 0.0, "y": 0.0}, "p2": {"x": 10.0, "y": -5.0}})
    cone_image.name = "C_far"
    s, f, c, c_image = mirrors_from_sheet_profile(Scene(), _exported_sheet([sphere, flat, cone, cone_image], (0.0, 0.0),
                                                                  (1.0, 0.0)))
    assert type(s) is ArcMirror and s.extent == pytest.approx((-20.0, 20.0)) and s.center == pytest.approx((0.0, 0.0))
    assert sorted((f.p1["y"], f.p2["y"])) == pytest.approx([-3.0, 3.0]) and f.name == "F"
    assert {(c.p2["y"]), (c_image.p2["y"])} == {5.0, -5.0} and c.name == c_image.name == "C"


def test_the_sheet_rebuild_refuses_what_is_not_a_exported_sheet():
    lens = SingletLens(Scene(), radius_front=60.0, radius_back=-20.0, thickness=5.0, semi_diameter=10.0, n=1.5)
    solid = export_profile(lens, symmetry={"kind": "revolve", "axis": lens.revolve_axis()},
                           physical_params={}, numerical_params={})
    with pytest.raises(ValueError, match="from_profile"):
        mirrors_from_sheet_profile(Scene(), solid)
    vertex, axis, _ = _frame(0.0)
    sheet = _exported_sheet([ConicMirror(Scene(), vertex, axis, 40.0, -1.0, semi_diameter=15.0, name="P")], vertex, axis)
    moved = {**sheet, "points": [[x + 1e-3, y] for x, y in sheet["points"]]}
    with pytest.raises(ValueError, match="from the vertex branch"):
        mirrors_from_sheet_profile(Scene(), moved)
    refracting = {**sheet, "spans": [{**sheet["spans"][0], "mechanism": "refract"}]}
    with pytest.raises(ValueError, match="reflect"):
        mirrors_from_sheet_profile(Scene(), refracting)
