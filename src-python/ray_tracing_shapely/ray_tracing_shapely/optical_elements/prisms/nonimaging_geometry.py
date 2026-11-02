"""
Python-specific module: nonimaging geometry
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
NONIMAGING GEOMETRY PRIMITIVES
===============================================================================
General 2-D ray-geometry primitives used throughout Chaves, "Introduction to
Nonimaging Optics" ch. 3's worked examples, and by the RXI's iterative surface
construction (ch. 9): line intersection, vector-form Snell refraction, and the
constant-optical-path-length point construction the string method generalizes
to. Also includes ch. 21's coptsl/ccoptpt/dcoptpt/rfnrm/rfxnrm for the RXI
direct method's (ch. 9, §9.7) wavefront-referenced and inverse-normal
constructions.

These are distinct from prism_utils.py/tir_utils.py, which are
refractometer-specific closed-form angle formulas for a flat-faced trapezoid.

Conventions (matching the book's own `isl`/`rfr`/`coptpt` notation):
- Points and directions are (x, y) tuples. Directions passed to rfr/coptpt
  must be unit vectors.
- rfr(v, n_surf, n1, n2): `v` is the direction from the hit point back toward
  the incident ray's origin (i.e. the negative of the direction of travel),
  and `n_surf` is the surface normal pointing into the medium being entered
  (n2). This matches the book's own calling convention, e.g.
  `rfr(-v2, -P1, 1, n)` in Chaves Ch. 3 eq. 3.41, where `-P1` is explicitly
  defined there as "the normal to the receiver entrance aperture at P1."
===============================================================================
"""

from __future__ import annotations

import math
from typing import Callable, Optional, Tuple

Point = Tuple[float, float]


def isl(P: Point, u: Point, Q: Point, v: Point) -> Point:
    """
    Intersection of line P + t*u with line Q + s*v.

    Args:
        P: A point on the first line.
        u: Direction of the first line.
        Q: A point on the second line.
        v: Direction of the second line.

    Returns:
        The (x, y) intersection point.

    Raises:
        ValueError: If the two lines are parallel (no unique intersection).
    """
    px, py = P
    ux, uy = u
    qx, qy = Q
    vx, vy = v
    denom = ux * vy - uy * vx
    if abs(denom) < 1e-12:
        raise ValueError("isl: parallel lines, no unique intersection")
    t = ((qx - px) * vy - (qy - py) * vx) / denom
    return (px + t * ux, py + t * uy)


def rfr(v: Point, n_surf: Point, n1: float, n2: float) -> Optional[Point]:
    """
    Vector-form Snell refraction.

    Args:
        v: Direction from the hit point back toward the incident ray's
            origin (i.e. minus the direction of travel). Must be a unit
            vector.
        n_surf: Surface normal pointing into the medium being entered (n2).
            Must be a unit vector.
        n1: Refractive index of the medium the ray is leaving.
        n2: Refractive index of the medium the ray is entering.

    Returns:
        Unit direction of the refracted ray (continuing forward, i.e. the
        actual direction of travel past the surface), or None on total
        internal reflection.
    """
    # I: actual direction of travel: I = -v. N: outward normal (opposing I): N = -n_surf.
    Ix, Iy = -v[0], -v[1]
    Nx, Ny = -n_surf[0], -n_surf[1]
    eta = n1 / n2
    cos_i = -(Ix * Nx + Iy * Ny)
    sin2_t = eta * eta * (1.0 - cos_i * cos_i)
    if sin2_t > 1.0:
        return None  # total internal reflection
    cos_t = math.sqrt(1.0 - sin2_t)
    k = eta * cos_i - cos_t
    return (eta * Ix + k * Nx, eta * Iy + k * Ny)


