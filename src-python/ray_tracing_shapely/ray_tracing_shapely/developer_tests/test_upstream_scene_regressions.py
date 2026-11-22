"""
Python-specific module: test upstream scene regressions
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
Bugs found by running the JavaScript simulator's own test scenes
===============================================================================
Each test is the smallest scene that shows the bug, and each checks the traced
result, not only that it runs:

- a diverging IdealLens, whose second construction line was built from a dict;
  and an IdealLens of either sign wrote the turned ray into the recorded
  incoming segment's points, leaving that segment zero-length;
- a SphericalLens given as its outline, which has no ``not_done`` of its own;
- a Glass with "Simulate Colors" on, whose Cauchy B was saved as ``cauchy_b``
  while the refraction read upstream's ``cauchyB``.

The old key ``cauchy_b`` still loads, with a DeprecationWarning.
===============================================================================
"""

import math
import warnings

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.glass.ideal_lens import IdealLens
from ray_tracing_shapely.core.scene_objs.glass.spherical_lens import SphericalLens
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay


def _xy(p):
    return (p['x'], p['y']) if isinstance(p, dict) else (p.x, p.y)


def _direction(seg):
    (x1, y1), (x2, y2) = _xy(seg.p1), _xy(seg.p2)
    n = math.hypot(x2 - x1, y2 - y1)
    return (x2 - x1) / n, (y2 - y1) / n


def _trace(scene):
    return Simulator(scene, max_rays=1000).run()


@pytest.mark.parametrize("focal_length", [-100, 100])
def test_an_ideal_lens_bends_a_ray_through_its_focus_and_keeps_the_incoming_segment(focal_length):
    # Lens on x = 0 from y = -50 to 50. A ray parallel to the axis at height 10
    # leaves towards the back focus (converging, slope -10/100) or as if from
    # the front focus (diverging, slope +10/100). The incoming segment, recorded
    # before the lens turns the ray, still runs from the source to the lens.
    scene = Scene()
    scene.add_object(IdealLens(scene, {'p1': {'x': 0, 'y': -50}, 'p2': {'x': 0, 'y': 50},
                                       'focalLength': focal_length}))
    scene.add_object(SingleRay(scene, {'p1': {'x': -50, 'y': 10}, 'p2': {'x': -40, 'y': 10}}))
    incoming, outgoing = _trace(scene)[:2]
    assert _xy(incoming.p1) == pytest.approx((-50, 10))
    assert _xy(incoming.p2) == pytest.approx((0, 10))
    assert _xy(outgoing.p1) == pytest.approx((0, 10))
    dx, dy = _direction(outgoing)
    assert dy / dx == pytest.approx(-10 / focal_length, rel=1e-9)


def test_a_spherical_lens_given_as_its_outline_traces():
    # Upstream's own scenes save a SphericalLens as its path. A ray through the
    # middle of a symmetric biconvex lens goes straight on.
    path = [{'x': 730, 'y': 400, 'arc': False}, {'x': 780, 'y': 400, 'arc': False},
            {'x': 790, 'y': 440, 'arc': True}, {'x': 780, 'y': 480, 'arc': False},
            {'x': 730, 'y': 480, 'arc': False}, {'x': 720, 'y': 440, 'arc': True}]
    scene = Scene()
    lens = SphericalLens(scene, {'path': path})
    assert lens.not_done is False
    scene.add_object(lens)
    scene.add_object(SingleRay(scene, {'p1': {'x': 600, 'y': 440}, 'p2': {'x': 610, 'y': 440}}))
    segments = _trace(scene)
    assert len(segments) >= 3          # to the lens, inside it, beyond it
    for seg in segments:
        assert _direction(seg)[1] == pytest.approx(0, abs=1e-12)


def test_a_glass_with_simulated_colours_uses_its_cauchy_b():
    # The ray enters a slab's face x = 0 at 1/10 rad slope and leaves its face x = 10:
    # parallel faces give back the entry slope whatever n(450 nm) is, so compare
    # the ray inside, whose slope depends on n = A + B / lambda^2.
    def slope_inside(b):
        scene = Scene()
        scene.simulate_colors = True
        glass = Glass(scene, {'path': [{'x': 0, 'y': -10}, {'x': 10, 'y': -10},
                                       {'x': 10, 'y': 10}, {'x': 0, 'y': 10}],
                              'refIndex': 1.5, 'cauchyB': b})
        scene.add_object(glass)
        scene.add_object(SingleRay(scene, {'p1': {'x': -20, 'y': 1}, 'p2': {'x': -10, 'y': 0},
                                           'wavelength': 450}))
        inside = [s for s in _trace(scene)          # forward, not the Fresnel reflections
                  if 0 <= _xy(s.p1)[0] < 10 - 1e-9 and _direction(s)[0] > 0]
        dx, dy = _direction(inside[0])
        return dy / dx

    def expected(b):
        n = 1.5 + b / (450 * 450 * 1e-6)
        sin_out = (-1 / math.hypot(10, 1)) / n
        return sin_out / math.sqrt(1 - sin_out ** 2)

    for b in (0.004, 0.02):
        assert slope_inside(b) == pytest.approx(expected(b), rel=1e-9)


def test_the_old_cauchy_b_key_still_loads_with_a_deprecation_warning():
    scene = Scene()
    with pytest.warns(DeprecationWarning, match="cauchy_b renamed to cauchyB"):
        glass = Glass(scene, {'path': [{'x': 0, 'y': 0}, {'x': 1, 'y': 0}, {'x': 0, 'y': 1}],
                              'cauchy_b': 0.01})
    assert glass.cauchyB == 0.01
    assert glass.cauchy_b == 0.01                    # the attribute's old name too
    assert scene.error is None                       # not an unknown key
    assert glass.serialize()['cauchyB'] == 0.01      # saved under upstream's name
    assert 'cauchy_b' not in glass.serialize()


def test_upstream_s_name_loads_without_a_warning():
    scene = Scene()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        glass = Glass(scene, {'path': [{'x': 0, 'y': 0}, {'x': 1, 'y': 0}, {'x': 0, 'y': 1}],
                              'cauchyB': 0.01})
    assert glass.cauchyB == 0.01
