"""
Python-specific module: test ray jobs
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
A set of 2D rays simulated as a job, in chunks that add up
===============================================================================
A singlet's profile and a fan of rays: the job's sums are the same run
twice; with a fixed brightness threshold, two chunks merged equal the whole
set; with the simulator's own thinning (one in amp, by its count of rays
processed so far) they agree on what entered, not on what left; the shares
add up to one; rays of the wrong shape are refused. An absorber behind a
mirror stops what arrives from behind and leaves the front face reflecting,
and what it stops counts as stopped.
===============================================================================
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.optical_elements.lenses import SingletLens
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_profile, export_sheet_profile
from ray_tracing_shapely.analysis.ray_jobs import (fate_shares, merge_ray_results,
                                                                   simulate_rays_2d_job)

CTX = SimpleNamespace(progress=lambda *a, **k: None)


def _inputs(tmp_path, k0, k1, exp=4):
    lens = SingletLens(Scene(), radius_front=60.0, radius_back=-20.0, thickness=5.0, semi_diameter=10.0, n=1.5)
    profile = export_profile(lens, symmetry={"kind": "revolve", "axis": lens.revolve_axis()},
                             physical_params={}, numerical_params={})
    path = tmp_path / "lens.json"
    path.write_text(json.dumps(profile))
    angles = [-20.0 + 2.0 * k for k in range(21)]
    rays = {"points": [[-20.0, 0.5 * (k % 7) - 1.5] for k in range(len(angles))],
            "directions": [[math.cos(math.radians(a)), math.sin(math.radians(a))] for a in angles],
            "flux": [0.5 + 0.02 * k for k in range(len(angles))]}
    cut = {key: v[k0:k1] for key, v in rays.items()}
    return {"profiles": [{"path": str(path), "n": 1.5}], "rays": cut, "flux_per_brightness": 1.0,
            "min_brightness_exp": exp}


def test_chunks_are_reproducible_and_add_up(tmp_path):
    whole = simulate_rays_2d_job(_inputs(tmp_path, 0, 21), CTX)
    assert simulate_rays_2d_job(_inputs(tmp_path, 0, 21), CTX)["hist"] == whole["hist"]
    merged = merge_ray_results([simulate_rays_2d_job(_inputs(tmp_path, 0, 10), CTX),
                                simulate_rays_2d_job(_inputs(tmp_path, 10, 21), CTX)])
    assert merged["rays"] == whole["rays"] == 21 and merged["chunks"] == 2
    for key in ("total_flux", "stopped_flux", "left_flux"):
        assert merged[key] == pytest.approx(whole[key], rel=1e-12), key
    assert merged["hist"] == pytest.approx(whole["hist"], rel=1e-12, abs=1e-15)
    thinned = [simulate_rays_2d_job(_inputs(tmp_path, a, b, exp=None), CTX) for a, b in ((0, 21), (0, 10), (10, 21))]
    split = merge_ray_results(thinned[1:])
    assert split["total_flux"] == pytest.approx(thinned[0]["total_flux"], rel=1e-12)
    assert split["left_flux"] != thinned[0]["left_flux"]                  # the thinning saw other counts
    shares = fate_shares(merged)
    assert sum(shares[k] for k in ("within 3 deg", "absorbed")) <= 1.0
    left = shares["within 3 deg"] + (1.0 - shares["within 3 deg"] - shares["absorbed"])
    assert left + shares["absorbed"] == pytest.approx(1.0)
    books = merged["left_flux"] + merged["stopped_flux"] + merged["dropped_flux"]
    assert books == pytest.approx(merged["total_flux"], rel=1e-12) and 0.0 <= merged["dropped_flux"] < 1e-3 * books


def test_rays_of_the_wrong_shape_are_refused(tmp_path):
    bad = _inputs(tmp_path, 0, 5)
    bad["rays"]["flux"] = bad["rays"]["flux"][:3]
    with pytest.raises(ValueError, match="differ in length"):
        simulate_rays_2d_job(bad, CTX)
    over = _inputs(tmp_path, 0, 5)
    over["flux_per_brightness"] = 0.1
    with pytest.raises(ValueError, match="flux_per_brightness"):
        simulate_rays_2d_job(over, CTX)
    with pytest.raises(ValueError, match="no results"):
        merge_ray_results([])


def _flat_mirror_inputs(tmp_path, absorbers):
    """A flat mirror across a vertical axis at y = 10; one ray up from below, one down from above."""
    mirror = Mirror(Scene(), {"p1": {"x": -10.0, "y": 10.0}, "p2": {"x": 10.0, "y": 10.0}})
    mirror.name = "M"
    profile = export_sheet_profile([mirror], symmetry={"kind": "revolve", "axis": {"point": [0.0, 0.0],
                                   "direction": [0.0, 1.0]}}, physical_params={}, numerical_params={})
    path = tmp_path / "flat.json"
    path.write_text(json.dumps(profile))
    rays = {"points": [[2.0, 0.0], [3.0, 20.0]], "directions": [[0.0, 1.0], [0.0, -1.0]], "flux": [0.5, 0.25]}
    return {"profiles": [{"path": str(path)}], "rays": rays, "flux_per_brightness": 1.0, "axis_deg": 90.0,
            "bin_deg": 1.0, "min_brightness_exp": 6, "absorbers": absorbers}


def test_an_absorber_behind_a_mirror_stops_what_comes_from_behind(tmp_path):
    bare = simulate_rays_2d_job(_flat_mirror_inputs(tmp_path, None), CTX)
    assert bare["stopped_flux"] == 0.0 and bare["left_flux"] == pytest.approx(0.75)   # both faces reflect
    backed = simulate_rays_2d_job(_flat_mirror_inputs(tmp_path, [[[-10.0, 10.05], [10.0, 10.05]]]), CTX)
    assert backed["stopped_flux"] == pytest.approx(0.25)                 # from above: stopped behind the mirror
    assert backed["left_flux"] == pytest.approx(0.5)                     # from below: reflected, as before
    assert backed["hist"][-1] == pytest.approx(0.5)                      # back down, 180 deg from +y
    books = backed["left_flux"] + backed["stopped_flux"] + backed["dropped_flux"]
    assert books == pytest.approx(backed["total_flux"])
    halves = []
    for k in (0, 1):
        one = _flat_mirror_inputs(tmp_path, [[[-10.0, 10.05], [10.0, 10.05]]])
        one["rays"] = {key: v[k:k + 1] for key, v in one["rays"].items()}
        halves.append(simulate_rays_2d_job(one, CTX))
    merged = merge_ray_results(halves)
    for key in ("total_flux", "stopped_flux", "left_flux"):
        assert merged[key] == pytest.approx(backed[key], rel=1e-12), key


@pytest.mark.parametrize("bad", [[[0.0, 1.0]], [[0.0, 1.0], [0.0, 1.0]], [[0.0, "x"], [1.0, 1.0]],
                                 [[0.0, float("nan")], [1.0, 1.0]]])
def test_a_malformed_absorber_is_refused(tmp_path, bad):
    with pytest.raises(ValueError, match=r"absorbers\[0\]"):
        simulate_rays_2d_job(_flat_mirror_inputs(tmp_path, [bad]), CTX)
