"""
Python-specific module: test simulator new ray floor
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
The dimmest new ray the queue keeps (C-CORE-03)
===============================================================================
A ray through a glass slab at normal incidence keeps (1 - R) / (1 + R) of its
power once every internal bounce is counted. By default the simulator's floor is
the smaller of 1e-6 and the scene's threshold, so a scene asking for 1e-14 gets
the series to 1e-12, and one at the default keeps the old behaviour. An explicit
floor overrides both.
===============================================================================
"""
import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.simulator import Simulator

N = 1.3
R = ((N - 1) / (N + 1)) ** 2
ALL_BOUNCES = (1 - R) / (1 + R)


def _slab(min_brightness_exp):
    scene = Scene()
    scene.min_brightness_exp = min_brightness_exp
    slab = [(50, -20), (60, -20), (60, 20), (50, 20)]
    scene.add_object(SingleRay(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}}))
    scene.add_object(Glass(scene, {"path": [{"x": x, "y": y, "arc": False} for x, y in slab], "refIndex": N}))
    det = Detector(scene, {"p1": {"x": 100, "y": -50}, "p2": {"x": 100, "y": 50}})
    scene.add_object(det)
    return scene, det


def test_a_fine_scene_threshold_is_traced_to():
    scene, det = _slab(14)
    sim = Simulator(scene)
    sim.run()
    assert sim.effective_new_ray_floor() == pytest.approx(1e-14)
    assert det.power == pytest.approx(ALL_BOUNCES, rel=1e-12)


def test_the_default_floor_is_unchanged_at_coarser_thresholds():
    for exp in (None, 4, 6):
        scene, _ = _slab(exp)
        assert Simulator(scene).effective_new_ray_floor() == pytest.approx(min(1e-6, scene.get_min_brightness_threshold()))
    scene, det = _slab(6)
    Simulator(scene).run()
    assert abs(det.power - ALL_BOUNCES) > 1e-9                 # the third transmitted ray, 8e-8, is below 1e-6


def test_an_explicit_floor_overrides_the_scene():
    scene, det = _slab(14)
    sim = Simulator(scene, new_ray_floor=1e-3)
    sim.run()
    assert sim.effective_new_ray_floor() == 1e-3
    assert det.power == pytest.approx((1 - R) ** 2)            # only the direct pass: the bounces are below 1e-3
    with pytest.raises(ValueError, match="new_ray_floor"):
        Simulator(scene, new_ray_floor=-1.0)
