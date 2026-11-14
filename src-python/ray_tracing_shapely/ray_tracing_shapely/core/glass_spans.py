"""
Python-specific module: glass spans
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
GLASS SPANS -- one entry per physical surface of a glass outline
===============================================================================
A glass outline (``path``) is a list of points. A straight edge joins two
consecutive points. A circular arc takes three: its start, a point it passes
through (flagged ``'arc': True``), and its end. Counting path entries as edges
therefore counts every arc twice, which is what the analysis layer used to do.

A path entry may also carry a ``curve`` descriptor (core.glass_curves): the
edge from it to the next entry is then an exact conic, asphere or spline, a
span of kind ``"conic"``, ``"asphere"`` or ``"spline"`` that delegates its
geometry to the curve.

A span is one physical surface: a straight edge, a whole arc, or a curve edge. Spans are
numbered in path order, starting from the first entry that is not an arc's
through-point. For an outline with no arcs, span ``i`` is exactly edge ``i``
(path entry ``i`` to ``i+1``), so nothing changes for straight glass.

The grouping rule and the arc's extent are the simulator's own
(``Glass.check_ray_intersects`` and ``Glass._point_is_on_arc``): an entry
followed by an arc-flagged entry starts an arc through that entry to the one
after; the arc is the part of the circle on the through-point's side of the
chord. Collinear arc points degrade to a straight span, as in the simulator.

Pure geometry on plain floats: no Shapely, no scene objects, so ``BaseGlass``
can depend on it without an import cycle.
===============================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .glass_curves import Curve, curve_from_descriptor

XY = Tuple[float, float]

#: Default maximum distance between an arc and the polyline that stands in
#: for it (scene units), used wherever an arc has to be drawn or tested as
#: straight pieces.
DEFAULT_MAX_SAG = 1e-5


def _circle_through(a: XY, b: XY, c: XY) -> Optional[Tuple[XY, float]]:
    """Centre and radius of the circle through three points, or None if collinear."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    scale = max(abs(ax), abs(ay), abs(bx), abs(by), abs(cx), abs(cy), 1.0)
    if abs(d) <= 1e-12 * scale * scale:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


