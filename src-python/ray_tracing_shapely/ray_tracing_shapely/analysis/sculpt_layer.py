"""
Python-specific module: sculpt layer -- flux tubes, edge bundles and handles drawn over a scene
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
PYTHON-SPECIFIC MODULE: sculpt layer
===============================================================================
What a person sculpting a design looks at, drawn as one more layer of an
`SVGRenderer`'s drawing (``layer-sculpt``, above the others):

- **Tubes** (`flux_tubes.TubeSet`): each a band between its two boundary rays,
  from the source to the receiver, filled by Map B (the share of its light
  delivered) on a sequential scale, 0 to 1.
- **Bundle rays** (`edge_bundles.BundleSet`): each a thin line from its source
  to its entry, its exit, and on along its own direction as far as the target
  is from the exit (so a miss shows), coloured by Map A (its S minus the
  bundle's mean) on a diverging scale centred on 0: blue shorter than the
  mean, red longer. The scale is symmetric and given by the caller
  (`opl_scale`), so that one kept for a session keeps colours comparable
  across edits; `opl_scale_for` gives one from a bundle set.
- **Surface spans**: each span of a bundle's entrance and exit edges (between
  two designed points) drawn over the outline, coloured by the mean Map A of
  the bundle rays that meet it; a span no ray meets is drawn grey.
- **Wavefront isolines**: per bundle, lines of equal S across its rays, at
  levels evenly spaced between where the last ray enters the glass and where
  the first reaches the target's distance.
- **Handles** (`first_order.handles`): a marker at each interior Hermite
  point of the glass's spline edges, with a tick along the glass's outward
  normal, the way a ``"position"`` move pushes it.

Every element carries what it stands for (`KB6`): ``data-tube-id``,
``data-bundle-id`` with ``data-seed``, ``data-glass`` with ``data-edge`` and
``data-span``, ``data-handle-id``; and the value its colour shows
(``data-delivered-fraction``, ``data-deviation``, ``data-level``), so a caller
that cannot see the colours reads the numbers.

A preview (`edge_bundles.predict`'s changes, per bundle and seed) can be given
to draw the bundles as the edit would leave them, at first order, on the same
scale.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

XY = Tuple[float, float]

#: Map A's diverging scale: blue (shorter than the mean), near white, red (longer).
_DIVERGING = ((33, 102, 172), (247, 247, 247), (178, 24, 43))
#: Map B's sequential scale, 0 to 1 (viridis stops).
_SEQUENTIAL = ((68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37))
#: A span no ray meets.
NO_VALUE = "#a0aec0"


def _hex(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _ramp(stops: Sequence[Sequence[int]], t: float) -> str:
    t = min(max(t, 0.0), 1.0) * (len(stops) - 1)
    k = min(int(t), len(stops) - 2)
    u = t - k
    return _hex([a + (b - a) * u for a, b in zip(stops[k], stops[k + 1])])


def diverging_color(value: float, scale: float) -> str:
    """Map A's colour of a deviation, on a symmetric scale of half-range ``scale``."""
    if scale <= 0:
        raise ValueError(f"the Map A scale must be positive, got {scale}")
    return _ramp(_DIVERGING, 0.5 + 0.5 * value / scale)


def sequential_color(fraction: float) -> str:
    """Map B's colour of a delivered fraction, 0 to 1."""
    return _ramp(_SEQUENTIAL, fraction)


def opl_scale_for(bundle_set: Any) -> float:
    """A Map A scale for a session: the largest deviation of the bundle set (or 1e-12, if none)."""
    dev = [abs(v) for b in bundle_set.bundles for v in b.deviations().values()]
    return max(dev, default=0.0) or 1e-12


def _pt(p: XY) -> XY:
    return (round(p[0], 9), round(p[1], 9))


def _layer(renderer: Any) -> Any:
    if not hasattr(renderer, "layer_sculpt"):
        renderer.layer_sculpt = renderer.dwg.add(renderer.dwg.g(
            id="layer-sculpt", transform="scale(1, -1)",
            **{"inkscape:groupmode": "layer", "inkscape:label": "Sculpt"}))
    return renderer.layer_sculpt


