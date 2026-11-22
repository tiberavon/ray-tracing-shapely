"""
Python-specific module: test property schema
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
Each object's editable properties, as the JavaScript simulator lists them
===============================================================================
- Order: a ported class's schema, without its Python-only entries, is
  upstream's getPropertySchema at the pin (v5.4.0), key by key and type by type,
  as read from upstream's source.
- Addressing: every key path reads a value from a real object, and writing one
  back through it changes the object.
- Coverage: every key an object saves is in its schema or named here as one
  upstream does not show either.
- key_path: upstream's rules for defaults, the empty path, made containers and
  default-valued writes.
===============================================================================
"""

import pytest

from ray_tracing_shapely.core.key_path import get_by_key_path, set_by_key_path
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.base_scene_obj import PROPERTY_TYPES
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.glass.ideal_lens import IdealLens
from ray_tracing_shapely.core.scene_objs.glass.spherical_lens import SphericalLens
from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
from ray_tracing_shapely.core.scene_objs.light_source.beam import Beam
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.mirror.ideal_mirror import IdealMirror
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.optical_elements.curved_glass import CurvedGlass
from ray_tracing_shapely.optical_elements.ground_glass import GroundGlass
from ray_tracing_shapely.optical_elements.sensors import Photodetector

LINE = [("p1", "point"), ("p2", "point")]
FILTER = [("filter", "boolean"), ("invert", "boolean"), ("wavelength", "number"), ("bandwidth", "number")]
BASE_GLASS = [("refIndex", "number"), ("cauchyB", "number"), ("partialReflect", "boolean")]
LIGHT = [("brightness", "number"), ("wavelength", "number")]

#: upstream v5.4.0 getPropertySchema, resolved through its class chains
UPSTREAM = {
    Mirror: LINE + FILTER,                                  # LineObjMixin(BaseFilter)
    Blocker: LINE + FILTER,
    IdealMirror: LINE + FILTER + [("focalLength", "number")],
    IdealLens: LINE + [("focalLength", "number")],          # LineObjMixin(BaseSceneObj)
    Detector: LINE + [("twoSided", "boolean"), ("irradMap", "boolean"), ("binSize", "number")],
    Glass: [("path", "array")] + BASE_GLASS,
    SphericalLens: [(f"path.{i}", "point") for i in range(6)] + BASE_GLASS,
    Beam: LINE + LIGHT + [("emisAngle", "number"), ("lambert", "boolean"), ("random", "boolean")],
    PointSource: [("", "point")] + LIGHT,
    SingleRay: LINE + LIGHT,
    AngleSource: LINE + LIGHT + [("emisAngle", "number"), ("symmetric", "boolean")],
}

#: saved keys upstream's schema leaves out too (construction state, or
#: addressed through another key)
NOT_SHOWN = {
    Glass: {"notDone"}, CurvedGlass: {"notDone"},
    SphericalLens: {"defBy", "p1", "p2", "params"},          # its path is shown as path.0 to path.5
    PointSource: {"x", "y"},                                 # its own point, key ""
    Photodetector: {"twoSided"},                             # always false
}

SCENE = Scene()
OBJECTS = {
    Mirror: Mirror(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    Blocker: Blocker(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    IdealMirror: IdealMirror(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    IdealLens: IdealLens(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    Detector: Detector(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    Photodetector: Photodetector(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    GroundGlass: GroundGlass(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    Glass: Glass(SCENE, {"path": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 0, "y": 1}]}),
    CurvedGlass: CurvedGlass(SCENE, {"path": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 0, "y": 1}]}),
    SphericalLens: SphericalLens(SCENE, {"p1": {"x": 0, "y": 10}, "p2": {"x": 0, "y": -10},
                                         "params": {"d": 2, "r1": 20, "r2": -20}}),
    Beam: Beam(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    PointSource: PointSource(SCENE, {"x": 0, "y": 0}),
    SingleRay: SingleRay(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
    AngleSource: AngleSource(SCENE, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}),
}


@pytest.mark.parametrize("cls", list(UPSTREAM), ids=lambda c: c.__name__)
def test_a_ported_class_lists_upstream_s_properties_in_upstream_s_order(cls):
    ours = [(x["key"], x["type"]) for x in cls.property_schema() if not x.get("python_only")]
    assert ours == UPSTREAM[cls]
    python_only = [x for x in cls.property_schema() if x.get("python_only")]
    assert cls.property_schema()[-len(python_only) or len(ours):] == (python_only or [])  # after upstream's


@pytest.mark.parametrize("cls", list(OBJECTS), ids=lambda c: c.__name__)
def test_every_entry_is_well_formed_and_addresses_a_value_of_a_real_object(cls):
    obj = OBJECTS[cls]
    for entry in cls.property_schema():
        assert entry["type"] in PROPERTY_TYPES and entry["label"]
        value = get_by_key_path(obj, entry["key"], cls.serializable_defaults)
        assert value is not None, entry["key"]


@pytest.mark.parametrize("cls", list(OBJECTS), ids=lambda c: c.__name__)
def test_every_saved_key_is_in_the_schema_or_named_as_not_shown(cls):
    shown = {x["key"].split(".")[0] for x in cls.property_schema()}
    assert set(cls.serializable_defaults) - shown == NOT_SHOWN.get(cls, set())


def test_units_are_separate_from_labels():
    beam = {x["key"]: x for x in Beam.property_schema()}
    assert (beam["wavelength"]["label"], beam["wavelength"]["unit"]) == ("Wavelength", "nm")
    assert (beam["emisAngle"]["label"], beam["emisAngle"]["unit"]) == ("Emission Angle", "°")
    assert "unit" not in beam["p1"]                       # the scene's length unit
    glass = {x["key"]: x for x in Glass.property_schema()}
    assert glass["cauchyB"]["unit"] == "μm²" and "Cauchy coefficient A" in glass["refIndex"]["label"]


def test_writing_through_a_key_path_changes_the_object():
    beam = Beam(Scene(), {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}})
    set_by_key_path(beam, "emisAngle", 12.0)
    set_by_key_path(beam, "p2.y", 3.0)
    assert beam.emisAngle == 12.0 and beam.p2 == {"x": 1, "y": 3.0}
    lens = SphericalLens(Scene(), {"p1": {"x": 0, "y": 10}, "p2": {"x": 0, "y": -10},
                                   "params": {"d": 2, "r1": 20, "r2": -20}})
    set_by_key_path(lens, "path.0.x", 5.0)
    assert lens.path[0]["x"] == 5.0


def test_key_path_follows_upstream_s_rules():
    data = {"p1": {"x": 1, "y": 2}, "path": [{"x": 0, "y": 0, "arc": True}]}
    assert get_by_key_path(data, "") is data
    assert get_by_key_path(data, "path.0.arc") is True
    assert get_by_key_path(data, "binSize", {"binSize": 1.0}) == 1.0     # from the defaults
    assert get_by_key_path(data, "missing.deep") is None
    assert get_by_key_path(data, "for") == [] and get_by_key_path(data, "if") is True
    set_by_key_path(data, "new.list.1", 7)                               # containers made on the way
    assert data["new"] == {"list": [None, 7]}
    set_by_key_path(data, "binSize", 1.0, {"binSize": 1.0})              # a default is not written
    assert "binSize" not in data
    set_by_key_path(data, "path.0.x", 0, {"path": [{"x": 0}]})          # inside a list item it is
    assert data["path"][0]["x"] == 0
    with pytest.raises(ValueError):
        set_by_key_path(data, "", 1)
