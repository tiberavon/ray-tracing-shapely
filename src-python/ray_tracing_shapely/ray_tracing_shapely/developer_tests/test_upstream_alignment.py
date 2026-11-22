"""
Python-specific module: test upstream alignment
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
The ported objects read and write the JavaScript simulator's own keys
===============================================================================
- Keys: every ported class loads upstream's names with no scene error and saves
  them; this package's earlier names still load, with a DeprecationWarning that
  names the caller's line, and still work as attributes.
- Detector: two-sided by default, a signed net flux, as upstream's. One-sided,
  a ray from the back does not meet it.
- Glass: ``partialReflect: false`` refracts all the light.
- Scene: ``max_ray_depth`` ends a ray after that many interactions; the rays
  an interaction spawns inherit its depth.
- Scene file 1.1 saves ``max_ray_depth`` (no limit as null); a 1.0 file's
  Detector that left its side out reads one-sided, as it meant then.
===============================================================================
"""

import math
import warnings

import pytest

from ray_tracing_shapely.analysis import scene_file as sf
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.glass.spherical_lens import SphericalLens
from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
from ray_tracing_shapely.core.scene_objs.light_source.beam import Beam
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.core.scene_objs.other.detector import Detector

LINE = {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}}
TRIANGLE = {"path": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 0, "y": 10}]}
LENS = {"p1": {"x": 0, "y": 10}, "p2": {"x": 0, "y": -10}, "params": {"d": 2, "r1": 20, "r2": -20}}

# class, upstream's keys with non-default values, this package's earlier names for them
CASES = [
    (Beam, {**LINE, "emisAngle": 20.0}, {"emis_angle": "emisAngle"}),
    (AngleSource, {**LINE, "emisAngle": 20.0}, {"emis_angle": "emisAngle"}),
    (Detector, {**LINE, "irradMap": True, "binSize": 2.0, "twoSided": False},
     {"irrad_map": "irradMap", "bin_size": "binSize", "two_sided": "twoSided"}),
    (Glass, {**TRIANGLE, "cauchyB": 0.01, "partialReflect": False},
     {"cauchy_b": "cauchyB"}),
    (SphericalLens, {**LENS, "defBy": "DR1R2", "partialReflect": False}, {}),
]


@pytest.mark.parametrize("cls,data,_", CASES, ids=[c[0].__name__ for c in CASES])
def test_upstream_keys_load_without_error_and_are_saved_as_they_came(cls, data, _):
    scene = Scene()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        obj = cls(scene, {"type": cls.type, **data})
    assert scene.error is None
    saved = obj.serialize()
    for key, value in data.items():
        if key in ("path", "p1", "p2", "params"):     # geometry, rebuilt on load
            continue
        assert getattr(obj, key) == value
        if key in cls.serializable_defaults and value != cls.serializable_defaults[key]:
            assert saved[key] == value


@pytest.mark.parametrize("cls,data,old", [c for c in CASES if c[2]], ids=[c[0].__name__ for c in CASES if c[2]])
def test_earlier_names_still_load_with_a_warning_at_the_callers_line_and_stay_attributes(cls, data, old):
    scene = Scene()
    legacy = {o: data[n] for o, n in old.items()}
    current = {k: v for k, v in data.items() if k not in old.values()}
    with pytest.warns(DeprecationWarning, match="renamed to") as caught:
        obj = cls(scene, {**current, **legacy})
    assert caught[0].filename == __file__        # the user's line, so it is shown
    assert scene.error is None
    for o, n in old.items():
        assert getattr(obj, n) == data[n] and getattr(obj, o) == data[n]
        assert o not in obj.serialize()
    o, n = next(iter(old.items()))
    setattr(obj, o, data[n])                      # writing the old name writes the current one
    assert getattr(obj, n) == data[n]


def _detector_between_two_rays(**json):
    """Two rays cross the line x = 100 (p1 above p2): one left to right (sign -1),
    one right to left (sign +1), with brightness 0.7 and 0.2."""
    scene = Scene()
    scene.add_object(SingleRay(scene, {"p1": {"x": 0, "y": 10}, "p2": {"x": 10, "y": 10}, "brightness": 0.7}))
    scene.add_object(SingleRay(scene, {"p1": {"x": 200, "y": -10}, "p2": {"x": 190, "y": -10}, "brightness": 0.2}))
    det = Detector(scene, {"p1": {"x": 100, "y": 50}, "p2": {"x": 100, "y": -50}, **json})
    scene.add_object(det)
    segments = Simulator(scene).run()
    return det, segments


def test_a_detector_is_two_sided_by_default_and_reads_the_signed_net_flux():
    det, _ = _detector_between_two_rays()
    assert det.twoSided is True
    assert det.power == pytest.approx(-0.7 + 0.2)
    assert sorted(r["sign"] for r in det.get_hit_records()) == [-1, 1]


