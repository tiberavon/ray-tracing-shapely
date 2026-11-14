"""
Python-specific module: collimator_design
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
Shared constructions for the LED collimators
===============================================================================
All in a canonical frame: the point source F at the origin, the optical axis
along +x, the section in the half-plane y >= 0 (r = y). Light leaves along +x.

- ``through_flat``: a ray from F refracted by a flat face x = f.
- ``collimating_face``: the face behind a flat one that makes the light from
  F leave parallel (a Cartesian oval, by constant optical path length),
  exact points with exact normals.
- ``ray_through_flat_to``: the ray from F that, after the flat face, passes
  through a given point.
- ``spline_descriptor``: points and normals as a spline glass edge
  (core.glass_curves).
- ``fit_conic``: the best conic through designed points, for a model that
  takes a plain conic.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

from ..prisms.nonimaging_geometry import rfnrm, rfr

XY = Tuple[float, float]
AXIS: XY = (1.0, 0.0)


def unit(v: XY) -> XY:
    length = math.hypot(v[0], v[1])
    return (v[0] / length, v[1] / length)


def dot(a: XY, b: XY) -> float:
    return a[0] * b[0] + a[1] * b[1]


def through_flat(phi: float, n: float, f: float) -> Tuple[XY, XY]:
    """Where the ray from F at ``phi`` (radians from the axis) meets the flat
    face x = f, and its direction inside the glass."""
    i = (math.cos(phi), math.sin(phi))
    q = (f, f * math.tan(phi))
    return q, rfr((-i[0], -i[1]), AXIS, 1.0, n)


def collimating_face(n: float, f: float, thickness: float, phi_max: float,
                     points: int) -> Tuple[List[XY], List[XY]]:
    """The face, ``thickness`` in front of a flat face at x = f, that sends the
    light of F out along the axis: points for ``phi`` from 0 to ``phi_max``
    (evenly spaced) and the unit normals there (pointing out of the glass).

    Constant optical path length: F to the flat (air), s inside (n), then the
    plane wavefront x = const (air). Linear in s, so every point is exact.
    """
    c = (n - 1.0) * thickness                      # the path at phi = 0, net of f
    pts, nrms = [], []
    for k in range(points):
        phi = phi_max * k / (points - 1)
        q, r = through_flat(phi, n, f)
        s = (c - math.hypot(q[0], q[1]) + q[0]) / (n - r[0])
        pts.append((q[0] + s * r[0], q[1] + s * r[1]))
        nrms.append(rfnrm(r, AXIS, n, 1.0))
    return pts, nrms


def ray_through_flat_to(target: XY, n: float, f: float) -> Tuple[float, XY, XY]:
    """The ray from F that, refracted by the flat face x = f, passes through
    ``target`` (in front of the face, y >= 0).

    Returns:
        (phi, the point on the flat face, the direction inside the glass).
    """
    def miss(phi: float) -> float:
        q, r = through_flat(phi, n, f)
        return r[0] * (target[1] - q[1]) - r[1] * (target[0] - q[0])

    lo, hi = 0.0, math.atan2(max(target[1], 0.0), f)
    if miss(lo) * miss(hi) > 0.0:
        if abs(miss(lo)) < 1e-15:
            return 0.0, *through_flat(0.0, n, f)
        raise ValueError(f"no ray from F through the flat face x = {f} reaches {target}.")
    for _ in range(64):                   # halvings past double precision
        mid = 0.5 * (lo + hi)
        if (miss(mid) > 0.0) == (miss(lo) > 0.0):
            lo = mid
        else:
            hi = mid
    phi = 0.5 * (lo + hi)
    return (phi, *through_flat(phi, n, f))


def spline_descriptor(points: Sequence[XY], normals: Sequence[XY]) -> Dict[str, Any]:
    """A spline edge through ``points`` whose normals are ``normals`` (either sign).

    Each tangent is its normal turned by 90 degrees, oriented along the order
    of the points.
    """
    tangents = []
    for k, (nx, ny) in enumerate(normals):
        t = (-ny, nx)
        a, b = (points[k], points[k + 1]) if k + 1 < len(points) else (points[k - 1], points[k])
        if dot(t, (b[0] - a[0], b[1] - a[1])) < 0.0:
            t = (-t[0], -t[1])
        tangents.append(list(unit(t)))
    return {"type": "spline", "points": [list(p) for p in points], "tangents": tangents}


def fit_conic(points: Sequence[XY], vertex_x: float, sense: float = 1.0) -> Tuple[float, float, float]:
    """The conic with its vertex at (vertex_x, 0) closest to ``points``.

    The conic is ``x = vertex_x - sense * z(y)``, ``z = c y^2 / (1 + sqrt(1 - (1 + K) c^2 y^2))``:
    with ``sense = 1`` it bends towards -x away from the axis (a convex front
    face), with ``sense = -1`` towards +x (a convex rear face).

    Returns:
        (R = 1 / c, K, the worst axial distance from a point to the conic).
    """
    data = [(y, sense * (vertex_x - x)) for x, y in points if abs(y) > 0.0]

    def z(y: float, c: float, k: float) -> float:
        root = 1.0 - (1.0 + k) * c * c * y * y
        return c * y * y / (1.0 + math.sqrt(max(root, 0.0)))

    y1, z1 = min(data, key=lambda d: abs(d[0]))
    c, k = 2.0 * z1 / (y1 * y1), -1.0             # curvature from the point nearest the vertex
    for _ in range(60):                            # Gauss-Newton on (c, K), numeric Jacobian
        rows = []
        for y, zz in data:
            f0 = z(y, c, k)
            dc = (z(y, c * (1 + 1e-7), k) - f0) / (c * 1e-7)
            dk = (z(y, c, k + 1e-7) - f0) / 1e-7
            rows.append((dc, dk, zz - f0))
        a11 = sum(r[0] * r[0] for r in rows)
        a12 = sum(r[0] * r[1] for r in rows)
        a22 = sum(r[1] * r[1] for r in rows)
        b1 = sum(r[0] * r[2] for r in rows)
        b2 = sum(r[1] * r[2] for r in rows)
        det = a11 * a22 - a12 * a12
        if det == 0.0:
            break
        step_c, step_k = (a22 * b1 - a12 * b2) / det, (a11 * b2 - a12 * b1) / det
        c, k = c + step_c, k + step_k
        if abs(step_c) < 1e-15 * abs(c) and abs(step_k) < 1e-13:
            break
    worst = max(abs(zz - z(y, c, k)) for y, zz in data)
    return 1.0 / c, k, worst


__all__ = ["AXIS", "collimating_face", "dot", "fit_conic", "ray_through_flat_to",
           "spline_descriptor", "through_flat", "unit"]
