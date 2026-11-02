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
from typing import ClassVar, List, Optional, Tuple

from .base_prism import BasePrism
from .nonimaging_geometry import Point, ccoptpt, hyp, rfr
from .sms_chain import (
    SMSPoint,
    _orient_toward_travel,
    _resolve_new_normal,
    build_sms_chain,
    sms_chain_step,
)


def _nrm(v: Point) -> Point:
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


def _neg(v: Point) -> Point:
    return (-v[0], -v[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


class RRLens(BasePrism):
    """
    RR SMS lens (Chaves Ch. 9 §9.2): two refractive surfaces designed
    together so E1->R2 and E2->R1 (crossed condition). Single Glass
    polygon: the N-surface (top) and X-surface (bottom), each grown from
    a seed hyperbola point via a short ccoptpt() fan (Chaves Ch. 9 eq.
    9.58-9.66) and then the shared sms_chain_step()/build_sms_chain()
    ping-pong engine out to the symmetry axis, mirrored to complete the
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
    ) -> None:
        self.e1, self.e2, self.r1, self.r2 = e1, e2, r1, r2
        self.n_lens = n
        self.etendue = etendue
        self.seed_n_angle_deg = seed_n_angle_deg
        self.seed_x_angle_deg = seed_x_angle_deg
        self.n_points_per_section = n_points_per_section

        (
            self.seed_N, self.seed_X, self.n_seed_N, self.n_seed_X,
            self.S_NR1, self.S_XE1, self.CO_1, self.CO_2,
            n_surface_points, x_surface_points,
        ) = self._build_profile()

        vertices = self._assemble_vertices(n_surface_points, x_surface_points)

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
        self.path = [{'x': x, 'y': y, 'arc': False} for x, y in vertices]
        self._functional_labels = {
            i: (str(i), f"Edge {i}") for i in range(len(vertices))
        }
        self._vertex_labels = {
            i: (str(i), f"Vertex {i}") for i in range(len(vertices))
        }
        self.auto_label_cardinal()
        if name is not None:
            self.name = name

    def _build_profile(self):
        """
        Build the right half of both surfaces: seed hyperbola points N/X
        (eq. 9.13-9.14 via hyp()), the two short ccoptpt() fans CO_1/CO_2
        (eq. 9.58-9.66), then the sms_chain ping-pong out to the symmetry
        axis (eq. 1877's own X13->N13-style alternation, generalized via
        build_sms_chain()).
        """
        e1, e2, r1, r2, n = self.e1, self.e2, self.r1, self.r2, self.n_lens
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

        # --- Ping-pong to the axis (eq. ~1877's X13->N13, generalized) ---
        # Growing from CO_1's far end (on the X-surface) using rays from
        # R2 targeting E1 produces new N-surface points; growing from
        # CO_2's far end (on the N-surface) using rays from E2 targeting
        # R1 produces new X-surface points. Alternate, tracking optical
        # path lengths S_RE1/S_ER2 (Chaves Ch. 9) that stay
        # constant for the whole outward chain on each surface.
        S_RE1 = math.hypot(*_sub(r2, X)) + n * math.hypot(*_sub(X, CO_2[-1].p)) + math.hypot(*_sub(CO_2[-1].p, e1))
        S_ER2 = S_RE1  # by symmetry, Chaves Ch. 9

        # build_sms_chain's own tag convention: 'seed' = the surface its
        # own `seed` argument lives on, 'other' = the alternate surface.
        # CO_1 (the X-surface fan) is the seed here, so 'seed' == X-surface,
        # 'other' == N-surface throughout this step_fn.
        def step_fn(current: SMSPoint, tag: str):
            if tag == 'seed':
                # On the X-surface: ray from R2, target E1 -> new N-surface point.
                S = S_RE1 - math.hypot(*_sub(r2, current.p))
                new = sms_chain_step(
                    known_point=current.p, known_normal=current.n, ray_source=r2,
                    n_before=1.0, n_after=n, target=e1, target_n=None, n_target=1.0,
                    S=S, mechanism='refract', new_mechanism='refract',
                )
                return new, 'other'
            else:
                # On the N-surface: ray from E2, target R1 -> new X-surface point.
                S = S_ER2 - math.hypot(*_sub(e2, current.p))
                new = sms_chain_step(
                    known_point=current.p, known_normal=current.n, ray_source=e2,
                    n_before=1.0, n_after=n, target=r1, target_n=None, n_target=1.0,
                    S=S, mechanism='refract', new_mechanism='refract',
                )
                return new, 'seed'

        n_surface_points = [CO_2[k] for k in range(len(CO_2))]
        x_surface_points = [CO_1[k] for k in range(len(CO_1))]

        seed_for_chain = [CO_1[-1]]
        try:
            grown_x, grown_n = build_sms_chain(
                seed=seed_for_chain,
                step_fn=step_fn,
                stop_condition=lambda p: p.p[0] <= 0.0,
                max_steps=200,
            )
        except RuntimeError:
            grown_x, grown_n = [CO_1[-1]], []

        # grown_x (the 'seed'/X-surface list) includes the seed point again
        # at index 0 -- drop it. grown_n is the 'other'/N-surface list.
        x_surface_points.extend(grown_x[1:])
        n_surface_points.extend(grown_n)

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
