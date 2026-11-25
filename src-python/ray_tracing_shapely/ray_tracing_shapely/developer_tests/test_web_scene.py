"""
Python-specific module: test web scene
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
The JavaScript simulator's own scene files, read and written
===============================================================================
- A version 5 web scene is read: every object of a type this package has,
  built from its entry as it stands and named; its settings; what is left out
  (a type this package lacks, a label) listed, not dropped in silence.
- Another version, or another format, is refused with what to do.
- A scene is written back in the web format: primitives as they serialize, a
  designed element as the Glass outline it traces as, a curved glass or a
  Python-only type left out and listed; what is written reads back the same.
The upstream conformance check (dev_doc/tools/upstream.py) reads its 31
scenes through this loader too.
===============================================================================
"""

import json

import pytest

from ray_tracing_shapely.analysis import scene_file as sf
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.optical_elements.curved_glass import CurvedGlass
from ray_tracing_shapely.optical_elements.sensors import Photodetector

# As the web simulator saves it (cf. its test/scenes/mirror/Mirror/default.json)
WEB = {
    "version": 5, "name": "default",
    "objs": [
        {"type": "AngleSource", "p1": {"x": 594.6, "y": 273.2}, "p2": {"x": 617.8, "y": 257.6},
         "brightness": 0.3, "emisAngle": 20},
        {"type": "Detector", "p1": {"x": 611.0, "y": 243.6}, "p2": {"x": 705.0, "y": 248.4},
         "irradMap": True, "binSize": 5},
        {"type": "Mirror", "p1": {"x": 648.6, "y": 235.6}, "p2": {"x": 670.6, "y": 236.0}},
        {"type": "TextLabel", "x": 0, "y": 0, "text": "a note"},
        {"type": "CircleGrinGlass", "p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}},
    ],
    "width": 1500, "height": 800, "rayModeDensity": 10, "lengthScale": 2, "colorMode": "linear",
    "origin": {"x": -964.5, "y": -265.0}, "scale": 2.5, "randomSeed": "0", "maxRayDepth": 50,
}


def test_a_web_scene_is_read_with_its_settings_and_what_was_left_out_listed():
    assert sf.is_web_scene(WEB)
    scene, report = sf.scene_from_web_dict(WEB)
    assert [(type(o).type, o.name) for o in scene.objs] == [
        ("AngleSource", "AngleSource1"), ("Detector", "Detector1"), ("Mirror", "Mirror1")]
    det = scene.get_object_by_name("Detector1")
    assert det.irradMap is True and det.binSize == 5 and det.twoSided is True
    assert scene.get_object_by_name("AngleSource1").emisAngle == 20
    assert (scene.ray_mode_density, scene.length_scale, scene.color_mode, scene.max_ray_depth, scene.name) == \
        (10, 2, "linear", 50, "default")
    assert [(x["index"], x["type"]) for x in report["skipped"]] == [(3, "TextLabel"), (4, "CircleGrinGlass")]
    assert report["ignored_settings"] == ["randomSeed"]       # the view's keys are not reported


def test_another_version_or_format_is_refused_with_what_to_do():
    with pytest.raises(sf.SceneFileError, match="Open and save it in the web simulator"):
        sf.scene_from_web_dict({**WEB, "version": 4})
    with pytest.raises(sf.SceneFileError, match="not a web simulator scene"):
        sf.scene_from_web_dict({"schema": sf.SCHEMA, "objects": []})
    assert not sf.is_web_scene(sf.scene_to_dict(Scene()))


def test_a_scene_is_written_in_the_web_format_and_reads_back_the_same(tmp_path):
    scene = Scene()
    scene.ray_mode_density = 3
    mirror = Mirror(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}})
    mirror.name = "M"
    scene.add_object(mirror)
    det = Detector(scene, {"p1": {"x": 0, "y": 5}, "p2": {"x": 10, "y": 5}, "twoSided": False})
    det.name = "D"
    scene.add_object(det)
    lens = sf.recipe_class("SingletLens")(scene, radius_front=30, radius_back=-30, thickness=4,
                                          semi_diameter=8, position=(20, 0))
    lens.name = "L"
    scene.add_object(lens)
    curved = CurvedGlass(scene, {"path": [
        {"x": 0, "y": -10, "arc": False},
        {"x": 10, "y": -10, "arc": False, "curve": {"type": "conic", "vertex": [30 - 300 ** 0.5, 0.0],
                                                    "axis": [-1.0, 0.0], "radius": 20.0, "conic": 0.0}},
        {"x": 10, "y": 10, "arc": False}, {"x": 0, "y": 10, "arc": False}]})
    curved.name = "C"
    scene.add_object(curved)
    sensor = Photodetector(scene, {"p1": {"x": 0, "y": 20}, "p2": {"x": 10, "y": 20}})
    sensor.name = "P"
    scene.add_object(sensor)

    path = tmp_path / "out.web.json"
    report = sf.save_web_scene(scene, path)
    assert sorted((x["name"], x["type"]) for x in report["skipped"]) == [("C", "CurvedGlass"), ("P", "Photodetector")]
    data = json.loads(path.read_text())
    assert data["version"] == 5 and data["rayModeDensity"] == 3
    assert [o["type"] for o in data["objs"]] == ["Mirror", "Detector", "Glass"]
    assert data["objs"][1]["twoSided"] is False
    assert [(p["x"], p["y"]) for p in data["objs"][2]["path"]] == [(p["x"], p["y"]) for p in lens.path]

    back, report = sf.load_web_scene(path)
    assert report == {"skipped": [], "ignored_settings": []}
    assert [o.serialize() for o in back.objs[:2]] == [mirror.serialize(), det.serialize()]
