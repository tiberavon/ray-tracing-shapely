"""
Python-specific module: first order -- what a small move of a designed surface does, untraced
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
PYTHON-SPECIFIC MODULE: first order
===============================================================================
A designed surface is a spline edge: Hermite points with their tangents
(`core.glass_curves.SplineCurve`). A *handle* is one interior point of it, and
it moves two ways: ``"position"`` moves the point by delta along the glass's
outward normal there (scene units); ``"normal"`` turns its tangent by delta
degrees, counter-clockwise. The end points of an edge are not handles: they
are the outline's vertices, shared with the next edge.

**How the curve moves.** Moving point i, or turning its tangent, changes the
two spans that meet at it; and since each span's tangents are scaled by its
chord, moving the point also rescales them. The displacement field is
therefore taken from the curve itself: the derivative, at a hit's parameter,
of `SplineCurve` under the edit (a central difference, its error far below
anything compared here). One formula, the curve's own.

**What a move does to a ray that meets the edge** (`p` is the optical
momentum, unit direction times index; delta x the surface's displacement at
the hit):

- its optical path length changes by ``(p_in - p_out) . delta x`` (Fermat:
  the path is stationary, so the ray's own deflection enters only at second
  order). Snell's law conserves the tangential momentum, so only the normal
  part of the displacement counts. This is S at the ray's *old* end point:
  where the moved ray now crosses the receiver, S differs further by its
  momentum there times the shift (the gradient of S is p);
- its outgoing direction turns by ``dphi * (1 - n1 cos t1 / (n2 cos t2))`` for
  a refraction and ``2 dphi`` for a reflection, where dphi is the turn of the
  surface's normal *where the ray now meets it*: the turn at the hit's
  parameter, plus the curvature times the parameter shift of the new hit
  point (the ray meets the moved surface a little along its own direction).

Nothing is traced. The estimate holds for small moves only:
`drag_ratio` is the move over the shorter adjacent chord (for a turn, the
angle in radians), and past `PREVIEW_LIMIT` a view should stop trusting it
and ask for a release, which re-traces (`flux_tubes.replay`). The bound
measured for the estimate's error against a re-trace is stated in
`C-SCULPT-02`.
===============================================================================
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from .flux_tubes import Arrival, SurfaceHit, TubeSet

XY = Tuple[float, float]

#: The kinds of move a handle makes.
KINDS = ("position", "normal")
#: Past this drag ratio the first-order estimate is not to be trusted (`drag_ratio`).
PREVIEW_LIMIT = 0.02
#: The central difference's step, relative to the shorter adjacent chord (position) or in degrees.
_STEP = 1e-6


class FirstOrderError(ValueError):
    """A handle or a move the estimate cannot be made for, with the reason."""


@dataclass(frozen=True)
class Handle:
    """One interior Hermite point of a glass's spline edge, and how it moves.

    Attributes:
        glass: The glass's name.
        edge: The edge index (as routes count edges).
        index: The point's index in the edge's spline.
        kind: ``"position"`` (along the outward normal, scene units) or ``"normal"`` (the tangent
            turned counter-clockwise, degrees).
        label: The edge's functional label, if the glass has one (``"N"``); else its index.
    """

    glass: str
    edge: int
    index: int
    kind: str
    label: str = ""

    @property
    def handle_id(self) -> str:
        return f"{self.glass}/{self.label or self.edge}/{self.index}"


@dataclass(frozen=True)
class HitChange:
    """The first-order change at one hit of the moved edge, per unit of the handle's move."""

    point: XY
    displacement: XY
    dopl: float
    dphi: float
    dtheta: float


@dataclass(frozen=True)
class ArrivalChange:
    """The first-order change of one arrival for a move ``delta``."""

    seed: int
    dopl: float
    hits: Tuple[HitChange, ...]


# --- the edge -----------------------------------------------------------------------------


def _glass(scene: Any, name: str) -> Any:
    found = [o for o in scene.objs if o.name == name]
    if not found:
        raise FirstOrderError(f"no object named {name!r}")
    if not getattr(found[0], "path", None):
        raise FirstOrderError(f"{name!r} is a {type(found[0]).__name__}, not a glass with an outline")
    return found[0]


def _span(glass: Any, edge: int) -> Any:
    from ..core.glass_spans import glass_spans  # noqa: PLC0415
    spans = [s for s in glass_spans(glass.path) if s.index == edge]
    if not spans:
        raise FirstOrderError(f"{glass.name!r} has no edge {edge}")
    if spans[0].kind != "spline":
        raise FirstOrderError(f"edge {edge} of {glass.name!r} is a {spans[0].kind}, not a spline: it has no handles")
    return spans[0]


