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

import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("transitions")
pytest.importorskip("pint")

from ray_tracing_shapely.optical_elements.eye_safety_classification_flow.persistence import (read_events,
                                                                                            read_result)
from ray_tracing_shapely.optical_elements.sources import (profile_sources, read_rayfile, slice_rayfile,  # noqa: E402
                                                          spec_rayfile, write_tm25)
from ray_tracing_shapely.optical_elements.sources import rayfile_slicing_flow as slicing_flow  # noqa: E402
from ray_tracing_shapely.optical_elements.sources.rayfile_slicing_flow import RayfileSlicingFlow  # noqa: E402


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
    flow.provide_choice(0.6)
    flow.provide_profile()


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
    assert flow.state == "awaiting_choice" and len(flow.result["rows"]) == 4 and flow.result["kept_range"] == [0.6, 0.9]
    for bad, match in ((0.0, "in \\(0, 1\\]"), (1.5, "in \\(0, 1\\]"), (True, "kept share or a limit"),
                       ("0.8", "a length with its unit"), ([0.6], "a kept share")):
        with pytest.raises(ValueError, match=match):
            flow.provide_choice(bad)
    assert flow.state == "awaiting_choice" and flow.choice is None
    flow.provide_choice("0.08 cm")
    assert flow.choice["max_offset_mm"] == pytest.approx(0.8) and flow.state == "awaiting_profile"
    flow.provide_profile(False)
    assert flow.state == "done" and flow.result["choice"]["max_offset_mm"] == pytest.approx(0.8)
    assert flow.result["profile"] is None


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


def _profile(path, version="1.5", sources=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": version, "sources": list(sources)}), encoding="utf-8")
    return path


def test_the_choice_is_made_from_the_table_in_the_context(tmp_path):
    path = _four_dies(tmp_path / "dies.TM25RAY")
    flow = RayfileSlicingFlow(tmp_path / "runs", render_svg=False)
    for answer in (path, "3 mm", "3 mm", 10, [0.5, 0.75]):
        flow.answer(str(answer) if isinstance(answer, Path) else answer)
    q = flow.question_state()
    assert q["question"]["name"] == "choice" and q["context"]["table"] == flow.table_markdown()
    limits = flow.result["limit_for_kept_share_mm"]
    assert f"h <= {limits['50%']:.3g} mm" in q["question"]["example"]
    flow.answer(0.75)
    assert flow.choice["max_offset_mm"] == pytest.approx(limits["75%"])
    assert flow.choice["kept_share"] == pytest.approx(0.75, abs=2.0 / flow.rayfile.n_rays)
    assert flow.question_state()["context"]["choice"] == flow.choice
    flow.answer_default()                                        # no profile
    assert flow.state == "done" and flow.question_state()["context"] is None
    events = [e for e in read_events(tmp_path / "runs", flow.run_id) if e["state"] == "writing_profile"]
    assert events and "nothing to write" in events[0]["message"]


def test_the_source_is_written_into_the_profile(tmp_path, monkeypatch):
    (tmp_path / "leds").mkdir()
    path = _four_dies(tmp_path / "leds" / "dies.TM25RAY")
    profile = _profile(tmp_path / "optic" / "profile.json",
                       sources=[{"name": "LED", "kind": "pencil", "position": [0, 0], "direction_deg": 90}])
    flow = RayfileSlicingFlow(tmp_path / "runs", render_svg=False)
    for answer in (str(path), "3 mm", "3 mm", 10, [0.5, 0.75], 0.6):
        flow.answer(answer)
    place = {"path": str(profile), "name": "LED", "position": [1.0, 2.0], "direction_deg": 90}
    for bad, reason in (({**place, "path": str(tmp_path / "none.json")}, "export the optic"),
                        ({**place, "path": str(_profile(tmp_path / "old.json", "1.3"))}, "needs 1.4"),
                        ({"path": str(profile)}, "missing"), ({**place, "extra": 1}, "unknown"),
                        ({**place, "position": [1.0]}, "position"), (None, "takes false or an object")):
        out = flow.answer(bad)
        assert not out["accepted"] and reason in out["reason"], (bad, out["reason"])
    assert flow.state == "awaiting_profile"
    # a write that fails sends the flow back to the question, saying why, and leaves the file as it was
    before = profile.read_text()
    def full(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(slicing_flow, "_write_atomic", full)
    back = flow.answer(place)
    assert back["accepted"] and back["sent_back"]["to"] == "profile" and "disk full" in back["sent_back"]["reason"]
    assert profile.read_text() == before
    monkeypatch.undo()
    done = flow.answer(place)
    assert done["finished"] and flow.result["profile"]["replaced"]          # the pencil of the same name
    written = profile_sources(json.loads(profile.read_text()))
    assert [s["name"] for s in written] == ["LED"] and written[0]["kind"] == "rayfile"
    spec = written[0]
    assert spec["rayfile"]["path"] == os.path.join("..", "leds", "dies.TM25RAY")
    assert spec["slice"]["max_offset_mm"] == pytest.approx(flow.choice["max_offset_mm"])
    assert spec["position"] == [1.0, 2.0, 0.0] and spec["direction_deg"] == 90.0
    assert spec_rayfile(spec, base_dir=profile.parent).n_rays == flow.rayfile.n_rays   # the path resolves
