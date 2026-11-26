"""
Python-specific module: sms chain
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

Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
SMS CHAIN ENGINE
===============================================================================
The generic Simultaneous Multiple Surface (SMS) alternating construction
(Chaves, "Introduction to Nonimaging Optics" ch. 9, §9.2/9.4): one shared
stepping primitive and driver loop, reused (per the book's own text, §9.4
lines 647/743/826) across the RR, XR, RX, and XX device families -- only
which law (refract vs. reflect) applies at each surface changes.

See dev_doc/architecture/components/nonimaging_design.md
for the full design rationale and equation-level citations; this module's
docstrings carry the same citations independently.

Conventions (matching nonimaging_geometry.py's own):
- Points and directions are (x, y) tuples.
- `mechanism` is 'refract' or 'reflect', describing the law applied AT the
  known point using its known normal.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Callable, List, NamedTuple, Optional, Tuple

from .nonimaging_geometry import Point, ccoptpt, coptsl, rfnrm, rfr, rfxnrm

_EPS = 1e-9


class SMSPoint(NamedTuple):
    """One computed point on an SMS surface, with its normal."""
    p: Point
    n: Point


def _nrm(v: Point) -> Point:
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


def _neg(v: Point) -> Point:
    return (-v[0], -v[1])


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _close(a: Point, b: Point, tol: float = 1e-6) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) < tol


def reflect(v: Point, n_surf: Point) -> Point:
    """
    Law of reflection, vector form: r = v - 2*(v.n)*n (Chaves Ch. 21 eq.
    21.160's rfx, not yet in nonimaging_geometry.py -- trivial one-liner,
    added here rather than there since it's SMS-chain-specific plumbing,
    not a Cartesian-oval primitive.

    Unlike rfr() (which takes the NEGATED direction of travel, per its own
    documented convention), this takes `v` as the actual direction of
    travel, un-negated -- confirmed against Chaves Ch. 9 Example 9.2 eq.
    9.73: reflect(i, n_X) matches the book's published t_X exactly,
    reflect(-i, n_X) does not (it's the exact negation). The reflection
    formula is also, unlike rfr's, invariant to n_surf's sign
    (reflect(v, -n) == reflect(v, n) algebraically), which is why
    sms_chain_step's known-normal re-orientation step matters only for
    the refract branch.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 21 "Plane Curves", eq. 21.160 (Section 21.15 item 24).
    """
    d = v[0] * n_surf[0] + v[1] * n_surf[1]
    return (v[0] - 2.0 * d * n_surf[0], v[1] - 2.0 * d * n_surf[1])


def _orient_toward_travel(n_surf: Point, i: Point) -> Point:
    """
    Re-orient a stored (unsigned-line) normal so it points in the general
    direction of the incident ray's own travel (cos_i = i.n_surf > 0),
    before feeding it to rfr()/reflect().

    This is NOT the same problem _resolve_new_normal() solves. A normal
    stored on an existing SMSPoint was oriented correctly for whichever
    direction it was originally computed against; reusing it for a new
    incident ray from a DIFFERENT source (the SMS "ping-pong" always does
    this -- see build_sms_chain()) can require the opposite sign, because
    rfr()'s own convention requires n_surf to point "into the medium being
    entered," which is direction-dependent, not an intrinsic property of
    the physical surface. Confirmed necessary against Chaves Ch. 9
    Example 9.1's own ping-pong step (line ~1877's X_13 -> N_13 point):
    X_13's normal, correctly oriented for X_13's OWN creation (a ray
    heading from N through X_13 toward R_1), needs to be flipped before
    it can be reused as the known_normal for the reverse-direction ray
    from R_2 through X_13 toward E_1 -- without this re-orientation, the
    resulting point misses N_13 by an order of magnitude, not just a sign.

    For the 'reflect' mechanism this is a no-op in effect (reflect() is
    invariant to n_surf's sign), but applying it unconditionally keeps
    sms_chain_step() simple.
    """
    return n_surf if _dot(i, n_surf) > 0 else _neg(n_surf)


def _resolve_new_normal(
    new_dir: Point, out_dir: Point, n_after: float, n_target: float, new_mechanism: str,
) -> Point:
    """
    Resolve rfnrm()'s/rfxnrm()'s "up to an overall sign" ambiguity
    (nonimaging_geometry.py's own documented caveat) for a NEWLY COMPUTED
    point, by checking which of the two candidate signs actually
    reproduces the already-known `out_dir` when fed back through the
    forward law (rfr()/reflect()) -- rather than assuming a fixed
    convention, which Chaves Ch. 9's own worked examples prove would be
    wrong: Example 9.1's seed point N needs one sign, Example 9.2's point
    X2 needs the other, for the exact same rfnrm() call shape. Verified
    against both before this function was written this way.
    """
    if new_mechanism == 'refract':
        candidate = rfnrm(new_dir, out_dir, n_after, n_target)
        check = rfr(_neg(new_dir), candidate, n_after, n_target)
    elif new_mechanism == 'reflect':
        candidate = rfxnrm(new_dir, out_dir)
        check = reflect(new_dir, candidate)
    else:
        raise ValueError(f"_resolve_new_normal: unknown mechanism '{new_mechanism}'")

    if check is not None and _close(check, out_dir):
        return candidate
    return _neg(candidate)


def sms_chain_step(
    known_point: Point,
    known_normal: Point,
    ray_source: Point,
    n_before: float,
    n_after: float,
    target: Point,
    target_n: Optional[Point],
    n_target: float,
    S: float,
    mechanism: str,
    new_mechanism: str,
) -> SMSPoint:
    """
    One SMS chain step (Chaves Ch. 9 §9.2's core loop, e.g. eq. 9.4-9.5):
    refract or reflect a ray from `ray_source` at `known_point` (using
    `known_normal`), then find the point on the OTHER surface, along that
    new ray direction, at which the optical path length to `target` equals
    `S` -- via ccoptpt() (target is a point) or coptsl() (target is a
    wavefront, `target_n` given as the wavefront's normal instead of
    None). Returns the new point and its normal (via rfnrm()/rfxnrm(),
    resolved to the sign that reproduces the known outgoing ray -- see
    _resolve_new_normal()).

    `known_point`/`known_normal` is always the *previous* step's output --
    the "ping-pong" alternation build_sms_chain() drives. `mechanism`
    describes the law applied AT known_point; `new_mechanism` describes
    the law that will apply AT the newly computed point -- these are
    independent and both required (Chaves Ch. 9's XR/RX/XX families
    alternate refract/reflect between their two fixed surfaces; RXI's own
    top surface alternates refract/reflect on itself across its two hits
    within a single device). This corrects the original roadmap stub's
    single `mechanism` parameter, which cannot distinguish "law at the
    known point" from "law that will govern the new point's own normal" --
    found necessary while implementing against Chaves Ch. 9 Example 9.2's
    reflect-then-refract-then-reflect chain (eq. 9.73-9.79), not assumed
    in advance.

    `n_target` (the target's own medium index -- ccoptpt's/coptsl's `n2`)
    is likewise a genuine addition over the roadmap stub: it is NOT
    generally equal to `n_after` (e.g. Chaves Ch. 9 eq. 9.74:
    ccoptpt(X, 1, t_X, R1, n, S_X) -- the ray from X travels in air
    (n_after=1) but focuses to R1, which sits in the glass (n_target=n)).

    Args:
        known_point: The previous step's point (or a seed point).
        known_normal: Its normal -- re-oriented internally toward the
            current incident ray's own direction of travel before use
            (see _orient_toward_travel()), so it need not already be
            oriented for this specific call.
        ray_source: The point the incident ray at `known_point` comes
            from. If the incident bundle is a wavefront rather than a
            point source, resolve the specific ray's crossing point with
            that wavefront first (isl() against the wavefront's own line,
            Chaves Ch. 9 eq. 9.72) and pass that point here -- this
            function always treats the incident ray as point-sourced.
        n_before: Refractive index of the medium from `ray_source` to
            `known_point`.
        n_after: Refractive index of the medium from `known_point` to the
            new point (ccoptpt's/coptsl's `n1`).
        target: The point (or a point on the wavefront, if `target_n` is
            given) the new point's own ray must satisfy the optical path
            length `S` to.
        target_n: None if `target` is a point focus (ccoptpt); the
            wavefront's unit normal (pointing in its direction of
            propagation) if `target` is a point on a plane wavefront
            (coptsl).
        n_target: Refractive index of the medium on the target's own side
            (ccoptpt's/coptsl's `n2`) -- not necessarily equal to
            `n_after`.
        S: The required optical path length to `target`.
        mechanism: 'refract' or 'reflect' -- the law at `known_point`.
        new_mechanism: 'refract' or 'reflect' -- the law that will govern
            the new point's own normal.

    Returns:
        The new SMSPoint.

    Raises:
        ValueError: If `mechanism`/`new_mechanism` is not 'refract' or
            'reflect', if refraction at `known_point` totally internally
            reflects (rfr() returns None), or if ccoptpt()/coptsl() has
            no solution for the given geometry.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 9 "Miñano-Benítez Design Method", §9.2 eq. 9.4-9.5 (RR),
        §9.4 eq. 9.33 (XR), eq. 9.34 (RX), eq. 9.35 (XX); Example 9.1
        (refract-refract, lines 1877+) and Example 9.2 (reflect-refract,
        eq. 9.67-9.79) both validated directly against this function.
    """
    if mechanism not in ('refract', 'reflect'):
        raise ValueError(f"sms_chain_step: unknown mechanism '{mechanism}'")
    if new_mechanism not in ('refract', 'reflect'):
        raise ValueError(f"sms_chain_step: unknown new_mechanism '{new_mechanism}'")

    i = _nrm((known_point[0] - ray_source[0], known_point[1] - ray_source[1]))
    oriented_normal = _orient_toward_travel(known_normal, i)

    if mechanism == 'refract':
        new_dir = rfr(_neg(i), oriented_normal, n_before, n_after)
        if new_dir is None:
            raise ValueError("sms_chain_step: total internal reflection at known_point")
    else:
        new_dir = reflect(i, oriented_normal)

    if target_n is None:
        new_point = ccoptpt(known_point, n_after, new_dir, target, n_target, S)
        out_dir = _nrm((target[0] - new_point[0], target[1] - new_point[1]))
    else:
        new_point = coptsl(known_point, new_dir, target, target_n, n_after, n_target, S)
        out_dir = target_n

    new_normal = _resolve_new_normal(new_dir, out_dir, n_after, n_target, new_mechanism)
    return SMSPoint(new_point, new_normal)


def seed_arc(p1: Point, n1: Point, p2: Point, n2: Point, n_points: int) -> List[SMSPoint]:
    """
    Short circular-arc seed between two points with known normals, center
    found via isl() intersecting the two normal lines (Chaves Ch. 9, Figure 9.4's P1-Q1 construction). Returns `n_points`
    SMSPoints (including both endpoints) with normals radiating from the
    found center -- the launch pad the alternating chain in
    sms_chain_step()/build_sms_chain() starts from.

    Degenerates to a straight-line seed (n_points evenly spaced points
    along the segment p1-p2, each with the same normal -- the average of
    n1/n2 if they differ only by floating-point noise, otherwise n1) when
    n1 and n2 are parallel (no meaningful finite center), handled as a
    documented special case, not an error, since a straight seed is
    exactly what Chaves Ch. 9's simpler P0-only variant (line 78) and
    the RXI direct method's AC segment
    (dev_doc/architecture/components/nonimaging_design.md,
    pin 4) both already use.

    Args:
        p1: First endpoint.
        n1: Its unit normal.
        p2: Second endpoint.
        n2: Its unit normal.
        n_points: Number of points to return, >= 2.

    Returns:
        List of `n_points` SMSPoints from p1 to p2 inclusive.

    Raises:
        ValueError: If n_points < 2.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 9 "Miñano-Benítez Design Method", §9.2, lines 126-127
        (Figure 9.4's P1-Q1 circular-arc construction).
    """
    if n_points < 2:
        raise ValueError("seed_arc: n_points must be >= 2")

    from .nonimaging_geometry import isl

    cross = n1[0] * n2[1] - n1[1] * n2[0]
    if abs(cross) < 1e-9:
        points = []
        for k in range(n_points):
            x = k / (n_points - 1)
            p = (p1[0] + x * (p2[0] - p1[0]), p1[1] + x * (p2[1] - p1[1]))
            points.append(SMSPoint(p, n1))
        return points

    center = isl(p1, n1, p2, n2)
    radius = math.hypot(p1[0] - center[0], p1[1] - center[1])

    angle1 = math.atan2(p1[1] - center[1], p1[0] - center[0])
    angle2 = math.atan2(p2[1] - center[1], p2[0] - center[0])
    # Take the shorter angular path from angle1 to angle2.
    delta = angle2 - angle1
    while delta > math.pi:
        delta -= 2 * math.pi
    while delta < -math.pi:
        delta += 2 * math.pi

    points = []
    for k in range(n_points):
        x = k / (n_points - 1)
        a = angle1 + x * delta
        p = (center[0] + radius * math.cos(a), center[1] + radius * math.sin(a))
        n = _nrm((p[0] - center[0], p[1] - center[1]))
        points.append(SMSPoint(p, n))
    return points


def build_sms_chain(
    seed: List[SMSPoint],
    step_fn: Callable[[SMSPoint, str], Tuple[SMSPoint, str]],
    stop_condition: Callable[[SMSPoint], bool],
    max_steps: int = 10000,
) -> Tuple[List[SMSPoint], List[SMSPoint]]:
    """
    The alternating ping-pong loop (Chaves Ch. 9 Figure 9.4/9.6): growing
    outward from `seed` (assumed to already be a short arc/segment on ONE
    surface, e.g. from seed_arc()), alternating a new point on the OTHER
    surface, then a new point back on the seed's surface, until
    `stop_condition` is met on the most recently produced point.

    Args:
        seed: The starting SMSPoint list, all on one surface, ordered
            outward from the device's symmetry axis (or however the
            caller defines "outward" -- stop_condition is evaluated in
            that same sense).
        step_fn: Given the most recently produced SMSPoint and a string
            tag identifying which surface it's on ('seed' for the seed
            surface, 'other' for the alternate one), returns
            (new_sms_point, new_surface_tag) -- the caller closes over
            the two alternating sms_chain_step() configurations (which
            ray_source/target/S/mechanism apply on which surface) here,
            since that bookkeeping is device-specific, not generic.
        stop_condition: Called on each newly produced point; the loop
            stops (without including that last point) once it returns
            True. Typical use: the point has crossed the device's
            symmetry axis (Chaves Ch. 9).
        max_steps: Safety bound against a stop_condition that never
            triggers (default: 10000).

    Returns:
        (seed_surface_points, other_surface_points) -- each an ordered
        point list, half of a symmetric device; the caller mirrors about
        the axis (Chaves Ch. 9) to complete it, exactly as
        DTIRCPrism/RXIOptic already assemble a symmetric polygon from a
        computed half-profile.

    Raises:
        RuntimeError: If `max_steps` is reached without `stop_condition`
            returning True.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 9 "Miñano-Benítez Design Method", §9.2 Figures 9.4/9.6 (the
        alternating construction, center-outward and edge-inward
        variants); Winston, Miñano, Benítez, Nonimaging Optics, Elsevier,
        2005, Ch. 8 "Simultaneous Multiple Surface Design Method" (the
        same alternation described via phase space/étendue rather than
        wavefronts -- see dev_doc/architecture/components/nonimaging_design.md for the
        cross-reading of both).
    """
    seed_points: List[SMSPoint] = list(seed)
    other_points: List[SMSPoint] = []

    current = seed[-1]
    current_tag = 'seed'

    for _ in range(max_steps):
        new_point, new_tag = step_fn(current, current_tag)
        if new_tag == 'seed':
            seed_points.append(new_point)
        else:
            other_points.append(new_point)
        if stop_condition(new_point):
            return seed_points, other_points
        current, current_tag = new_point, new_tag

    raise RuntimeError(
        f"build_sms_chain: stop_condition not met within max_steps={max_steps}"
    )


def grow_sms_chains(
    seed: List[SMSPoint],
    seed_step: Callable[[SMSPoint], Optional[SMSPoint]],
    other_step: Callable[[SMSPoint], Optional[SMSPoint]],
    max_steps: int = 1000,
    outward: Optional[Callable[[SMSPoint, SMSPoint], bool]] = None,
) -> Tuple[List[SMSPoint], List[SMSPoint]]:
    """
    The SMS chains as the book grows them: one chain from every seed point (Chaves Ch. 9,
    Example 9.2: "this process must now be repeated for all other points of c and then for
    the new points"). Each chain alternates a point on the other surface (``seed_step``) and
    one back on the seed's surface (``other_step``) until a step returns None (the surface's
    physical end, decided by the caller) or raises ValueError (no solution: total internal
    reflection, or no point at the required optical path length).

    The chains interleave: the points of all of them, on each surface, sample one curve.

    ``outward(new, previous)``, if given, is asked of each new point against the chain's
    previous point on the same surface; False ends the chain there. A surface that turns
    back on itself (a top surface turned vertical, no longer facing the light) ends where it
    turns.

    Returns:
        ``(seed_surface_points, other_surface_points)``: the seed, then every chain's points,
        in the order computed (the caller orders them along each surface).
    """
    seed_points: List[SMSPoint] = list(seed)
    other_points: List[SMSPoint] = []
    for start in seed:
        current, last_other = start, None
        for _ in range(max_steps):
            try:
                other = seed_step(current)
            except ValueError:
                break
            if other is None or (outward and last_other is not None and not outward(other, last_other)):
                break
            other_points.append(other)
            last_other = other
            try:
                nxt = other_step(other)
            except ValueError:
                break
            if nxt is None or (outward and not outward(nxt, current)):
                break
            seed_points.append(nxt)
            current = nxt
        else:
            raise RuntimeError(f"grow_sms_chains: a chain did not end within max_steps={max_steps}")
    return seed_points, other_points


# ---------------------------------------------------------------------------
# Targets through a refracting curve: the wavefronts after a surface already built
# ---------------------------------------------------------------------------

def _bisect(f: Callable[[float], float], a: float, b: float, tol: float = 1e-14) -> float:
    """A root of f in [a, b], where f changes sign."""
    fa = f(a)
    if fa == 0.0:
        return a
    if (fa > 0.0) == (f(b) > 0.0):
        raise ValueError("_bisect: no sign change")
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = f(m)
        if fm == 0.0 or b - a < tol:
            return m
        if (fm > 0.0) == (fa > 0.0):
            a, fa = m, fm
        else:
            b = m
    return 0.5 * (a + b)


def curve_through(points: List[Point], normals: List[Point]):
    """A cubic Hermite spline through ``points`` in order, perpendicular to ``normals`` there
    (a ``SplineCurve``, parameter 0 at the first point, 1 at the next...)."""
    from ...core.glass_curves import SplineCurve

    tangents = []
    for k, (n_k) in enumerate(normals):
        t = (-n_k[1], n_k[0])
        a, b = points[max(k - 1, 0)], points[min(k + 1, len(points) - 1)]
        if _dot(t, (b[0] - a[0], b[1] - a[1])) < 0.0:
            t = _neg(t)
        tangents.append(t)
    return SplineCurve(points, tangents, 0.0, float(len(points) - 1))


class RefractedEikonal:
    """
    The optical path from a source to a point P through one refracting curve, and the ray's
    direction at P: the eikonal of the source's wavefront after the curve.

    An SMS chain targets a point (ccoptpt) or a flat wavefront (coptsl). After a curved surface
    the wavefront is neither; it is carried as what it is, the optical path from the source
    through the curve. Evaluating it at P finds the curve point X where the source's ray,
    refracted, passes through P: a one-dimensional root in the curve's parameter, scanned over
    each knot span and refined. (Chaves Ch. 9 section 9.7: the wavefronts w3 and w4 of the
    rays from the receiver edges R1 and R2 "propagated through the cavity", and the input
    wavefronts w1 and w2 after the RXI's top surface.)

    Args:
        curve: The refracting curve (a ``Curve`` of ``core.glass_curves``: ``point``, ``deriv``,
            ``line_hits``), traversed from parameter ``s_range[0]`` to ``s_range[1]``.
        source: ``("point", S0)`` for rays from the point S0, or ``("plane", v)`` for a flat
            wavefront travelling along the unit vector v (its optical path to X is n1 v.X, up to
            a constant that cancels in every SMS path-length difference).
        n1, n2: Refractive indices before and after the curve.
        side: +1 if the n2 medium lies on the left of the curve's traversal, -1 if on its
            right. A ray that meets the curve from the n2 side is not one of this source's
            rays there, and is skipped.
        s_range: The part of the curve the rays may cross (default: all of it).

    A ray counts only if it meets the curve once: from a point source to X and from X to P
    the segment crosses the curve nowhere else. Where several rays reach P (a fold in the
    wavefront), ``hint`` picks the one crossing nearest it; without one, the shortest path.
    """

    def __init__(self, curve, source, n1: float, n2: float, side: float = 1.0,
                 s_range: Optional[Tuple[float, float]] = None, per_span: int = 16) -> None:
        if source[0] not in ("point", "plane"):
            raise ValueError(f"RefractedEikonal: source is ('point', P) or ('plane', v), got {source[0]!r}")
        self.curve, self.source, self.n1, self.n2, self.side = curve, source, n1, n2, side
        self.lo, self.hi = s_range if s_range is not None else (min(curve.p_start, curve.p_end),
                                                                max(curve.p_start, curve.p_end))
        self.per_span = per_span
        self._last: Optional[float] = None

    def _arrival(self, X: Point) -> Tuple[Point, float]:
        kind, s0 = self.source
        if kind == "point":
            d = (X[0] - s0[0], X[1] - s0[1])
            return _nrm(d), self.n1 * math.hypot(*d)
        return s0, self.n1 * _dot(X, s0)

    def normal(self, s: float) -> Point:
        d = self.curve.deriv(s)
        return _nrm((-d[1], d[0]))

    def refracted(self, s: float) -> Tuple[Point, Optional[Point], float]:
        """The curve point at s, the source's ray refracted there (None if it meets the curve
        from the n2 side), and the optical path to the curve point."""
        X = self.curve.point(s)
        d, opl = self._arrival(X)
        nn = self.normal(s)
        if _dot(d, nn) * self.side <= 0.0:
            return X, None, opl
        return X, rfr(_neg(d), nn if _dot(d, nn) > 0.0 else _neg(nn), self.n1, self.n2), opl

    def _clear(self, X: Point, P: Point, s: float) -> bool:
        segments = [(X, P)]
        if self.source[0] == "point":
            segments.append((self.source[1], X))
        for a, b in segments:
            for t, p in self.curve.line_hits(a, (b[0] - a[0], b[1] - a[1])):
                if 1e-7 < t < 1.0 - 1e-7 and abs(p - s) > 1e-6:
                    return False
        return True

    def _grid(self, lo: float, hi: float) -> List[float]:
        xs, k = [], math.floor(lo)
        while k < hi:
            a, b = max(lo, k), min(hi, k + 1.0)
            if b > a:
                xs.extend(a + (b - a) * j / self.per_span for j in range(self.per_span))
            k += 1
        xs.append(hi)
        return xs

    def rays(self, P: Point, near: Optional[float] = None) -> List[Tuple[float, Point, float]]:
        """The rays reaching P: ``(optical path, unit direction at P, curve parameter)``. With
        ``near``, only those crossing the curve within two knot spans of it."""
        lo, hi = self.lo, self.hi
        if near is not None:
            lo, hi = max(lo, near - 2.0), min(hi, near + 2.0)
        def miss(s: float) -> float:
            X, t, _ = self.refracted(s)
            if t is None:
                raise ValueError
            return t[0] * (P[1] - X[1]) - t[1] * (P[0] - X[0])

        roots, prev = [], None
        for s in self._grid(lo, hi):
            try:
                v = miss(s)
            except ValueError:
                prev = None
                continue
            if v == 0.0 or (prev is not None and (prev[1] > 0.0) != (v > 0.0)):
                roots.append(s if v == 0.0 else _bisect(miss, prev[0], s))
            prev = (s, v)
        for s in (lo, hi):                      # a ray exactly through an end of the range
            try:
                if abs(miss(s)) < 1e-9 and all(abs(s - r) > 1e-9 for r in roots):
                    roots.append(s)
            except ValueError:
                pass
        found = []
        for s in roots:
            X, t, opl = self.refracted(s)
            to_p = (P[0] - X[0], P[1] - X[1])
            if t is not None and _dot(t, to_p) > 0.0 and self._clear(X, P, s):
                found.append((opl + self.n2 * math.hypot(*to_p), _nrm(to_p), s))
        return found

    def __call__(self, P: Point, hint: Optional[float] = None) -> Tuple[float, Point, float]:
        """``(optical path, unit direction at P, curve parameter)`` of the ray reaching P.

        The search looks first within two knot spans of ``hint`` (or, without one, of the last
        ray found: an SMS step asks along one ray, point after nearby point), and over the
        whole curve only if no ray crosses there.

        Raises:
            ValueError: If no ray of the source reaches P through the curve.
        """
        near = hint if hint is not None else self._last
        found = self.rays(P, near) if near is not None else []
        if not found:
            found = self.rays(P)
        if not found:
            raise ValueError("RefractedEikonal: no ray reaches the point through the curve")
        best = min(found, key=lambda f: abs(f[2] - hint)) if hint is not None else min(found)
        self._last = best[2]
        return best


def eikonal_reflect_step(
    known_point: Point,
    known_normal: Point,
    incident: Point,
    path_to_known: float,
    target: Callable[[Point], Tuple[float, Point, float]],
    S: float,
    n: float,
    t_max: float,
    n_scan: int = 64,
) -> Tuple[SMSPoint, float]:
    """
    One SMS step between two reflecting surfaces in one medium of index n, toward a target
    given as an optical path: reflect the ray arriving at ``known_point`` (unit direction
    ``incident``, optical path ``path_to_known`` from its source), and find the point P along
    the reflected ray at which ``path_to_known + n [known, P] + target(P) = S``.

    ``target(P)`` returns ``(optical path from P on, unit direction of the target's ray at P,
    its curve parameter)``, as a ``RefractedEikonal`` does; its ray at P is the light's own
    direction there, reversed. The new normal reflects the ray into it. This is the step of
    Chaves Ch. 9 section 9.7 whose target is a wavefront after a curve ("through the cavity
    to R1"); with a target that is a point it reduces to ccoptpt's.

    The target need not reach every point of the ray (the cavity hides some of the glass from
    a receiver edge). The path-length mismatch is scanned over (0, t_max] where it exists,
    each covered stretch opened at its exact edge, and the first sign change refined: the
    mismatch rises along the ray, by n (1 + cos) >= 0 per unit length.

    Returns:
        ``(new point with its normal, its target's curve parameter)``.

    Raises:
        ValueError: If no point of the ray up to ``t_max`` has the optical path S.
    """
    d = reflect(incident, _orient_toward_travel(known_normal, incident))

    def at(t: float) -> Point:
        return (known_point[0] + d[0] * t, known_point[1] + d[1] * t)

    def mismatch(t: float) -> float:
        return path_to_known + n * t + target(at(t))[0] - S

    def value(t: float) -> Optional[float]:
        """The mismatch at t, or None where the target does not reach."""
        try:
            return mismatch(t)
        except ValueError:
            return None

    ts = [t_max * (k / n_scan) ** 2 for k in range(1, n_scan + 1)]
    prev = None
    for k, t in enumerate(ts):
        v = value(t)
        if v is None:
            prev = None
            continue
        if prev is None and k > 0:
            a, b, vb = ts[k - 1], t, v
            for _ in range(40):             # the edge of the stretch the target reaches
                m = 0.5 * (a + b)
                vm = value(m)
                if vm is None:
                    a = m
                else:
                    b, vb = m, vm
            prev = (b, vb)
        if prev is None:
            prev = (t, v)
            continue
        if (prev[1] < 0.0) != (v < 0.0):
            t0 = _bisect(mismatch, prev[0], t)
            P = at(t0)
            _, ray, s = target(P)
            out = _neg(ray)
            return SMSPoint(P, _nrm((out[0] - d[0], out[1] - d[1]))), s
        prev = (t, v)
    raise ValueError("eikonal_reflect_step: no point of the reflected ray has the optical path S")


class SurfaceLabel(NamedTuple):
    """One designed surface of an SMS element: its labels, role and mechanism, and its points
    (on one side of the symmetry axis; the other side is their mirror image in x)."""

    short: str
    long: str
    role: Optional[object]
    mechanism: Optional[object]
    points: List[Point]


def label_sms_edges(vertices, surfaces, rim: SurfaceLabel, tol: float = 1e-9, axis_x: float = 0.0):
    """Label each edge of an SMS element's outline by the designed surface it lies on.

    Edge i runs from vertex i to vertex i + 1 (the last closes the outline). It belongs to a
    surface when both its ends are among that surface's points, on either side of the axis (the
    vertical line ``x = axis_x``);
    any other edge (one joining two surfaces) is ``rim``'s. A surface drawn as several edges
    numbers them from the axis outward (``N1``, ``N2``...), the same on both halves.

    Returns:
        ``(functional_labels, role_tags, mechanisms)``: by edge index ``{i: (short, long)}`` and
        ``{i: role}``, and by short label ``{short: mechanism}``, as ``BasePrism`` keeps them.
    """
    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    members = []
    for surface in surfaces:
        keys = {key(p) for p in surface.points} | {key((2.0 * axis_x - p[0], p[1])) for p in surface.points}
        members.append((surface, keys))
    n = len(vertices)
    owners = []
    for i in range(n):
        a, b = key(vertices[i]), key(vertices[(i + 1) % n])
        owners.append(next((sf for sf, keys in members if a in keys and b in keys), rim))
    # A surface drawn as several edges numbers them outward from the axis, by the distance of
    # each edge's midpoint from it: the two halves share the numbers, and every edge of one half
    # has its own label, which a revolved half-section needs.
    mid_r = [round(abs((vertices[i][0] + vertices[(i + 1) % n][0]) / 2.0 - axis_x) / tol) for i in range(n)]
    labels, roles, mechanisms = {}, {}, {}
    for sf in {o.short: o for o in owners}.values():
        edges = [i for i in range(n) if owners[i] is sf]
        ranks = {r: k + 1 for k, r in enumerate(sorted({mid_r[i] for i in edges}))}
        for i in edges:
            numbered = len(ranks) > 1
            short = f"{sf.short}{ranks[mid_r[i]]}" if numbered else sf.short
            labels[i] = (short, f"{sf.long}, segment {ranks[mid_r[i]]} from the axis" if numbered else sf.long)
            roles[i] = sf.role
            mechanisms[short] = sf.mechanism
    return labels, roles, mechanisms


def spline_outline(vertices, surfaces, tol: float = 1e-9, axis_x: float = 0.0):
    """An SMS element's polyline outline turned into a glass path whose designed surfaces are
    exact splines.

    Consecutive vertices that lie on one designed surface (either half; a surface given as the
    points of one side) become a single spline edge through them, its tangents the chain's
    normals turned by 90 degrees (``collimator_design.spline_descriptor``), so the edge passes
    through every chain point with the chain's own normal there. A point without a chain normal
    (a corner added by the assembly) takes its tangent from its neighbours. Any other edge (one
    joining two surfaces) stays straight. A surface is split where it turns sharply (a corner,
    such as the direct RXI's top at C): a smooth spline across a corner would overshoot it.

    Args:
        vertices: The polyline outline, in order.
        surfaces: Per designed surface, its points: ``SMSPoint`` (with normals) or bare points.
        tol: How close a vertex must be to a surface point to be on it.
        axis_x: The element's axis, the vertical line its halves are mirror images about.

    Returns:
        The path: ``{"x", "y", "arc": False}`` per vertex kept, with ``"curve"`` on a spline
        edge's first vertex.
    """
    from ..lenses.collimator_design import spline_descriptor  # noqa: PLC0415

    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    member, normal = {}, {}
    for k, surface in enumerate(surfaces):
        for q in surface:
            pt, nv = (q.p, q.n) if isinstance(q, SMSPoint) else (q, None)
            for mx in (1.0, -1.0):
                kk = key((axis_x + mx * (pt[0] - axis_x), pt[1]))
                member.setdefault(kk, k)
                if nv is not None:
                    normal.setdefault(kk, (mx * nv[0], nv[1]))
    n = len(vertices)
    owner = [member.get(key(v)) for v in vertices]
    start = next((i for i in range(n) if owner[i] != owner[i - 1]), None)
    if start is None:
        if owner[0] is None:              # no designed surface at all: keep it as it is
            return [{"x": float(x), "y": float(y), "arc": False} for x, y in vertices]
        # every vertex on one surface (a lens closed by one straight edge, the XR's dielectric):
        # the surface runs from the first vertex to the last, and the closing edge stays straight
        start = 0
    order = [(start + i) % n for i in range(n)]
    runs, cur = [], [order[0]]
    for i in order[1:]:
        if owner[i] is not None and owner[i] == owner[cur[-1]]:
            cur.append(i)
        else:
            runs.append(cur)
            cur = [i]
    runs.append(cur)
    def corner(pts, j) -> bool:
        """Whether the surface turns sharply at its interior point j: a chord to a neighbour more
        than 30 degrees off the tangent the chain's normal there gives, or, without a normal,
        the chords turning by more than 30 degrees."""
        a, p, b = pts[j - 1], pts[j], pts[j + 1]
        c1, c2 = (p[0] - a[0], p[1] - a[1]), (b[0] - p[0], b[1] - p[1])
        l1, l2 = math.hypot(*c1), math.hypot(*c2)
        nv = normal.get(key(p))
        if nv is not None:
            ln = math.hypot(*nv)
            return any(abs(c[0] * nv[0] + c[1] * nv[1]) / (lc * ln) > 0.5 for c, lc in ((c1, l1), (c2, l2)))
        return (c1[0] * c2[0] + c1[1] * c2[1]) / (l1 * l2) < math.cos(math.radians(30.0))

    pieces = []                           # each run split at its corners; a corner ends one piece, starts the next
    for run in runs:
        pts = [vertices[i] for i in run]
        cur = [run[0]]
        for j in range(1, len(run)):
            cur.append(run[j])
            if j < len(run) - 1 and corner(pts, j):
                pieces.append(cur)
                cur = [run[j]]
        pieces.append(cur)
    path = []
    for k, run in enumerate(pieces):
        if k + 1 < len(pieces) and pieces[k + 1][0] == run[-1]:
            run_end_shared = True         # the next piece starts at this piece's last point
        else:
            run_end_shared = False
        pts = [vertices[i] for i in run]
        if len(run) >= 3 and owner[run[0]] is not None:
            nrms = []
            for j, q in enumerate(pts):
                nv = normal.get(key(q))
                if nv is None:                # from the neighbours: the chord turned by 90 degrees
                    a, b = pts[max(j - 1, 0)], pts[min(j + 1, len(pts) - 1)]
                    nv = (-(b[1] - a[1]), b[0] - a[0])
                nrms.append(nv)
            path.append({"x": float(pts[0][0]), "y": float(pts[0][1]), "arc": False,
                         "curve": spline_descriptor([tuple(map(float, q)) for q in pts], nrms)})
            if not run_end_shared:
                path.append({"x": float(pts[-1][0]), "y": float(pts[-1][1]), "arc": False})
        else:
            path.extend({"x": float(q[0]), "y": float(q[1]), "arc": False}
                        for q in (pts[:-1] if run_end_shared else pts))
    return path


__all__ = ['RefractedEikonal', 'SMSPoint', 'SurfaceLabel', 'build_sms_chain', 'curve_through',
           'eikonal_reflect_step', 'grow_sms_chains', 'label_sms_edges', 'reflect', 'seed_arc',
           'sms_chain_step', 'spline_outline']
