"""
Python-specific module: test rayfile slicing flow
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
The rayfile slicing flow: its questions, its checks, its table
===============================================================================
A synthetic four-die emitter, written as a TM-25 file, is taken through the
flow. The table's limits are the footprint's half diagonal in equal steps,
its kept shares rise to 1, and the limits it reports at the ends of the kept
range are the flux-weighted quantiles of |h|. A bare number, a file that does
not parse and a footprint the rays do not fit in each send the flow back to
its question, with the reason.
===============================================================================
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("transitions")
pytest.importorskip("pint")

from ray_tracing_shapely.optical_elements.eye_safety_classification_flow.persistence import (read_events,
                                                                                            read_result)
from ray_tracing_shapely.optical_elements.sources import read_rayfile, slice_rayfile, write_tm25
from ray_tracing_shapely.optical_elements.sources.rayfile_slicing_flow import RayfileSlicingFlow


def _four_dies(path, n=8000, centre=(0.0, 0.0), seed=7):
    """Four 0.8 mm dies at (+-0.6, +-0.6) mm about ``centre``, each Lambertian."""
    rng = np.random.default_rng(seed)
    die = rng.integers(0, 4, n)
    cx = np.where(die % 2 == 0, -0.6, 0.6) + centre[0]
    cy = np.where(die < 2, -0.6, 0.6) + centre[1]
    pos = np.c_[cx + 0.8 * (rng.random(n) - 0.5), cy + 0.8 * (rng.random(n) - 0.5), np.zeros(n)]
    sin_t, phi = np.sqrt(rng.random(n)), 2 * np.pi * rng.random(n)
    dirs = np.c_[sin_t * np.cos(phi), sin_t * np.sin(phi), np.sqrt(1.0 - sin_t ** 2)]
    write_tm25(path, pos, dirs, np.full(n, 1.0 / n), name="four dies")
    return path


def _through(flow, path, width="3 mm", length="3 mm"):
    flow.provide_rayfile(path)
    flow.provide_package_width(width)
    flow.provide_package_length(length)
    flow.provide_n_slices()
    flow.provide_kept_range()


def test_the_table_of_a_four_die_emitter(tmp_path):
    path = _four_dies(tmp_path / "dies.TM25RAY")
    flow = RayfileSlicingFlow(tmp_path / "runs", render_svg=False)
    _through(flow, path)
    assert flow.state == "done"
    r = flow.result
    limits = [row["max_offset_mm"] for row in r["rows"]]
    assert r["half_diagonal_mm"] == pytest.approx(1.5 * math.sqrt(2))
    assert np.allclose(limits, r["half_diagonal_mm"] * np.arange(1, 11) / 10)
    kept = [row["kept_share"] for row in r["rows"]]
    assert np.all(np.diff(kept) >= 0.0) and kept[-1] == pytest.approx(1.0)
    rf = read_rayfile(path)
    exact = slice_rayfile(rf, (0.0, 0.0), 0.0, max_offset_mm=0.0).offset_quantiles(rf.flux, (0.5, 0.75))
    assert r["limit_for_kept_share_mm"] == pytest.approx({"50%": exact[0.5], "75%": exact[0.75]})
    assert [row["in_kept_range"] for row in r["rows"]] == [0.5 <= k <= 0.75 for k in kept]
    # direction is independent of start here, so every slice leaves as the LED does
    assert all(abs(row["within_30deg"] - r["led_within_30deg"]) < 0.03 for row in r["rows"])
    assert r["warnings"] == []
    assert read_result(tmp_path / "runs", flow.run_id)["result"]["rows"] == r["rows"]
    table = flow.table_markdown()
    assert table.count("\n| ") == 11 and "50% of the flux is kept at h <=" in table
    states = [e["state"] for e in read_events(tmp_path / "runs", flow.run_id)]
    assert states[0] == "awaiting_rayfile" and states[-1] == "done" and "slicing" in states


def test_wrong_answers_go_back_to_their_question(tmp_path):
    path = _four_dies(tmp_path / "dies.TM25RAY")
    (tmp_path / "junk.TM25RAY").write_bytes(b"not a rayfile")
    flow = RayfileSlicingFlow(tmp_path / "runs", render_svg=False)
    flow.provide_rayfile(tmp_path / "junk.TM25RAY")
    assert flow.state == "awaiting_rayfile" and "could not be read" in flow.explain_current_state()
    flow.provide_rayfile(path)
    with pytest.raises(ValueError, match="bare number"):
        flow.provide_package_width(3.0)
    assert flow.state == "awaiting_package_width"
    flow.provide_package_width("1.5 mm")                               # the dies reach 1 mm from the axis
    flow.provide_package_length("3 mm")
    assert flow.state == "awaiting_package_width" and "outside a 1.5 x 3 mm package" in flow.explain_current_state()
    flow.provide_package_width("0.3 cm")
    flow.provide_package_length("3 mm")
    assert flow.state == "awaiting_n_slices" and flow.width_mm == pytest.approx(3.0)
    with pytest.raises(ValueError, match="positive integer"):
        flow.provide_n_slices(0)
    flow.provide_n_slices(4)
    with pytest.raises(ValueError, match="kept_range"):
        flow.provide_kept_range((0.8, 0.5))
    flow.provide_kept_range((0.6, 0.9))
    assert flow.state == "done" and len(flow.result["rows"]) == 4 and flow.result["kept_range"] == [0.6, 0.9]


def test_warnings_and_reset(tmp_path):
    flow = RayfileSlicingFlow(tmp_path / "runs", render_svg=False)
    _through(flow, _four_dies(tmp_path / "dies.TM25RAY"), width="20 mm", length="20 mm")
    assert len(flow.result["warnings"]) == 1 and "small part" in flow.result["warnings"][0]
    flow.reset()
    assert flow.state == "start" and flow.result is None and flow.attempt == 2
    flow.begin()
    with pytest.raises(RuntimeError, match="no table yet"):
        flow.table_markdown()
    _through(flow, _four_dies(tmp_path / "off.TM25RAY", centre=(0.3, 0.0)), width="4 mm", length="3 mm")
    assert flow.state == "done" and flow.result["package_mm"] == [4.0, 3.0]
    assert len(flow.result["warnings"]) == 1 and "off the axis" in flow.result["warnings"][0]


def test_the_chosen_limit_becomes_a_source_spec(tmp_path):
    path = _four_dies(tmp_path / "dies.TM25RAY")
    flow = RayfileSlicingFlow(tmp_path / "runs", render_svg=False)
    with pytest.raises(RuntimeError, match="no table yet"):
        flow.source_spec("led", (0.0, 0.0), 0.0, kept_share=0.75)
    _through(flow, path)
    spec = flow.source_spec("led", (5.0, 1.0), 0.0, kept_share=0.75, path="dies.TM25RAY", base_dir=tmp_path)
    assert spec["slice"]["max_offset_mm"] == pytest.approx(flow.result["limit_for_kept_share_mm"]["75%"])
    assert spec["slice"]["kept_share"] == pytest.approx(0.75, abs=2.0 / flow.rayfile.n_rays)
    assert spec["rayfile"]["path"] == "dies.TM25RAY" and spec["rayfile"]["format"] == "tm25"
    by_limit = flow.source_spec("led", (5.0, 1.0), 0.0, max_offset_mm=0.5, path="dies.TM25RAY", base_dir=tmp_path)
    assert by_limit["slice"]["max_offset_mm"] == 0.5
    with pytest.raises(ValueError, match="exactly one"):
        flow.source_spec("led", (0.0, 0.0), 0.0, kept_share=0.5, max_offset_mm=1.0)
