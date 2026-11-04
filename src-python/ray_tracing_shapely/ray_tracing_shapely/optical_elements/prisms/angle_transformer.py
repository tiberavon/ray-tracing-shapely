"""
Python-specific module: angle transformer
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
ANGLE TRANSFORMER (mirror composite)
===============================================================================
An air-filled mirror device transforming an acceptance half-angle theta1 into
a (generally smaller) exit half-angle theta2, per Chaves, "Introduction to
Nonimaging Optics" ch. 3, Example 3.3. As theta2 -> 90 deg, the flat mirror
segment shrinks to zero length and the device turns into a CPC.

Not a BasePrism subclass: the device is air-filled with discrete mirror
facets (Mirror line segments), not a single dielectric Glass polygon --
_edge_roles/edge_index dual-labelling doesn't apply the way it does for
DTIRCPrism. A free composite-builder function instead, per
dev_doc/architecture/components/nonimaging_design.md

Geometry (right side; left side is the exact mirror image about x=0):
    E = (exit_width/2, 0), F = (-exit_width/2, 0)   -- exit aperture corners
    P = isl(F, u, E, t)   -- flat mirror EP's far end (eq. 3.22)
    A = parabola_point(phi2)   -- parabola PA's far end, phi2 = -2*theta1
        (independent of theta2 -- the parabola's own angular span is set
        purely by the acceptance angle; theta2 only moves where P sits on it)

`Mirror` has no polyline (p1/p2 only -- core/scene_objs/mirror/mirror.py),
so every Mirror object always reports edge_index=0 in the ray-graph
(_surface_edges, analysis/bidirectional.py). Subdividing the parabolic arc
into n_arc_segments Mirror objects therefore encodes position-along-the-arc
in `surface_name` (f'{name_prefix}_arc_seg{i}'), not edge_index -- a
structurally different mechanism than DTIRCPrism's single-polygon
edge_index-for-free. This class is scoped to the analytic theta2->90deg
limit check (dev_doc/architecture/components/analysis_bidirectional.md), not
wall-position auditing, so a coarse default (n_arc_segments=1, one chord per
arc) is deliberate, not a placeholder to refine later.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

from .nonimaging_geometry import isl
from ..roles import Role

if TYPE_CHECKING:
    from ...core.scene import Scene
    from ...core.scene_objs.mirror.mirror import Mirror

Point = Tuple[float, float]


def _parabola_point(phi: float, F: Point, alpha: float, K: float) -> Point:
    """Point on the parabola with focus F, axis direction alpha, at polar
    parameter phi (see module docstring / Chaves Ch. 3 eq. 3.23)."""
    denom = 1.0 - math.cos(phi)
    if abs(denom) < 1e-9:
        raise ValueError("angle_transformer: phi too close to the parabola's axis direction")
    coeff = K / denom
    return (F[0] + coeff * math.cos(phi + alpha), F[1] + coeff * math.sin(phi + alpha))


def build_angle_transformer(
    scene: 'Scene',
    theta1_deg: float,
    theta2_deg: float,
    exit_width: float = 1.0,
    n_arc_segments: int = 1,
    name_prefix: str = 'angle_xform',
) -> Dict[str, Any]:
    """
    Build an angle transformer's mirror composite in `scene`.

    Args:
        scene: The scene to add the Mirror objects to.
        theta1_deg: Acceptance half-angle (entrance) in degrees, in (0, 90).
        theta2_deg: Exit half-angle in degrees, in (0, 90].
        exit_width: Full width of the exit aperture EF (the book's worked
            example uses 1.0, "exit aperture of dimension 1").
        n_arc_segments: Number of straight Mirror segments approximating
            each side's parabolic arc. Default 1 (single chord) -- see
            module docstring for why this stays coarse by design.
        name_prefix: Base name for the created Mirror objects.

    Returns:
        Dict with:
            'mirrors': List[Mirror], all created Mirror objects.
            'E', 'F': exit aperture corners (right, left).
            'P', 'Q': flat-mirror/parabola junction points (right, left).
            'A', 'B': entrance-side parabola endpoints (right, left).

    Raises:
        ValueError: If theta1_deg/theta2_deg are out of range, or the
            resulting tangent direction is degenerate.
    """
    from ...core.scene_objs.mirror.mirror import Mirror

    if not (0.0 < theta1_deg < 90.0):
        raise ValueError(f"theta1_deg must be in (0, 90), got {theta1_deg}")
    if not (0.0 < theta2_deg <= 90.0):
        raise ValueError(f"theta2_deg must be in (0, 90], got {theta2_deg}")
    if n_arc_segments < 1:
        raise ValueError("n_arc_segments must be >= 1")

    theta1 = math.radians(theta1_deg)
    theta2 = math.radians(theta2_deg)
    half = exit_width / 2.0

    E = (half, 0.0)
    F = (-half, 0.0)

    beta = math.pi / 2 - theta2
    u = (math.cos(beta), math.sin(beta))
    alpha = math.pi / 2 + theta1
    v = (math.cos(alpha), math.sin(alpha))

    tx, ty = u[0] + v[0], u[1] + v[1]
    t_norm = math.hypot(tx, ty)
    if t_norm < 1e-9:
        raise ValueError(
            "angle_transformer: degenerate tangent direction for this "
            "theta1_deg/theta2_deg combination"
        )
    t = (tx / t_norm, ty / t_norm)

    P = isl(F, u, E, t)
    Q = (-P[0], P[1])

    dx, dy = P[0] - F[0], P[1] - F[1]
    dist_PF = math.hypot(dx, dy)
    K = dist_PF - (dx * v[0] + dy * v[1])
    if K <= 0:
        raise ValueError(
            "angle_transformer: degenerate parabola (K <= 0) for this "
            "theta1_deg/theta2_deg combination"
        )

    phi1 = math.atan2(dy, dx) - alpha
    phi2 = -2.0 * theta1
    A = _parabola_point(phi2, F, alpha, K)
    B = (-A[0], A[1])

    mirrors: List['Mirror'] = []

    def _make_mirror(p1: Point, p2: Point, name: str) -> 'Mirror':
        m = Mirror(scene)
        m.p1 = {'x': p1[0], 'y': p1[1]}
        m.p2 = {'x': p2[0], 'y': p2[1]}
        m.name = name
        m.role = Role.WALL
        scene.add_object(m)
        mirrors.append(m)
        return m

    _make_mirror(E, P, f'{name_prefix}_flat_right')
    arc_pts_right: List[Point] = [P]
    for i in range(1, n_arc_segments + 1):
        frac = i / n_arc_segments
        phi = phi1 + frac * (phi2 - phi1)
        arc_pts_right.append(_parabola_point(phi, F, alpha, K) if i < n_arc_segments else A)
    for i in range(n_arc_segments):
        _make_mirror(arc_pts_right[i], arc_pts_right[i + 1], f'{name_prefix}_arc_right_seg{i}')

    _make_mirror(F, Q, f'{name_prefix}_flat_left')
    arc_pts_left = [(-x, y) for x, y in arc_pts_right]
    for i in range(n_arc_segments):
        _make_mirror(arc_pts_left[i], arc_pts_left[i + 1], f'{name_prefix}_arc_left_seg{i}')

    return {'mirrors': mirrors, 'E': E, 'F': F, 'P': P, 'Q': Q, 'A': A, 'B': B}


__all__ = ['build_angle_transformer']
