"""
Python-specific module: glass curves
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
GLASS CURVES -- exact conic, asphere and spline edges for a glass outline
===============================================================================
A glass ``path`` entry may carry a ``curve`` descriptor: the edge from that
entry to the next one is then this curve, not a straight line. Three kinds:

- ``{"type": "conic", "vertex": [a, b], "axis": [ua, ub], "radius": R,
  "conic": K}``: the conic section ``s**2 - 2 R z + (1 + K) z**2 = 0`` in
  the vertex's frame (z along ``axis``, s to its left), on the branch through
  the vertex, as far as it is single-valued in s. ``R`` is signed: the
  vertex's centre of curvature is at ``vertex + R * axis``. The same
  descriptor and convention as ``ConicMirror``.
- ``{"type": "asphere", "vertex": [a, b], "axis": [ua, ub], "radius": R,
  "conic": K, "coefficients": [A1, A2, ...]}``: the even asphere
  ``z(s) = c s**2 / (1 + sqrt(1 - (1 + K) c**2 s**2)) + A1 s**2 + A2 s**4 + ...``
  with ``c = 1 / R``, in the same frame as the conic. The coefficients start
  at s**2, the order of Zemax's EVENASPH and Optiland's ``even_asphere``, so a
  design's numbers go in unchanged. ``R`` may be ``None``: a flat base, the
  polynomial alone. With no coefficients it is the conic.
- ``{"type": "spline", "points": [[a, b], ...], "tangents": [[ta, tb], ...]}``:
  a cubic Hermite curve through the points with the given unit tangents
  (pointing towards increasing index), each segment's tangents scaled by its
  chord. The tangent, so the normal, is exact at every point: the designer's
  own, not one estimated from neighbours. Between points the curve is the
  cubic; the normal is continuous along it. An optional ``"domain": [p0, p1]``
  restricts the edge to that parameter range (p in [0, n - 1], point k at
  p = k): a piece of a spline, cut anywhere, is the same spline over a
  narrower range, exactly. (Cutting it into a new spline through the cut
  points would not be: the chord scaling of the tangents would change.)

The path entries' own coordinates are the curve's end points; the path may
run along the curve either way.

Everything is exact for the curve the descriptor defines. A line meets a
conic at the roots of a quadratic (the numerically stable form), and a
spline segment at the roots of a cubic, isolated in Bernstein form (a sign
change count bounds the roots in an interval) and refined by safeguarded
Newton steps. An asphere has no closed form. A line is first tested against
the edge's sag bounds, which most lines miss. Within the s range where it is
inside them, its meeting points are bracketed on sub-intervals (at most
``ASPHERE_INTERVALS`` over the whole edge), and where the line's offset from
the curve turns within one, at the turn too, so a line crossing twice inside
a sub-interval is found; then refined by safeguarded Newton. A line that only grazes the edge, crossing twice closer than the
refinement can separate, can be missed: a tangent ray. Arc length, nearest points and sampling at equal steps along
the curve are computed numerically, to rounding.

Pure Python on floats, like core.glass_spans, which builds on it.
===============================================================================
"""

from __future__ import annotations

import bisect
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

XY = Tuple[float, float]

#: How close, relative to the curve's size, a path end point must lie to the curve.
ENDPOINT_TOL = 1e-9
#: Intervals of the arc-length table.
_TABLE_INTERVALS = 512
#: Sub-intervals of an asphere edge searched for a line's meeting points.
ASPHERE_INTERVALS = 32
#: Three-point Gauss-Legendre nodes and weights on [0, 1].
_GL = ((0.5 - math.sqrt(15.0) / 10.0, 5.0 / 18.0), (0.5, 8.0 / 18.0),
       (0.5 + math.sqrt(15.0) / 10.0, 5.0 / 18.0))


def _dot(a: XY, b: XY) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _sub(a: XY, b: XY) -> XY:
    return (a[0] - b[0], a[1] - b[1])


