"""
Python-specific module: test rayfile slice
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
A rayfile turned into the 2D plane: meridional rays kept exactly, skew ones
measured
===============================================================================
Rays in planes through the axis have no skew (h = 0) and must land in the 2D
plane unchanged but for the turn. A ray whose line passes the axis at a
known distance must report that distance, keep its direction, and be kept
or dropped by the limit. A ray along the axis has no transverse direction:
its start is turned instead.
===============================================================================
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.optical_elements.sources import Rayfile, slice_rayfile

AT, AXIS_DEG = (10.0, 5.0), 30.0
N2 = np.array([math.cos(math.radians(AXIS_DEG)), math.sin(math.radians(AXIS_DEG))])
P2 = np.array([-N2[1], N2[0]])


def _rayfile(pos, dirs, flux=None):
    pos, dirs = np.asarray(pos, float), np.asarray(dirs, float)
    dirs = dirs / np.linalg.norm(dirs, axis=1)[:, None]
    flux = np.full(len(pos), 0.5) if flux is None else np.asarray(flux, float)
    return Rayfile(positions=pos, directions=dirs, flux=flux)


def _local(points):
    """2D scene points back to (along the axis, across it) from the LED's origin."""
    rel = np.asarray(points) - np.array(AT)
    return rel @ N2, rel @ P2


def test_meridional_rays_are_all_kept_unchanged_but_for_the_turn():
    rng = np.random.default_rng(2)
    n = 500
    rho, phi, z = 3.0 * rng.random(n), 2 * np.pi * rng.random(n), rng.random(n)
    radial = np.c_[np.cos(phi), np.sin(phi), np.zeros(n)]
    tilt = np.radians(80.0 * rng.random(n) - 40.0)                    # towards or away from the axis
    pos = rho[:, None] * radial + np.c_[np.zeros(n), np.zeros(n), z]
    dirs = np.sin(tilt)[:, None] * radial + np.c_[np.zeros(n), np.zeros(n), np.cos(tilt)]
    rf = _rayfile(pos, dirs)
    slc = slice_rayfile(rf, AT, AXIS_DEG, max_offset_mm=0.0)
    assert np.abs(slc.offsets_mm).max() < 1e-12 and len(slc.flux) == n and slc.skew_share == 0.0
    along, across = _local(slc.points)
    assert np.allclose(along, z) and np.allclose(np.abs(across), rho)
    d_along, d_across = slc.directions @ N2, slc.directions @ P2
    assert np.allclose(d_along, np.cos(tilt)) and np.allclose(np.abs(d_across), np.abs(np.sin(tilt)))
    # a ray heading away from the axis still heads away from it in the plane, and towards it, towards it
    assert np.all(np.sign(across * d_across) == np.sign(np.sin(tilt)))


def test_a_skew_ray_reports_its_distance_from_the_axis_and_keeps_its_direction():
    alpha = math.radians(20.0)
    rf = _rayfile([[1.0, 0.0, 0.0]], [[0.0, math.sin(alpha), math.cos(alpha)]])
    kept = slice_rayfile(rf, AT, AXIS_DEG, max_offset_mm=1.0)
    assert kept.offsets_mm[0] == pytest.approx(1.0)
    along, across = _local(kept.points)
    assert (along[0], across[0]) == pytest.approx((0.0, 0.0))        # it passes the axis where it started
    assert kept.directions[0] @ N2 == pytest.approx(math.cos(alpha))
    assert abs(kept.directions[0] @ P2) == pytest.approx(math.sin(alpha))
    dropped = slice_rayfile(rf, AT, AXIS_DEG, max_offset_mm=0.99)
    assert len(dropped.flux) == 0 and dropped.skew_share == pytest.approx(1.0)


def test_a_ray_along_the_axis_has_its_start_turned():
    rf = _rayfile([[0.3, 0.4, 0.2]], [[0.0, 0.0, 1.0]])
    slc = slice_rayfile(rf, AT, AXIS_DEG, max_offset_mm=0.0)
    along, across = _local(slc.points)
    assert slc.offsets_mm[0] == 0.0 and along[0] == pytest.approx(0.2) and abs(across[0]) == pytest.approx(0.5)
    assert np.allclose(slc.directions[0], N2)


def test_the_skew_share_quantiles_and_the_2d_source():
    pos = [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    a = math.radians(30.0)
    dirs = [[0.0, math.sin(a), math.cos(a)], [0.0, math.sin(a), math.cos(a)], [math.sin(a), 0.0, math.cos(a)]]
    rf = _rayfile(pos, dirs, flux=[1.0, 2.0, 1.0])                  # h = 1, 2, 0
    slc = slice_rayfile(rf, AT, AXIS_DEG, max_offset_mm=1.5)
    assert sorted(np.round(np.abs(slc.offsets_mm), 9)) == [0.0, 1.0, 2.0]
    assert slc.skew_share == pytest.approx(0.5) and slc.kept_flux == pytest.approx(2.0)
    assert slc.offset_quantiles(rf.flux, (0.25, 0.5, 0.75)) == pytest.approx({0.25: 0.0, 0.5: 1.0, 0.75: 2.0})
    src = slc.source_2d(Scene(), name="led")
    assert src.name == "led" and max(r["brightness"] for r in src.rays) == 1.0 and src.flux_per_brightness == 1.0
    assert len(slc.rays()) == 2
    nothing_kept = slice_rayfile(_rayfile([[1.0, 0.0, 0.0]], [[0.0, 1.0, 1.0]]), AT, AXIS_DEG, max_offset_mm=0.1)
    with pytest.raises(ValueError, match="within"):
        nothing_kept.source_2d(Scene())
    with pytest.raises(ValueError, match=">= 0"):
        slice_rayfile(rf, AT, AXIS_DEG, max_offset_mm=-1.0)
    with pytest.raises(ValueError, match="2D plane"):
        slice_rayfile(rf, (0.0, 0.0, 1.0), 0.0, max_offset_mm=1.0)
