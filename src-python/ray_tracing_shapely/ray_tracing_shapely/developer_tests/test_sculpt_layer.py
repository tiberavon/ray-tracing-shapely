"""
Python-specific module: test sculpt layer
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
The sculpt layer: tubes, bundles, spans, isolines and handles, each with its identity
===============================================================================
On the Example 9.1 RR lens (Chaves), as a sculpted glass with no edits:

- every tube is drawn, one band (or line) per route its rays take, filled by
  Map B on the sequential scale;
- every counted bundle ray is drawn with its bundle and seed, stroked by Map
  A on the diverging scale; a preview shifts the deviations it draws;
- every span of the bundles' entrance and exit edges is drawn, coloured by the
  mean deviation of the rays that meet it, or grey;
- isolines lie at equal S along the bundle's rays;
- every handle is drawn once, with its id, its tick along the outward normal;
- the colour scales: blue below the mean, red above, symmetric, clamped; the
  layer is above the drawing's others (KB6: identities and values on every
  element).
===============================================================================
"""

import math
import xml.etree.ElementTree as ET

import pytest

from ray_tracing_shapely.analysis import edge_bundles as eb
from ray_tracing_shapely.analysis import first_order as fo
from ray_tracing_shapely.analysis import flux_tubes as ft
from ray_tracing_shapely.analysis import sculpt_layer as sl
from ray_tracing_shapely.analysis.sculpted_glass import SculptedGlass
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.svg_renderer import SVGRenderer
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens

ARGS = {"e1": [-1.0, 2.0], "e2": [1.0, 2.0], "r1": [-0.5, -2.0], "r2": [0.5, -2.0],
        "seed_n_angle_deg": 303.3, "seed_x_angle_deg": 42.7}
SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture(scope="module")
def drawn():
    scene = Scene()
    scene.ray_density = 2.0
    scene.add_object(SculptedGlass(scene, {"recipe": "RRLens", "args": ARGS}, [], name="lens"))
    src = PointSource(scene, {"x": -1.0, "y": 2.0, "brightness": 0.5})
    src.name = "E1"
    scene.add_object(src)
    det = Detector(scene, {"p1": {"x": -0.6, "y": -2.0}, "p2": {"x": 0.6, "y": -2.0}})
    det.name = "R"
    scene.add_object(det)
    lens = RRLens(Scene(), *(tuple(ARGS[k]) for k in ("e1", "e2", "r1", "r2")), seed_n_angle_deg=303.3,
                  seed_x_angle_deg=42.7, name="lens")
    tubes = ft.partition(scene, "R")
    bundles = eb.edge_bundles(scene, eb.rr_bundles(lens), eb.BundleSettings(per_span=1))
    renderer = SVGRenderer(width=800, height=800, viewbox=(-1.6, -2.4, 3.2, 4.8))
    renderer.draw_scene(scene, None, draw_rays=False)
    sl.draw_sculpt_layer(renderer, scene, tubes=tubes, bundles=bundles, handles_of="lens")
    root = ET.fromstring(renderer.to_string())
    return scene, tubes, bundles, root


def _all(root, cls):
    return [e for e in root.iter() if e.get("class") == cls]


def test_every_tube_is_drawn_per_route_and_filled_by_map_b(drawn):
    _, tubes, _, root = drawn
    groups = {g.get("data-tube-id"): g for g in _all(root, "sculpt-tube")}
    assert set(groups) == {t.tube_id for t in tubes.tubes}
    for t in tubes.tubes:
        g = groups[t.tube_id]
        assert float(g.get("data-delivered-fraction")) == pytest.approx(t.delivered_fraction, rel=1e-5)
        routes = [e for e in g if e.get("class") == "sculpt-tube-route"]
        best = {}
        for a in t.arrivals:
            if a.seed not in best or a.power > best[a.seed].power:
                best[a.seed] = a
        assert {e.get("data-route") for e in routes} == {ft.route_text(a.route) for a in best.values()}
        assert sum(int(e.get("data-rays")) for e in routes) == len(best)
        color = sl.sequential_color(t.delivered_fraction)
        assert all(e.get("stroke") == color for e in routes)


def test_every_bundle_ray_is_drawn_by_map_a(drawn):
    _, _, bundles, root = drawn
    rays = _all(root, "sculpt-bundle-ray")
    scale = sl.opl_scale_for(bundles)
    for b in bundles.bundles:
        dev = b.deviations()
        mine = {int(e.get("data-seed")): e for e in rays if e.get("data-bundle-id") == b.bundle_id}
        assert set(mine) == set(dev)
        for seed, e in mine.items():
            assert float(e.get("data-deviation")) == pytest.approx(dev[seed], rel=1e-5, abs=1e-12)
            assert e.get("stroke") == sl.diverging_color(dev[seed], scale)