class Curve:
    """A smooth plane curve traversed from parameter ``p_start`` to ``p_end``.

    The parameter may decrease along the traversal (a path that runs the
    curve backwards). Subclasses provide point, first and second derivative
    in the parameter, the meeting points with a line, and the descriptor.
    """

    kind = ""

    def __init__(self, p_start: float, p_end: float) -> None:
        if p_start == p_end:
            raise ValueError("a curve edge needs two different end points.")
        self.p_start = float(p_start)
        self.p_end = float(p_end)
        self._table: Optional[Tuple[List[float], List[float]]] = None
        self._key_cache: Optional[List[float]] = None

    # --- provided by subclasses -------------------------------------------------
    def point(self, p: float) -> XY:
        raise NotImplementedError

    def deriv(self, p: float) -> XY:
        raise NotImplementedError

    def deriv2(self, p: float) -> XY:
        raise NotImplementedError

    def _line_roots(self, origin: XY, direction: XY) -> List[Tuple[float, float]]:
        """``(t, p)`` for every point ``origin + t * direction`` on the whole curve."""
        raise NotImplementedError

    def descriptor(self) -> Dict[str, Any]:
        raise NotImplementedError

    def with_domain(self, p_start: float, p_end: float) -> "Curve":
        raise NotImplementedError

    @property
    def size(self) -> float:
        """A length scale for tolerances."""
        raise NotImplementedError

    # --- shared -------------------------------------------------------------------
    @property
    def lo(self) -> float:
        return min(self.p_start, self.p_end)

    @property
    def hi(self) -> float:
        return max(self.p_start, self.p_end)

    @property
    def sense(self) -> float:
        """+1 if the traversal runs towards increasing parameter, -1 if not."""
        return 1.0 if self.p_end > self.p_start else -1.0

    @property
    def start(self) -> XY:
        return self.point(self.p_start)

    @property
    def end(self) -> XY:
        return self.point(self.p_end)

    def tangent(self, p: float) -> XY:
        """Unit tangent in the direction of travel."""
        dx, dy = self.deriv(p)
        length = math.hypot(dx, dy)
        return (self.sense * dx / length, self.sense * dy / length)

    def left_normal(self, p: float) -> XY:
        """Unit normal to the left of the direction of travel."""
        tx, ty = self.tangent(p)
        return (-ty, tx)

    def line_hits(self, origin: XY, direction: XY, slack: float = 0.0) -> List[Tuple[float, float]]:
        """``(t, p)`` for every point ``origin + t * direction`` on this curve's
        traversed part (parameter within ``slack`` of it), sorted by ``t``."""
        lo, hi = self.lo - slack, self.hi + slack
        hits = [(t, min(max(p, self.lo), self.hi)) for t, p in self._line_roots(origin, direction)
                if lo <= p <= hi]
        return sorted(hits)

    def _speed(self, p: float) -> float:
        dx, dy = self.deriv(p)
        return math.hypot(dx, dy)

    def _breaks(self) -> List[float]:
        """Parameters inside the domain where the derivative may jump (knots)."""
        return []

    def _arc_table(self) -> Tuple[List[float], List[float]]:
        """Parameters along the traversal and the arc length to each.

        Intervals never straddle a break (a spline's knots, where the
        parameter speed jumps), so the Gauss-Legendre rule stays exact to
        rounding on each.
        """
        if self._table is None:
            grid = {self.p_start + (self.p_end - self.p_start) * k / _TABLE_INTERVALS
                    for k in range(_TABLE_INTERVALS + 1)}
            grid.update(b for b in self._breaks() if self.lo < b < self.hi)
            ps = sorted(grid, key=lambda p: (p - self.p_start) * self.sense)
            ss = [0.0]
            for a, b in zip(ps[:-1], ps[1:]):
                h = b - a
                ss.append(ss[-1] + abs(h) * sum(w * self._speed(a + x * h) for x, w in _GL))
            self._table = (ps, ss)
        return self._table

    @property
    def length(self) -> float:
        return self._arc_table()[1][-1]

    def _interval(self, p: float) -> int:
        ps, _ = self._arc_table()
        keys = self._keys()
        k = bisect.bisect_right(keys, (p - self.p_start) * self.sense) - 1
        return min(max(k, 0), len(ps) - 2)

    def _keys(self) -> List[float]:
        if getattr(self, "_key_cache", None) is None:
            self._key_cache = [(q - self.p_start) * self.sense for q in self._arc_table()[0]]
        return self._key_cache

    def arc_length_to(self, p: float) -> float:
        """Arc length along the traversal from ``p_start`` to parameter ``p``."""
        ps, ss = self._arc_table()
        k = self._interval(p)
        a = ps[k]
        h = p - a
        return ss[k] + abs(h) * sum(w * self._speed(a + x * h) for x, w in _GL)

    def param_at(self, fraction: float) -> float:
        """The parameter a given fraction of the way along the traversal, by arc length."""
        if fraction <= 0.0:
            return self.p_start
        if fraction >= 1.0:
            return self.p_end
        ps, ss = self._arc_table()
        target = fraction * ss[-1]
        k = min(max(bisect.bisect_right(ss, target) - 1, 0), len(ps) - 2)
        a, b = ps[k], ps[k + 1]
        p = a + (b - a) * (target - ss[k]) / max(ss[k + 1] - ss[k], 1e-300)
        for _ in range(4):  # Newton on s(p) - target, kept inside [a, b]
            step = (self.arc_length_to(p) - target) / (self.sense * self._speed(p))
            p = min(max(p - step, min(a, b)), max(a, b))
        return p

    def fraction_of(self, p: float) -> float:
        return self.arc_length_to(p) / self.length

    def nearest(self, q: XY) -> Tuple[float, float]:
        """``(distance, p)``: the traversed part's point nearest ``q``."""
        count = 64
        best = min((math.dist(q, self.point(self.lo + (self.hi - self.lo) * k / count)),
                    self.lo + (self.hi - self.lo) * k / count) for k in range(count + 1))
        p = best[1]
        for _ in range(20):  # Newton on (P - q) . P' = 0
            d1, d2 = self.deriv(p), self.deriv2(p)
            r = _sub(self.point(p), q)
            g = _dot(r, d1)
            gp = _dot(d1, d1) + _dot(r, d2)
            if gp <= 0.0:
                break
            new = min(max(p - g / gp, self.lo), self.hi)
            if abs(new - p) <= 1e-15 * max(1.0, abs(p)):
                p = new
                break
            p = new
        return math.dist(q, self.point(p)), p

    def coords(self, max_sag: float) -> List[XY]:
        """A polyline along the traversal, no chord further than ``max_sag`` from the curve."""
        out: List[XY] = [self.start]

        def refine(a: float, b: float, depth: int) -> None:
            pa, pb, pm = self.point(a), self.point(b), self.point(0.5 * (a + b))
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            chord = math.hypot(dx, dy)
            dev = (abs((pm[0] - pa[0]) * dy - (pm[1] - pa[1]) * dx) / chord
                   if chord > 0.0 else math.dist(pm, pa))
            if dev > max_sag and depth < 40:
                refine(a, 0.5 * (a + b), depth + 1)
                refine(0.5 * (a + b), b, depth + 1)
            else:
                out.append(pb)

        pieces = 8
        for k in range(pieces):
            refine(self.p_start + (self.p_end - self.p_start) * k / pieces,
                   self.p_start + (self.p_end - self.p_start) * (k + 1) / pieces, 0)
        out[-1] = self.end
        return out


