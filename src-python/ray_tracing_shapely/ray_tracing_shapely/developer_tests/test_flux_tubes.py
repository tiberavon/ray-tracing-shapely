"""
Python-specific module: test flux tubes
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
Flux tubes on the Example 9.1 RR lens (Chaves), a point source at its edge E1
===============================================================================
- the tubes deliver equal shares of the receiver's power, to within one ray's
  share; their emitted shares and the share outside them add up to 1; each
  tube's boundary rays deliver, and its route is the lens's two refractions,
  by two different edges;
- a point source is read round from just after its longest dark run, so the
  tubes are contiguous runs of the emission order and none straddles the
  dark side;
- C-SCULPT-01: the seeds replayed on the unedited scene give back every
  arrival, its route, its optical path length (to 1e-9) and its power;
- light lost inside a tube (a blocker in its middle) stays in it and lowers
  its delivered share (Map B);
- the caller's scene is not traced: its detector and threshold are untouched;
- refused with the reason: a gradient-index glass, an unknown receiver or one
  that is not a detector, too few rays for the tubes, a trace stopped by its
  cap, two objects with one name, settings out of range;
- the set round-trips through JSON.
===============================================================================
"""

import json
import math

import pytest

from ray_tracing_shapely.analysis import flux_tubes as ft
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens

E1, E2, R1, R2 = (-1.0, 2.0), (1.0, 2.0), (-0.5, -2.0), (0.5, -2.0)


def _two_refractions(route):
    """The lens's two refractions, by two different edges, then the receiver."""
    return (len(route) == 3 and [(n, e) for n, _, e in route] == [("lens", "refract"), ("lens", "refract"),
                                                                    ("R", "arrive")]
            and route[0][1] is not None and route[1][1] is not None and route[0][1] != route[1][1])


def rr_scene(density=2.0):
    scene = Scene()
    scene.add_object(RRLens(scene, E1, E2, R1, R2, seed_n_angle_deg=303.3, seed_x_angle_deg=42.7,
                            n=1.5, etendue=1.0, n_points_per_section=5, name="lens"))
    src = PointSource(scene, {"x": E1[0], "y": E1[1], "brightness": 0.5})
    src.name = "E1"
    scene.add_object(src)
    det = Detector(scene, {"p1": {"x": -0.6, "y": -2.0}, "p2": {"x": 0.6, "y": -2.0}})
    det.name = "R"
    scene.add_object(det)
    scene.ray_density = density
    return scene


@pytest.fixture(scope="module")
def tubes():
    return ft.partition(rr_scene(), "R", ft.TubeSettings(tubes=8))


def _delivered(t):
    return sum(a.power for a in t.arrivals)


def test_the_tubes_deliver_equal_shares(tubes):
    assert [t.tube_id for t in tubes.tubes] == [f"E1/T{k}" for k in range(8)]
    total = sum(_delivered(t) for t in tubes.tubes)
    one_ray = max(sum(a.power for a in t.arrivals if a.seed == j) for t in tubes.tubes for j in range(len(t.seeds)))
    for t in tubes.tubes:
        assert abs(_delivered(t) - total / 8) <= one_ray, (t.tube_id, _delivered(t), total / 8, one_ray)
        first, last = t.boundary
        assert 0 <= first <= last < len(t.seeds)
        assert any(a.seed == first for a in t.arrivals) and any(a.seed == last for a in t.arrivals)
        assert _two_refractions(t.signature) and dict(t.routes)[t.signature] > 0.85   # the rest: TIR at the lens's side edge
        assert 0 < t.delivered_fraction <= 1
    assert abs(sum(t.power_fraction for t in tubes.tubes) + tubes.outside_fraction["E1"] - 1) < 1e-12
    assert [row["tube_id"] for row in tubes.power_map()] == [t.tube_id for t in tubes.tubes]


def test_a_point_source_is_read_round_from_its_longest_dark_run(tubes):
    angles = [math.atan2(s.d[1], s.d[0]) for t in tubes.tubes for s in t.seeds]
    steps = [(b - a + math.pi) % (2 * math.pi) - math.pi for a, b in zip(angles, angles[1:])]
    spacing = abs(steps[0])
    assert all(abs(abs(x) - spacing) < 1e-9 for x in steps), "the tubes are one contiguous run of the emission"
    assert len({math.copysign(1, x) for x in steps}) == 1, "in one direction round"
    assert all(s.d[1] < 0 for t in tubes.tubes for s in t.seeds), "all towards the lens, none across the dark side"


