"""
Python-specific module: test block chain
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
The example chain: a rayfile to a risk group, as blocks and by hand (KD5)
===============================================================================
- the chain run as blocks from JSON, and the same chain written by hand with
  the library's own calls, give the same numbers, exactly: the slice, the
  reading, the irradiance, the weighted value, the group;
- the trace's JSON form is its run folder, read back to the same readings;
- each link refuses what it must: a shared name, a revolved reading, a
  radiance where an irradiance goes, both blue-light forms, an unknown
  detector, a profile the detector does not keep;
- the spectral weighting: a flat band weighs its share, the unweighted IR
  band nothing of a visible source.
===============================================================================
"""

import json

import numpy as np
import pytest

pytest.importorskip("pint")

from ray_tracing_shapely.blocks import BlockTypeError, call_block, run_block  # noqa: E402
from ray_tracing_shapely.blocks.types import TRACE, Trace  # noqa: E402

SPECTRUM = [(400.0, 0.0), (450.0, 1.0), (500.0, 0.2), (550.0, 0.6), (650.0, 0.3), (750.0, 0.0)]
ALPHA = 0.005                                         # rad: a small source, blue light as an irradiance


@pytest.fixture(scope="module")
def rayfile_path(tmp_path_factory):
    from ray_tracing_shapely.optical_elements.sources.rayfile import write_tm25
    rng = np.random.default_rng(1)
    n = 600
    th, ph = rng.uniform(-1.3, 1.3, n), rng.uniform(-0.05, 0.05, n)
    dirs = np.c_[np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]
    pos = np.c_[rng.uniform(-0.4, 0.4, n), rng.uniform(-0.4, 0.4, n), np.zeros(n)]
    return str(write_tm25(tmp_path_factory.mktemp("led") / "led.tm25", pos, dirs, np.cos(th) * 1e-3,
                          spectrum_nm=SPECTRUM))


DETECTOR = {"p1": [80, -40], "p2": [80, 40], "irradMap": True, "binSize": "10 mm", "name": "det"}


def _by_blocks(rayfile_path, runs_dir):
    """The chain, every link run from the JSON form of its inputs."""
    sl = run_block("slice_rayfile", {"rayfile": rayfile_path, "position": [0, 0], "direction_deg": "0 deg",
                                     "max_offset_mm": "0.5 mm"})["slice"]
    entries = [run_block("source_from_slice", {"slice": sl, "name": "led"})["entry"],
               run_block("TIRCollimator", {"name": "tir"})["entry"],
               run_block("Detector", DETECTOR)["entry"]]
    scene = run_block("assemble", {"entries": entries})["scene"]
    trace = run_block("trace", {"scene": scene, "runs_dir": str(runs_dir), "run_id": "r1"})["trace"]
    reading = run_block("detector_reading", {"trace": trace, "detector": "det", "profile": True})["reading"]
    phys = run_block("physical_reading", {"reading": reading, "calibration": "1 W/m", "detector_length": "80 mm"})
    weighted = run_block("hazard_weighted", {"irradiance": phys["irradiance"], "rayfile": rayfile_path,
                                             "hazard": "blue_light"})["weighted"]
    group = run_block("classify_iec62471", {"alpha": f"{ALPHA} rad",
                                            "blue_light_irradiance": weighted})["classification"]
    return {"slice": sl, "trace": trace, "reading": reading, "physical": phys, "weighted": weighted,
            "classification": group}


def _by_hand(rayfile_path):
    """The same chain in a notebook's own calls: no block, no unit parsed."""
    from ray_tracing_shapely.analysis.parameter_study import read_detector
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs import Detector
    from ray_tracing_shapely.core.simulator import Simulator
    from ray_tracing_shapely.optical_elements.eye_safety import iec62471, weighted_fraction
    from ray_tracing_shapely.optical_elements.physical_scene import PhysicalScene
    from ray_tracing_shapely.optical_elements.sources import read_rayfile, slice_rayfile
    from ray_tracing_shapely.optical_elements.lenses import TIRCollimator
    from ray_tracing_shapely.optical_elements.units import ureg

    rf = read_rayfile(rayfile_path)
    slc = slice_rayfile(rf, (0.0, 0.0), 0.0, max_offset_mm=0.5)
    scene = Scene()
    scene.add_object(slc.source_2d(scene, "led"))
    tir = TIRCollimator(scene)
    tir.name = "tir"
    scene.add_object(tir)
    det = Detector(scene, {"p1": {"x": 80, "y": -40}, "p2": {"x": 80, "y": 40}, "irradMap": True, "binSize": 10})
    det.name = "det"
    scene.add_object(det)
    result = Simulator(scene, max_rays=100000).run_with_result()
    reading = read_detector(scene, result, "det", profile=True)
    phys = PhysicalScene(scene_unit="mm")
    phys.set_calibration(1.0, ureg.Quantity(1.0, "W/m"))
    irradiance = (reading["power"] * phys.calibration_factor / ureg.Quantity(phys.to_m(80.0), "m")).to("W/m^2")
    weighted = irradiance.magnitude * weighted_fraction(rf.spectrum_nm, "blue_light")
    return {"slice": slc, "reading": reading, "irradiance": irradiance.magnitude, "weighted": weighted,
            "group": iec62471.classify_measurement(ALPHA, blue_light_value=weighted)}


@pytest.fixture(scope="module")
def chains(rayfile_path, tmp_path_factory):
    return _by_blocks(rayfile_path, tmp_path_factory.mktemp("runs")), _by_hand(rayfile_path)


def _magnitude(text):
    number, _unit = text.split(" ", 1)
    return float(number)