class ConicCurve(Curve):
    """A conic section's vertex branch, parameterised by s, the distance left of its axis.

    ``s**2 - 2 R z + (1 + K) z**2 = 0``, z along ``axis`` from ``vertex``.
    """

    kind = "conic"

    def __init__(self, vertex: XY, axis: XY, radius: float, conic: float,
                 p_start: float, p_end: float) -> None:
        length = math.hypot(axis[0], axis[1])
        if length == 0.0:
            raise ValueError("a conic's axis cannot be zero.")
        if radius == 0.0 or not math.isfinite(radius):
            raise ValueError(f"a conic edge needs a finite non-zero vertex radius, got {radius!r}; "
                             "a flat edge is a line.")
        self.vertex = (float(vertex[0]), float(vertex[1]))
        self.axis = (axis[0] / length, axis[1] / length)
        self.left = (-self.axis[1], self.axis[0])
        self.radius = float(radius)
        self.conic = float(conic)
        super().__init__(p_start, p_end)
        for p in (p_start, p_end):
            if self._root(p) <= 0.0:
                raise ValueError(
                    f"conic edge reaches s = {p:.6g}, at or past where the conic stops "
                    "being single-valued across its axis (its equator).")

    def _root(self, s: float) -> float:
        return 1.0 - (1.0 + self.conic) * s * s / (self.radius * self.radius)

    def _z(self, s: float) -> float:
        return s * s / (self.radius * (1.0 + math.sqrt(max(self._root(s), 0.0))))

    def point(self, p: float) -> XY:
        z = self._z(p)
        return (self.vertex[0] + z * self.axis[0] + p * self.left[0],
                self.vertex[1] + z * self.axis[1] + p * self.left[1])

    def deriv(self, p: float) -> XY:
        dz = p / (self.radius * math.sqrt(max(self._root(p), 1e-300)))
        return (dz * self.axis[0] + self.left[0], dz * self.axis[1] + self.left[1])

    def deriv2(self, p: float) -> XY:
        d2z = 1.0 / (self.radius * max(self._root(p), 1e-300) ** 1.5)
        return (d2z * self.axis[0], d2z * self.axis[1])

    def _line_roots(self, origin: XY, direction: XY) -> List[Tuple[float, float]]:
        o = _sub(origin, self.vertex)
        z0, s0 = _dot(o, self.axis), _dot(o, self.left)
        dz, ds = _dot(direction, self.axis), _dot(direction, self.left)
        kp, r = 1.0 + self.conic, self.radius
        a = ds * ds + kp * dz * dz
        b = 2.0 * (s0 * ds - r * dz + kp * z0 * dz)
        c = s0 * s0 - 2.0 * r * z0 + kp * z0 * z0
        roots: List[float] = []
        scale = max(abs(b), abs(a), 1e-300)
        if abs(a) <= 1e-14 * scale:
            if b != 0.0:
                roots.append(-c / b)
        else:
            disc = b * b - 4.0 * a * c
            if disc < 0.0:
                return []
            q = -0.5 * (b + math.copysign(math.sqrt(disc), b))
            roots.append(q / a)
            if q != 0.0:
                roots.append(c / q)
        out = []
        for t in roots:
            z = z0 + t * dz
            if 1.0 - kp * z / r >= -1e-12:  # the vertex's own branch
                out.append((t, s0 + t * ds))
        return out

    def descriptor(self) -> Dict[str, Any]:
        return {"type": "conic", "vertex": list(self.vertex), "axis": list(self.axis),
                "radius": self.radius, "conic": self.conic}

    def with_domain(self, p_start: float, p_end: float) -> "ConicCurve":
        return ConicCurve(self.vertex, self.axis, self.radius, self.conic, p_start, p_end)

    @property
    def size(self) -> float:
        return max(abs(self.radius), self.hi - self.lo, 1.0)

    def param_of(self, q: XY) -> float:
        """The parameter s of a point on (or near) the curve."""
        return _dot(_sub(q, self.vertex), self.left)


