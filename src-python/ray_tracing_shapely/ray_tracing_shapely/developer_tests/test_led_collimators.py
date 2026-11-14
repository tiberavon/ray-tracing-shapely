"""
Python-specific module: test led collimators
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

The TIR collimator of US 7,762,697 B2 (FIG. 3) and a Fresnel
collimator, in 2D.

The witness is the design's own promise, checked by the tracer: a ray from F
leaves along the axis. For the TIR collimator, through both channels, to the
spline's accuracy; for the Fresnel lens, exactly through the cap and through
each facet's middle, and within a bound that shrinks with the zone width
elsewhere on a facet. Light the design does not promise to collimate (the
patent's short 22c, the mount, the risers) is found where the design says.
"""

import math
from types import SimpleNamespace

import pytest

from ray_tracing_shapely.analysis.glass_geometry import glass_to_polygon
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.lenses import FresnelLens, TIRCollimator
from ray_tracing_shapely.optical_elements.lenses.collimator_design import ray_through_flat_to
from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_profile
from ray_tracing_shapely.optical_elements.roles import Mechanism

F = (200.0, 50.0)                 # away from the world origin, as every 3D pilot


def _exit(make, angle_deg, origin=F):
    """Trace one ray from ``origin`` at ``angle_deg`` (from +x) through a fresh element.

    Returns:
        (direction of the brightest ray leaving the element in degrees from +x,
         the point it leaves from), or None if nothing leaves it.
    """
    scene = Scene()
    element = make(scene)
    scene.add_object(element)
    t = math.radians(angle_deg)
    scene.add_object(SingleRay(scene, {"p1": {"x": origin[0], "y": origin[1]},
                                       "p2": {"x": origin[0] + math.cos(t), "y": origin[1] + math.sin(t)}}))
    segs = Simulator(scene, max_rays=2000).run_with_result(name="collimator").segments
    leaving = [s for s in segs if s.p1 != {"x": origin[0], "y": origin[1]}
               and element.check_ray_intersects(SimpleNamespace(p1=s.p1, p2=s.p2)) is None]
    if not leaving:
        return None
    s = max(leaving, key=lambda sg: sg.total_brightness)
    return (math.degrees(math.atan2(s.p2["y"] - s.p1["y"], s.p2["x"] - s.p1["x"])),
            (s.p1["x"] - origin[0], s.p1["y"] - origin[1]))


def _tir(**kw):
    return lambda scene: TIRCollimator(scene, position=F, **kw)


def _span(lo, hi, count):
    return [lo + (hi - lo) * (k + 0.5) / count for k in range(count)]


# --- the TIR collimator ------------------------------------------------------------------

def test_the_tir_collimator_has_the_patents_topology_and_labels():
    c = TIRCollimator(Scene(), position=F)
    labels = [c.get_functional_label(i)[0] for i in range(len(c.path))]
    assert labels == ["12b", "22b", "22d-back", "22d-side", "22c", "22a", "ST", "12a",
                      "ST", "22a", "22c", "22d-side", "22d-back", "22b"]
    assert c._edge_mechanisms["22c"] is Mechanism.TIR
    assert all(c._edge_mechanisms[k] is Mechanism.REFRACT for k in ("12a", "12b", "22a", "22b"))
    assert glass_to_polygon(c).is_valid
    d = c.design
    assert d["phi_corner"] == pytest.approx(math.degrees(math.atan2(18.2, 25.9)))
    assert d["phi_corner"] < d["phi_end"] < d["phi_start"] < d["phi_top"]
    assert d["tir_margin_deg"] > 5.0 and d["outer_radius"] == pytest.approx(33.5)
    # 12a's rim, a consequence of the design, lands where FIG. 3 draws it
    # (read there as (28.3, 19.5)): the dimensions and n = 1.49 agree.
    rim = c.path[labels.index("12a")]
    assert abs(rim["x"] - F[0] - 28.3) < 1.0 and abs(-(rim["y"] - F[1]) - 19.5) < 0.2


def test_both_channels_collimate_the_light_of_f():
    c = TIRCollimator(Scene(), position=F)
    d = c.design
    central = _span(-d["phi_corner"], d["phi_corner"], 12)
    ring = _span(d["phi_end"], d["phi_start"], 10)
    for a in central + ring + [-x for x in ring]:
        angle, _ = _exit(_tir(), a)
        assert abs(angle) < 2e-4, a