def _label(glass: Any, edge: int) -> str:
    """The edge's functional label (``"X"``, `KA1`), else its edge label, else ""."""
    for labels in (getattr(glass, "_functional_labels", None), getattr(glass, "edge_labels", None)):
        entry = labels.get(edge) if isinstance(labels, dict) else None
        if isinstance(entry, (tuple, list)) and entry:
            return str(entry[0])
    return ""


def handles(scene: Any, glass: str, kinds: Sequence[str] = KINDS) -> List[Handle]:
    """Every handle of a glass's spline edges: its interior points, each in the given kinds."""
    from ..core.glass_spans import glass_spans  # noqa: PLC0415
    obj = _glass(scene, glass)
    out = []
    for span in glass_spans(obj.path):
        if span.kind != "spline":
            continue
        n = len(obj.path[span.path_indices[0]]["curve"]["points"])
        for i in range(1, n - 1):
            for kind in kinds:
                out.append(Handle(glass, span.index, i, kind, _label(obj, span.index)))
    return out


def _check(handle: Handle, desc: Dict[str, Any]) -> None:
    if handle.kind not in KINDS:
        raise FirstOrderError(f"a handle moves by {' or '.join(KINDS)}, not {handle.kind!r}")
    n = len(desc["points"])
    if not 1 <= handle.index <= n - 2:
        raise FirstOrderError(f"point {handle.index} of a {n}-point edge is not interior: an end point is the "
                              f"outline's vertex, not a handle (handles are 1 to {n - 2})")


def _orientation(glass: Any) -> float:
    pts = [(v["x"], v["y"]) for v in glass.path]
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    return 1.0 if area > 0 else -1.0


def outward_normal(glass: Any, span: Any, index: int) -> XY:
    """The glass's outward unit normal at point ``index`` of a spline edge."""
    desc = glass.path[span.path_indices[0]]["curve"]
    tx, ty = desc["tangents"][index]
    length = math.hypot(tx, ty)
    s = span.shape.sense
    tx, ty = s * tx / length, s * ty / length                 # along the outline's travel
    k = _orientation(glass)                                   # counter-clockwise: outward is to the right
    return (k * ty, -k * tx)


def edited_descriptor(glass: Any, span: Any, handle: Handle, delta: float) -> Dict[str, Any]:
    """The edge's spline descriptor with the handle moved by ``delta``."""
    desc = copy.deepcopy(glass.path[span.path_indices[0]]["curve"])
    _check(handle, desc)
    i = handle.index
    if handle.kind == "position":
        nx, ny = outward_normal(glass, span, i)
        x, y = desc["points"][i]
        desc["points"][i] = [x + delta * nx, y + delta * ny]
    else:
        tx, ty = desc["tangents"][i]
        a = math.radians(delta)
        desc["tangents"][i] = [tx * math.cos(a) - ty * math.sin(a), tx * math.sin(a) + ty * math.cos(a)]
    return desc


def edited_path(scene: Any, handle: Handle, delta: float) -> List[Dict[str, Any]]:
    """The glass's path with the handle moved by ``delta``: what a re-trace is made on."""
    glass = _glass(scene, handle.glass)
    span = _span(glass, handle.edge)
    path = copy.deepcopy(glass.path)
    path[span.path_indices[0]]["curve"] = edited_descriptor(glass, span, handle, delta)
    return path


def drag_ratio(scene: Any, handle: Handle, delta: float) -> float:
    """How large a move is for the estimate: over the shorter adjacent chord, or the angle in radians."""
    glass = _glass(scene, handle.glass)
    span = _span(glass, handle.edge)
    desc = glass.path[span.path_indices[0]]["curve"]
    _check(handle, desc)
    if handle.kind == "normal":
        return abs(math.radians(delta))
    pts = desc["points"]
    i = handle.index
    return abs(delta) / min(math.dist(pts[i - 1], pts[i]), math.dist(pts[i], pts[i + 1]))


# --- the field ----------------------------------------------------------------------------


def _curve(glass: Any, span: Any, desc: Dict[str, Any]) -> Any:
    from ..core.glass_curves import curve_from_descriptor  # noqa: PLC0415
    i, j = span.path_indices[0], span.path_indices[-1]
    return curve_from_descriptor(desc, (glass.path[i]["x"], glass.path[i]["y"]),
                                 (glass.path[j]["x"], glass.path[j]["y"]))


def _cross(a: XY, b: XY) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _dot(a: XY, b: XY) -> float:
    return a[0] * b[0] + a[1] * b[1]


