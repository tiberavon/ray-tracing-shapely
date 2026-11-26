"""
Python-specific module: rx concentrator
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
RX CONCENTRATOR -- Miñano-Benítez RX SMS Optic (Chaves Ch. 9, §9.4, eq. 9.34)
===============================================================================
One dielectric: light refracts in at its top surface (R), reflects off its
mirror-coated bottom (X), and reaches the receiver R1R2, immersed in the
glass between them and facing down. Rays perpendicular to wavefront w2 are
concentrated onto R1, rays perpendicular to w1 onto R2.

The construction (Figures 9.38-9.39):
  1. P0 on the axis, on the top surface, a height above the receiver; its
     normal is vertical (symmetry).
  2. The ray r1 of w2 refracts into the glass at P0; P1 lies along it, at a
     chosen depth. n1 reflects it to R1. This fixes the optical path length
     S = [W2, P0] + n[P0, P1] + n[P1, R1] (eq. 9.34), the same from w1 to R2.
  3. The mirror between Q1 (P1's mirror image) and P1 is a circle, centred
     where the axis meets P1's normal line.
  4. From every point of that circle, a chain: a ray from R2 reflects at the
     mirror point and fixes the top's next point, which refracts it out
     perpendicular to w1; a ray of w2 refracts at that top point and fixes
     the mirror's next point, which reflects it to R1; and so on outward.
  5. A chain ends where the surfaces meet: a ray from R2 reflected at the
     mirror no longer rises to the top, or the mirror would rise above the
     top. The top curves down to meet the mirror at the rim.

The chain from Q1 returns to P0 exactly (the symmetric image of r1's path):
a check of the construction, kept in the tests.

See dev_doc/architecture/components/nonimaging_design.md
===============================================================================
"""

from __future__ import annotations

import math
from typing import ClassVar, List, Optional, Tuple, TYPE_CHECKING

from .base_prism import BasePrism
from .nonimaging_geometry import Point, isl, rfr, rfxnrm
from .sms_chain import SMSPoint, grow_sms_chains, seed_arc, sms_chain_step

if TYPE_CHECKING:
    from ...core.scene import Scene


def _nrm(v: Point) -> Point:
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


