"""
Python-specific module: test rayfile source spec
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
A rayfile in profile.json: its path, its parser's format, and its slice
===============================================================================
A ``rayfile`` source spec records where the file is, the format its parser
takes, what the file held when the spec was written, and how the 2D section
was sliced. Written into a profile (schema 1.4) and read back, it must build
the same 2D source as slicing the file by hand; a changed file, a slice
record that no longer matches, and a spec with no slice in 2D are refused.
===============================================================================
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.optical_elements.lenses import SingletLens
from ray_tracing_shapely.optical_elements.prisms.profile_export import PROFILE_SCHEMA_VERSION, export_profile
from ray_tracing_shapely.optical_elements.sources import (build_source_2d, profile_sources, rayfile_source_spec,
                                                          read_rayfile, slice_rayfile, spec_rayfile,
                                                          validate_source_spec, write_tm25)

AT, AXIS = (-20.0, 1.0), 0.0
SPECTRUM = [(600.0, 20.0), (633.0, 100.0), (660.0, 30.0)]


def _write(path, n=3000, seed=4, scale=1.0):
    rng = np.random.default_rng(seed)
    pos = np.c_[2.0 * rng.random(n) - 1.0, 2.0 * rng.random(n) - 1.0, np.zeros(n)]
    sin_t, phi = np.sqrt(rng.random(n)), 2 * np.pi * rng.random(n)
    dirs = np.c_[sin_t * np.cos(phi), sin_t * np.sin(phi), np.sqrt(1.0 - sin_t ** 2)]
    return write_tm25(path, pos, dirs, np.full(n, scale / n), spectrum_nm=SPECTRUM)


def test_a_rayfile_spec_through_a_profile_builds_the_slice(tmp_path):
    _write(tmp_path / "led.TM25RAY")
    spec = rayfile_source_spec("led", "led.TM25RAY", AT, AXIS, max_offset_mm=0.4, base_dir=tmp_path)
    assert validate_source_spec(spec) == spec
    assert spec["rayfile"]["format"] in ("tm25",) and spec["rayfile"]["path"] == "led.TM25RAY"
    lens = SingletLens(Scene(), radius_front=60.0, radius_back=-20.0, thickness=5.0, semi_diameter=10.0, n=1.5)
    profile = export_profile(lens, symmetry={"kind": "revolve", "axis": lens.revolve_axis()},
                             physical_params={}, numerical_params={}, sources=[spec])
    assert profile["schema_version"] == PROFILE_SCHEMA_VERSION == "1.5"
    (stored,) = profile_sources(json.loads(json.dumps(profile)))
    assert stored == spec
    # the format is the parser's argument
    rf = read_rayfile(tmp_path / stored["rayfile"]["path"], stored["rayfile"]["format"])
    slc = slice_rayfile(rf, AT, AXIS, max_offset_mm=0.4)
    assert stored["slice"] == {"max_offset_mm": 0.4, "kept_share": pytest.approx(1.0 - slc.skew_share),
                               "rays_kept": len(slc.flux)}
    src = build_source_2d(Scene(), stored, base_dir=tmp_path)
    assert src.name == "led" and len(src.rays) == len(slc.flux)
    assert np.allclose([r["p"] for r in src.rays], slc.points) and np.allclose([r["d"] for r in src.rays], slc.directions)
    assert src.wavelength == pytest.approx(633.0)                  # the spectrum's peak, without wavelength_um


def test_a_changed_file_or_a_stale_slice_is_refused(tmp_path):
    path = _write(tmp_path / "led.TM25RAY")
    spec = rayfile_source_spec("led", str(path), AT, AXIS, max_offset_mm=0.4)
    assert spec_rayfile(spec).n_rays == 3000
    stale = json.loads(json.dumps(spec))
    stale["slice"]["rays_kept"] -= 1
    with pytest.raises(ValueError, match="the spec recorded"):
        build_source_2d(Scene(), stale)
    _write(path, scale=2.0)                                         # same name, other rays
    with pytest.raises(ValueError, match="not the file the spec was written for"):
        build_source_2d(Scene(), spec)


def test_what_a_rayfile_spec_refuses(tmp_path):
    path = _write(tmp_path / "led.TM25RAY")
    spec = rayfile_source_spec("led", str(path), AT, AXIS)
    assert "slice" not in spec and spec["flux"] == pytest.approx(1.0) and spec["wavelength_um"] is None
    with pytest.raises(ValueError, match="only once it is sliced"):
        build_source_2d(Scene(), spec)
    with pytest.raises(ValueError, match="off the 2D plane"):
        build_source_2d(Scene(), rayfile_source_spec("led", str(path), (*AT, 0.5), AXIS, max_offset_mm=0.4))
    for bad, match in (({"format": "ldt"}, "format must be one of"), ({"sha256": "abc"}, "sha256"),
                       ({"n_rays": 0}, "n_rays")):
        broken = json.loads(json.dumps(spec))
        broken["rayfile"].update(bad)
        with pytest.raises(ValueError, match=match):
            validate_source_spec(broken)
    with pytest.raises(ValueError, match="its file's"):
        validate_source_spec({**spec, "flux": 5.0})
    with pytest.raises(ValueError, match="unknown field"):
        validate_source_spec({**spec, "emission": "lambertian"})
    with pytest.raises(ValueError, match="not one of"):
        read_rayfile(path, "ldt")
