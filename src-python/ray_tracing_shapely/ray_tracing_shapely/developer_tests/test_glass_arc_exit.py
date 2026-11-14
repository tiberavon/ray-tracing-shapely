"""
Python-specific module: test glass arc exit
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

A ray that enters glass through an arc and leaves through the same arc.

Found by comparing a 2D trace with its 3D counterpart: a ray reflected
back into an LED's hemispherical dome went straight through its far side.
Glass._check_arc_intersection returned the nearer of the circle's two roots,
which for a ray starting on the arc is its own start; check_ray_intersects
then discarded that as too short, and the far root, where the ray really
leaves, was lost. Whether the start root counted as on the ray depended on
rounding, so the dome failed at some positions and not others. The fix
skips a too-short root inside the arc test, as _process_arc_segment and the
circle mixin always did.
"""

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.lenses import SingletLens

R = 3.0


def _singlet_dome(scene, x0, y0):
    return SingletLens(scene, radius_front=math.inf, radius_back=-R, thickness=R,
                       semi_diameter=R * (1 - 1e-5), n=1.5, position=(x0, y0), rotation=90.0)


def _glass_dome(scene, x0, y0):
    return Glass(scene, {"path": [{"x": x0 - R, "y": y0, "arc": False},
                                  {"x": x0, "y": y0 + R, "arc": True},
                                  {"x": x0 + R, "y": y0, "arc": False}], "refIndex": 1.5})


@pytest.mark.parametrize("make", [_singlet_dome, _glass_dome], ids=["SingletLens", "Glass"])
@pytest.mark.parametrize("x0, y0", [(0.0, 0.0), (0.5, 0.0), (3.0, 0.0), (30.0, 0.0), (100.0, 0.0),
                                    (300.0, 100.0), (-250.0, 40.0)])
def test_a_ray_that_enters_through_an_arc_leaves_through_it(make, x0, y0):
    """The ray from (x0 - 19.949, y0 + 1.745) enters the dome's arc at about
    (x0 - 2.73, y0 + 1.244) and must leave through the arc's far side, about
    (x0 + 2.986, y0 + 0.287): every point where the transmitted ray inside the
    glass ends is on the circle, not somewhere beyond it."""
    scene = Scene()
    dome = make(scene, x0, y0)
    scene.add_object(dome)
    start = (x0 - 19.949, y0 + 1.745)
    through = (x0 - 2.7299, y0 + 1.244)
    scene.add_object(SingleRay(scene, {"p1": {"x": start[0], "y": start[1]},
                                       "p2": {"x": through[0], "y": through[1]}}))
    sim = Simulator(scene, max_rays=50)
    sim.record_surface_hits = True
    segs = sim.run_with_result(name="arc").segments
    first = segs[0]
    entry = (first.p2["x"], first.p2["y"])
    assert math.hypot(entry[0] - x0, entry[1] - y0) == pytest.approx(R, abs=1e-9)
    inside = max((s for s in segs if s.parent_uuid == first.uuid), key=lambda s: s.total_brightness)
    end = (inside.p2["x"], inside.p2["y"])
    assert getattr(inside, "hit_surface_uuid", None) == dome.uuid
    assert math.hypot(end[0] - x0, end[1] - y0) == pytest.approx(R, abs=1e-9)
    assert end[0] - x0 == pytest.approx(2.9863, abs=1e-3)
