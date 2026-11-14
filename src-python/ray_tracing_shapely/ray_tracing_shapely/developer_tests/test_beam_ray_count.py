"""
Python-specific module: test beam ray count
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
A Beam emits as many rays as upstream does, each from inside its segment
===============================================================================
n = length * ray_density / length_scale. Upstream places rays at
(i + 0.5) * step for floor(n + 0.5) positions, and a random beam emits
ceil(n * m) rays (KW-CORE-02). The translation used max(1, int(n)), which
put a short beam's one ray outside it and dropped a fractional beam's last.
===============================================================================
"""

from __future__ import annotations

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.beam import Beam


def _beam(length: float, ray_density: float, *, random: bool = False) -> Beam:
    scene = Scene()
    scene.ray_density = ray_density
    beam = Beam(scene)
    beam.p1 = {'x': 0.0, 'y': 0.0}
    beam.p2 = {'x': 0.0, 'y': length}
    beam.random = random
    scene.add_object(beam)
    return beam


def _origins_along(beam: Beam):
    """Each emitted ray's start as a fraction of the beam's length."""
    rays = beam.on_simulation_start()['newRays']
    return [ray.p1.y / beam.p2['y'] for ray in rays]


@pytest.mark.parametrize("n, count", [(0.1, 0), (0.49, 0), (0.5, 1), (0.9, 1), (1.0, 1),
                                      (1.7, 2), (3.5, 4), (10.0, 10)])
def test_positions_are_floor_n_plus_half(n, count):
    beam = _beam(10.0 * n, 0.1)                    # length_scale 1: n = length * 0.1
    assert len(_origins_along(beam)) == count


def test_every_ray_starts_inside_the_beam():
    for n in (0.5, 0.7, 1.7, 3.5, 7.2):
        fractions = _origins_along(_beam(10.0 * n, 0.1))
        assert fractions and all(0.0 <= f <= 1.0 + 1e-12 for f in fractions)
        assert fractions == pytest.approx([(i + 0.5) / n for i in range(len(fractions))])


def test_a_beam_too_short_for_one_ray_emits_none_and_says_so():
    beam = _beam(1.0, 0.1)                          # n = 0.1: once its one ray started 5 lengths away
    assert _origins_along(beam) == []
    assert beam.warning and 'no ray' in beam.warning


@pytest.mark.parametrize("n, count", [(0.1, 1), (1.7, 2), (3.5, 4), (3.0, 3)])
def test_a_random_beam_emits_ceil_n(n, count):
    beam = _beam(10.0 * n, 0.1, random=True)       # no divergence: m = 1
    fractions = _origins_along(beam)
    assert len(fractions) == count == math.ceil(n)
    assert all(0.0 <= f <= 1.0 for f in fractions)
