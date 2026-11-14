"""
Python-specific module: test irradiance
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
Light on a plane: an irradiance map in 3D, a line profile in 2D
===============================================================================
A collimated disc of uniform flux must give its flux over its area, centred,
and nothing outside it. Single rays must land where the plane's axes put
them, on a plane whose axis is turned in the 2D plane; rays heading away or
starting past the plane are not counted. In 2D, the rays that left a lens
are its last segments that end on nothing, which only a run that records
surface hits can say.
===============================================================================
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from ray_tracing_shapely.analysis.irradiance import ExitPlane, exit_rays_2d, irradiance_map, line_profile
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.lenses import SingletLens
from ray_tracing_shapely.optical_elements.sources import RaySetSource


def test_a_collimated_disc_gives_its_flux_over_its_area():
    rng = np.random.default_rng(3)
    n, radius = 200_000, 4.0
    r, phi = radius * np.sqrt(rng.random(n)), 2 * np.pi * rng.random(n)
    points = np.c_[np.full(n, -10.0), r * np.cos(phi), r * np.sin(phi)]           # (a, b, c), axis along +a
    directions = np.tile([1.0, 0.0, 0.0], (n, 1))
    imap = irradiance_map(points, directions, np.full(n, 2.0 / n), ExitPlane.at((0.0, 0.0), 0.0),
                          half_size_mm=6.0, pixels=60)
    s = imap.summary()
    assert s["flux_on_map"] == pytest.approx(2.0) and s["rays_on_map"] == n
    rho = np.hypot(*np.meshgrid(imap.u_centres_mm, imap.v_centres_mm))
    inside = imap.values[rho < radius - 0.3]                       # ~160 rays a pixel: 8% Poisson noise
    assert inside.mean() == pytest.approx(2.0 / (math.pi * radius ** 2), rel=0.01) and inside.std() / inside.mean() < 0.12
    assert imap.values[rho > radius + 0.2].sum() == 0.0
    assert np.allclose(s["centroid_mm"], 0.0, atol=0.02)
    assert s["rms_width_mm"] == pytest.approx([radius / 2, radius / 2], rel=0.02)    # a uniform disc: R/2
    assert s["fwhm_mm"]["u_at_v0"] == pytest.approx(2 * radius, abs=0.4)
    json.dumps(imap.to_dict())


def test_rays_land_where_the_planes_axes_put_them():
    t = math.radians(30.0)
    n_ax, u_ax = np.array([math.cos(t), math.sin(t), 0.0]), np.array([-math.sin(t), math.cos(t), 0.0])
    origin = np.array([5.0, 2.0, 0.0])
    plane = ExitPlane.at(origin, 30.0)
    start = origin - 20.0 * n_ax
    target = origin + 1.5 * u_ax + np.array([0.0, 0.0, -0.75])          # u = 1.5, v = -0.75
    good = (target - start) / np.linalg.norm(target - start)
    points = np.array([start, start, origin + 1.0 * n_ax])
    directions = np.array([good, -good, n_ax])                          # one lands; one heads away; one starts past
    imap = irradiance_map(points, directions, np.ones(3), plane, half_size_mm=2.0, pixels=8)
    assert imap.rays_on_map == 1 and imap.flux_total == 3.0 and imap.rays_past_plane == 1
    assert imap.summary()["rays_past_plane"] == 1
    band = imap.section("u", -0.75, half_width_mm=0.5)[1]            # rows at v = -1.25, -0.75, -0.25, averaged
    assert band.sum() == pytest.approx(imap.section("u", -0.75)[1].sum() / 3)
    k_v, k_u = np.unravel_index(int(np.argmax(imap.values)), imap.values.shape)
    assert imap.u_centres_mm[k_u] == pytest.approx(1.75) and imap.v_centres_mm[k_v] == pytest.approx(-0.75)
    assert imap.section("u", -0.75)[1].sum() > 0 and imap.section("v", 1.75)[1].sum() > 0
    with pytest.raises(ValueError, match="off the map"):
        imap.section("u", 3.0)


def test_a_2d_lens_profile_and_its_refusal():
    scene = Scene()
    scene.add_object(SingletLens(scene, radius_front=60.0, radius_back=-20.0, thickness=5.0, semi_diameter=10.0,
                                 n=1.5))
    angles = np.radians(np.linspace(-40.0, 40.0, 81))
    scene.add_object(RaySetSource.from_rays(scene, [(-20.0, 0.0)] * len(angles),
                                            np.c_[np.cos(angles), np.sin(angles)], np.ones(len(angles)),
                                            flux_per_brightness=0.5))
    recorded = Simulator(scene, max_rays=20_000, record_surface_hits=True).run_with_result(name="r").segments
    points, directions, flux = exit_rays_2d(recorded, flux_per_brightness=0.5)
    # every ray leaves this lens; dim reflections are sampled (kept 1 in amp, times amp), so the sum is the
    # source's in expectation only
    assert flux.sum() == pytest.approx(0.5 * len(angles), rel=0.01)
    profile = line_profile(points, directions, flux, ExitPlane.at((40.0, 0.0), 0.0), half_size_mm=30.0, bins=60)
    s = profile.summary()
    assert abs(s["centroid_mm"]) < 0.5 and s["flux_on_line"] <= s["flux_total"]   # a lens on its axis: symmetric
    json.dumps(profile.to_dict())
    plain = Simulator(scene, max_rays=20_000).run_with_result(name="p").segments
    with pytest.raises(ValueError, match="record_surface_hits"):
        exit_rays_2d(plain)


def test_flux_per_mm_of_radius_is_what_a_2d_section_carries():
    rng = np.random.default_rng(5)
    n, radius = 200_000, 4.0
    r, phi = radius * np.sqrt(rng.random(n)), 2 * np.pi * rng.random(n)        # uniform irradiance on a disc
    points = np.c_[np.full(n, -10.0), r * np.cos(phi), r * np.sin(phi)]
    imap = irradiance_map(points, np.tile([1.0, 0.0, 0.0], (n, 1)), np.full(n, 1.0 / n),
                          ExitPlane.at((0.0, 0.0), 0.0), half_size_mm=5.0, pixels=100)
    rc, dphi_dr = imap.radial_profile()
    inside = (rc > 0.5) & (rc < radius - 0.5)
    assert np.allclose(dphi_dr[inside], 2.0 * rc[inside] / radius ** 2, rtol=0.08)  # 2 pi r E, E = 1 / (pi R^2)
    assert (dphi_dr * np.diff(np.arange(0.0, 5.0 + 0.025, 0.1))).sum() == pytest.approx(1.0, rel=1e-9)
    # a 2D fan that is the meridional section of the same disc: rays uniform in u, so flat per mm of |u|
    u = np.linspace(-radius, radius, 4001)
    profile = line_profile(np.c_[np.full(len(u), -10.0), u], np.tile([1.0, 0.0], (len(u), 1)), np.ones(len(u)),
                           ExitPlane.at((0.0, 0.0), 0.0), half_size_mm=5.0, bins=100)
    fc, folded = profile.folded()
    assert np.allclose(folded[(fc > 0.2) & (fc < radius - 0.2)], 2 * 4001 / 8.0, rtol=0.05)