class AsphereCurve(Curve):
    """An even asphere's profile, parameterised by s, the distance left of its axis.

    ``z(s) = c s**2 / (1 + sqrt(1 - (1 + K) c**2 s**2)) + sum A_i s**(2 i)``
    (i = 1, 2, ...), z along ``axis`` from ``vertex``, c = 1 / R (0 for R None).
    """

    kind = "asphere"

    def __init__(self, vertex: XY, axis: XY, radius: Optional[float], conic: float,
                 coefficients: Sequence[float], p_start: float, p_end: float) -> None:
        length = math.hypot(axis[0], axis[1])
        if length == 0.0:
            raise ValueError("an asphere's axis cannot be zero.")
        if radius is not None and (radius == 0.0 or not math.isfinite(radius)):
            raise ValueError(f"an asphere's vertex radius must be finite and non-zero, or None for a flat base; "
                             f"got {radius!r}")
        coefficients = [float(a) for a in coefficients]
        if not all(math.isfinite(a) for a in coefficients):
            raise ValueError(f"asphere coefficients must be finite, got {coefficients}")
        if radius is None and not any(coefficients):
            raise ValueError("an asphere with a flat base and no coefficients is a line.")
        self.vertex = (float(vertex[0]), float(vertex[1]))
        self.axis = (axis[0] / length, axis[1] / length)
        self.left = (-self.axis[1], self.axis[0])
        self.radius = None if radius is None else float(radius)
        self.conic = float(conic)
        self.coefficients = coefficients
        self._c = 0.0 if radius is None else 1.0 / float(radius)
        super().__init__(p_start, p_end)
        for p in (p_start, p_end):
            if self._root(p) <= 0.0:
                raise ValueError(
                    f"asphere edge reaches s = {p:.6g}, at or past where its conic base stops "
                    "being single-valued across its axis (its equator).")
        self._z_bounds: Optional[Tuple[float, float]] = None

    def z_bounds(self) -> Tuple[float, float]:
        """Bounds on the sag over the edge: sampled, widened by the curvature between samples."""
        if self._z_bounds is None:
            count = 4 * ASPHERE_INTERVALS
            step = (self.hi - self.lo) / count
            ss = [self.lo + step * k for k in range(count + 1)]
            zs = [self._z(v) for v in ss]
            bend = max(abs(self._d2z(v)) for v in ss)
            margin = 2.0 * bend * step * step / 8.0 + 1e-12 * self.size
            self._z_bounds = (min(zs) - margin, max(zs) + margin)
        return self._z_bounds

    def _root(self, s: float) -> float:
        return 1.0 - (1.0 + self.conic) * self._c * self._c * s * s

    def _z(self, s: float) -> float:
        s2 = s * s
        z = self._c * s2 / (1.0 + math.sqrt(max(self._root(s), 0.0)))
        power = s2
        for a in self.coefficients:
            z += a * power
            power *= s2
        return z

    def _dz(self, s: float) -> float:
        dz = self._c * s / math.sqrt(max(self._root(s), 1e-300))
        power = s                                   # s**(2i - 1)
        for i, a in enumerate(self.coefficients, start=1):
            dz += 2 * i * a * power
            power *= s * s
        return dz

    def _d2z(self, s: float) -> float:
        d2z = self._c / max(self._root(s), 1e-300) ** 1.5
        power = 1.0                                 # s**(2i - 2)
        for i, a in enumerate(self.coefficients, start=1):
            d2z += 2 * i * (2 * i - 1) * a * power
            power *= s * s
        return d2z

    def point(self, p: float) -> XY:
        z = self._z(p)
        return (self.vertex[0] + z * self.axis[0] + p * self.left[0],
                self.vertex[1] + z * self.axis[1] + p * self.left[1])

    def deriv(self, p: float) -> XY:
        dz = self._dz(p)
        return (dz * self.axis[0] + self.left[0], dz * self.axis[1] + self.left[1])

    def deriv2(self, p: float) -> XY:
        d2z = self._d2z(p)
        return (d2z * self.axis[0], d2z * self.axis[1])

    def _line_roots(self, origin: XY, direction: XY) -> List[Tuple[float, float]]:
        """The meeting points within the edge's own s range (an asphere has no "whole curve")."""
        o = _sub(origin, self.vertex)
        z0, s0 = _dot(o, self.axis), _dot(o, self.left)
        dz, ds = _dot(direction, self.axis), _dot(direction, self.left)
        lo, hi = self.lo, self.hi
        scale = self.size
        if abs(ds) <= 1e-14 * math.hypot(dz, ds):              # the line runs along the axis: s is fixed
            if lo - 1e-12 * scale <= s0 <= hi + 1e-12 * scale and dz != 0.0:
                return [((self._z(s0) - z0) / dz, s0)]
            return []
        slope = dz / ds                                          # the line's z as a function of s
        # Only where the line is within the edge's sag bounds can it meet the edge: most lines miss.
        z_lo, z_hi = self.z_bounds()
        if abs(slope) > 1e-300:
            s_a, s_b = sorted((s0 + (z_lo - z0) / slope, s0 + (z_hi - z0) / slope))
            s_a, s_b = max(s_a, lo), min(s_b, hi)
        elif z_lo <= z0 <= z_hi:
            s_a, s_b = lo, hi
        else:
            return []
        if s_a > s_b:
            return []

        def h(s: float) -> float:
            return z0 + (s - s0) * slope - self._z(s)

        def hp(s: float) -> float:
            return slope - self._dz(s)

        def refine(f, fp, a: float, b: float) -> float:
            fa = f(a)
            x = 0.5 * (a + b)
            for _ in range(100):
                fx = f(x)
                if fx == 0.0:
                    break
                if (fx > 0.0) == (fa > 0.0):
                    a, fa = x, fx
                else:
                    b = x
                d = fp(x)
                new = x - fx / d if d != 0.0 else 0.5 * (a + b)
                if not (min(a, b) < new < max(a, b)):
                    new = 0.5 * (a + b)
                if abs(new - x) <= 1e-15 * max(1.0, abs(x)):
                    x = new
                    break
                x = new
            return x

        def d2(s: float) -> float:
            return -self._d2z(s)

        roots: List[float] = []
        count = max(1, int(math.ceil(ASPHERE_INTERVALS * (s_b - s_a) / (hi - lo))))
        edges = [s_a + (s_b - s_a) * k / count for k in range(count + 1)]
        for a, b in zip(edges[:-1], edges[1:]):
            pieces = [(a, b)]
            if hp(a) * hp(b) < 0.0:                              # h turns inside: split at the turn
                m = refine(hp, d2, a, b)
                pieces = [(a, m), (m, b)]
            for u, v in pieces:
                hu, hv = h(u), h(v)
                if hu == 0.0:
                    roots.append(u)
                elif hv != 0.0 and (hu > 0.0) != (hv > 0.0):
                    roots.append(refine(h, hp, u, v))
        if h(s_b) == 0.0:
            roots.append(s_b)
        out: List[Tuple[float, float]] = []
        for s in sorted(roots):
            if out and abs(s - out[-1][1]) <= 1e-12 * scale:
                continue
            out.append(((s - s0) / ds, s))
        return out

    def descriptor(self) -> Dict[str, Any]:
        return {"type": "asphere", "vertex": list(self.vertex), "axis": list(self.axis),
                "radius": self.radius, "conic": self.conic, "coefficients": list(self.coefficients)}

    def with_domain(self, p_start: float, p_end: float) -> "AsphereCurve":
        return AsphereCurve(self.vertex, self.axis, self.radius, self.conic, self.coefficients, p_start, p_end)

    @property
    def size(self) -> float:
        return max(abs(self.radius) if self.radius is not None else 0.0, self.hi - self.lo, 1.0)

    def param_of(self, q: XY) -> float:
        """The parameter s of a point on (or near) the curve."""
        return _dot(_sub(q, self.vertex), self.left)


