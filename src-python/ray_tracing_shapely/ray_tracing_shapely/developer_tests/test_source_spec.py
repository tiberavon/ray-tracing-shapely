"""
Python-specific module: test source spec
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
Source specifications, their 2D section, and profile.json's sources (1.3)
===============================================================================
A source spec is written once, in the 2D scene's frame; its 2D source is its
exact section by the scene plane, sampled deterministically. The patch case
is the LED collimator's chip: 2 x 1 mm, rolled 15 deg about the axis, one
corner on the focus F -- its section is 1/cos(15 deg) long, not its 1 mm side.
===============================================================================
"""

from __future__ import annotations

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.lenses import SingletLens
from ray_tracing_shapely.optical_elements.prisms.profile_export import (PROFILE_SCHEMA_VERSION,
                                                                        export_profile)
from ray_tracing_shapely.optical_elements.sources import (RaySetSource, build_source_2d, merged_sources,
                                                          patch_centre, patch_section, profile_sources,
                                                          source_axes, validate_source_spec)

F = (3.0, -2.0)
CHIP = {"name": "chip", "kind": "patch", "position": list(F), "direction_deg": 0.0, "emission": "lambertian",
        "size": [1.0, 2.0], "roll_deg": -15.0, "anchor": [0.0, 0.0]}


# --- validation -----------------------------------------------------------------------


def test_defaults_are_filled_in():
    spec = validate_source_spec({"name": "s", "kind": "point", "position": [1, 2], "direction_deg": 30,
                                 "emission": "lambertian"})
    assert spec["position"] == [1.0, 2.0, 0.0]
    assert spec["half_angle_deg"] == 90.0
    assert (spec["flux"], spec["flux_unit"], spec["wavelength_um"]) == (1.0, "W", 0.55)


@pytest.mark.parametrize("bad, words", [
    ({"kind": "point", "emission": "lambertian", "half_angle_deg": 30}, "no 3D counterpart"),
    ({"kind": "patch", "emission": "uniform", "half_angle_deg": 90, "size": [1, 1]}, "no 3D counterpart"),
    ({"kind": "point", "emission": "uniform"}, "needs 'half_angle_deg'"),
    ({"kind": "pencil", "emission": "uniform"}, "unknown field"),
    ({"kind": "point", "emission": "lambertian", "size": [1, 1]}, "unknown field"),
    ({"kind": "patch", "emission": "lambertian"}, "needs 'size'"),
    ({"kind": "laser"}, "kind must be"),
    ({"kind": "point", "emission": "lambertian", "flux_unit": "cd"}, "flux_unit"),
])
def test_what_has_no_exact_source_is_refused(bad, words):
    with pytest.raises(ValueError, match=words):
        validate_source_spec({"name": "s", "position": [0, 0], "direction_deg": 0, **bad})


# --- geometry -------------------------------------------------------------------------


def test_axes_are_orthonormal_and_e_in_lies_in_the_plane_at_roll_0():
    for direction in (0.0, 37.0, 180.0, -90.0):
        for roll in (0.0, -15.0, 40.0):
            ax = source_axes(validate_source_spec({**CHIP, "direction_deg": direction, "roll_deg": roll}))
            vs = [ax["n"], ax["e_in"], ax["e_out"]]
            for i in range(3):
                for j in range(3):
                    dot = sum(vs[i][k] * vs[j][k] for k in range(3))
                    assert dot == pytest.approx(1.0 if i == j else 0.0, abs=1e-15)
            if roll == 0.0:
                assert ax["e_in"][2] == 0.0 and ax["e_out"] == (0.0, 0.0, 1.0)


def test_the_chip_section_is_longer_than_its_side():
    spec = validate_source_spec(CHIP)
    (a1, b1), (a2, b2) = patch_section(spec)
    # The axis is +a, so the section lies along b, from F upwards, 1/cos(15 deg) long.
    assert (a1, b1) == pytest.approx(F, abs=1e-12)
    assert a2 == pytest.approx(F[0], abs=1e-12)
    assert b2 - b1 == pytest.approx(1.0 / math.cos(math.radians(15.0)), rel=1e-12)
    centre = patch_centre(spec)
    t = math.radians(15.0)       # half of each side, along e_in = (0, cos, -sin), e_out = (0, sin, cos)
    assert centre == pytest.approx((F[0], F[1] + 0.5 * math.cos(t) + 1.0 * math.sin(t),
                                    -0.5 * math.sin(t) + 1.0 * math.cos(t)), abs=1e-12)


