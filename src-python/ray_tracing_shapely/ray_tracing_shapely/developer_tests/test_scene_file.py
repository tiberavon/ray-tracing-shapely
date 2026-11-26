"""
Python-specific module: test scene file
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
A scene saved to a file and opened again
===============================================================================
Every primitive and every designed element round-trips: built, saved, loaded,
the same serialize(), the same names, roles and labels, the same rays when
traced. A designed element is saved as its recipe, so changing one argument in
the file gives what the constructor gives with that argument. Parts (an XR's
primary mirrors, an RXI's mirror) come back as their owner's own objects, once.
A scene that would not come back the same is refused, by name.
===============================================================================
"""
import json
import math

import numpy as np
import pytest

from ray_tracing_shapely.analysis import scene_file as sf
from ray_tracing_shapely.analysis.scene_file import SceneFileError
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.beam import Beam
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.optical_elements.sensors.photodetector import Photodetector
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.lenses.tir_collimator import TIRCollimator
from ray_tracing_shapely.optical_elements.prisms.equilateral import EquilateralPrism
from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic
from ray_tracing_shapely.optical_elements.prisms.xr_concentrator import XRConcentrator
from ray_tracing_shapely.optical_elements.roles import Role


def _spline_points():
    xs = np.linspace(-2.0, 2.0, 9)
    points = [(float(x), 0.1 * float(x) ** 2) for x in xs]
    normals = [(-0.2 * x / math.hypot(0.2 * x, 1.0), 1.0 / math.hypot(0.2 * x, 1.0)) for x, _ in points]
    return points, normals


def _every_recipe(scene):
    """One of every registered recipe, with the arguments their own tests use."""
    R = sf.recipe_class
    points, normals = _spline_points()
    return {
        "CircularArcMirror": R("CircularArcMirror")(scene, (0.0, 0.0), (1.0, 0.0), 10.0, semi_diameter=10.0),
        "ConicMirror": R("ConicMirror")(scene, (0.0, 30.0), (0.0, -1.0), 20.0, -1.0, semi_diameter=15.0),
        "SplineMirror": R("SplineMirror")(scene, points, normals),
        "DTIRCPrism": R("DTIRCPrism")(scene, theta_deg=10.0, n=1.5),
        "EquilateralPrism": R("EquilateralPrism")(scene, side_length=10.0, position=(40.0, 2.0)),
        "RightAnglePrism": R("RightAnglePrism")(scene, leg_length=8.0, position=(60.0, 2.0)),
        "RefractometerPrism": R("RefractometerPrism")(scene, n_prism=1.72, n_sample_range=(1.30, 1.50),
                                                      measuring_surface_length=20.0),
        "SingletLens": R("SingletLens")(scene, radius_front=60.0, radius_back=-20.0, thickness=5.0,
                                        semi_diameter=10.0, n=1.5),
        "RRLens": R("RRLens")(scene, (-1.0, 2.0), (1.0, 2.0), (-0.5, -2.0), (0.5, -2.0),
                              seed_n_angle_deg=303.3, seed_x_angle_deg=42.7),
        "RXIOptic": R("RXIOptic")(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16),
        "RXIOpticDirect": R("RXIOpticDirect")(scene, (-1.0, 0.0), (1.0, 0.0), theta_deg=10.0, n=1.5),
        "RXConcentrator": R("RXConcentrator")(scene, (-0.5, 0.0), (0.5, 0.0), theta_deg=2.0),
        "XRConcentrator": R("XRConcentrator")(scene, (-0.5, 0.0), (0.5, 0.0), theta_deg=2.0,
                                              p0=(0.0, -4.0), n0=(0.0, -1.0), n=1.5),
        "SculptedGlass": R("SculptedGlass")(
            scene, {"recipe": "RRLens", "args": {"e1": [-1.0, 2.0], "e2": [1.0, 2.0], "r1": [-0.5, -2.0],
                                                 "r2": [0.5, -2.0], "seed_n_angle_deg": 303.3,
                                                 "seed_x_angle_deg": 42.7}},
            [{"edge": "N", "index": 26, "kind": "position", "delta": 0.002}]),
        "TIRCollimator": R("TIRCollimator")(scene),
        "FresnelLens": R("FresnelLens")(scene, focal_distance=20.0, semi_diameter=10.0, zones=4, thickness=2.0),
    }


def _primitives(scene):
    glass = Glass(scene, {"path": [{"x": 0, "y": 0, "arc": False}, {"x": 10, "y": 0, "arc": False},
                                   {"x": 5, "y": 8, "arc": False}], "refIndex": 1.6})
    glass.label_edge(0, "B", "Base")
    glass.role = Role.ABSORBER
    return {
        "Mirror": Mirror(scene, {"p1": {"x": 0, "y": -50}, "p2": {"x": 10, "y": -50}}),
        "Glass": glass,
        "Beam": Beam(scene, {"p1": {"x": -5, "y": -80}, "p2": {"x": 5, "y": -80}}),
        "PointSource": PointSource(scene, {"x": 0, "y": -30}),
        "SingleRay": SingleRay(scene, {"p1": {"x": 0, "y": -90}, "p2": {"x": 0, "y": -89}}),
        "Detector": Detector(scene, {"p1": {"x": -20, "y": 80}, "p2": {"x": 20, "y": 80}}),
        "Photodetector": Photodetector(scene, {"p1": {"x": -20, "y": 90}, "p2": {"x": 20, "y": 90},
                                               "absorbingSide": -1}),
    }