def test_light_the_design_does_not_collect_goes_where_the_design_says():
    d = TIRCollimator(Scene(), position=F).design
    # Through 22b's front part, short of 22c's end (the patent's short ring): out through
    # 22a without total internal reflection, far off the axis.
    for a in _span(d["phi_corner"] + 0.5, d["phi_end"] - 0.5, 4):
        angle, _ = _exit(_tir(), a)
        assert abs(angle) > 30.0, a
    # Through 22b's rear part, past 22c's start: into the mount, out of its side.
    for a in _span(d["phi_start"], d["phi_top"], 3):
        angle, (x, y) = _exit(_tir(), a)
        assert abs(y - 21.8) < 1e-6 and abs(angle) > 60.0, a


def test_a_full_ring_collects_all_of_22bs_light():
    c = TIRCollimator(Scene(), position=F, outer_radius=None, exit_tilt_deg=12.0)
    assert c.design["phi_end"] == c.design["phi_corner"]
    assert c.design["outer_radius"] == pytest.approx(40.37, abs=0.01)
    for a in _span(c.design["phi_corner"], c.design["phi_start"], 8):
        angle, _ = _exit(_tir(outer_radius=None, exit_tilt_deg=12.0), a)
        assert abs(angle) < 2e-4, a


def test_the_spline_converges_and_a_conic_12a_is_close():
    def worst(**kw):
        d = TIRCollimator(Scene(), position=F, **kw).design
        angles = _span(0.0, d["phi_corner"], 9) + _span(d["phi_end"], d["phi_start"], 9)
        return max(abs(_exit(_tir(**kw), a)[0]) for a in angles)

    coarse, fine = worst(points=7), worst(points=33)
    assert fine < 2e-4 and coarse > 20 * fine
    conic = TIRCollimator(Scene(), position=F, central="conic")
    assert conic.design["conic_K"] == pytest.approx(-0.58, abs=0.02)
    assert conic.design["conic_sag_error"] < 0.02
    # The fitted conic misses the exact face by up to 0.012 mm: 0.34 deg at worst over the
    # central channel (30 rays), 0.20 deg on these 9.
    assert max(abs(_exit(_tir(central="conic"), a)[0]) for a in _span(0.0, 35.0, 9)) < 0.4


def test_a_rotated_collimator_collimates_along_its_axis():
    for a in (10.0, 50.0):
        angle, _ = _exit(_tir(rotation=30.0), 30.0 + a)
        assert abs(angle - 30.0) < 2e-4


def test_the_design_refuses_what_it_cannot_build():
    with pytest.raises(ValueError, match="inside 12a's rim"):
        TIRCollimator(Scene(), outer_radius=None)            # FIG. 3's 14 deg tilt, full ring
    with pytest.raises(ValueError, match="reaches 22c's rear end"):
        TIRCollimator(Scene(), mount_length=40.0)
    with pytest.raises(ValueError, match="outer_radius"):
        TIRCollimator(Scene(), outer_radius=50.0)
    with pytest.raises(ValueError, match="central"):
        TIRCollimator(Scene(), central="bezier")


# --- the Fresnel collimator ----------------------------------------------------------------

def _fresnel(**kw):
    args = dict(focal_distance=20.0, semi_diameter=15.0, zones=5)
    args.update(kw)
    return lambda scene: FresnelLens(scene, position=F, **args)


def _facet_middles(lens):
    """Each upper facet's middle point, relative to F."""
    out = []
    for i, e in enumerate(lens.path):
        label = lens.get_functional_label(i)[0]
        nxt = lens.path[(i + 1) % len(lens.path)]
        if label.startswith("F") and e["y"] + nxt["y"] > 2 * F[1]:
            out.append(((e["x"] + nxt["x"]) / 2 - F[0], (e["y"] + nxt["y"]) / 2 - F[1]))
    return out


@pytest.mark.parametrize("grooves", ["entrance", "exit"])
def test_a_fresnel_lens_is_exact_through_its_cap_and_each_facets_middle(grooves):
    lens = _fresnel(grooves=grooves)(Scene())
    labels = [lens.get_functional_label(i)[0] for i in range(len(lens.path))]
    assert sorted(set(labels)) == sorted({"FLAT", "CAP", "RIM"} | {f"{p}{k}" for k in range(1, 5) for p in "FR"})
    assert glass_to_polygon(lens).is_valid
    cap_tol = 1e-6 if grooves == "entrance" else 2e-5    # a conic cap, or a 17-point spline
    for a in (0.0, 2.0, -4.0, 7.0):
        assert abs(_exit(_fresnel(grooves=grooves), a)[0]) < cap_tol
    middles = _facet_middles(lens)
    assert len(middles) == 4
    for m in middles:
        if grooves == "entrance":
            a = math.degrees(math.atan2(m[1], m[0]))
        else:
            a = math.degrees(ray_through_flat_to(m, 1.49, 20.0)[0])
        assert abs(_exit(_fresnel(grooves=grooves), a)[0]) < 1e-6