def test_an_unrolled_centred_patch_section_is_its_in_plane_side():
    spec = validate_source_spec({**CHIP, "roll_deg": 0.0, "anchor": [0.5, 0.5], "direction_deg": 90.0})
    (a1, b1), (a2, b2) = patch_section(spec)
    # Axis +b: p = (-1, 0); going along +p the axis is on the right.
    assert (a1, b1) == pytest.approx((F[0] + 0.5, F[1]), abs=1e-12)
    assert (a2, b2) == pytest.approx((F[0] - 0.5, F[1]), abs=1e-12)


def test_a_patch_off_the_plane_has_no_section_and_no_2d_source():
    spec = {**CHIP, "position": [F[0], F[1], 2.5]}
    assert patch_section(validate_source_spec(spec)) is None
    with pytest.raises(ValueError, match="does not cross the 2D plane"):
        build_source_2d(Scene(), spec)


# --- 2D -------------------------------------------------------------------------------


def test_uniform_point_fan_is_symmetric_and_equally_weighted():
    spec = {"name": "p", "kind": "point", "position": [0, 0], "direction_deg": 45.0,
            "emission": "uniform", "half_angle_deg": 30.0, "flux": 2.0}
    src = build_source_2d(Scene(), spec, n_angles=6)
    angles = sorted(math.degrees(math.atan2(r["d"][1], r["d"][0])) for r in src.rays)
    assert angles == pytest.approx([45 - 25, 45 - 15, 45 - 5, 45 + 5, 45 + 15, 45 + 25], abs=1e-12)
    assert {r["brightness"] for r in src.rays} == {1.0}
    assert src.flux_per_brightness == pytest.approx(2.0 / 6)
    assert src.name == "p"


def test_lambertian_weights_are_the_cosine_largest_one():
    src = build_source_2d(Scene(), {**CHIP, "roll_deg": 0.0}, n_angles=9, n_positions=3)
    assert len(src.rays) == 27
    for r in src.rays:
        off = math.atan2(r["d"][1], r["d"][0])
        assert r["brightness"] == pytest.approx(math.cos(off), rel=1e-12)     # 9 angles: one on the axis
    assert max(r["brightness"] for r in src.rays) == pytest.approx(1.0)


def test_a_point_off_the_plane_has_no_2d_source():
    with pytest.raises(ValueError, match="off the 2D plane"):
        build_source_2d(Scene(), {"name": "p", "kind": "pencil", "position": [0, 0, 1e-6], "direction_deg": 0})


def test_ray_set_source_rays_leave_where_given_with_their_brightness():
    scene = Scene()
    src = build_source_2d(scene, CHIP, n_angles=5, n_positions=4)
    scene.add_object(src)
    segments = Simulator(scene, max_rays=1000).run_with_result(name="t").segments
    firsts = [s for s in segments if s.parent_uuid is None]          # the source's own rays
    starts = sorted((round(s.p1["x"], 12), round(s.p1["y"], 12), round(s.total_brightness, 12)) for s in firsts)
    given = sorted((round(r["p"][0], 12), round(r["p"][1], 12), round(r["brightness"], 12)) for r in src.rays)
    assert starts == given


def test_ray_set_source_refuses_a_bad_ray():
    scene = Scene()
    scene.add_object(RaySetSource.from_rays(scene, [(0, 0)], [(1, 0)], [1.5]))
    with pytest.raises(ValueError, match=r"brightness must be in \(0, 1\]"):
        Simulator(scene, max_rays=10).run_with_result(name="t")


# --- profile.json 1.3 -----------------------------------------------------------------


def _profile(sources=None):
    lens = SingletLens(Scene(), radius_front=60.0, radius_back=-20.0, thickness=5.0, semi_diameter=10.0, n=1.5)
    return export_profile(lens, symmetry={"kind": "revolve", "axis": lens.revolve_axis()},
                          physical_params={}, numerical_params={}, sources=sources)


def test_profile_carries_its_sources_validated():
    profile = _profile([CHIP])
    assert profile["schema_version"] == PROFILE_SCHEMA_VERSION == "1.5"
    assert profile["sources"] == [validate_source_spec(CHIP)]
    assert _profile()["sources"] == []
    assert profile_sources({"schema_version": "1.2"}) == []       # a 1.2 profile has none


def test_one_source_in_two_profiles_is_merged_or_refused():
    one, two = _profile([CHIP]), _profile([CHIP])
    assert merged_sources({"lens.json": one, "ring.json": two}) == [validate_source_spec(CHIP)]
    moved = _profile([{**CHIP, "position": [F[0], F[1] + 0.1]}])
    with pytest.raises(ValueError, match="'lens.json' and 'ring.json'"):
        merged_sources({"lens.json": one, "ring.json": moved})


def test_two_sources_with_one_name_in_one_profile_are_refused():
    with pytest.raises(ValueError, match="several sources named"):
        _profile([CHIP, CHIP])