@dataclass(frozen=True)
class GlassSpan:
    """One physical surface of a glass outline: a straight edge, a circular arc, or a
    conic, asphere or spline edge (``shape``, a core.glass_curves.Curve).

    Attributes:
        index: The span number (the edge index the analysis layer reports).
        kind: ``"line"``, ``"arc"``, ``"conic"``, ``"asphere"`` or ``"spline"``.
        path_indices: The path entries the span is built from: two for a
            line, three (start, through-point, end) for an arc.
        start: First point, in path order.
        end: Last point, in path order.
        through: For an arc, the flagged point it passes through.
        center: For an arc, its circle's centre.
        radius: For an arc, its circle's radius.
        direction: For an arc, +1 if it runs counter-clockwise from start to
            end, -1 if clockwise.
        sweep: For an arc, the angle it spans, in radians (0, 2*pi).
        shape: For a conic, asphere or spline span, the curve, traversed from start
            to end.
    """

    index: int
    kind: str
    path_indices: Tuple[int, ...]
    start: XY
    end: XY
    through: Optional[XY] = None
    center: Optional[XY] = None
    radius: Optional[float] = None
    direction: int = 0
    sweep: float = 0.0
    shape: Optional[Curve] = None

    @property
    def is_arc(self) -> bool:
        return self.kind == "arc"

    @property
    def is_freeform(self) -> bool:
        """A conic or spline edge: geometry from ``shape``."""
        return self.shape is not None

    @property
    def is_curved(self) -> bool:
        """Anything but a straight edge: an arc, a conic or a spline."""
        return self.kind != "line"

    @property
    def scale(self) -> float:
        """A length scale for tolerances: an arc's radius, a curve's size, a line's length."""
        if self.is_arc:
            return self.radius
        if self.is_freeform:
            return self.shape.size
        return self.length

    @property
    def length(self) -> float:
        """Length along the surface (arc length for an arc or curve)."""
        if self.is_arc:
            return self.radius * self.sweep
        if self.is_freeform:
            return self.shape.length
        return math.dist(self.start, self.end)

    def _start_angle(self) -> float:
        return math.atan2(self.start[1] - self.center[1], self.start[0] - self.center[0])

    def point_at(self, fraction: float) -> XY:
        """The point a given fraction of the way along the surface (0 = start, 1 = end)."""
        if self.is_freeform:
            return self.shape.point(self.shape.param_at(fraction))
        if not self.is_arc:
            return (self.start[0] + fraction * (self.end[0] - self.start[0]),
                    self.start[1] + fraction * (self.end[1] - self.start[1]))
        angle = self._start_angle() + self.direction * fraction * self.sweep
        return (self.center[0] + self.radius * math.cos(angle),
                self.center[1] + self.radius * math.sin(angle))

    @property
    def midpoint(self) -> XY:
        """The point halfway along the surface (on the curve, for an arc)."""
        return self.point_at(0.5)

    def normal_at(self, point: XY) -> XY:
        """A unit normal at the point of the surface nearest ``point``.

        Unoriented: for a line or a curve, the left normal of the direction of
        travel; for an arc, the radial direction away from the centre. Orient
        it with the owning glass (see
        ``analysis.glass_geometry.edge_outward_normal``).
        """
        if self.is_freeform:
            return self.shape.left_normal(self.shape.nearest(point)[1])
        if not self.is_arc:
            dx, dy = self.end[0] - self.start[0], self.end[1] - self.start[1]
            length = math.hypot(dx, dy)
            if length == 0.0:
                return (0.0, 0.0)
            return (-dy / length, dx / length)
        _, s = self.locate(point)
        px, py = self.point_at(s / self.length if self.length else 0.0)
        return ((px - self.center[0]) / self.radius, (py - self.center[1]) / self.radius)

    def locate(self, point: XY) -> Tuple[float, float]:
        """Distance from ``point`` to the surface, and how far along it the nearest point is.

        Returns:
            ``(distance, s)``: ``s`` is measured along the surface from
            ``start``, in scene units, in ``[0, length]``.
        """
        if self.is_freeform:
            dist, p = self.shape.nearest(point)
            return dist, self.shape.arc_length_to(p)
        if not self.is_arc:
            sx, sy = self.start
            dx, dy = self.end[0] - sx, self.end[1] - sy
            length2 = dx * dx + dy * dy
            if length2 == 0.0:
                return math.dist(point, self.start), 0.0
            t = max(0.0, min(1.0, ((point[0] - sx) * dx + (point[1] - sy) * dy) / length2))
            nearest = (sx + t * dx, sy + t * dy)
            return math.dist(point, nearest), t * math.sqrt(length2)
        angle = math.atan2(point[1] - self.center[1], point[0] - self.center[0])
        t = (self.direction * (angle - self._start_angle())) % (2.0 * math.pi)
        if t <= self.sweep:
            return abs(math.dist(point, self.center) - self.radius), self.radius * t
        to_start, to_end = math.dist(point, self.start), math.dist(point, self.end)
        return (to_start, 0.0) if to_start <= to_end else (to_end, self.length)

    def intersect_segment(self, a: XY, b: XY, tol: float = 1e-9) -> List[XY]:
        """Points where the segment ``a``-``b`` meets this surface, exactly.

        A segment that ends on the surface counts (within ``tol``), which is
        how a traced ray segment meets the surface it hit. For an arc this is
        solved against the circle, not a polyline: a densified arc lies
        slightly inside a convex curve, so a segment ending on the true curve
        would miss it.

        Returns:
            The meeting points, nearest ``a`` first (empty if none).
        """
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg_len = math.hypot(dx, dy)
        if seg_len == 0.0:
            return [a] if self.locate(a)[0] <= tol else []
        slack = tol / seg_len
        if self.is_freeform:
            hits = []
            p_slack = tol / max(self.shape.size, 1e-300)
            for t, p in self.shape.line_hits(a, (dx, dy), slack=p_slack):
                if -slack <= t <= 1 + slack:
                    q = (a[0] + t * dx, a[1] + t * dy)
                    if q not in hits:
                        hits.append(q)
            return hits
        if not self.is_arc:
            ex, ey = self.end[0] - self.start[0], self.end[1] - self.start[1]
            denom = dx * ey - dy * ex
            if denom == 0.0:
                return []
            wx, wy = self.start[0] - a[0], self.start[1] - a[1]
            t = (wx * ey - wy * ex) / denom
            u = (wx * dy - wy * dx) / denom
            edge_slack = tol / max(math.hypot(ex, ey), 1e-300)
            if -slack <= t <= 1 + slack and -edge_slack <= u <= 1 + edge_slack:
                return [(a[0] + t * dx, a[1] + t * dy)]
            return []
        fx, fy = a[0] - self.center[0], a[1] - self.center[1]
        qa = dx * dx + dy * dy
        qb = 2.0 * (fx * dx + fy * dy)
        qc = fx * fx + fy * fy - self.radius * self.radius
        disc = qb * qb - 4.0 * qa * qc
        if disc < 0.0:
            return []
        root = math.sqrt(disc)
        hits = []
        for t in sorted(((-qb - root) / (2.0 * qa), (-qb + root) / (2.0 * qa))):
            if -slack <= t <= 1 + slack:
                p = (a[0] + t * dx, a[1] + t * dy)
                if self.locate(p)[0] <= tol and p not in hits:
                    hits.append(p)
        return hits

    @property
    def curve(self) -> Dict[str, Any]:
        """The exact shape, as ``profile.json``'s ``spans[].curve`` descriptor."""
        if self.is_freeform:
            return self.shape.descriptor()
        if not self.is_arc:
            return {"type": "line"}
        return {"type": "circle", "center": [self.center[0], self.center[1]], "radius": self.radius}

    def samples(self, count: int) -> List[XY]:
        """``count`` points at equal steps along the surface, both end points exact."""
        if count < 2:
            raise ValueError(f"a span needs at least 2 samples, got {count}")
        pts = [self.point_at(k / (count - 1)) for k in range(count)]
        pts[0], pts[-1] = self.start, self.end
        return pts

    def outward_normal_at(self, point: XY) -> XY:
        """The unit normal pointing out of a counter-clockwise outline this span belongs to.

        The interior of a counter-clockwise outline lies to the left of travel,
        so the outward normal is to the right: for a line, the right normal of
        start->end; for an arc, the radial direction times its turning
        direction (away from the centre on a counter-clockwise arc, towards it
        on a clockwise one); for a curve, the right normal of travel.
        """
        nx, ny = self.normal_at(point)
        if self.is_arc:
            return (self.direction * nx, self.direction * ny)
        return (-nx, -ny)

    def piece(self, f0: float, f1: float) -> "GlassSpan":
        """The part of this span between fractions ``f0 < f1`` of the way along it."""
        start, end = self.point_at(f0), self.point_at(f1)
        if f0 == 0.0:
            start = self.start
        if f1 == 1.0:
            end = self.end
        if self.is_freeform:
            shape = self.shape.with_domain(self.shape.param_at(f0), self.shape.param_at(f1))
            return GlassSpan(self.index, self.kind, self.path_indices, start, end, shape=shape)
        if not self.is_arc:
            return GlassSpan(self.index, "line", self.path_indices, start, end)
        return GlassSpan(self.index, "arc", self.path_indices, start, end,
                         self.point_at(0.5 * (f0 + f1)), self.center, self.radius,
                         self.direction, (f1 - f0) * self.sweep)

    def coords(self, max_sag: float = DEFAULT_MAX_SAG) -> List[XY]:
        """The surface as a polyline, start and end included.

        A line is its two end points. An arc or a curve is divided so that no
        chord strays further than ``max_sag`` from it.
        """
        if self.is_freeform:
            pts = self.shape.coords(max_sag)
            pts[0], pts[-1] = self.start, self.end
            return pts
        if not self.is_arc:
            return [self.start, self.end]
        ratio = max(-1.0, min(1.0, 1.0 - max_sag / self.radius))
        step = 2.0 * math.acos(ratio) if ratio < 1.0 else self.sweep
        count = max(2, int(math.ceil(self.sweep / max(step, 1e-12))))
        pts = [self.point_at(k / count) for k in range(count + 1)]
        pts[0], pts[-1] = self.start, self.end
        return pts