class SplineCurve(Curve):
    """A cubic Hermite curve through points with given unit tangents, parameter p in [0, n - 1]."""

    kind = "spline"

    def __init__(self, points: Sequence[XY], tangents: Sequence[XY],
                 p_start: float, p_end: float) -> None:
        if len(points) < 2 or len(points) != len(tangents):
            raise ValueError(f"a spline needs at least 2 points and one tangent per point, "
                             f"got {len(points)} points and {len(tangents)} tangents.")
        self.points = [(float(x), float(y)) for x, y in points]
        self.tangents = []
        for tx, ty in tangents:
            length = math.hypot(tx, ty)
            if length == 0.0 or not math.isfinite(length):
                raise ValueError("a spline tangent must be a finite non-zero vector.")
            self.tangents.append((tx / length, ty / length))
        self._coef = []
        for k in range(len(self.points) - 1):
            p0, p1 = self.points[k], self.points[k + 1]
            h = math.dist(p0, p1)
            if h == 0.0:
                raise ValueError(f"spline points {k} and {k + 1} coincide.")
            m0 = (self.tangents[k][0] * h, self.tangents[k][1] * h)
            m1 = (self.tangents[k + 1][0] * h, self.tangents[k + 1][1] * h)
            a = p0
            b = m0
            c = (-3 * p0[0] - 2 * m0[0] + 3 * p1[0] - m1[0], -3 * p0[1] - 2 * m0[1] + 3 * p1[1] - m1[1])
            d = (2 * p0[0] + m0[0] - 2 * p1[0] + m1[0], 2 * p0[1] + m0[1] - 2 * p1[1] + m1[1])
            bez = (p0, (p0[0] + m0[0] / 3, p0[1] + m0[1] / 3),
                   (p1[0] - m1[0] / 3, p1[1] - m1[1] / 3), p1)
            self._coef.append((a, b, c, d, bez))
        last = len(self.points) - 1
        if not (0.0 <= min(p_start, p_end) and max(p_start, p_end) <= last):
            raise ValueError(f"spline parameters must lie in [0, {last}].")
        super().__init__(p_start, p_end)

    def _segment(self, p: float) -> Tuple[int, float]:
        k = min(max(int(math.floor(p)), 0), len(self._coef) - 1)
        return k, p - k

    def point(self, p: float) -> XY:
        k, u = self._segment(p)
        a, b, c, d, _ = self._coef[k]
        return (a[0] + u * (b[0] + u * (c[0] + u * d[0])), a[1] + u * (b[1] + u * (c[1] + u * d[1])))

    def deriv(self, p: float) -> XY:
        k, u = self._segment(p)
        _, b, c, d, _ = self._coef[k]
        return (b[0] + u * (2 * c[0] + 3 * u * d[0]), b[1] + u * (2 * c[1] + 3 * u * d[1]))

    def deriv2(self, p: float) -> XY:
        k, u = self._segment(p)
        _, _, c, d, _ = self._coef[k]
        return (2 * c[0] + 6 * u * d[0], 2 * c[1] + 6 * u * d[1])

    def _line_roots(self, origin: XY, direction: XY) -> List[Tuple[float, float]]:
        nrm = (-direction[1], direction[0])
        dd = _dot(direction, direction)
        found: List[Tuple[float, float]] = []
        for k, (a, b, c, d, bez) in enumerate(self._coef):
            g = [_dot(nrm, _sub(q, origin)) for q in bez]   # Bernstein coefficients of f(u)
            if all(v > 0.0 for v in g) or all(v < 0.0 for v in g):
                continue
            poly = (_dot(nrm, _sub(a, origin)), _dot(nrm, b), _dot(nrm, c), _dot(nrm, d))
            for u in _bernstein_roots(g, poly):
                p = k + u
                if any(abs(p - q) <= 1e-12 for _, q in found):
                    continue  # a shared knot found by both segments
                found.append((_dot(_sub(self.point(p), origin), direction) / dd, p))
        return found

    def _breaks(self) -> List[float]:
        return [float(k) for k in range(1, len(self.points) - 1)]

    def descriptor(self) -> Dict[str, Any]:
        desc = {"type": "spline", "points": [list(p) for p in self.points],
                "tangents": [list(t) for t in self.tangents]}
        if {self.lo, self.hi} != {0.0, float(len(self.points) - 1)}:
            desc["domain"] = [self.p_start, self.p_end]
        return desc

    def with_domain(self, p_start: float, p_end: float) -> "SplineCurve":
        return SplineCurve(self.points, self.tangents, p_start, p_end)

    @property
    def size(self) -> float:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return max(max(xs) - min(xs), max(ys) - min(ys), 1.0)


