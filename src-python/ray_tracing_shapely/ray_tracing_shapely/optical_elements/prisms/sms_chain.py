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


__all__ = ['SMSPoint', 'reflect', 'sms_chain_step', 'seed_arc', 'build_sms_chain']
