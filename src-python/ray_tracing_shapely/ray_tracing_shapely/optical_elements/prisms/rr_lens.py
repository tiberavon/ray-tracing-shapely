"""
Python-specific module: rr lens
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
RR LENS -- Miñano-Benítez RR SMS Lens
===============================================================================
Two refractive surfaces designed together with the shared sms_chain engine
(sms_chain.py) so that edge rays from E1/E2 focus onto R2/R1 respectively
(the "crossed" condition). Validated end to end against Chaves,
"Introduction to Nonimaging Optics" ch. 9, Example 9.1 (§9.13, lines
1783-1887) -- the same kind of complete numeric oracle DTIRCPrism/
AngleTransformerPrism were built and tested against.

See dev_doc/architecture/components/nonimaging_design.md
===============================================================================
"""

from __future__ import annotations

import math
from typing import ClassVar, List, Optional, Tuple, TYPE_CHECKING

from .base_prism import BasePrism
from .nonimaging_geometry import Point, ccoptpt, hyp, rfr
from .sms_chain import (
    SMSPoint,
    _orient_toward_travel,
    _resolve_new_normal,
    grow_sms_chains,
    sms_chain_step,
)

if TYPE_CHECKING:
    from ...core.scene import Scene


def _nrm(v: Point) -> Point:
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