@pytest.mark.parametrize("front,power", [(1, 0.2), (-1, -0.7)])
def test_a_one_sided_detector_is_not_met_by_rays_from_its_back(front, power):
    det, segments = _detector_between_two_rays(twoSided=False, absorbingSide=front)
    assert det.power == pytest.approx(power)
    # the ray from the back passes as if the detector were not there: no
    # segment of it ends on x = 100
    ends = [s for s in segments if abs(s.p2["x"] - 100) < 1e-9]
    assert len(ends) == 1


def _slab(partial_reflect):
    scene = Scene()
    scene.add_object(Glass(scene, {"path": [{"x": 0, "y": -10}, {"x": 10, "y": -10},
                                            {"x": 10, "y": 10}, {"x": 0, "y": 10}],
                                   "refIndex": 1.5, "partialReflect": partial_reflect}))
    scene.add_object(SingleRay(scene, {"p1": {"x": -20, "y": 1}, "p2": {"x": -10, "y": 0}, "brightness": 1.0}))
    return Simulator(scene, max_rays=200).run()


def test_partial_reflect_off_refracts_all_the_light():
    on, off = _slab(True), _slab(False)
    assert len(on) > len(off) == 3                 # in, through, out; no reflections
    last = max(off, key=lambda s: s.p1["x"])
    assert last.brightness_s + last.brightness_p == pytest.approx(1.0)


def _between_mirrors(depth):
    scene = Scene()
    scene.max_ray_depth = depth
    scene.add_object(Mirror(scene, {"p1": {"x": 0, "y": -10}, "p2": {"x": 0, "y": 10}}))
    scene.add_object(Mirror(scene, {"p1": {"x": 10, "y": -10}, "p2": {"x": 10, "y": 10}}))
    scene.add_object(SingleRay(scene, {"p1": {"x": 5, "y": 0}, "p2": {"x": 6, "y": 0}}))
    return Simulator(scene, max_rays=50).run()


@pytest.mark.parametrize("depth,segments", [(5, 6), (0, 1), (-3, 1), (None, 50), (math.inf, 50)])
def test_max_ray_depth_ends_a_ray_after_that_many_interactions(depth, segments):
    out = _between_mirrors(depth)
    assert len(out) == segments
    if segments < 50:
        assert out[-1].p2["x"] in (0.0, 10.0)      # drawn up to the mirror, then ended


def test_rays_an_interaction_spawns_inherit_its_depth():
    # A glass slab splits the ray at each face. With depth 1 only the first
    # interaction happens: its reflected and refracted rays have depth 1 and end
    # at the next object they meet.
    scene = Scene()
    scene.max_ray_depth = 1
    scene.add_object(Glass(scene, {"path": [{"x": 0, "y": -10}, {"x": 10, "y": -10},
                                            {"x": 10, "y": 10}, {"x": 0, "y": 10}], "refIndex": 1.5}))
    scene.add_object(Mirror(scene, {"p1": {"x": -30, "y": -20}, "p2": {"x": -30, "y": 20}}))
    scene.add_object(SingleRay(scene, {"p1": {"x": -20, "y": 1}, "p2": {"x": -10, "y": 0}}))
    out = Simulator(scene, max_rays=200).run()
    assert len(out) == 3                           # in; refracted to the far face; reflected to the mirror
    assert sorted(s.depth for s in out) == [0, 1, 1]


def test_the_scene_file_keeps_max_ray_depth_and_no_limit_is_null(tmp_path):
    for depth, saved in ((7, 7), (math.inf, None)):
        scene = Scene()
        scene.max_ray_depth = depth
        data = sf.scene_to_dict(scene)
        assert data["version"] == sf.VERSION == "1.1"
        assert data["settings"]["max_ray_depth"] == saved
        assert sf.scene_from_dict(data).max_ray_depth == depth


def test_a_1_0_scene_file_detector_without_a_side_reads_one_sided_as_it_meant():
    entry = {"name": "d", "object": {"type": "Detector", "p1": {"x": 0, "y": 0}, "p2": {"x": 0, "y": 1}}}
    old = sf.scene_from_dict({"schema": sf.SCHEMA, "version": "1.0", "settings": {}, "objects": [entry]})
    new = sf.scene_from_dict({"schema": sf.SCHEMA, "version": "1.1", "settings": {}, "objects": [entry]})
    assert old.get_object_by_name("d").twoSided is False
    assert new.get_object_by_name("d").twoSided is True