def test_every_span_is_drawn_and_coloured_by_the_rays_that_meet_it(drawn):
    scene, _, bundles, root = drawn
    spans = _all(root, "sculpt-span")
    glass = scene.objs[0]
    n = len(glass.path[0]["curve"]["points"]) - 1
    m = len(glass.path[2]["curve"]["points"]) - 1
    assert len(spans) == n + m
    coloured = [e for e in spans if e.get("data-deviation") is not None]
    assert coloured and all(e.get("stroke") != sl.NO_VALUE for e in coloured)
    assert all(e.get("stroke") == sl.NO_VALUE for e in spans if e.get("data-deviation") is None)
    assert sum(int(e.get("data-hits")) for e in coloured) == 2 * sum(len(b.counted) for b in bundles.bundles)


def test_isolines_lie_at_equal_s(drawn):
    _, _, bundles, root = drawn
    for b in bundles.bundles:
        isos = [e for e in _all(root, "sculpt-isoline") if e.get("data-bundle-id") == b.bundle_id]
        assert len(isos) >= 5
        spec = b.spec
        for e in isos:
            level = float(e.get("data-level"))
            pts = [tuple(map(float, p.split(","))) for p in e.get("points").split()]
            for q in pts:
                # some ray of the bundle passes through q with S = level there
                best = min(abs(_s_at(spec, r, q) - level) for r in b.counted if _on(spec, r, q))
                assert best < 1e-6


def _segments(spec, r):
    d = r.hits[-1].p_out
    n = math.hypot(*d)
    reach = math.dist(r.exit, spec.target)
    end = (r.exit[0] + reach * d[0] / n, r.exit[1] + reach * d[1] / n)
    return [(spec.source, r.entry, 1.0), (r.entry, r.exit, math.hypot(*r.hits[0].p_out)), (r.exit, end, 1.0)]


def _on(spec, r, q):
    for a, b, _ in _segments(spec, r):
        ab, aq = math.dist(a, b), math.dist(a, q)
        if abs(aq + math.dist(q, b) - ab) < 1e-7:
            return True
    return False


def _s_at(spec, r, q):
    s = 0.0
    for a, b, n in _segments(spec, r):
        if abs(math.dist(a, q) + math.dist(q, b) - math.dist(a, b)) < 1e-7:
            return s + n * math.dist(a, q)
        s += n * math.dist(a, b)
    return math.inf


def test_every_handle_is_drawn_once_with_its_normal_tick(drawn):
    scene, _, _, root = drawn
    groups = _all(root, "sculpt-handle")
    ids = [g.get("data-handle-id") for g in groups]
    expected = {h.handle_id for h in fo.handles(scene, "lens")}
    assert len(ids) == len(set(ids)) and set(ids) == expected
    glass = scene.objs[0]
    for g in groups[::7]:
        edge, index = int(g.get("data-edge")), int(g.get("data-index"))
        line = g.find(f"{SVG}line")
        dx = float(line.get("x2")) - float(line.get("x1"))
        dy = float(line.get("y2")) - float(line.get("y1"))
        nx, ny = fo.outward_normal(glass, fo._span(glass, edge), index)
        assert (dx * nx + dy * ny) / math.hypot(dx, dy) == pytest.approx(1.0, abs=1e-6)


def test_a_preview_shifts_the_deviations_drawn(drawn):
    scene, _, bundles, _ = drawn
    b = bundles.bundles[0]
    seed = next(iter(b.deviations()))
    preview = {b.bundle_id: {seed: 1e-4}}
    renderer = SVGRenderer(width=400, height=400, viewbox=(-1.6, -2.4, 3.2, 4.8))
    sl.draw_sculpt_layer(renderer, scene, bundles=bundles, preview=preview, opl_scale=1e-3, isolines=0)
    root = ET.fromstring(renderer.to_string())
    drawn_dev = {int(e.get("data-seed")): float(e.get("data-deviation")) for e in _all(root, "sculpt-bundle-ray")
                 if e.get("data-bundle-id") == b.bundle_id}
    moved = {s: v + (1e-4 if s == seed else 0.0) for s, v in b.deviations().items()}
    mean = sum(moved.values()) / len(moved)
    for s, v in moved.items():
        assert drawn_dev[s] == pytest.approx(v - mean, rel=1e-5, abs=1e-12)
    assert root.find(f".//{SVG}g[@id='sculpt-bundles']").get("data-opl-scale") == "0.001"


def test_the_scales_and_the_layer_order(drawn):
    _, _, _, root = drawn
    def rgb(c):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    lo, mid, hi = rgb(sl.diverging_color(-1, 1)), rgb(sl.diverging_color(0, 1)), rgb(sl.diverging_color(1, 1))
    assert lo[2] > lo[0] and hi[0] > hi[2] and min(mid) > 240           # blue, near white, red
    assert sl.diverging_color(5, 1) == sl.diverging_color(1, 1)          # clamped
    assert sl.diverging_color(-0.3, 2) == sl.diverging_color(-0.15, 1)   # one scale, symmetric
    assert sl.sequential_color(0.0) == "#440154" and sl.sequential_color(1.0) == "#fde725"
    with pytest.raises(ValueError, match="positive"):
        sl.diverging_color(0.1, 0.0)
    layers = [g.get("id") for g in root.findall(f"{SVG}g")]
    assert layers[-1] == "layer-sculpt"