def coptpt(P: Point, v: Point, focus: Point, n: float, S: float) -> Point:
    """
    Constant-optical-path-length point.

    Finds Q = P + t*v (t > 0, the smallest such t) such that
    n*(|P-Q| + |Q-focus|) == S -- i.e. Q is the point along the ray from P
    in direction v, in a medium of index n, at which the remaining optical
    path length to `focus` brings the total from P to exactly S. Used
    throughout ch. 3's string-method constructions and, in substance, by the
    RXI's iterative surface calculation (ch. 9, §9.6).

    Args:
        P: Starting point.
        v: Unit direction of the ray from P.
        focus: The point the remaining path length is measured to.
        n: Refractive index of the medium (weights both legs of the path).
        S: The constant total optical path length (already net of any
            preceding segment, e.g. S - [P, W] for a wavefront point W).

    Returns:
        The (x, y) point Q.

    Raises:
        ValueError: If no t > 0 solves the equation (S is unreachable
            with the given geometry).
    """
    px, py = P
    vx, vy = v
    fx, fy = focus
    dx0, dy0 = px - fx, py - fy

    # n*t + n*sqrt((dx0+t*vx)^2 + (dy0+t*vy)^2) == S
    # => sqrt(...) == S/n - t == A - t, with A = S/n
    A = S / n
    a = (vx * vx + vy * vy) - 1.0  # == 0 exactly when v is a unit vector
    b = 2.0 * (dx0 * vx + dy0 * vy) + 2.0 * A
    c = (dx0 * dx0 + dy0 * dy0) - A * A

    if abs(a) < 1e-12:
        # The (unit-vector) case that always applies in practice: linear.
        if abs(b) < 1e-12:
            raise ValueError("coptpt: degenerate, no solution for t")
        roots = [-c / b]
    else:
        disc = b * b - 4 * a * c
        if disc < 0:
            raise ValueError("coptpt: no real solution for t")
        sq = math.sqrt(disc)
        roots = [(-b + sq) / (2 * a), (-b - sq) / (2 * a)]

    positive_roots = [t for t in roots if t > 1e-9]
    if not positive_roots:
        raise ValueError("coptpt: no t > 0 solves the equation")
    t = min(positive_roots)
    return (px + t * vx, py + t * vy)


def coptsl(F: Point, v: Point, Q: Point, n_wave: Point, n1: float, n2: float, S: float) -> Point:
    """
    Constant-optical-path-length point against a plane wavefront (eq. 21.159).

    Finds P = F + t*v (t > 0) such that n1*[F,P] + n2*s == S, where s is the
    signed distance from P to the plane wavefront defined by point Q and unit
    normal n_wave (pointing in the direction of propagation, away from F) --
    i.e. the point along the ray from F, in a medium of index n1, at which
    the remaining optical path length to the wavefront (in a medium of index
    n2) totals S.

    Direct closed-form solve (eq. 21.159, no quadratic -- s is linear in t
    unlike coptpt's/ccoptpt's point-focus case):
        s = (Q - P).n_wave = (Q - F - t*v).n_wave
        n1*t + n2*((Q-F).n_wave - t*(v.n_wave)) == S
        t = (S - n2*(Q-F).n_wave) / (n1 - n2*(v.n_wave))

    Args:
        F: Starting point.
        v: Unit direction of the ray from F.
        Q: A point on the target plane wavefront.
        n_wave: Unit normal of the wavefront, pointing in the direction of
            propagation (away from F).
        n1: Refractive index of the medium the ray travels through from F.
        n2: Refractive index of the medium on the far side of the wavefront
            (weights the s term -- matches the book's S = n1*t + n2*s).
        S: The constant total optical path length.

    Returns:
        The (x, y) point P.

    Raises:
        ValueError: If v is parallel to the wavefront (n1 - n2*(v.n_wave) == 0,
            no solution) or the solution has t <= 0.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 21 "Plane Curves", eq. 21.159 (Section 21.13/21.15).
    """
    fx, fy = F
    vx, vy = v
    qx, qy = Q
    nwx, nwy = n_wave

    denom = n1 - n2 * (vx * nwx + vy * nwy)
    if abs(denom) < 1e-12:
        raise ValueError("coptsl: v is parallel to the wavefront, no solution for t")

    q_minus_f_dot_nw = (qx - fx) * nwx + (qy - fy) * nwy
    t = (S - n2 * q_minus_f_dot_nw) / denom
    if t <= 1e-9:
        raise ValueError("coptsl: no t > 0 solves the equation")
    return (fx + t * vx, fy + t * vy)