def _bernstein_roots(g: Sequence[float], poly: Sequence[float]) -> List[float]:
    """Roots in [0, 1] of the cubic with Bernstein coefficients ``g`` (power-basis
    coefficients ``poly``, lowest first, for evaluation), each isolated by the
    sign changes of the coefficients and refined by safeguarded Newton."""

    def f(u: float) -> float:
        return poly[0] + u * (poly[1] + u * (poly[2] + u * poly[3]))

    def fp(u: float) -> float:
        return poly[1] + u * (2 * poly[2] + 3 * u * poly[3])

    scale = max(abs(v) for v in g) or 1.0
    roots: List[float] = []
    stack = [(0.0, 1.0, list(g), 0)]
    while stack:
        lo, hi, cs, depth = stack.pop()
        signs = [v for v in cs if abs(v) > 1e-15 * scale]
        changes = sum(1 for a, b in zip(signs[:-1], signs[1:]) if (a > 0) != (b > 0))
        if changes == 0:
            for u in (lo, hi):  # a root exactly at an end, where a coefficient is 0
                if abs(f(u)) <= 1e-15 * scale and all(abs(u - r) > 1e-12 for r in roots):
                    roots.append(u)
            continue
        if changes == 1 or depth > 40:
            a, b = lo, hi
            fa = f(a)
            u = 0.5 * (a + b)
            for _ in range(100):
                fu = f(u)
                if fu == 0.0:
                    break
                if (fu > 0) == (fa > 0):
                    a, fa = u, fu
                else:
                    b = u
                d = fp(u)
                new = u - fu / d if d != 0.0 else 0.5 * (a + b)
                if not (a < new < b):
                    new = 0.5 * (a + b)
                if abs(new - u) <= 1e-16:
                    u = new
                    break
                u = new
            if all(abs(u - r) > 1e-12 for r in roots):
                roots.append(u)
            continue
        # de Casteljau split at the middle
        b0, b1, b2, b3 = cs
        b01, b12, b23 = 0.5 * (b0 + b1), 0.5 * (b1 + b2), 0.5 * (b2 + b3)
        b012, b123 = 0.5 * (b01 + b12), 0.5 * (b12 + b23)
        mid = 0.5 * (b012 + b123)
        m = 0.5 * (lo + hi)
        stack.append((lo, m, [b0, b01, b012, mid], depth + 1))
        stack.append((m, hi, [mid, b123, b23, b3], depth + 1))
    return sorted(roots)