def test_the_queue_is_upstream_s_slots_walked_in_passes():
    # Upstream's rayIndex is a ray's slot: the ray that goes on keeps it, a
    # spawned ray is appended. Two parallel rays A (slot 0) and B (slot 1) at
    # normal incidence on a slab. Pass 1: A and B meet the front face; their
    # reflections take slots 2 and 3 and leave the scene. Pass 2: A and B,
    # refracted, meet the back face; their internal reflections take slots 4
    # and 5 and meet the front face. So the glass sees 0, 1, 0, 1, 4, 5. Which
    # weak rays the glass keeps by sampling depends on these numbers.
    scene = Scene()
    glass = Glass(scene, {"path": [{"x": 0, "y": -10}, {"x": 10, "y": -10},
                                   {"x": 10, "y": 10}, {"x": 0, "y": 10}], "refIndex": 1.5})
    seen = []
    incident = glass.on_ray_incident

    def recording(ray, ray_index, *args, **kwargs):
        seen.append(ray_index)
        return incident(ray, ray_index, *args, **kwargs)

    glass.on_ray_incident = recording
    scene.add_object(glass)
    for y in (1, -1):
        scene.add_object(SingleRay(scene, {"p1": {"x": -20, "y": y}, "p2": {"x": -10, "y": y}}))
    Simulator(scene, max_rays=200).run()
    assert seen[:6] == [0, 1, 0, 1, 4, 5]


# --- what is not upstream's lives outside core, under its own type ----------

# A slab whose right edge, from (10, -10) to (10, 10), is a circle of radius 20
# bulging outwards: its vertex is on the axis at x = 30 - sqrt(300).
VERTEX_X = 30.0 - math.sqrt(300.0)
SLAB_WITH_CURVE = [{"x": 0, "y": -10, "arc": False},
                   {"x": 10, "y": -10, "arc": False,
                    "curve": {"type": "conic", "vertex": [VERTEX_X, 0.0], "axis": [-1.0, 0.0],
                              "radius": 20.0, "conic": 0.0}},
                   {"x": 10, "y": 10, "arc": False},
                   {"x": 0, "y": 10, "arc": False}]


def test_a_glass_refuses_a_curved_edge_and_a_curved_glass_reads_it():
    from ray_tracing_shapely.optical_elements.curved_glass import CurvedGlass
    ray = {"p1": {"x": 20, "y": 0}, "p2": {"x": 19, "y": 0}}

    def trace(cls):
        scene = Scene()
        scene.add_object(cls(scene, {"path": [dict(p) for p in SLAB_WITH_CURVE]}))
        scene.add_object(SingleRay(scene, ray))
        return Simulator(scene, max_rays=50).run()

    with pytest.raises(ValueError, match="CurvedGlass"):
        trace(Glass)
    segments = trace(CurvedGlass)
    # the ray along the axis meets the curve's vertex, not the chord at x = 10
    assert segments[0].p2["x"] == pytest.approx(VERTEX_X)
    scene = Scene()
    assert CurvedGlass(scene, {"path": SLAB_WITH_CURVE}).serialize()["type"] == "CurvedGlass"


def test_python_only_objects_are_not_in_core():
    import ray_tracing_shapely.core.scene_objs as core_objs
    import ray_tracing_shapely.core.scene_objs.other as core_other
    from ray_tracing_shapely.analysis.backward_detector_source import BackwardDetectorSource  # noqa: F401
    from ray_tracing_shapely.optical_elements.ground_glass import GroundGlass
    from ray_tracing_shapely.optical_elements.sensors import Photodetector  # noqa: F401
    assert not hasattr(core_objs, "GroundGlass") and not hasattr(core_other, "Photodetector")
    assert GroundGlass.type == "GroundGlass"


def test_a_1_0_scene_file_s_curved_glass_and_ground_glass_read_under_their_new_types():
    entries = [
        {"name": "lens", "object": {"type": "Glass", "path": SLAB_WITH_CURVE}},
        {"name": "plain", "object": {"type": "Glass", "path": [
            {k: v for k, v in p.items() if k != "curve"} for p in SLAB_WITH_CURVE]}},
        {"name": "diffuser", "object": {"type": "ground_glass", "p1": {"x": 0, "y": 0}, "p2": {"x": 0, "y": 1}}},
    ]
    scene = sf.scene_from_dict({"schema": sf.SCHEMA, "version": "1.0", "settings": {}, "objects": entries})
    assert [type(scene.get_object_by_name(n)).__name__ for n in ("lens", "plain", "diffuser")] == \
        ["CurvedGlass", "Glass", "GroundGlass"]


def test_the_circle_mirror_left_the_name_arcmirror_to_upstream_s_three_point_mirror():
    from ray_tracing_shapely.optical_elements.mirrors import CircularArcMirror
    assert CircularArcMirror.type == "CircularArcMirror"
    assert sf.recipe_class("ArcMirror") is CircularArcMirror      # a file's old recipe name still reads
    assert "ArcMirror" not in sf.list_recipes()
    with pytest.warns(DeprecationWarning, match="CircularArcMirror"):
        from ray_tracing_shapely.optical_elements.mirrors import ArcMirror
    assert ArcMirror is CircularArcMirror