class RXConcentrator(BasePrism):
    """
    RX SMS optic (Chaves Ch. 9 §9.4, eq. 9.34, Figures 9.37-9.39): a refracting top surface
    (R) and a mirror-coated bottom (X), one dielectric, with the receiver R1R2 immersed
    between them, facing down.

    Args:
        r1, r2: The receiver's edges (r1 left of r2, the same height), immersed in the glass.
        theta_deg: The acceptance half-angle: the bundles perpendicular to w1 and w2 are
            tilted by +theta and -theta from the vertical.
        n: The dielectric's refractive index.
        top_height: How far P0, the top surface's centre, lies above the receiver.
        mirror_depth: How far P1, the mirror's seed point, lies from P0 along the ray
            refracted there (the book's free choice).
        n_seed: Points on the seed circle Q1P1, both ends included: one chain from each.
        max_steps: A safety bound on each chain's length; a chain ends where the surfaces
            meet, well before it.
        edges: ``"spline"`` (each surface one exact spline through its points, with their
            normals) or ``"polyline"``.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press, Ch. 9
        "Miñano-Benítez Design Method", §9.4, eq. 9.34, Figures 9.37-9.39.
    """

    _edge_roles: ClassVar[List[Tuple[str, str]]] = []
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None
    _supports_refinement: ClassVar[bool] = False
    type = 'RXConcentrator'
    #: The constructor's arguments that are positions (a point, or a sequence of points):
    #: what moving the whole element shifts, its directions left as they are.
    placement_points = ('r1', 'r2')

    def __init__(
        self,
        scene: 'Scene',
        r1: Point,
        r2: Point,
        theta_deg: float,
        n: float = 1.5,
        top_height: float = 2.0,
        mirror_depth: float = 12.0,
        n_seed: int = 6,
        max_steps: int = 1000,
        name: Optional[str] = None,
        edges: str = "spline",
    ) -> None:
        if abs(r1[1] - r2[1]) > 1e-12 or r1[0] >= r2[0]:
            raise ValueError("RXConcentrator: r1 and r2 at one height, r1 left of r2")
        if top_height <= 0.0 or mirror_depth <= top_height:
            raise ValueError("RXConcentrator: top_height > 0, and the mirror below the receiver "
                             "(mirror_depth > top_height)")
        self.r1, self.r2 = r1, r2
        self.theta_deg = theta_deg
        self.n_lens = n
        self.top_height = top_height
        self.mirror_depth = mirror_depth

        self._build_profile(n_seed, max_steps)
        vertices = self._assemble_vertices()

        from ...core.scene_objs.glass.glass import Glass
        Glass.__init__(self, scene, json_obj=None)
        self.size = 0.0
        self._position = (0.0, 0.0)
        self._rotation = 0.0
        self._anchor = 'centroid'
        self.refIndex = n
        if edges not in ("spline", "polyline"):
            raise ValueError(f"edges is 'spline' or 'polyline', got {edges!r}")
        self.edges = edges
        self.polyline_vertices = vertices
        cx = 0.5 * (r1[0] + r2[0])                 # the axis: the halves are mirror images about it
        if edges == "spline":
            from .sms_chain import spline_outline
            self.path = spline_outline(vertices, [self.lens_points, self.mirror_points], axis_x=cx)
            vertices = [(v['x'], v['y']) for v in self.path]
        else:
            self.path = [{'x': x, 'y': y, 'arc': False} for x, y in vertices]
        from ..roles import Mechanism, Role
        from .sms_chain import SurfaceLabel, label_sms_edges

        (self._functional_labels, self._edge_role_tags,
         self._edge_mechanisms) = label_sms_edges(vertices, [
            SurfaceLabel("R", "R surface (refracting)", Role.ENTRANCE, Mechanism.REFRACT,
                         [p.p for p in self.lens_points]),
            SurfaceLabel("X", "X surface (mirror-coated)", Role.WALL, Mechanism.REFLECT,
                         [p.p for p in self.mirror_points]),
        ], rim=SurfaceLabel("RIM", "Rim", None, Mechanism.REFRACT, []), axis_x=cx)
        self._vertex_labels = {i: (str(i), f"Vertex {i}") for i in range(len(vertices))}
        self.auto_label_cardinal()
        if name is not None:
            self.name = name
        self._mirrors: List[object] = []   # the coating is the glass's own: X reflects

    # ------------------------------------------------------------------
    def _build_profile(self, n_seed: int, max_steps: int) -> None:
        r1, r2, n = self.r1, self.r2, self.n_lens
        th = math.radians(self.theta_deg)
        cx = 0.5 * (r1[0] + r2[0])
        # The bundles travel down: w2's toward -x (to R1), w1's toward +x (to R2).
        d2 = (-math.sin(th), -math.cos(th))
        d1 = (math.sin(th), -math.cos(th))
        self.d1, self.d2 = d1, d2

        # eq. 9.34: P0, the ray r1 refracted there, P1 and its normal
        P0 = (cx, r1[1] + self.top_height)
        t0 = rfr((-d2[0], -d2[1]), (0.0, -1.0), 1.0, n)
        P1 = (P0[0] + self.mirror_depth * t0[0], P0[1] + self.mirror_depth * t0[1])
        n1 = rfxnrm(t0, _nrm((r1[0] - P1[0], r1[1] - P1[1])))
        # the wavefronts: lines perpendicular to each bundle, through a point up-ray from P0
        lead = self.top_height + self.mirror_depth
        W2 = (P0[0] - lead * d2[0], P0[1] - lead * d2[1])
        W1 = (2.0 * cx - W2[0], W2[1])
        v2 = (-d2[1], d2[0])
        S = lead + n * math.hypot(P1[0] - P0[0], P1[1] - P0[1]) + n * math.hypot(r1[0] - P1[0], r1[1] - P1[1])
        self.P0, self.P1, self.W1, self.W2, self.S = P0, P1, W1, W2, S

        Q1 = (2.0 * cx - P1[0], P1[1])
        nq1 = (-n1[0], n1[1])
        seed = seed_arc(Q1, nq1, P1, n1, n_seed)
        self.C = isl((cx, 0.0), (0.0, 1.0), P1, n1)

        centre = (cx, r1[1])

        def faces(T: SMSPoint, d: Point) -> bool:
            # the top at T faces a bundle travelling along d: d meets its outward side
            out = T.n
            if out[0] * (T.p[0] - centre[0]) + out[1] * (T.p[1] - centre[1]) < 0.0:
                out = (-out[0], -out[1])
            return d[0] * out[0] + d[1] * out[1] < 0.0

        def mirror_step(X: SMSPoint) -> Optional[SMSPoint]:
            # a ray from R2 reflects at X; the top's point refracts it out, perpendicular to w1
            T = sms_chain_step(X.p, X.n, r2, n, n, W1, (-d1[0], -d1[1]), 1.0,
                               S - n * math.hypot(X.p[0] - r2[0], X.p[1] - r2[1]), 'reflect', 'refract')
            # the top ends where it no longer faces both bundles: turned past them, it is in its
            # own shadow
            return T if T.p[1] > X.p[1] and faces(T, d1) and faces(T, d2) else None

        def top_step(T: SMSPoint) -> Optional[SMSPoint]:
            # a ray of w2 refracts at T; the mirror's point reflects it to R1
            src = isl(T.p, (-d2[0], -d2[1]), W2, v2)
            X = sms_chain_step(T.p, T.n, src, 1.0, n, r1, None, n,
                               S - math.hypot(T.p[0] - src[0], T.p[1] - src[1]), 'refract', 'reflect')
            return None if X.p[1] >= T.p[1] else X

        def outward(new: SMSPoint, previous: SMSPoint) -> bool:
            # the chains grow left of the axis: each surface's next point further left
            return new.p[0] < previous.p[0] - 1e-12

        mirror, top = grow_sms_chains(seed, mirror_step, top_step, max_steps=max_steps, outward=outward)
        self.seed_points = seed
        self.mirror_points = self._left_half_outward(mirror)
        self.lens_points = self._left_half_outward(top)

    def _left_half_outward(self, points: List[SMSPoint]) -> List[SMSPoint]:
        """The points on the left of the axis (the chains grow there; the right half is their
        mirror image), each once, from the axis outward."""
        cx = 0.5 * (self.r1[0] + self.r2[0])
        kept, seen = [], set()
        for q in points:
            if q.p[0] > cx + 1e-9:
                continue
            k = (round(q.p[0], 9), round(q.p[1], 9))
            if k not in seen:
                seen.add(k)
                kept.append(q)
        return sorted(kept, key=lambda q: -q.p[0])

    def _assemble_vertices(self) -> List[Tuple[float, float]]:
        """Counter-clockwise: the top from its right rim to its left, then the mirror from its
        left rim to its right; the rims are the short edges where the two meet."""
        cx = 0.5 * (self.r1[0] + self.r2[0])

        def mirrored(p):
            return (2.0 * cx - p[0], p[1])
        top_left = [q.p for q in self.lens_points]                        # axis outward
        mirror_left = [q.p for q in self.mirror_points]                   # axis outward
        top_right = [mirrored(p) for p in top_left if p[0] < cx - 1e-9]
        mirror_right = [mirrored(p) for p in mirror_left if p[0] < cx - 1e-9]
        top_axis = [p for p in top_left if abs(p[0] - cx) <= 1e-9]
        top_left_only = [p for p in top_left if p[0] < cx - 1e-9]
        mirror_left_only = [p for p in mirror_left if p[0] < cx - 1e-9]
        return (list(reversed(top_right)) + top_axis + top_left_only
                + list(reversed(mirror_left_only)) + mirror_right)


__all__ = ['RXConcentrator']