def _pixel(renderer: Any) -> float:
    return renderer.user_viewbox[2] / renderer.width


# --- tubes --------------------------------------------------------------------------------


def _ray_line(seed: Any, arrival: Any) -> List[XY]:
    return [tuple(seed.p)] + [tuple(h.point) for h in arrival.hits] + [tuple(arrival.point)]


def _draw_tubes(renderer: Any, group: Any, tube_set: Any, px: float) -> None:
    """One group per tube; in it, per route its rays take, a band between the route's first and
    last rays (a lone ray: a line). A band across two routes would cover where no light went."""
    from .flux_tubes import route_text  # noqa: PLC0415
    dwg = renderer.dwg
    for t in tube_set.tubes:
        best: Dict[int, Any] = {}
        for a in t.arrivals:
            if a.seed not in best or a.power > best[a.seed].power:
                best[a.seed] = a
        color = sequential_color(t.delivered_fraction)
        g = group.add(dwg.g(class_="sculpt-tube"))
        g["data-tube-id"] = t.tube_id
        g["data-source"] = t.source_label
        g["data-delivered-fraction"] = f"{t.delivered_fraction:.6g}"
        g["data-power-fraction"] = f"{t.power_fraction:.6g}"
        by_route: Dict[Any, List[int]] = {}
        for seed in sorted(best):
            by_route.setdefault(best[seed].route, []).append(seed)
        shares = dict(t.routes)
        for route, seeds in by_route.items():
            first, last = _ray_line(t.seeds[seeds[0]], best[seeds[0]]), _ray_line(t.seeds[seeds[-1]], best[seeds[-1]])
            if len(seeds) > 1:
                el = dwg.polygon([_pt(p) for p in first + last[::-1]], fill=color, fill_opacity=0.35,
                                 stroke=color, stroke_width=0.6 * px, stroke_opacity=0.8)
            else:
                el = dwg.polyline([_pt(p) for p in first], fill="none", stroke=color, stroke_width=1.0 * px)
            el["class"] = "sculpt-tube-route"
            el["data-tube-id"] = t.tube_id
            el["data-route"] = route_text(route)
            el["data-route-share"] = f"{shares.get(route, 0.0):.6g}"
            el["data-rays"] = str(len(seeds))
            g.add(el)


# --- bundles ------------------------------------------------------------------------------


def _bundle_line(spec: Any, ray: Any) -> Tuple[List[XY], List[float]]:
    """The drawn path of a bundle ray and S at each of its vertices."""
    out_dir = ray.hits[-1].p_out
    n_out = math.hypot(*out_dir)
    d = (out_dir[0] / n_out, out_dir[1] / n_out)
    reach = math.dist(ray.exit, spec.target)
    end = (ray.exit[0] + reach * d[0], ray.exit[1] + reach * d[1])
    pts = [tuple(spec.source), tuple(ray.entry), tuple(ray.exit), end]
    s_exit = ray.opl - spec.target_index * reach
    s_entry = math.hypot(*ray.hits[0].p_in) * math.dist(spec.source, ray.entry)
    return pts, [0.0, s_entry, s_exit, ray.opl]


def _at_level(pts: List[XY], s: List[float], level: float) -> Optional[XY]:
    for (a, sa), (b, sb) in zip(zip(pts, s), zip(pts[1:], s[1:])):
        if sa <= level <= sb and sb > sa:
            u = (level - sa) / (sb - sa)
            return (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]))
    return None


def _spans_of(curve: Any, point: XY) -> int:
    _, p = curve.nearest(point)
    return min(int(p), len(curve.points) - 2)


