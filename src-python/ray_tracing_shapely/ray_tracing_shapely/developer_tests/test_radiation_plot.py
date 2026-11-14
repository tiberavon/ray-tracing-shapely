"""
Python-specific module: test radiation plot
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
A rayfile's radiation pattern, and its slice's, against known emitters
===============================================================================
A Lambertian point emitter has intensity (flux / pi) cos(theta), a share
sin^2(theta) of its flux within theta, and a full width at half maximum of
120 degrees; every ray of a point at the axis is meridional, so its slice
must reproduce the half averages bin for bin. Rays confined to one plane
through the axis must show in that plane's cross section and not in the
other's.
===============================================================================
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from ray_tracing_shapely.optical_elements.sources import (Rayfile, radiation_pattern, radiation_plot_svg,
                                                          slice_rayfile)


def _lambertian(n, seed=3, offset=None):
    rng = np.random.default_rng(seed)
    sin_t, phi = np.sqrt(rng.random(n)), 2 * np.pi * rng.random(n)
    cos_t = np.sqrt(1.0 - sin_t ** 2)
    dirs = np.c_[sin_t * np.cos(phi), sin_t * np.sin(phi), cos_t]
    pos = np.zeros((n, 3)) if offset is None else offset(rng, n)
    return Rayfile(positions=pos, directions=dirs, flux=np.full(n, 2.0 / n))


def test_a_lambertian_point_and_its_slice():
    rf = _lambertian(400_000)
    pat = radiation_pattern(rf, slice_rayfile(rf, (0.0, 0.0), 0.0, max_offset_mm=0.0), bin_deg=10.0)
    c, halves = pat.centres_deg, pat.curves["3d_halves"]
    front = np.abs(c) < 80.0
    assert np.allclose(halves[front], 2.0 / math.pi * np.cos(np.radians(c[front])), rtol=0.03)
    assert np.allclose(pat.curves["slice"], halves, rtol=1e-12, atol=1e-12)
    s = pat.summary()
    assert s["curves"]["3d_halves"]["fwhm_deg"] == pytest.approx(120.0, abs=3.0)
    for a in (30.0, 60.0):
        assert s["within_deg"]["3d"][a] == pytest.approx(math.sin(math.radians(a)) ** 2, abs=0.005)
        assert s["within_deg"]["slice"][a] == pytest.approx(s["within_deg"]["3d"][a], abs=1e-12)
    assert s["skew_share"] == 0.0 and s["flux_unit"] == "W/sr"


def test_a_slice_of_an_extended_emitter_is_scaled_to_the_whole_flux():
    disc = lambda rng, n: np.c_[2.0 * rng.random(n) - 1.0, 2.0 * rng.random(n) - 1.0, np.zeros(n)]
    rf = _lambertian(300_000, seed=5, offset=disc)
    slc = slice_rayfile(rf, (0.0, 0.0), 90.0, max_offset_mm=0.2)
    pat = radiation_pattern(rf, slc, bin_deg=10.0)
    assert 0.6 < pat.skew_share < 0.95
    c = pat.centres_deg
    front = np.abs(c) < 60.0
    # position and direction are independent here: the kept rays are a fair sample of the directions
    assert np.allclose(pat.curves["slice"][front], pat.curves["3d_halves"][front], rtol=0.05)


def test_the_cross_sections_follow_the_roll():
    n = 20_000
    t = np.radians(1.0 + 39.0 * np.random.default_rng(1).random(n))
    to_plus_x = np.c_[np.sin(t), np.zeros(n), np.cos(t)]              # rays in the x-z plane, tilted to +x
    rf = Rayfile(positions=np.zeros((n, 3)), directions=to_plus_x, flux=np.full(n, 1.0 / n))
    at_0, at_90 = radiation_pattern(rf, roll_deg=0.0), radiation_pattern(rf, roll_deg=90.0)
    assert at_0.curves["3d_in_plane"].sum() == 0.0 and at_0.curves["3d_across"].sum() > 0.0
    assert at_90.curves["3d_across"].sum() == 0.0
    # at roll 90 the plane's positive side is -x, so every ray lands at a negative angle
    c, in_plane = at_90.centres_deg, at_90.curves["3d_in_plane"]
    assert in_plane[c < 0].sum() > 0.0 and in_plane[c > 0].sum() == 0.0
    assert "slice" not in at_0.curves and at_0.max_offset_mm is None


def test_the_svg_and_the_refusals():
    rf = _lambertian(20_000)
    slc = slice_rayfile(rf, (0.0, 0.0), 0.0, max_offset_mm=0.5)
    pat = radiation_pattern(rf, slc, bin_deg=5.0)
    for polar in (False, True):
        svg = radiation_plot_svg(pat, polar=polar, title="emitter")
        assert svg.startswith("<svg") and svg.count("<polyline") == 4 and "emitter" in svg
        assert "slice, scaled to the whole flux" in svg and "skew share" in svg
    rel = radiation_plot_svg(pat, relative=True, curves=["slice"], max_angle_deg=180.0, polar=True)
    assert rel.count("<polyline") == 1 and "relative intensity" in rel
    with pytest.raises(ValueError, match="no curve"):
        radiation_plot_svg(pat, curves=["far field"])
    with pytest.raises(ValueError, match="whole number"):
        radiation_pattern(rf, bin_deg=7.0)
    with pytest.raises(ValueError, match="window_deg"):
        radiation_pattern(rf, window_deg=0.0)
    with pytest.raises(ValueError, match="contradicts"):
        radiation_pattern(rf, slc, roll_deg=45.0)
