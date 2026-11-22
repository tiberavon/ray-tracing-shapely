"""
Python-specific module: test photodetector
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
A Detector is a flux probe; a Photodetector reads the power it absorbs
===============================================================================
A Detector's power keeps the crossing's sign: one absorbing from its -1 side
reads light crossing that way as negative, which is how a line in a design tells
which way the light goes. A Photodetector, built on it, reads the light absorbed
on its front face as positive whichever way its line is drawn, ignores the other
face, refuses twoSided, and is found wherever detectors are.
===============================================================================
"""
import pytest

from ray_tracing_shapely.analysis import scene_file as sf
from ray_tracing_shapely.analysis.simulation_result import detector_hits_of
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.optical_elements.sensors.photodetector import Photodetector
from ray_tracing_shapely.core.simulator import Simulator

# A ray along +x crosses a vertical line drawn downwards (p1 above p2): sign -1.
DOWN = {"p1": {"x": 100, "y": 50}, "p2": {"x": 100, "y": -50}, "irradMap": True, "binSize": 10}


def _trace(cls, brightness=0.7, **kw):
    scene = Scene()
    scene.add_object(SingleRay(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}, "brightness": brightness}))
    det = cls(scene, {**DOWN, **kw})
    scene.add_object(det)
    Simulator(scene).run()
    return det


def test_a_detector_reads_the_crossing_direction_as_the_sign_of_its_power():
    det = _trace(Detector)                                  # two-sided, the default: signed flux
    assert det.power == pytest.approx(-0.7)
    assert det.get_hit_records()[0]["sign"] == -1
    assert sum(det.bin_data) == pytest.approx(-0.7)


def test_a_photodetector_reads_absorbed_power_whichever_way_its_line_is_drawn():
    det = _trace(Photodetector, absorbingSide=-1)
    assert det.power == pytest.approx(0.7)
    assert sum(det.bin_data) == pytest.approx(0.7) and min(det.bin_data) >= 0
    assert det.get_hit_records()[0]["sign"] == -1          # the record still says which way it crossed


def test_a_photodetector_ignores_light_on_its_back_face():
    det = _trace(Photodetector)                             # front +1; the ray crosses -1
    assert det.power == 0.0 and det.get_hit_records() == []


def test_a_photodetector_is_one_sided():
    with pytest.raises(ValueError, match="twoSided"):
        Photodetector(Scene(), {**DOWN, "twoSided": True})
    with pytest.raises(ValueError, match="absorbingSide"):
        Photodetector(Scene(), {**DOWN, "absorbingSide": 0})


def test_a_photodetector_is_found_where_detectors_are_and_saved_as_itself(tmp_path):
    scene = Scene()
    scene.add_object(SingleRay(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}}))
    det = Photodetector(scene, {**DOWN, "absorbingSide": -1})
    det.name = "sensor"
    scene.add_object(det)
    Simulator(scene).run()
    assert len(detector_hits_of(scene)[det.uuid]) == 1
    loaded = sf.load_scene(sf.save_scene(scene, tmp_path / "s.scene.json"))
    again = loaded.get_object_by_name("sensor")
    assert type(again) is Photodetector and again.absorbingSide == -1