def test_the_seeds_replayed_give_back_every_arrival(tubes):
    """C-SCULPT-01, on the unedited scene."""
    again = ft.replay(rr_scene(), tubes)
    assert again.rays == sum(len(t.seeds) for t in tubes.tubes)
    for t in tubes.tubes:
        r = again.tubes[t.tube_id]
        before = sorted((a.seed, a.route, a.opl, a.power) for a in t.arrivals)
        after = sorted((a.seed, a.route, a.opl, a.power) for a in r.arrivals)
        assert len(before) == len(after), t.tube_id
        for (s0, r0, o0, p0), (s1, r1, o1, p1) in zip(before, after):
            assert (s0, r0) == (s1, r1) and abs(o0 - o1) < 1e-9 and abs(p0 - p1) < 1e-12
        assert r.signature == t.signature and abs(r.delivered_fraction - t.delivered_fraction) < 1e-12


def test_light_lost_inside_a_tube_stays_in_it(tubes):
    middle = tubes.tubes[4]
    d = middle.seeds[len(middle.seeds) // 2].d
    at = (E1[0] + 1.0 * d[0], E1[1] + 1.0 * d[1])
    spacing = 2 * math.pi / 1000 * 1.5            # wide enough for one or two rays
    half = (-d[1] * spacing, d[0] * spacing)
    scene = rr_scene()
    blocker = Blocker(scene, {"p1": {"x": at[0] - half[0], "y": at[1] - half[1]},
                              "p2": {"x": at[0] + half[0], "y": at[1] + half[1]}})
    blocker.name = "stop"
    scene.add_object(blocker)
    blocked = ft.partition(scene, "R", ft.TubeSettings(tubes=8))
    worst = min(blocked.tubes, key=lambda t: t.delivered_fraction)
    assert worst.delivered_fraction < 0.8 < min(t.delivered_fraction for t in tubes.tubes)
    assert sum(len(t.seeds) for t in blocked.tubes) == sum(len(t.seeds) for t in tubes.tubes)


def test_the_callers_scene_is_not_traced():
    scene = rr_scene()
    det = next(o for o in scene.objs if o.name == "R")
    det.power = 123.0
    ft.partition(scene, "R", ft.TubeSettings(tubes=4))
    assert det.power == 123.0 and scene.min_brightness_exp is None


def test_refusals_say_why():
    from ray_tracing_shapely.core.scene_objs.base_grin_glass import BaseGrinGlass

    class Grin(BaseGrinGlass):
        type = "test_grin"

    scene = rr_scene()
    grin = Grin(scene, {"refIndexFn": "1.5", "absorptionFn": "0", "origin": {"x": 5, "y": 5},
                        "stepSize": 0.1, "intersectTol": 0.001})
    grin.name = "grin"
    scene.add_object(grin)
    with pytest.raises(ft.FluxTubeError, match="gradient-index glass"):
        ft.partition(scene, "R")
    with pytest.raises(ft.FluxTubeError, match="no object named 'nowhere'"):
        ft.partition(rr_scene(), "nowhere")
    with pytest.raises(ft.FluxTubeError, match="not a detector"):
        ft.partition(rr_scene(), "lens")
    with pytest.raises(ft.FluxTubeError, match="raise the scene's ray density or lower the tube count"):
        ft.partition(rr_scene(density=0.5), "R", ft.TubeSettings(tubes=10, min_rays_per_tube=5))
    with pytest.raises(ft.FluxTubeError, match="raise max_rays"):
        ft.partition(rr_scene(), "R", ft.TubeSettings(max_rays=50))
    twin = rr_scene()
    twin.objs[0].name = "R"
    with pytest.raises(ft.FluxTubeError, match="two objects share a name"):
        ft.partition(twin, "R")
    for bad in ({"tubes": 0}, {"min_rays_per_tube": 0}, {"max_rays": 0}, {"min_brightness_exp": 0}):
        with pytest.raises(ft.FluxTubeError):
            ft.TubeSettings(**bad)


def test_the_set_round_trips_through_json(tubes):
    back = ft.TubeSet.from_dict(json.loads(json.dumps(tubes.to_dict())))
    assert back == tubes
    a, b = back.tubes[0].signature[0][1], back.tubes[0].signature[1][1]
    assert ft.route_text(back.tubes[0].signature) == f"lens#{a} refract → lens#{b} refract → R arrive"