def _draw_bundles(renderer: Any, group: Any, scene: Any, bundle_set: Any, scale: float, px: float,
                  preview: Optional[Dict[str, Dict[int, float]]], isolines: int) -> None:
    from .edge_bundles import _glass, _spline  # noqa: PLC0415
    dwg = renderer.dwg
    span_values: Dict[Tuple[str, int, int], List[float]] = {}
    curves: Dict[Tuple[str, int], Any] = {}
    for b in bundle_set.bundles:
        spec = b.spec
        dev = b.deviations()
        if preview and spec.bundle_id in preview:
            change = preview[spec.bundle_id]
            moved = {s: v + change.get(s, 0.0) for s, v in dev.items()}
            mean = sum(moved.values()) / len(moved) if moved else 0.0
            dev = {s: v - mean for s, v in moved.items()}
        g = group.add(dwg.g(class_="sculpt-bundle"))
        g["data-bundle-id"] = spec.bundle_id
        glass = _glass(scene, spec.glass)
        for edge in (spec.entrance, spec.exit):
            curves.setdefault((spec.glass, edge), _spline(glass, edge))
        lines = []
        for r in b.counted:
            pts, s = _bundle_line(spec, r)
            lines.append((r.aim, pts, s))
            line = dwg.polyline([_pt(p) for p in pts], fill="none", stroke=diverging_color(dev[r.seed], scale),
                                stroke_width=1.0 * px)
            line["class"] = "sculpt-bundle-ray"
            line["data-bundle-id"] = spec.bundle_id
            line["data-seed"] = str(r.seed)
            line["data-deviation"] = f"{dev[r.seed]:.6g}"
            if r.miss is not None:
                line["data-miss"] = f"{r.miss:.6g}"
            g.add(line)
            for edge, point in ((spec.entrance, r.entry), (spec.exit, r.exit)):
                k = _spans_of(curves[(spec.glass, edge)], point)
                span_values.setdefault((spec.glass, edge, k), []).append(dev[r.seed])
        if lines and isolines > 0:
            lines.sort(key=lambda x: x[0])
            lo = max(x[2][1] for x in lines)
            hi = min(x[2][3] for x in lines)
            for q in range(1, isolines + 1):
                level = lo + (hi - lo) * q / (isolines + 1)
                runs: List[List[XY]] = [[]]
                for _, pts, s in lines:
                    p = _at_level(pts, s, level)
                    if p is None:
                        if runs[-1]:
                            runs.append([])
                    else:
                        runs[-1].append(p)
                for run in runs:
                    if len(run) < 2:
                        continue
                    iso = dwg.polyline([_pt(p) for p in run], fill="none", stroke="#4a5568",
                                       stroke_width=0.7 * px, stroke_dasharray=f"{3 * px:.6g} {2 * px:.6g}")
                    iso["class"] = "sculpt-isoline"
                    iso["data-bundle-id"] = spec.bundle_id
                    iso["data-level"] = f"{level:.9g}"
                    g.add(iso)
    for (glass, edge), curve in curves.items():
        for k in range(len(curve.points) - 1):
            values = span_values.get((glass, edge, k))
            pts = [curve.point(k + u / 8) for u in range(9)]
            color = diverging_color(sum(values) / len(values), scale) if values else NO_VALUE
            piece = dwg.polyline([_pt(p) for p in pts], fill="none", stroke=color,
                                 stroke_width=(3.0 if values else 1.5) * px, stroke_linecap="round")
            piece["class"] = "sculpt-span"
            piece["data-glass"] = glass
            piece["data-edge"] = str(edge)
            piece["data-span"] = str(k)
            if values:
                piece["data-deviation"] = f"{sum(values) / len(values):.6g}"
                piece["data-hits"] = str(len(values))
            group.add(piece)


# --- handles ------------------------------------------------------------------------------