def curve_from_descriptor(desc: Dict[str, Any], start: XY, end: XY) -> Curve:
    """The curve a path entry's ``curve`` descriptor defines, traversed from ``start`` to ``end``.

    Raises:
        ValueError: If either end point is not on the curve (within
            ENDPOINT_TOL of its size), or the descriptor is malformed.
        NotImplementedError: For a curve type other than conic and spline.
    """
    kind = desc.get("type")
    if kind == "conic":
        base = ConicCurve(desc["vertex"], desc["axis"], float(desc["radius"]), float(desc["conic"]),
                          0.0, 1e-300)
        p0, p1 = base.param_of(start), base.param_of(end)
        curve: Curve = base.with_domain(p0, p1)
    elif kind == "asphere":
        radius = desc.get("radius")
        base = AsphereCurve(desc["vertex"], desc["axis"], None if radius is None else float(radius),
                            float(desc.get("conic", 0.0)), desc.get("coefficients", []), 0.0, 1e-300)
        curve = base.with_domain(base.param_of(start), base.param_of(end))
    elif kind == "spline":
        points = [tuple(p) for p in desc["points"]]
        tangents = [tuple(t) for t in desc["tangents"]]
        last = len(points) - 1
        if desc.get("domain") is not None:
            p0, p1 = (float(v) for v in desc["domain"])
            curve = SplineCurve(points, tangents, p0, p1)
            if math.dist(curve.start, start) > math.dist(curve.end, start):
                curve = SplineCurve(points, tangents, p1, p0)   # the path runs it the other way
        elif math.dist(points[0], start) <= math.dist(points[-1], start):
            curve = SplineCurve(points, tangents, 0.0, float(last))
        else:
            curve = SplineCurve(points, tangents, float(last), 0.0)
    else:
        raise NotImplementedError(f"glass curve type {kind!r}: only 'conic', 'asphere' and 'spline' are built.")
    tol = ENDPOINT_TOL * curve.size
    for name, want, got in (("start", start, curve.start), ("end", end, curve.end)):
        if math.dist(want, got) > tol:
            raise ValueError(f"the path's {name} point {list(want)} is {math.dist(want, got):.3g} "
                             f"from its {kind} curve (tolerance {tol:.3g}).")
    return curve


