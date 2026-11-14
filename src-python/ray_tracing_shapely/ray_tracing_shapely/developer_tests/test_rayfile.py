"""
Python-specific module: test rayfile
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
IES TM-25 rayfiles: read the one layout checked, refuse every other
===============================================================================
Every file here is synthetic, written by write_tm25: a measured LED's file
is its supplier's and no shipped test needs one. A Lambertian square emitter
written and read back must keep every ray and its spectrum, and its
far-field intensity must follow cos(theta). A file that is not the layout
described in the module is refused, by the field that differs.
===============================================================================
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from ray_tracing_shapely.optical_elements.sources.rayfile import (RAY_FLAGS, intensity_vs_angle, read_rayfile,
                                                                  write_tm25)

N = 20_000
SPECTRUM = [(840.0, 10.0), (850.0, 80.0), (854.0, 100.0), (860.0, 60.0), (870.0, 5.0)]


def lambertian(n=N, seed=3, side=1.0, flux=2.0):
    """A ``side`` mm square at z = 0 emitting a Lambertian hemisphere along +z, equal flux per ray."""
    rng = np.random.default_rng(seed)
    pos = np.c_[(rng.random(n) - 0.5) * side, (rng.random(n) - 0.5) * side, np.zeros(n)]
    cos_t = np.sqrt(rng.random(n))
    phi = 2 * np.pi * rng.random(n)
    sin_t = np.sqrt(1 - cos_t ** 2)
    dirs = np.c_[sin_t * np.cos(phi), sin_t * np.sin(phi), cos_t]
    return pos, dirs, np.full(n, flux / n)


@pytest.fixture
def written(tmp_path):
    pos, dirs, flux = lambertian()
    return write_tm25(tmp_path / "lamb.TM25RAY", pos, dirs, flux, name="LAMB-1", spectrum_nm=SPECTRUM), pos, dirs, flux


def test_a_written_file_reads_back_ray_for_ray(written):
    path, pos, dirs, flux = written
    rf = read_rayfile(path)
    assert (rf.name, rf.n_rays, rf.flux_unit) == ("LAMB-1", N, "W")
    assert np.abs(rf.positions - pos).max() < 1e-6 and np.abs(rf.directions - dirs).max() < 1e-6
    assert rf.total_flux == pytest.approx(2.0, rel=1e-6)
    assert rf.header["radiant_flux_W"] == pytest.approx(2.0, rel=1e-6)
    assert rf.header["ray_flags"] == RAY_FLAGS and rf.header["wavelength_range_nm"] == (840.0, 870.0)
    assert np.array_equal(rf.spectrum_nm, np.array(SPECTRUM)) and rf.peak_wavelength_um() == pytest.approx(0.854)


def test_a_lambertian_file_has_a_cosine_far_field(written):
    rf = read_rayfile(written[0])
    theta, intensity = intensity_vs_angle(rf, n_bins=18)
    forward = theta < 80.0
    assert np.abs(intensity[forward] / (2.0 / np.pi) - np.cos(np.radians(theta[forward]))).max() < 0.05
    assert intensity[theta > 90.0].sum() == 0.0
    assert np.sum(intensity * 2 * np.pi * (np.cos(np.radians(theta - 5)) - np.cos(np.radians(theta + 5)))) \
        == pytest.approx(rf.total_flux)


def _patched(path, offset, fmt, *values):
    data = bytearray(path.read_bytes())
    struct.pack_into(fmt, data, offset, *values)
    path.write_bytes(bytes(data))


@pytest.mark.parametrize("offset, fmt, value, message", [
    (0, "<4s", b"TM26", "not a format this reader reads"),
    (4, "<i", 2020, "checked only against 2013"),
    (0x100, "<i", 0, "ray-data flags"),
])
def test_a_different_layout_is_refused(written, offset, fmt, value, message):
    path = written[0]
    _patched(path, offset, fmt, value)
    with pytest.raises(ValueError, match=message):
        read_rayfile(path)


def test_a_wrong_ray_count_or_a_non_unit_direction_is_refused(written, tmp_path):
    path, pos, dirs, flux = written
    _patched(path, 0x14, "<q", N + 1)
    with pytest.raises(ValueError, match="need"):
        read_rayfile(path)
    with pytest.raises(ValueError, match="unit length"):
        write_tm25(tmp_path / "bad.TM25RAY", pos, 2 * dirs, flux)
    bad = write_tm25(tmp_path / "bad.TM25RAY", pos, dirs, flux)
    data = bytearray(bad.read_bytes())
    struct.pack_into("<f", data, len(data) - 4 * 4, 2.0)          # the last ray's x direction
    bad.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="unit length"):
        read_rayfile(bad)