def _draw_handles(renderer: Any, group: Any, scene: Any, glass: str, px: float, tick: Optional[float]) -> None:
    from . import first_order as fo  # noqa: PLC0415
    dwg = renderer.dwg
    obj = fo._glass(scene, glass)
    seen = set()
    for h in fo.handles(scene, glass, kinds=("position",)):
        if (h.edge, h.index) in seen:
            continue
        seen.add((h.edge, h.index))
        span = fo._span(obj, h.edge)
        p = tuple(obj.path[span.path_indices[0]]["curve"]["points"][h.index])
        nx, ny = fo.outward_normal(obj, span, h.index)
        length = tick if tick is not None else 10 * px
        g = group.add(dwg.g(class_="sculpt-handle"))
        g["data-handle-id"] = h.handle_id
        g["data-glass"] = glass
        g["data-edge"] = str(h.edge)
        g["data-index"] = str(h.index)
        g.add(dwg.line(start=_pt(p), end=_pt((p[0] + length * nx, p[1] + length * ny)), stroke="#2d3748",
                       stroke_width=0.8 * px))
        g.add(dwg.circle(center=_pt(p), r=2.5 * px, fill="white", stroke="#2d3748", stroke_width=0.8 * px))


# --- the layer ----------------------------------------------------------------------------


def draw_sculpt_layer(renderer: Any, scene: Any, *, tubes: Any = None, bundles: Any = None,
                      handles_of: Optional[str] = None, opl_scale: Optional[float] = None,
                      preview: Optional[Dict[str, Dict[int, float]]] = None, isolines: int = 5,
                      tick_length: Optional[float] = None, pixel: Optional[float] = None,
                      preview_outline: Optional[Sequence[XY]] = None, trusted: bool = True) -> Any:
    """Draw the sculpt layer onto ``renderer`` (an `SVGRenderer`), above its other layers.

    Args:
        renderer: The drawing; its view gives one screen pixel, unless ``pixel`` does.
        scene: The scene the tubes, bundles and handles are of.
        tubes: A `flux_tubes.TubeSet`, drawn as bands by Map B.
        bundles: An `edge_bundles.BundleSet`, drawn by Map A, with its surface spans and isolines.
        handles_of: The name of a glass whose handles to draw.
        opl_scale: Map A's half-range; `opl_scale_for(bundles)` if not given. Keep one for a session.
        preview: Per bundle and seed, a first-order change of S (`edge_bundles.predict`) to draw
            the bundles with.
        isolines: Wavefront isolines per bundle (0: none).
        tick_length: The handles' normal ticks, in scene units (ten pixels, if not given).
        pixel: One screen pixel in scene units: the strokes' width unit.
        preview_outline: The outline an edit being previewed would give, drawn dashed.
        trusted: Whether the preview is within its first-order limit. If not, the previewed
            bundles and outline are marked ``sculpt-untrusted`` (a view fades them).

    Returns:
        The layer's group.
    """
    px = pixel if pixel is not None else _pixel(renderer)
    layer = _layer(renderer)
    if tubes is not None:
        _draw_tubes(renderer, layer.add(renderer.dwg.g(id="sculpt-tubes")), tubes, px)
    if bundles is not None:
        scale = opl_scale if opl_scale is not None else opl_scale_for(bundles)
        group = layer.add(renderer.dwg.g(id="sculpt-bundles"))
        group["data-opl-scale"] = f"{scale:.6g}"
        if preview is not None:
            group["data-preview"] = "true"
            if not trusted:
                group["class"] = "sculpt-untrusted"
        _draw_bundles(renderer, group, scene, bundles, scale, px, preview, isolines)
    if preview_outline is not None:
        line = renderer.dwg.polygon([_pt(p) for p in preview_outline], fill="none", stroke="#d69e2e",
                                    stroke_width=1.5 * px, stroke_dasharray=f"{4 * px:.6g} {3 * px:.6g}")
        line["class"] = "sculpt-preview-outline" + ("" if trusted else " sculpt-untrusted")
        line["data-trusted"] = "true" if trusted else "false"
        layer.add(line)
    if handles_of is not None:
        _draw_handles(renderer, layer.add(renderer.dwg.g(id="sculpt-handles")), scene, handles_of, px,
                      tick_length)
    return layer


__all__ = ["NO_VALUE", "diverging_color", "draw_sculpt_layer", "opl_scale_for", "sequential_color"]