def _xy(entry: Dict[str, Any]) -> XY:
    return (float(entry["x"]), float(entry["y"]))


def glass_spans(path: Sequence[Dict[str, Any]]) -> List[GlassSpan]:
    """Group a glass path into its physical surfaces.

    Args:
        path: The glass's ``path``: dicts with ``x``, ``y`` and an optional
            ``arc`` flag.

    Returns:
        One ``GlassSpan`` per surface, numbered in path order. Empty for an
        empty path.

    Raises:
        ValueError: For a curve entry whose end points are not on its curve.
    """
    n = len(path) if path else 0
    spans: List[GlassSpan] = []
    for i in range(n):
        if path[i].get("arc", False):
            continue  # an arc's through-point belongs to the arc that starts before it
        j = (i + 1) % n
        desc = path[i].get("curve")
        if desc:
            if path[j].get("arc", False):
                raise ValueError(f"path entry {i} starts a curve edge, so entry {j} cannot be "
                                 "an arc's through-point.")
            start, end = _xy(path[i]), _xy(path[j])
            shape = curve_from_descriptor(desc, start, end)
            spans.append(GlassSpan(len(spans), shape.kind, (i, j), start, end, shape=shape))
            continue
        if path[j].get("arc", False):
            k = (i + 2) % n
            start, through, end = _xy(path[i]), _xy(path[j]), _xy(path[k])
            circle = _circle_through(start, through, end)
            if circle is None:
                spans.append(GlassSpan(len(spans), "line", (i, j, k), start, end))
                continue
            center, radius = circle
            a_start = math.atan2(start[1] - center[1], start[0] - center[0])
            a_through = math.atan2(through[1] - center[1], through[0] - center[0])
            a_end = math.atan2(end[1] - center[1], end[0] - center[0])
            ccw_to_end = (a_end - a_start) % (2.0 * math.pi)
            ccw_to_through = (a_through - a_start) % (2.0 * math.pi)
            if ccw_to_through <= ccw_to_end:
                direction, sweep = 1, ccw_to_end
            else:
                direction, sweep = -1, 2.0 * math.pi - ccw_to_end
            spans.append(GlassSpan(len(spans), "arc", (i, j, k), start, end, through,
                                   center, radius, direction, sweep))
        else:
            spans.append(GlassSpan(len(spans), "line", (i, j), _xy(path[i]), _xy(path[j])))
    return spans


def outline_coords(path: Sequence[Dict[str, Any]], max_sag: float = DEFAULT_MAX_SAG) -> List[XY]:
    """The closed outline as one ring of points (first point not repeated), arcs densified."""
    ring: List[XY] = []
    for span in glass_spans(path):
        ring.extend(span.coords(max_sag)[:-1])
    return ring


__all__ = ["GlassSpan", "glass_spans", "outline_coords", "DEFAULT_MAX_SAG"]