def _cartesian_oval_general(
    F: Point, n1: float, v: Point, G: Point, n2: float, S: float,
    converging: bool, fn_name: str,
) -> Point:
    """
    Shared quadratic solve for ccoptpt()/dcoptpt() (eq. 21.152-21.154):
    P = F + t*v (t > 0) with
        n1*[F,P] + n2*[P,G] == S  (converging, eq. 21.156)
        n1*[F,P] - n2*[P,G] == S  (diverging, eq. 21.157)

    Both cases reduce, after moving the n2*[P,G] term to the other side and
    squaring, to the same quadratic in t:
        (n1^2-n2^2)*t^2 - 2*C1*t + C2 == 0
        C1 = n1*S + n2^2*(F-G).v
        C2 = S^2 - n2^2*(F-G).(F-G)
        t = (C1 +/- sqrt(C1^2 - (n1^2-n2^2)*C2)) / (n1^2-n2^2)

    (matching eq. 21.153's C1/C2 and the delta=+/-1 root choice). Squaring
    can introduce spurious roots where the un-squared residual
    (S - n1*t for converging, n1*t - S for diverging) would be negative --
    those are filtered out, since [P,G] = n2*that_residual >= 0 always holds
    for an actual point G at distance [P,G] >= 0.

    When n1 == n2, (n1^2-n2^2) vanishes and the quadratic degenerates to a
    linear equation -- not a true singularity: this is exactly the same
    same-index equation coptpt() already solves (verified algebraically:
    the linear-branch solution here equals coptpt(F, v, G, n, S) term for
    term), so it is solved directly rather than raised as an error.
    """
    fx, fy = F
    gx, gy = G
    vx, vy = v
    dx, dy = fx - gx, fy - gy
    dv = dx * vx + dy * vy
    d2 = dx * dx + dy * dy

    a_coef = n1 * n1 - n2 * n2
    C1 = n1 * S + n2 * n2 * dv
    C2 = S * S - n2 * n2 * d2

    if abs(a_coef) < 1e-12:
        b_lin = 2.0 * C1
        if abs(b_lin) < 1e-12:
            raise ValueError(f"{fn_name}: degenerate, no solution for t")
        t_candidates = [C2 / b_lin]
    else:
        disc = C1 * C1 - a_coef * C2
        if disc < 0:
            raise ValueError(f"{fn_name}: no real solution for t (S unreachable)")
        sq = math.sqrt(disc)
        t_candidates = [(C1 + sq) / a_coef, (C1 - sq) / a_coef]

    valid_ts = []
    for t in t_candidates:
        if t <= 1e-9:
            continue
        residual = (S - n1 * t) if converging else (n1 * t - S)
        if residual < -1e-9:
            continue  # squaring introduced a spurious root
        valid_ts.append(t)

    if not valid_ts:
        raise ValueError(f"{fn_name}: no t > 0 solves the equation")
    t = min(valid_ts)
    return (fx + t * vx, fy + t * vy)


def ccoptpt(F: Point, n1: float, v: Point, G: Point, n2: float, S: float) -> Point:
    """
    General two-index Cartesian-oval point, converging case (eq. 21.152 with
    gamma=1, i.e. eq. 21.156): the point P = F + t*v on the surface that
    refracts a ray from F (medium n1) toward G (medium n2), given the
    optical path length S = n1*[F,P] + n2*[P,G].

    This generalizes coptpt() above to two DIFFERENT refractive indices --
    coptpt(P, v, focus, n, S) is the n1=n2=n degenerate case (eq. 21.158),
    kept as its own function rather than folded into this one because it is
    already shipped, tested, and consumed by dtirc.py with that exact
    signature; this is additive, not a replacement. When n1 == n2, this
    function's quadratic degenerates to that same equation and is solved
    directly (see _cartesian_oval_general docstring) -- it does not raise.

    Quadratic solve per eq. 21.152-21.153 (delta=-1 for n1>n2, +1 for n1<n2):
        C1 = n1*S + n2^2*(F-G).v
        C2 = S^2 - n2^2*(F-G).(F-G)
        t = (C1 + delta*sqrt(C2*(n2^2-n1^2) + C1^2)) / (n1^2 - n2^2)

    Args:
        F: Point source, immersed in medium of index n1.
        n1: Refractive index at F.
        v: Unit direction of the ray from F.
        G: Focus the refracted ray converges to, immersed in medium of index n2.
        n2: Refractive index at G.
        S: Optical path length, S = n1*[F,P] + n2*[P,G].

    Returns:
        The (x, y) point P.

    Raises:
        ValueError: If the discriminant is negative (S unreachable) or no
            candidate root has both t > 0 and a non-negative [P,G] residual.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 21 "Plane Curves", eq. 21.152-21.153, 21.156 (Section 21.15
        item 22), and Ch. 9 "Miñano-Benítez Design Method", §9.7 (e.g.
        "ccoptpt(I, n, v, C, n, S_I)" for the RXI direct method's bottom
        surface).
    """
    return _cartesian_oval_general(F, n1, v, G, n2, S, converging=True, fn_name="ccoptpt")


def dcoptpt(F: Point, n1: float, v: Point, G: Point, n2: float, S: float) -> Point:
    """
    General two-index Cartesian-oval point, diverging case (eq. 21.152 with
    gamma=-1, i.e. eq. 21.157): the point P = F + t*v on the surface that
    refracts a ray from F (medium n1) so it appears to diverge from G
    (medium n2), given S = n1*[F,P] - n2*[P,G].

    Same C1/C2 as ccoptpt (S is substituted differently -- see eq. 21.153),
    delta sign flipped per eq. 21.154's gamma=-1 case.

    Args, returns, raises: mirror ccoptpt() above, with S = n1*[F,P] - n2*[P,G].

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 21 "Plane Curves", eq. 21.152-21.154, 21.157 (Section 21.15
        item 22).
    """
    return _cartesian_oval_general(F, n1, v, G, n2, S, converging=False, fn_name="dcoptpt")