class _Field:
    """The handle's displacement field on its edge, per unit of the handle's move."""

    def __init__(self, scene: Any, handle: Handle) -> None:
        self.glass = _glass(scene, handle.glass)
        self.span = _span(self.glass, handle.edge)
        desc = self.glass.path[self.span.path_indices[0]]["curve"]
        _check(handle, desc)
        if handle.kind == "position":
            pts, i = desc["points"], handle.index
            self.step = _STEP * min(math.dist(pts[i - 1], pts[i]), math.dist(pts[i], pts[i + 1]))
        else:
            self.step = _STEP * 1e3                       # degrees
        self.base = self.span.shape
        self.plus = _curve(self.glass, self.span, edited_descriptor(self.glass, self.span, handle, self.step))
        self.minus = _curve(self.glass, self.span, edited_descriptor(self.glass, self.span, handle, -self.step))

    def at(self, point: XY, p_in: XY, p_out: XY, event: str) -> HitChange:
        _, p = self.base.nearest(point)
        h = 2 * self.step
        a, b = self.plus.point(p), self.minus.point(p)
        dx = ((a[0] - b[0]) / h, (a[1] - b[1]) / h)
        d1 = self.base.deriv(p)
        d2 = self.base.deriv2(p)
        da, db = self.plus.deriv(p), self.minus.deriv(p)
        turn = math.remainder(math.atan2(da[1], da[0]) - math.atan2(db[1], db[0]), 2 * math.pi) / h
        speed2 = _dot(d1, d1)
        nrm = (-d1[1] / math.sqrt(speed2), d1[0] / math.sqrt(speed2))
        n_in = math.hypot(*p_in)
        d_in = (p_in[0] / n_in, p_in[1] / n_in)
        along = _dot(d_in, nrm)
        if abs(along) < 1e-12:                            # grazing: the new hit point is not defined
            raise FirstOrderError(f"a ray grazes {self.glass.name!r} at {point}: no first-order estimate there")
        dt = _dot(dx, nrm) / along                        # how far along itself the ray meets the moved edge
        dp = _dot((dt * d_in[0] - dx[0], dt * d_in[1] - dx[1]), d1) / speed2
        dphi = turn + _cross(d1, d2) / speed2 * dp        # the normal's turn where the ray now meets it
        dopl = _dot((p_in[0] - p_out[0], p_in[1] - p_out[1]), dx)
        return HitChange(point, dx, dopl, dphi, dphi * turn_factor(p_in, p_out, nrm, event))


def turn_factor(p_in: XY, p_out: XY, normal: XY, event: str) -> float:
    """How much the outgoing direction turns per unit turn of the normal, the incoming held.

    ``2`` for a reflection (and total internal reflection); for a refraction
    ``1 - n1 cos t1 / (n2 cos t2)``, the indices being the momenta's lengths.
    """
    if event in ("reflect", "tir"):
        return 2.0
    n1, n2 = math.hypot(*p_in), math.hypot(*p_out)
    c1, c2 = abs(_dot(p_in, normal)) / n1, abs(_dot(p_out, normal)) / n2
    if c2 < 1e-12:
        raise FirstOrderError("a refraction at grazing exit: its turn is unbounded at first order")
    return 1.0 - n1 * c1 / (n2 * c2)


# --- the estimates ------------------------------------------------------------------------


def _on_edge(hit: SurfaceHit, handle: Handle) -> bool:
    return hit.surface == handle.glass and hit.edge == handle.edge


def predict_arrival(field: "_Field", handle: Handle, arrival: Arrival, delta: float) -> ArrivalChange:
    """The first-order change of one arrival's S (at its old end point) for the move ``delta``."""
    changes = tuple(field.at(h.point, h.p_in, h.p_out, h.event) for h in arrival.hits if _on_edge(h, handle))
    return ArrivalChange(arrival.seed, delta * sum(c.dopl for c in changes), changes)


def predict(scene: Any, tube_set: TubeSet, handle: Handle, delta: float) -> Dict[str, List[ArrivalChange]]:
    """Per tube, the first-order change of each of its arrivals for the move ``delta``; nothing traced.

    An arrival that does not meet the handle's edge has no hits in its change and dopl 0.
    """
    field = _Field(scene, handle)
    return {t.tube_id: [predict_arrival(field, handle, a, delta) for a in t.arrivals] for t in tube_set.tubes}


def opl_at_old_end(new: Arrival, old: Arrival) -> float:
    """A re-traced arrival's S brought back to the old arrival's end point, to first order.

    The moved ray crosses the receiver elsewhere; S there differs from S at the old point by the
    momentum times the shift (the gradient of S is p). This is what `predict` estimates.
    """
    shift = (old.point[0] - new.point[0], old.point[1] - new.point[1])
    return new.opl + _dot(new.momentum, shift)


__all__ = ["ArrivalChange", "FirstOrderError", "Handle", "HitChange", "KINDS", "PREVIEW_LIMIT", "drag_ratio",
           "edited_descriptor", "edited_path", "handles", "opl_at_old_end", "outward_normal", "predict",
           "predict_arrival", "turn_factor"]