def _named_scene(objects):
    scene = Scene()
    for name, obj in objects(scene).items():
        obj.name = name
        scene.add_object(obj)
    return scene


def _lens(scene, **kw):
    lens = TIRCollimator(scene, **kw)
    lens.name = "lens"
    return lens


def _signature(obj):
    return json.dumps(obj.serialize(), sort_keys=True)


def test_every_recipe_is_registered():
    assert set(_every_recipe(Scene())) == set(sf.list_recipes())


def test_every_recipe_and_primitive_round_trips_through_a_file(tmp_path):
    scene = _named_scene(lambda s: {**_every_recipe(s), **_primitives(s)})
    scene.min_brightness_exp = 4
    scene.ray_mode_density = 0.05
    path = sf.save_scene(scene, tmp_path / "all.scene.json")

    data = json.loads(path.read_text())
    assert data["schema"] == sf.SCHEMA and data["version"] == sf.VERSION
    assert {e["recipe"] for e in data["objects"] if "recipe" in e} >= set(sf.list_recipes())

    loaded = sf.load_scene(path)
    assert [o.name for o in loaded.objs] == [o.name for o in scene.objs]
    assert [type(o) for o in loaded.objs] == [type(o) for o in scene.objs]
    assert [_signature(o) for o in loaded.objs] == [_signature(o) for o in scene.objs]
    assert loaded.min_brightness_exp == 4 and loaded.ray_mode_density == 0.05
    glass = loaded.get_object_by_name("Glass")
    assert glass.role is Role.ABSORBER and glass.edge_labels[0] == ("B", "Base")


def test_a_loaded_scene_traces_the_same_rays(tmp_path):
    scene = Scene()
    lens = _lens(scene)
    prism = EquilateralPrism(scene, side_length=12.0, position=(0.0, 70.0))
    prism.name = "prism"
    source = PointSource(scene, {"x": 0, "y": 0})
    source.name = "led"
    det = Detector(scene, {"p1": {"x": -60, "y": 120}, "p2": {"x": 60, "y": 120}})
    det.name = "screen"
    for o in (lens, prism, source, det):
        scene.add_object(o)
    scene.ray_mode_density = 0.2

    loaded = sf.load_scene(sf.save_scene(scene, tmp_path / "lens.scene.json"))

    def rays(s):
        segments = Simulator(s, max_rays=400).run_with_result(name="t").segments
        return [(round(g.p1["x"] if isinstance(g.p1, dict) else g.p1.x, 9),
                 round(g.p1["y"] if isinstance(g.p1, dict) else g.p1.y, 9),
                 round(g.brightness_s + g.brightness_p, 12)) for g in segments]

    first = rays(scene)
    assert len(first) > 20
    assert rays(loaded) == first


def test_one_argument_changed_in_the_file_is_the_constructor_with_it(tmp_path):
    scene = Scene()
    lens = _lens(scene)
    scene.add_object(lens)
    data = sf.scene_to_dict(scene)
    data["objects"][0]["args"]["cavity_depth"] = 6.0

    changed = sf.scene_from_dict(json.loads(json.dumps(data)))
    direct = _lens(Scene(), cavity_depth=6.0)
    assert _signature(changed.objs[0]) == _signature(direct)
    assert _signature(changed.objs[0]) != _signature(lens)


def test_parts_come_back_as_their_owners_own_objects_once():
    scene = Scene()
    xr = XRConcentrator(scene, (-0.5, 0.0), (0.5, 0.0), theta_deg=2.0, p0=(0.0, -4.0), n0=(0.0, -1.0), n=1.5)
    xr.name = "xr"
    scene.add_object(xr)
    for i, m in enumerate(xr.primary):
        m.name = f"xr_mirror_{i}"
        scene.add_object(m)
    rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)
    rxi.name = "rxi"
    scene.add_object(rxi)                     # its constructor already added its mirror

    data = sf.scene_to_dict(scene)
    parts = [e for e in data["objects"] if "part_of" in e]
    assert {e["name"] for e in parts} == {m.name for m in xr.primary} | {"rxi_s2_mirror"}

    loaded = sf.scene_from_dict(data)
    assert [o.name for o in loaded.objs] == [o.name for o in scene.objs]
    loaded_xr = loaded.get_object_by_name("xr")
    assert all(any(m is p for p in loaded_xr.primary) for m in loaded.objs if m.name.startswith("xr_mirror"))
    assert [_signature(o) for o in loaded.objs] == [_signature(o) for o in scene.objs]