def _neg(v: Point) -> Point:
    return (-v[0], -v[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


#: How far from symmetric about one vertical line the edge points may be, in scene units.
_SYMMETRY_TOL = 1e-9


def _axis(e1: Point, e2: Point, r1: Point, r2: Point) -> float:
    """The x of the vertical line E1/E2 and R1/R2 are mirror images about, or ValueError."""
    x0 = (e1[0] + e2[0]) / 2
    off = [abs(e1[1] - e2[1]), abs(r1[1] - r2[1]), abs((r1[0] + r2[0]) / 2 - x0)]
    if max(off) > _SYMMETRY_TOL:
        raise ValueError(
            f"an RR lens is symmetric about a vertical line: E1 and E2 must be mirror images about it, and R1 "
            f"and R2 about the same line (E1 {tuple(e1)}, E2 {tuple(e2)}, R1 {tuple(r1)}, R2 {tuple(r2)}: E1/E2 "
            f"heights differ by {off[0]:.3g}, R1/R2 heights by {off[1]:.3g}, their midlines by {off[2]:.3g})")
    return x0


def _moved(entry: dict, x0: float) -> dict:
    """A path entry moved by x0 along x: its vertex and, on a spline edge, its points (its
    tangents unchanged)."""
    out = dict(entry, x=entry['x'] + x0)
    if entry.get('curve'):
        curve = dict(entry['curve'])
        curve['points'] = [[x + x0, y] for x, y in curve['points']]
        out['curve'] = curve
    return out


class RRLens(BasePrism):
    """
    RR SMS lens (Chaves Ch. 9 §9.2): two refractive surfaces designed
    together so E1->R2 and E2->R1 (crossed condition). Single Glass
    polygon: the N-surface (top) and X-surface (bottom), each grown from
    a seed hyperbola point via a short ccoptpt() fan (Chaves Ch. 9 eq.
    9.58-9.66) and then the shared sms_chain_step()/grow_sms_chains()
    engine, one chain from every fan point, out to the symmetry axis
    (reproducing the book's 26 points per surface), mirrored to complete the
    lens (Chaves Ch. 9's own "the left half ... is obtained by
    symmetry").

    Args mirror Example 9.1 exactly: e1, e2, r1, r2 (Points), n
    (refractive index), etendue (U). seed_n_angle_deg/seed_x_angle_deg
    (phi on h_E/h_R, degrees) are Example 9.1's own free choice (line
    1795), exposed rather than hidden -- there is no universally "right"
    seed angle for an arbitrary e1/e2/r1/r2/etendue, so this class does
    not default them. n_points_per_section is Example 9.1's own N_p
    (default 5, matching the book's oracle exactly; higher values shrink
    the achieved focus "waist" per the book's own note, line 1887).

    Note on architecture: unlike most BasePrism subclasses, this class's
    geometry is defined by absolute foci (e1/e2/r1/r2), not a relocatable
    size/position/rotation template -- so, like BasePrism.from_vertices()
    (base_prism.py:378), it bypasses BasePrism.__init__()'s own
    rotate-and-recenter machinery (which would otherwise force the
    computed polygon's centroid to (0, 0), silently breaking the exact
    match to Example 9.1's own absolute coordinates) and assigns `path`
    directly.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 9 "Miñano-Benítez Design Method", §9.2 (construction) and
        §9.13 Example 9.1, lines 1783-1887 (this class's test oracle).
    """

    _edge_roles: ClassVar[List[Tuple[str, str]]] = []
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None
    _supports_refinement: ClassVar[bool] = False
    type = 'RRLens'
    #: The constructor's arguments that are positions (a point, or a sequence of points):
    #: what moving the whole element shifts, its directions left as they are.
    placement_points = ('e1', 'e2', 'r1', 'r2')

    def __init__(
        self,
        scene: 'Scene',
        e1: Point,
        e2: Point,
        r1: Point,
        r2: Point,
        seed_n_angle_deg: float,
        seed_x_angle_deg: float,
        n: float = 1.5,
        etendue: float = 1.0,
        n_points_per_section: int = 5,
        name: Optional[str] = None,
        edges: str = "spline",
    ) -> None:
        self.e1, self.e2, self.r1, self.r2 = e1, e2, r1, r2
        # The lens is symmetric about the vertical line through the midpoint of E1 and E2: it is
        # built in that line's frame (the chains stop at its axis, and the left half is the right
        # half's mirror image), then moved back. Edge points that are not symmetric about one
        # vertical line are refused: the construction would build another lens without a word.
        x0 = _axis(e1, e2, r1, r2)
        e1, e2, r1, r2 = ((p[0] - x0, p[1]) for p in (e1, e2, r1, r2))
        self.axis_x = x0
        self.n_lens = n
        self.etendue = etendue
        self.seed_n_angle_deg = seed_n_angle_deg
        self.seed_x_angle_deg = seed_x_angle_deg
        self.n_points_per_section = n_points_per_section

        (
            seed_N, seed_X, self.n_seed_N, self.n_seed_X,
            self.S_NR1, self.S_XE1, CO_1, CO_2,
            n_surface_points, x_surface_points,
        ) = self._build_profile((e1, e2, r1, r2))
        back = lambda q: (q[0] + x0, q[1])  # noqa: E731 -- the lens's frame to the scene's
        local_n, local_x = n_surface_points, x_surface_points
        self.seed_N, self.seed_X = back(seed_N), back(seed_X)
        self.CO_1 = [SMSPoint(back(q.p), q.n) for q in CO_1]
        self.CO_2 = [SMSPoint(back(q.p), q.n) for q in CO_2]

        # the outline and its labels are made in the lens's frame (both read the left half as the
        # right half's mirror about x = 0), and the finished path moved back
        vertices = self._assemble_vertices(local_n, local_x)
        # the right half's points, in the scene's frame (as the chains computed them, moved back)
        n_surface_points = [SMSPoint(back(q.p), q.n) for q in local_n]
        x_surface_points = [SMSPoint(back(q.p), q.n) for q in local_x]
        self.n_surface_points, self.x_surface_points = n_surface_points, x_surface_points

        # Bypass BasePrism.__init__()'s size/position/rotation template --
        # see class docstring. Mirrors BasePrism.from_vertices()'s own
        # construction (base_prism.py:378-437) with dual-labeling applied
        # via numeric edge labels, same as that escape hatch.
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
        self.polyline_vertices = [back(v) for v in vertices]
        if edges == "spline":
            from .sms_chain import spline_outline
            # each designed surface one spline through the chain's points, with the chain's normals
            path = spline_outline(vertices, [local_n, local_x])
            vertices = [(v['x'], v['y']) for v in path]
        else:
            path = [{'x': x, 'y': y, 'arc': False} for x, y in vertices]
        self.path = [_moved(entry, x0) for entry in path]
        from ..roles import Mechanism, Role
        from .sms_chain import SurfaceLabel, label_sms_edges

        # Each designed surface labelled: N faces the emitters E1/E2 (light enters it), X the
        # receiver R1/R2 (light leaves it); an edge joining them is the rim (glass, refracting).
        (self._functional_labels, self._edge_role_tags,
         self._edge_mechanisms) = label_sms_edges(vertices, [
            SurfaceLabel("N", "N surface (facing the emitter)", Role.ENTRANCE, Mechanism.REFRACT,
                         [p.p for p in local_n]),
            SurfaceLabel("X", "X surface (facing the receiver)", Role.EXIT, Mechanism.REFRACT,
                         [p.p for p in local_x]),
        ], rim=SurfaceLabel("RIM", "Rim", None, Mechanism.REFRACT, []))
        self._vertex_labels = {
            i: (str(i), f"Vertex {i}") for i in range(len(vertices))
        }
        self.auto_label_cardinal()
        if name is not None:
            self.name = name

    def _build_profile(self, points):
        """
        Build the right half of both surfaces: seed hyperbola points N/X
        (eq. 9.13-9.14 via hyp()), the two short ccoptpt() fans CO_1/CO_2
        (eq. 9.58-9.66), then the SMS chains out to the symmetry axis, one
        from every fan point (the X13->N13 alternation, generalized via
        grow_sms_chains()).
        """
        (e1, e2, r1, r2), n = points, self.n_lens        # in the lens's own frame: its axis is x = 0
        Np = self.n_points_per_section

        h_E = hyp(e1, e2, self.etendue, 1.0)
        h_R = hyp(r1, r2, self.etendue, 1.0)
        N = h_E(math.radians(self.seed_n_angle_deg))
        X = h_R(math.radians(self.seed_x_angle_deg))

        # --- CO_1 (X-surface fan), eq. 9.58-9.62 ---
        s1 = _nrm(_sub(N, e1))
        t1 = _nrm(_sub(X, N))
        n_N = _resolve_new_normal(s1, t1, 1.0, n, 'refract')
        s2 = _nrm(_sub(N, e2))
        n_N_oriented = _orient_toward_travel(n_N, s2)
        t2 = rfr(_neg(s2), n_N_oriented, 1.0, n)
        S_NR1 = n * math.hypot(*_sub(N, X)) + math.hypot(*_sub(X, r1))

        CO_1: List[SMSPoint] = []
        for k in range(Np + 1):
            x = k / Np
            t = _nrm((x * t2[0] + (1 - x) * t1[0], x * t2[1] + (1 - x) * t1[1]))
            P = ccoptpt(N, n, t, r1, 1.0, S_NR1)
            out_dir = _nrm(_sub(r1, P))
            nn = _resolve_new_normal(t, out_dir, n, 1.0, 'refract')
            CO_1.append(SMSPoint(P, nn))

        # --- CO_2 (N-surface fan), eq. 9.63-9.66 ---
        s1p = _nrm(_sub(X, r1))
        t1p = _nrm(_sub(N, X))
        n_X = _resolve_new_normal(s1p, t1p, 1.0, n, 'refract')
        s2p = _nrm(_sub(X, r2))
        n_X_oriented = _orient_toward_travel(n_X, s2p)
        t2p = rfr(_neg(s2p), n_X_oriented, 1.0, n)
        S_XE1 = n * math.hypot(*_sub(X, N)) + math.hypot(*_sub(N, e1))

        CO_2: List[SMSPoint] = []
        for k in range(Np + 1):
            x = k / Np
            t = _nrm((x * t2p[0] + (1 - x) * t1p[0], x * t2p[1] + (1 - x) * t1p[1]))
            P = ccoptpt(X, n, t, e1, 1.0, S_XE1)
            out_dir = _nrm(_sub(e1, P))
            nn = _resolve_new_normal(t, out_dir, n, 1.0, 'refract')
            CO_2.append(SMSPoint(P, nn))

        # --- The chains to the axis (the X13->N13 alternation, generalized) ---
        # On the X-surface, a ray from R2 toward E1 gives a new N-surface point; on the
        # N-surface, a ray from E2 toward R1 gives a new X-surface point. The optical path
        # lengths S_RE1/S_ER2 (Chaves Ch. 9) are the same for every chain.
        S_RE1 = math.hypot(*_sub(r2, X)) + n * math.hypot(*_sub(X, CO_2[-1].p)) + math.hypot(*_sub(CO_2[-1].p, e1))
        S_ER2 = S_RE1  # by symmetry, Chaves Ch. 9

        # The chains, as the book grows them: one from every point of CO_1 and of CO_2, then
        # from the points they give (Chaves Ch. 9, Example 9.1: "repeated for all the points of
        # X-X1 ... for all the points of N-N1 ... repeated for the new points"). A chain ends at
        # the axis: only the points right of it are kept, the left half being their mirror image.
        def x_to_n(current: SMSPoint) -> Optional[SMSPoint]:
            # on the X-surface: a ray from R2, toward E1 -> a new N-surface point
            new = sms_chain_step(
                known_point=current.p, known_normal=current.n, ray_source=r2,
                n_before=1.0, n_after=n, target=e1, target_n=None, n_target=1.0,
                S=S_RE1 - math.hypot(*_sub(r2, current.p)), mechanism='refract', new_mechanism='refract',
            )
            return new if new.p[0] > 0.0 else None

        def n_to_x(current: SMSPoint) -> Optional[SMSPoint]:
            # on the N-surface: a ray from E2, toward R1 -> a new X-surface point
            new = sms_chain_step(
                known_point=current.p, known_normal=current.n, ray_source=e2,
                n_before=1.0, n_after=n, target=r1, target_n=None, n_target=1.0,
                S=S_ER2 - math.hypot(*_sub(e2, current.p)), mechanism='refract', new_mechanism='refract',
            )
            return new if new.p[0] > 0.0 else None

        x_from_1, n_from_1 = grow_sms_chains(CO_1, x_to_n, n_to_x, max_steps=200)
        n_from_2, x_from_2 = grow_sms_chains(CO_2, n_to_x, x_to_n, max_steps=200)

        def once(points: List[SMSPoint]) -> List[SMSPoint]:
            # chains from different points meet the same points to round-off: those count once
            kept: List[SMSPoint] = []
            for q in sorted(points, key=lambda q: -q.p[0]):
                if not kept or math.hypot(q.p[0] - kept[-1].p[0], q.p[1] - kept[-1].p[1]) > 1e-7:
                    kept.append(q)
            return kept

        n_surface_points = once(n_from_1 + n_from_2)
        x_surface_points = once(x_from_1 + x_from_2)

        return (
            N, X, n_N, n_X, S_NR1, S_XE1, CO_1, CO_2,
            n_surface_points, x_surface_points,
        )

    def _assemble_vertices(
        self, n_surface_points: List[SMSPoint], x_surface_points: List[SMSPoint],
    ) -> List[Tuple[float, float]]:
        """
        Assemble the full symmetric polygon: right-half N-surface (outer
        to axis) + mirrored left-half N-surface + mirrored left-half
        X-surface + right-half X-surface (axis to outer), CCW.
        """
        n_right = [p.p for p in n_surface_points if p.p[0] >= -1e-9]
        x_right = [p.p for p in x_surface_points if p.p[0] >= -1e-9]

        n_right.sort(key=lambda p: -p[0])  # outer -> axis
        x_right.sort(key=lambda p: p[0])   # axis -> outer

        n_left = [(-x, y) for x, y in reversed(n_right)]
        x_left = [(-x, y) for x, y in reversed(x_right)]

        # CCW: start at N-surface outer-right, go to axis, mirror across
        # to N-surface outer-left, down to X-surface outer-left, across
        # to axis, mirror to X-surface outer-right, close.
        vertices = n_right + n_left + x_left + x_right
        return vertices


__all__ = ['RRLens']