def test_the_chain_as_blocks_equals_the_chain_by_hand(chains):
    blocks, hand = chains
    assert blocks["reading"] == json.loads(json.dumps(hand["reading"]))
    assert _magnitude(blocks["physical"]["irradiance"]) == hand["irradiance"]
    assert _magnitude(blocks["weighted"]) == hand["weighted"]
    assert blocks["classification"]["group"] == hand["group"]
    assert hand["reading"]["hits"] > 100 and 0.5 < hand["reading"]["share"] < 1.0   # the collimator does collimate


def test_the_profile_is_each_bins_irradiance(chains):
    blocks, hand = chains
    profile = [_magnitude(v) for v in blocks["physical"]["profile"]]
    bins = hand["reading"]["profile"]["power"]
    assert profile == pytest.approx([p / 0.010 for p in bins], rel=1e-12)          # 1 W/m over a 10 mm bin
    assert sum(bins) == pytest.approx(hand["reading"]["power"], rel=1e-12)


def test_the_slice_reads_back_as_the_same_slice(chains):
    blocks, hand = chains
    again = run_block("slice_rayfile", {"rayfile": blocks["slice"]["rayfile"], "position": [0, 0],
                                        "direction_deg": "0 deg", "max_offset_mm": "0.5 mm"})["slice"]
    assert again == blocks["slice"]
    live = call_block("source_from_slice", {"slice": blocks["slice"], "name": "led"})["entry"]
    assert live == hand["slice"].scene_entry("led")


def test_the_trace_reads_back_from_its_folder(chains):
    blocks, _hand = chains
    back = TRACE.parse(blocks["trace"])
    assert isinstance(back, Trace) and back.result is None
    assert set(back.readings) == {"det"}
    assert [o.name for o in back.scene.objs] == ["led", "tir", "det"]
    assert TRACE.format(back) == blocks["trace"]


def test_a_trace_not_saved_has_no_json_form(rayfile_path):
    entry = run_block("Detector", DETECTOR)["entry"]
    with pytest.raises(BlockTypeError, match="runs_dir"):
        run_block("trace", {"scene": run_block("assemble", {"entries": [entry]})["scene"]})
    live = call_block("trace", {"scene": run_block("assemble", {"entries": [entry]})["scene"]})["trace"]
    assert live.readings["det"]["hits"] == 0 and live.folder is None


def test_assemble_refuses_a_shared_name():
    entry = run_block("Detector", DETECTOR)["entry"]
    with pytest.raises(BlockTypeError, match="C-LABEL-01"):
        run_block("assemble", {"entries": [entry, entry]})


def test_detector_reading_refusals(chains):
    blocks, _hand = chains
    with pytest.raises(BlockTypeError, match="no detector named 'tir'"):
        run_block("detector_reading", {"trace": blocks["trace"], "detector": "tir"})
    assert "profile" not in run_block("detector_reading", {"trace": blocks["trace"], "detector": "det"})["reading"]


def test_a_revolved_reading_is_refused_with_the_reason(chains):
    blocks, _hand = chains
    with pytest.raises(BlockTypeError, match="RevolvedProjection.*C-EYE-03"):
        run_block("physical_reading", {"reading": blocks["reading"], "calibration": "1 W/m",
                                       "detector_length": "80 mm", "symmetry": "revolve"})


def test_physical_reading_checks_its_units(chains):
    blocks, _hand = chains
    with pytest.raises(BlockTypeError):
        run_block("physical_reading", {"reading": blocks["reading"], "calibration": "1 W",
                                       "detector_length": "80 mm"})


def test_classification_refuses_the_wrong_kind():
    with pytest.raises(BlockTypeError):                                    # a radiance where E_IR goes
        run_block("classify_iec62471", {"alpha": "0.005 rad", "ir": "5 W/(m^2*sr)"})
    with pytest.raises(BlockTypeError, match="not both"):
        run_block("classify_iec62471", {"alpha": "0.005 rad", "blue_light_irradiance": "1 W/m^2",
                                        "blue_light_radiance": "1 W/(m^2*sr)"})
    with pytest.raises(BlockTypeError, match="blue_light at alpha 0.05 rad"):   # a large source: a radiance
        run_block("classify_iec62471", {"alpha": "0.05 rad", "blue_light_irradiance": "1 W/m^2"})
    with pytest.raises(BlockTypeError):                                    # a bare number for an angle
        run_block("classify_iec62471", {"alpha": 0.005, "ir": "1 W/m^2"})


def test_classification_lists_its_limits():
    out = run_block("classify_iec62471", {"alpha": "5 mrad", "blue_light_irradiance": "0.5 W/m^2"})
    c = out["classification"]
    assert c["group"] == "RG1"
    assert [(lim["group"], lim["within"]) for lim in c["limits"]] == [("exempt", False), ("rg1", True),
                                                                      ("rg2", True)]


def test_weighted_fraction():
    from ray_tracing_shapely.optical_elements.eye_safety import weighted_fraction
    flat_near_uv = [(300.0, 1.0), (315.0, 1.0), (400.0, 1.0), (500.0, 1.0)]
    assert weighted_fraction(flat_near_uv, "near_uv") == pytest.approx(85.0 / 200.0)
    assert weighted_fraction(SPECTRUM, "ir") == 0.0
    assert 0.0 < weighted_fraction(SPECTRUM, "blue_light") < 1.0
    with pytest.raises(ValueError, match="unknown hazard"):
        weighted_fraction(SPECTRUM, "x")
    with pytest.raises(ValueError, match="increase"):
        weighted_fraction(list(reversed(SPECTRUM)), "ir")