def transform_descriptor(desc: Dict[str, Any], point_fn: Callable[[XY], XY],
                         vector_fn: Callable[[XY], XY], scale: float = 1.0) -> Dict[str, Any]:
    """A curve descriptor moved, rotated, mirrored or scaled as the path points are.

    Args:
        point_fn: Maps a point.
        vector_fn: Maps a direction (the linear part of point_fn, without scale).
        scale: The uniform scale factor in point_fn (scales a conic's radius;
            an asphere's coefficient of s**(2 i) by scale**(1 - 2 i)).
    """
    kind = desc.get("type")
    if kind == "asphere":
        out = dict(desc)
        out["vertex"] = list(point_fn(tuple(desc["vertex"])))
        out["axis"] = list(vector_fn(tuple(desc["axis"])))
        if desc.get("radius") is not None:
            out["radius"] = float(desc["radius"]) * scale
        out["coefficients"] = [float(a) * scale ** (1 - 2 * i)
                               for i, a in enumerate(desc.get("coefficients", []), start=1)]
        return out
    if kind == "conic":
        out = dict(desc)
        out["vertex"] = list(point_fn(tuple(desc["vertex"])))
        out["axis"] = list(vector_fn(tuple(desc["axis"])))
        out["radius"] = float(desc["radius"]) * scale
        return out
    if kind == "spline":
        out = dict(desc)
        out["points"] = [list(point_fn(tuple(p))) for p in desc["points"]]
        out["tangents"] = [list(vector_fn(tuple(t))) for t in desc["tangents"]]
        return out
    raise NotImplementedError(f"glass curve type {kind!r}")


__all__ = ["Curve", "ConicCurve", "AsphereCurve", "SplineCurve", "curve_from_descriptor", "transform_descriptor",
           "ENDPOINT_TOL"]
