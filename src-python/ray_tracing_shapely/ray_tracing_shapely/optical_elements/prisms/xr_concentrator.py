"""
Python-specific module: xr concentrator
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
XR CONCENTRATOR -- Miñano-Benítez XR SMS Optic (Chaves Ch. 9, Example 9.2)
===============================================================================
The XR: a primary mirror in air (X), and below the receiver a dielectric whose
lower face is a refracting surface (R). The receiver R1R2 faces down into the
dielectric. Light from above passes beside the dielectric, reflects off the
primary, and refracts up through R onto the receiver. Rays perpendicular to
wavefront w2 are concentrated onto R1, those perpendicular to w1 onto R2.

Example 9.2's construction (eq. 9.67-9.79), generalized: P0 and its normal on
R, the ray from R2 refracted out there, P1 along it on the primary, the seed
circle Q1P1, then one SMS chain from every point of the circle (the book:
"repeated for all other points of c and then for the new points"):
  - on the primary, a ray of w2 reflects and fixes R's next point, which
    refracts it to R1;
  - on R, a ray from R2 refracts out and fixes the primary's next point, which
    reflects it perpendicular to w1.
The surfaces end as the book's do:
  - R at its first point above the receiver's plane (it closes the dielectric
    there, with a straight top through the receiver's level);
  - the primary where the rays of w2 it reflects stop reaching R.
With the book's parameters, every point of the book's two lists is
reproduced, and no other.

Two objects: the dielectric (this class, a glass) and the primary
(``self.primary``, a ``SplineMirror``, or flat ``Mirror`` segments with
``edges="polyline"``). Both go into the scene: ``self.objects()``.

See dev_doc/architecture/components/nonimaging_design.md
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, List, Optional, Tuple, TYPE_CHECKING

from .base_prism import BasePrism
from .nonimaging_geometry import Point, isl, rfr, rfxnrm
from .sms_chain import SMSPoint, grow_sms_chains, seed_arc, sms_chain_step

if TYPE_CHECKING:
    from ...core.scene import Scene


def _nrm(v: Point) -> Point:
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


class XRConcentrator(BasePrism):
    """
    XR SMS optic (Chaves Ch. 9 §9.4, Example 9.2): a primary mirror (X) in air, and a
    dielectric below the receiver R1R2 whose lower face (R) refracts the primary's light up
    onto it.

    Args:
        r1, r2: The receiver's edges (r1 left of r2, at one height), immersed in the
            dielectric, facing down.
        theta_deg: The acceptance half-angle.
        p0, n0: A point and its normal on R, on the axis below the receiver (Example 9.2:
            (0, -4) and (0, -1)).
        n: The dielectric's refractive index.
        p1_extension: How far P1, the primary's seed point, lies from P0 along the ray from R2
            refracted out there (eq. 9.68's free "10").
        wavefront_offset: How far from P1 the wavefront w1 passes (eq. 9.69's free "15").
        n_points_on_seed_circle: Points on the seed circle Q1P1, both ends included: one chain
            from each (Example 9.2: 6, the book listing five after dropping P1).
        max_steps: A safety bound on each chain's length.
        edges: ``"spline"`` (R and the primary exact splines through their points, with their
            normals) or ``"polyline"``.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press, Ch. 9
        "Miñano-Benítez Design Method", §9.4, eq. 9.33, Figures 9.30-9.36; Example 9.2,
        eq. 9.67-9.79, Figures 9.108-9.110.
    """

    _edge_roles: ClassVar[List[Tuple[str, str]]] = []
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None
    _supports_refinement: ClassVar[bool] = False
    type = 'XRConcentrator'

    def __init__(
        self,
        scene: 'Scene',
        r1: Point,
        r2: Point,
        theta_deg: float,
        p0: Point,
        n0: Point,
        n: float = 1.5,
        p1_extension: float = 10.0,
        wavefront_offset: float = 15.0,
        n_points_on_seed_circle: int = 6,
        max_steps: int = 1000,
        name: Optional[str] = None,
        edges: str = "spline",
    ) -> None:
        if abs(r1[1] - r2[1]) > 1e-12 or r1[0] >= r2[0]:
            raise ValueError("XRConcentrator: r1 and r2 at one height, r1 left of r2")
        if edges not in ("spline", "polyline"):
            raise ValueError(f"edges is 'spline' or 'polyline', got {edges!r}")
        self.r1, self.r2 = r1, r2
        self.theta_deg = theta_deg
        self.p0, self.n0 = p0, n0
        self.n_lens = n
        self._build_profile(p1_extension, wavefront_offset, n_points_on_seed_circle, max_steps)
        vertices = self._assemble_vertices()

        from ...core.scene_objs.glass.glass import Glass
        Glass.__init__(self, scene, json_obj=None)
        self.size = 0.0
        self._position = (0.0, 0.0)
        self._rotation = 0.0
        self._anchor = 'centroid'
        self.refIndex = n
        self.edges = edges
        self.polyline_vertices = vertices
        from ..roles import Mechanism, Role
        if edges == "spline":
            from .sms_chain import spline_outline
            self.path = self._split_where_r_turns(spline_outline(vertices, [self.lens_points]))
            vertices = [(v['x'], v['y']) for v in self.path]
        else:
            self.path = [{'x': x, 'y': y, 'arc': False} for x, y in vertices]
        from .sms_chain import SurfaceLabel, label_sms_edges

        (self._functional_labels, self._edge_role_tags,
         self._edge_mechanisms) = label_sms_edges(vertices, [
            SurfaceLabel("R", "R surface (refracting)", Role.ENTRANCE, Mechanism.REFRACT,
                         [p.p for p in self.lens_points]),
        ], rim=SurfaceLabel("TOP", "Top, at the receiver's level", None, Mechanism.REFRACT, []))
        if edges == "spline" and len(self.path) == 4:
            # R in three pieces of one spline: the cap through the axis, and the zone either side
            # beyond the turn, where the lens curls back toward the axis
            self._functional_labels = {0: ("R2", "R surface (refracting), beyond its turn"),
                                       1: ("R1", "R surface (refracting)"),
                                       2: ("R2", "R surface (refracting), beyond its turn")}
            self._edge_role_tags = {0: Role.ENTRANCE, 1: Role.ENTRANCE, 2: Role.ENTRANCE}
            self._edge_mechanisms = {"R1": Mechanism.REFRACT, "R2": Mechanism.REFRACT}
        # the closing edge joins R's two ends, so both its ends are R's points: it is the top
        top = len(vertices) - 1
        self._functional_labels[top] = ("TOP", "Top, at the receiver's level")
        self._edge_role_tags.pop(top, None)
        self._edge_mechanisms["TOP"] = Mechanism.REFRACT
        self._vertex_labels = {i: (str(i), f"Vertex {i}") for i in range(len(vertices))}
        self.auto_label_cardinal()
        if name is not None:
            self.name = name
        self.primary = self._make_primary(scene, edges)

    def _split_where_r_turns(self, path: List[dict]) -> List[dict]:
        """R as one spline (the path's first edge, then the straight top), cut where its distance
        from the axis peaks on each side, the curve unchanged (each piece the same spline over a
        narrower domain). Revolved, a surface must be single-valued in r: the cap through the
        axis is, and so is each zone beyond the turn, where the lens curls back."""
        desc = path[0].get("curve")
        if len(path) != 2 or not desc or desc.get("type") != "spline":
            return path
        from ...core.glass_curves import SplineCurve
        last = float(len(desc["points"]) - 1)
        curve = SplineCurve(desc["points"], desc["tangents"], 0.0, last)
        cx = 0.5 * (self.r1[0] + self.r2[0])
        turns = []
        for k in range(len(desc["points"]) - 1):
            # dx/du on segment k, a quadratic in u: b + 2 c u + 3 d u^2 (x components)
            _, b, c, d, _ = curve._coef[k]
            qa, qb, qc = 3.0 * d[0], 2.0 * c[0], b[0]
            roots = ([-qc / qb] if abs(qa) < 1e-15 and qb != 0.0 else
                     [(-qb + sgn * math.sqrt(qb * qb - 4 * qa * qc)) / (2 * qa)
                      for sgn in (1.0, -1.0)] if abs(qa) >= 1e-15 and qb * qb >= 4 * qa * qc else [])
            turns += [k + u for u in roots if 1e-9 < u < 1.0 - 1e-9]
        turns = sorted(turns, key=lambda p: curve.point(p)[0])
        if len(turns) != 2 or not curve.point(turns[0])[0] < cx < curve.point(turns[1])[0]:
            return path
        lo, hi = sorted(turns)
        pieces = [(0.0, lo), (lo, hi), (hi, last)]
        out = []
        for p0, p1 in pieces:
            x, y = curve.point(p0)
            out.append({"x": float(x), "y": float(y), "arc": False, "curve": {**desc, "domain": [p0, p1]}})
        out.append(path[1])
        return out

    def objects(self) -> List[Any]:
        """The dielectric and the primary: everything the XR puts into a scene."""
        return [self] + list(self.primary)

    # ------------------------------------------------------------------
    def _build_profile(self, p1_extension, wavefront_offset, n_seed, max_steps) -> None:
        r1, r2, n = self.r1, self.r2, self.n_lens
        th = math.radians(self.theta_deg)
        p0, n0 = self.p0, self.n0
        cx, cy = 0.5 * (r1[0] + r2[0]), r1[1]

        # eq. 9.67-9.71: the ray from R2 refracted out at P0, P1 along it and its normal, the
        # wavefronts, S
        t = rfr(_nrm((r2[0] - p0[0], r2[1] - p0[1])), n0, n, 1.0)
        p1 = (p0[0] + p1_extension * t[0], p0[1] + p1_extension * t[1])
        s1 = (math.cos(math.pi / 2 + th), math.sin(math.pi / 2 + th))
        n1 = rfxnrm(t, s1)
        w1 = (p1[0] + wavefront_offset * s1[0], p1[1] + wavefront_offset * s1[1])
        w2 = (2.0 * cx - w1[0], w1[1])
        v2 = (math.cos(-th), math.sin(-th))
        s2 = (-v2[1], v2[0])
        S = (math.hypot(w1[0] - p1[0], w1[1] - p1[1]) + math.hypot(p1[0] - p0[0], p1[1] - p0[1])
             + n * math.hypot(p0[0] - r2[0], p0[1] - r2[1]))
        self.C = isl((cx, 0.0), (0.0, 1.0), p1, n1)
        self.W1, self.W2, self.S, self.P1 = w1, w2, S, p1

        q1 = (2.0 * cx - p1[0], p1[1])
        seed = seed_arc(q1, (-n1[0], n1[1]), p1, n1, n_seed)

        def mirror_step(X: SMSPoint) -> SMSPoint:
            # a ray of w2 reflects at X; R's point refracts it to R1
            src = isl(X.p, s2, w2, v2)
            return sms_chain_step(X.p, X.n, src, 1.0, 1.0, r1, None, n,
                                  S - math.hypot(X.p[0] - src[0], X.p[1] - src[1]), 'reflect', 'refract')

        def lens_step(L: SMSPoint) -> Optional[SMSPoint]:
            # R ends at its first point above the receiver's plane: the chain stops there
            if L.p[1] > cy:
                return None
            # a ray from R2 refracts out at L; the primary's point reflects it perpendicular to w1
            return sms_chain_step(L.p, L.n, r2, n, 1.0, w1, s1, 1.0,
                                  S - n * math.hypot(r2[0] - L.p[0], r2[1] - L.p[1]), 'refract', 'reflect')

        mirror, lens = grow_sms_chains(seed, mirror_step, lens_step, max_steps=max_steps)
        self.seed_points = seed

        def angle(q: SMSPoint) -> float:          # about the receiver's centre, from straight down
            return math.atan2(-(q.p[0] - cx), -(q.p[1] - cy))

        lens_points = []
        for q in self._left_half(lens, angle):
            lens_points.append(q)
            if q.p[1] > cy:
                break
        end = angle(lens_points[-1])
        def reaches_the_lens(q: SMSPoint) -> bool:
            # the primary is as wide as the w2 rays it reflects reach the lens (a point where a
            # chain found no lens point to reach lies beyond it)
            try:
                return angle(mirror_step(q)) <= end + 1e-12
            except ValueError:
                return False

        mirror_points = [q for q in self._left_half(mirror, angle) if reaches_the_lens(q)]
        # the seed circle's own point on the axis: the primary's half-section starts there
        radius = math.hypot(p1[0] - self.C[0], p1[1] - self.C[1])
        on_axis = SMSPoint((cx, self.C[1] - radius), (0.0, -1.0))
        if not mirror_points or abs(mirror_points[0].p[0] - cx) > 1e-9:
            mirror_points.insert(0, on_axis)
        self.lens_points, self.mirror_points = lens_points, mirror_points

    def _left_half(self, points: List[SMSPoint], angle) -> List[SMSPoint]:
        """The points left of the axis (or on it), each once, from the axis outward. Chains of
        different seed points meet the same points to round-off: those count once."""
        cx = 0.5 * (self.r1[0] + self.r2[0])
        kept: List[SMSPoint] = []
        for q in sorted((q for q in points if q.p[0] <= cx + 1e-9), key=angle):
            if not kept or math.hypot(q.p[0] - kept[-1].p[0], q.p[1] - kept[-1].p[1]) > 1e-7:
                kept.append(q)
        return kept

    def _assemble_vertices(self) -> List[Tuple[float, float]]:
        """Counter-clockwise: R from its left end through P0 to its right end, then the straight
        top back to the left end."""
        cx = 0.5 * (self.r1[0] + self.r2[0])
        left = [q.p for q in self.lens_points]                       # P0 outward
        right = [(2.0 * cx - x, y) for x, y in left if x < cx - 1e-9]
        on_axis = [p for p in left if abs(p[0] - cx) <= 1e-9]
        return list(reversed([p for p in left if p[0] < cx - 1e-9])) + on_axis + right

    def _make_primary(self, scene: 'Scene', edges: str) -> List[Any]:
        cx = 0.5 * (self.r1[0] + self.r2[0])
        left = self.mirror_points                                   # the axis outward
        pts = ([(2.0 * cx - q.p[0], q.p[1]) for q in reversed(left[1:])] + [q.p for q in left])
        normals = ([(-q.n[0], q.n[1]) for q in reversed(left[1:])] + [q.n for q in left])
        from ..roles import Role
        if edges == "spline":
            from ..mirrors.spline import SplineMirror
            return [SplineMirror(scene, pts, normals, name="X", role=Role.WALL)]
        from ...core.scene_objs.mirror.mirror import Mirror
        out = []
        for k, (a, b) in enumerate(zip(pts, pts[1:])):
            m = Mirror(scene)
            m.p1, m.p2 = {'x': a[0], 'y': a[1]}, {'x': b[0], 'y': b[1]}
            m.name = f"X{k}"
            out.append(m)
        return out


__all__ = ['XRConcentrator']