def test_an_element_in_the_scene_only_through_its_parts_is_written_not_added():
    scene = Scene()
    xr = XRConcentrator(scene, (-0.5, 0.0), (0.5, 0.0), theta_deg=2.0, p0=(0.0, -4.0), n0=(0.0, -1.0), n=1.5)
    for i, m in enumerate(xr.primary):
        m.name = f"m{i}"
        scene.add_object(m)
    data = sf.scene_to_dict(scene)
    assert data["objects"][-1]["recipe"] == "XRConcentrator" and data["objects"][-1]["in_scene"] is False
    loaded = sf.scene_from_dict(data)
    assert [o.name for o in loaded.objs] == [o.name for o in scene.objs]


def test_the_construction_record():
    scene = Scene()
    prism = EquilateralPrism(scene, side_length=10.0, position=(1.0, 2.0))
    assert prism._construction_args == {"side_length": 10.0, "position": (1.0, 2.0), "rotation": 0.0,
                                        "n": 1.5, "anchor": "centroid"}
    assert prism._built_inside is None
    mirror = Mirror(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}})
    assert mirror._construction_args is None and mirror._built_inside is None
    xr = XRConcentrator(scene, (-0.5, 0.0), (0.5, 0.0), theta_deg=2.0, p0=(0.0, -4.0), n0=(0.0, -1.0), n=1.5)
    assert all(m._built_inside is xr for m in xr.primary)


def test_recipe_parameters_read_the_constructor():
    params = {p["name"]: p for p in sf.recipe_parameters("TIRCollimator")}
    assert params["cavity_depth"]["default"] == 5.35 and not params["cavity_depth"]["required"]
    assert params["position"]["default"] == [0.0, 0.0]
    rr = {p["name"]: p for p in sf.recipe_parameters("RRLens")}
    assert rr["seed_n_angle_deg"]["required"] and rr["e1"]["required"]


def test_register_recipe_refuses_a_clash():
    with pytest.raises(ValueError, match="primitive"):
        sf.register_recipe("Mirror", "x.y:Z")
    with pytest.raises(ValueError, match="already registered"):
        sf.register_recipe("TIRCollimator", "x.y:Z")
    sf.register_recipe("TIRCollimator", sf._RECIPES["TIRCollimator"])     # the same again: accepted


def test_a_designed_element_edited_after_it_was_built_is_refused():
    scene = Scene()
    prism = EquilateralPrism(scene, side_length=10.0)
    prism.name = "prism"
    scene.add_object(prism)
    prism.move(5.0, 0.0)
    with pytest.raises(SceneFileError, match="'prism'.*changed after it was built.*path"):
        sf.scene_to_dict(scene)


def test_shared_names_and_unknown_classes_are_refused(tmp_path):
    scene = Scene()
    for _ in range(2):
        m = Mirror(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}})
        m.name = "M"
        scene.add_object(m)
    with pytest.raises(SceneFileError, match="shared: M"):
        sf.save_scene(scene, tmp_path / "x.scene.json")
    assert not (tmp_path / "x.scene.json").exists()

    class MyPrism(EquilateralPrism):
        pass

    scene = Scene()
    scene.add_object(MyPrism(scene, side_length=5.0))
    with pytest.raises(SceneFileError, match="MyPrism is neither a primitive nor a registered recipe"):
        sf.scene_to_dict(scene)


def test_an_argument_that_is_not_plain_data_is_refused():
    scene = Scene()
    prism = EquilateralPrism(scene, side_length=10.0)
    prism._construction_args["anchor"] = object()
    scene.add_object(prism)
    with pytest.raises(SceneFileError, match="anchor: a object is not plain data"):
        sf.scene_to_dict(scene)


def test_a_file_that_cannot_be_read_is_refused():
    scene = Scene()
    scene.add_object(_lens(scene))
    data = sf.scene_to_dict(scene)

    with pytest.raises(SceneFileError, match="not a scene file"):
        sf.scene_from_dict({**data, "schema": "other"})
    with pytest.raises(SceneFileError, match="version '2.0'"):
        sf.scene_from_dict({**data, "version": "2.0"})
    with pytest.raises(SceneFileError, match="no recipe 'Lens'; recipes: CircularArcMirror"):
        sf.scene_from_dict({**data, "objects": [{"name": "x", "recipe": "Lens", "args": {}}]})
    with pytest.raises(SceneFileError, match="no primitive type 'Lamp'"):
        sf.scene_from_dict({**data, "objects": [{"name": "x", "object": {"type": "Lamp"}}]})
    bad = json.loads(json.dumps(data))
    bad["objects"][0]["args"]["cavity_depth"] = "deep"
    with pytest.raises(SceneFileError, match="'lens': TIRCollimator could not be built"):
        sf.scene_from_dict(bad)
    with pytest.raises(SceneFileError, match="unknown scene setting 'colour'"):
        sf.scene_from_dict({**data, "settings": {"colour": 1}})