def test_narrower_zones_collimate_better():
    def worst(zones):
        lens = _fresnel(zones=zones, grooves="exit")(Scene())
        edge = math.degrees(math.atan2(14.0, 20.0))
        out = []
        for a in _span(0.0, edge, 60):
            r = _exit(_fresnel(zones=zones, grooves="exit"), a)
            if r is not None and abs(r[0]) < 20.0:               # risers and the rim excluded
                out.append(abs(r[0]))
        return max(out), lens

    coarse, _ = worst(5)
    fine, lens = worst(15)
    assert 2.5 < coarse < 5.0 and fine < coarse / 2.5
    assert len(lens.design["facet_angles"]) == 14


def test_risers_facing_the_led_shadow_part_of_the_light():
    # Grooves towards F: the risers face the light, and rays that meet one leave far
    # off the axis. Grooves away from F: the light inside runs nearly along the
    # risers and none is lost to them over the same angles.
    def stray(grooves):
        return sum(1 for a in _span(0.0, 28.0, 56)
                   if abs(_exit(_fresnel(grooves=grooves), a)[0]) > 20.0)

    assert stray("entrance") >= 4 and stray("exit") == 0


def test_a_riser_leans_by_its_draft():
    lens = _fresnel(grooves="exit", riser_draft_deg=3.0)(Scene())
    for i, e in enumerate(lens.path):
        if lens.get_functional_label(i)[0] in {f"R{k}" for k in range(1, 5)}:
            nxt = lens.path[(i + 1) % len(lens.path)]
            dx, dy = nxt["x"] - e["x"], nxt["y"] - e["y"]
            assert math.degrees(math.atan2(abs(dy), abs(dx))) == pytest.approx(3.0, abs=1e-9)


def test_a_conic_exit_cap_and_the_refusals():
    lens = _fresnel(grooves="exit", cap="conic")(Scene())
    assert lens.design["cap_sag_error"] < 1e-3
    assert abs(_exit(_fresnel(grooves="exit", cap="conic"), 4.0)[0]) < 1e-3
    entrance = _fresnel(grooves="entrance")(Scene())
    assert entrance.design["cap_K"] == pytest.approx(-1.49 ** 2)
    assert entrance.design["cap_R"] == pytest.approx(0.49 * 20.0)
    with pytest.raises(ValueError, match="zones"):
        _fresnel(zones=1)(Scene())
    with pytest.raises(ValueError, match="grooves"):
        _fresnel(grooves="both")(Scene())
    with pytest.raises(ValueError, match="riser_draft_deg"):
        _fresnel(riser_draft_deg=45.0)(Scene())


# --- profile.json ----------------------------------------------------------------------

@pytest.mark.parametrize("make", [_tir(rotation=20.0), _fresnel(grooves="exit", zones=6)],
                         ids=["tir", "fresnel"])
@pytest.mark.parametrize("kind", ["revolve", "free"])
def test_both_collimators_round_trip_through_a_profile(make, kind):
    element = make(Scene())
    sym = {"kind": "revolve", "axis": element.revolve_axis()} if kind == "revolve" else {"kind": "free"}
    profile = export_profile(element, symmetry=sym, physical_params={}, numerical_params={})
    back = BasePrism.from_profile(Scene(), profile, n=1.49)
    def corners(el):
        return sorted((round(e["x"], 9), round(e["y"], 9)) for e in el.path)
    assert corners(back) == corners(element)
    names = {back.get_functional_label(i)[0] for i in range(len(back.path))}
    assert names == {element.get_functional_label(i)[0] for i in range(len(element.path))}


def test_section_faces_are_in_the_canonical_frame_wherever_the_collimator_is():
    a = TIRCollimator(Scene()).section_faces(9)
    b = TIRCollimator(Scene(), position=F, rotation=30.0).section_faces(9)
    assert set(a) == {"12b", "22b", "12a", "22c", "22a"}
    for label in a:
        for k in (0, 1):
            diff = max(abs(u - v) for p, q in zip(a[label][k], b[label][k]) for u, v in zip(p, q))
            assert diff < 1e-9, label
    pts, _ = a["22c"]
    assert math.dist(pts[0], (8.3, 21.8)) < 1e-12 and abs(pts[-1][1] - 33.5) < 1e-9
    assert math.dist(a["22a"][0][1], pts[-1]) < 1e-12               # 22a ends at 22c's front end