def rfnrm(i: Point, r: Point, n1: float, n2: float) -> Point:
    """
    Recover the unit surface normal from a known incident ray and refracted
    ray (eq. 21.163): n = nrm(n1*i - n2*r).

    Used by the SMS iterative method (ch. 9 §9.6) to back out a new surface
    point's normal once both the incoming and outgoing ray directions at
    that point are already known -- the inverse problem to rfr().

    Args:
        i: Unit incident ray direction (direction of travel, not negated --
            this is the raw book convention, since there is no existing
            rfr()-style pre-negated usage to match here). If pairing this
            with rfr()'s inputs/outputs: i = (-v[0], -v[1]) where v is
            rfr()'s own `v` argument, and r is rfr()'s return value directly
            (already "direction of travel", per rfr()'s own docstring).
        r: Unit refracted ray direction.
        n1: Refractive index of the incident medium.
        n2: Refractive index of the refracted medium.

    Returns:
        Unit normal (x, y). Recovers the surface normal used inside rfr()
        up to an overall sign (n_surf or -n_surf, depending on the sign of
        (eta*cos_i - cos_t) in rfr()'s own construction) -- both point along
        the true surface normal's line, only the "into which medium" sense
        of the sign is not determined by i/r alone.

    Raises:
        ValueError: If n1*i - n2*r is (numerically) zero (i, r, n1, n2 are
            inconsistent with any real refraction).

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 21 "Plane Curves", eq. 21.163 (Section 21.15 item 26). Called
        "rfrnrm" at some worked-example call sites in Ch. 9 (e.g. eq. 9.58,
        9.63) -- the same function under an inconsistent name in the book's
        own prose; §21.15's own function-definitions catalog is treated as
        authoritative here.
    """
    ix, iy = i
    rx, ry = r
    nx, ny = n1 * ix - n2 * rx, n1 * iy - n2 * ry
    mag = math.hypot(nx, ny)
    if mag < 1e-12:
        raise ValueError("rfnrm: i, r, n1, n2 are inconsistent with any real refraction")
    return (nx / mag, ny / mag)


def rfxnrm(i: Point, r: Point) -> Point:
    """
    Recover the unit surface normal from a known incident and reflected ray
    (eq. 21.164): rfnrm(i, r, 1, 1) = nrm(i - r).

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 21 "Plane Curves", eq. 21.164 (Section 21.15 item 27).
    """
    return rfnrm(i, r, 1.0, 1.0)


def hyp(F: Point, G: Point, U: float, n: float) -> Callable[[float], Point]:
    """
    Hyperbola through foci F, G with implied vertex spacing U (eq.
    21.131): returns a function of phi (radians) giving points on the
    hyperbola satisfying n*([P,F] - [P,G]) = U/2 -- the seed locus
    Chaves Ch. 9 eq. 9.13-9.14 uses (e.g. h_E/h_R in Example 9.1,
    Chaves Ch. 9). n scales the foci distance when the
    locus is measured as an optical (not geometric) path-length
    difference; 1.0 for an air-side hyperbola (Example 9.1 uses n=1 for
    both h_E and h_R, since both emitter and receiver sides are in air
    there).

    alpha = angh(G - F) (eq. 21.130) is computed here via atan2, which
    gives an angle coterminal with angh's own arccos-based definition
    (eq. 21.7) -- identical cos/sin, so equivalent inside this formula
    without needing angh's own branch-at-2pi bookkeeping.

    Args:
        F: First focus.
        G: Second focus.
        U: Twice the vertex-spacing constant (Chaves Ch. 9's own
            étendue-style parameter -- see eq. 9.13-9.14).
        n: Refractive index scaling the foci distance (Chaves Ch. 9's medium-scaled formula, no equation number in the
            source -- an inline formula in running text).

    Returns:
        A function phi -> (x, y) tracing the hyperbola.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 21 "Plane Curves", eq. 21.129-21.131 (Section 21.15 item 12);
        Ch. 9 "Miñano-Benítez Design Method", eq. 9.13-9.14, Example 9.1
        (lines 1789-1791, this function's test oracle: h_E/h_R evaluated
        at phi=303.3deg/42.7deg reproduce N/X exactly).
    """
    fx, fy = F
    gx, gy = G
    f = math.hypot(gx - fx, gy - fy)
    alpha = math.atan2(gy - fy, gx - fx)
    numerator = (U / (2.0 * n)) ** 2 - f * f

    def curve(phi: float) -> Point:
        denom = U / n - 2.0 * f * math.cos(phi)
        coeff = numerator / denom
        a = phi + alpha
        return (coeff * math.cos(a) + fx, coeff * math.sin(a) + fy)

    return curve


__all__ = ['isl', 'rfr', 'coptpt', 'coptsl', 'ccoptpt', 'dcoptpt', 'rfnrm', 'rfxnrm', 'hyp']
