"""
Python-specific module: test mirror coated edge
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
A glass edge whose mechanism is reflect is a mirror, the glass's own
===============================================================================
A singlet exported, its back face's mechanism set to reflect in the profile
(a Mangin mirror), rebuilt by from_profile: a ray reaching the coated face from
inside, or from outside, reflects there at the face's exact normal, with its
brightness whole. The other face still refracts; an element that declares no
reflecting mechanism is unchanged.
===============================================================================
"""

from __future__ import annotations

import json
import math

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.lenses import SingletLens
from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_profile

LENS = dict(radius_front=60.0, radius_back=-20.0, thickness=5.0, semi_diameter=10.0, n=1.5)


def _profile(coat=("S2",)):
    lens = SingletLens(Scene(), **LENS)
    profile = json.loads(json.dumps(export_profile(lens, symmetry={"kind": "revolve", "axis": lens.revolve_axis()},
                                                   physical_params={}, numerical_params={})))
    for sp in profile["spans"]:
        if sp["short_label"] in coat:
            sp["mechanism"] = "reflect"
    return profile


def _trace(profile, start, direction):
    scene = Scene()
    glass = BasePrism.from_profile(scene, profile, n=LENS["n"])
    scene.add_object(glass)
    scene.add_object(SingleRay(scene, {"p1": {"x": start[0], "y": start[1]},
                                       "p2": {"x": start[0] + direction[0], "y": start[1] + direction[1]}}))
    segs = Simulator(scene, max_rays=100, record_surface_hits=True).run_with_result(name="m").segments
    kids = {}
    for g in segs:
        kids.setdefault(g.parent_uuid, []).append(g)
    return glass, kids


def _chain(kids):
    s, out = kids[None][0], []
    while True:
        out.append(s)
        nxt = sorted(kids.get(s.uuid, []), key=lambda g: -g.total_brightness)
        if not nxt:
            return out
        s = nxt[0]


def _unit(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n)


def test_the_coated_face_reflects_from_inside_exactly_and_losslessly():
    glass, kids = _trace(_profile(), (-20.0, 3.0), (1.0, 0.0))
    chain = _chain(kids)
    _, at_back, after = chain[0], chain[1], chain[2]
    assert glass.edge_reflects(next(sp.path_indices[0] for sp in glass.spans
                                    if glass.get_functional_label(sp.index)[0] == "S2"))
    d_in = _unit((at_back.p2["x"] - at_back.p1["x"], at_back.p2["y"] - at_back.p1["y"]))
    d_out = _unit((after.p2["x"] - after.p1["x"], after.p2["y"] - after.p1["y"]))
    hp = at_back.hit_point
    assert hp is not None and hp["x"] > 0.0                       # met the back face
    assert d_out[0] < 0.0, "reflected back towards the front face"
    assert abs(at_back.total_brightness - after.total_brightness) < 1e-12, "a perfect mirror loses nothing"
    # the law of reflection about the recorded normal: d_out = d_in - 2 (d_in . n) n
    nx, ny = _unit((at_back.hit_normal["x"], at_back.hit_normal["y"]))
    dot = d_in[0] * nx + d_in[1] * ny
    expected = (d_in[0] - 2 * dot * nx, d_in[1] - 2 * dot * ny)
    assert math.dist(expected, d_out) < 1e-12, (expected, d_out)


def test_the_coated_face_reflects_from_outside_and_the_other_face_refracts():
    _, kids = _trace(_profile(), (30.0, 2.0), (-1.0, 0.0))        # from behind, onto the coated back
    first = _chain(kids)
    d_out = _unit((first[1].p2["x"] - first[1].p1["x"], first[1].p2["y"] - first[1].p1["y"]))
    assert d_out[0] > 0.0 and len(first) == 2, "reflected away, never entering the glass"
    _, plain = _trace(_profile(coat=()), (30.0, 2.0), (-1.0, 0.0))
    assert len(_chain(plain)) >= 3, "uncoated, the ray enters the glass"
    _, front = _trace(_profile(), (-20.0, 3.0), (1.0, 0.0))
    entered = _chain(front)[1]
    assert entered.p2["x"] > entered.p1["x"], "the uncoated front face still refracts the ray in"
