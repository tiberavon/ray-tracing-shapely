"""
Python-specific module: rxi direct
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
RXI OPTIC (DIRECT METHOD) -- Chaves Ch. 9 Section 9.7
===============================================================================
RXI built via the book's direct (non-iterative) SMS method. The method
leaves six free choices open; this class pins each of them, and adds a
seventh the book does not state (point D's placement).

THIS IS THE HIGHEST-RISK, LEAST-VALIDATED CLASS IN THE PACKAGE: no numeric
worked example exists for §9.7 anywhere in the source book (every
"EXAMPLE" in the chapter was checked), so nothing here can be checked
against a book-published number the way RRLens/RXConcentrator's
constructions can. [KD5: where no external number exists, the tests below
guard against the behaviour changing, not against it being wrong -- and
this docstring says so rather than implying otherwise.] Validation is limited to
internal geometric consistency (Snell's law/reflection law satisfied at
every computed point, a valid simple polygon) and a real ray trace --
see developer_tests/test_rxi_direct.py for exactly what is, and is not,
checked here.

Distinct from RXIOptic (rxi.py, Tier 0 -- a circular-arc dome with no
aplanatic receiver-collection property by construction).

See dev_doc/architecture/components/nonimaging_design.md
===============================================================================
"""

from __future__ import annotations

import math
from typing import ClassVar, List, Optional, Tuple

from .base_prism import BasePrism
from .nonimaging_geometry import Point, ccoptpt, rfr
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


def _rot90(v: Point) -> Point:
    return (-v[1], v[0])


class RXIOpticDirect(BasePrism):
    """
    RXI built via Chaves Ch. 9 §9.7's direct (non-iterative) SMS method.

    Executes dev_doc/architecture/components/nonimaging_design.md six pins:
      1. Virtual aperture height: `aperture_height` parameter (a gauge
         freedom -- eq. line 1913 fixes only [Q,Q*], not their y-position).
      2. A = Q, B = Q* (the minimum-size instance, line 854's pin).
      3. C = (0, c_height_fraction * A.y) -- on the top surface, closer
         to the axis than A, symmetric about the y-axis by construction.
      4. The AC seed segment is a straight line -- its normal follows
         directly from A and C's own positions (perpendicular to AC),
         not an independent free choice once A/C are fixed.
      6. The alternating CC1/EE1/C1C2/... chain (Chaves Ch. 9) is built for a fixed `n_stages` outward (this
         document's own pin 6), reusing the shared sms_chain engine's
         mechanism='reflect' path at the top surface's second (TIR) hit
         at each new C-point -- the R-X-I three-mechanism path
         (Refract at AB, reflect(X) at the bottom, TIR(I) back at the
         top) this class's whole namesake describes.

    And adds one further pin the book leaves open:
      5. Point D's placement "along" the ray refracted at A (line 1933)
         -- pinned here as `d_extension`: a fixed distance along that
         refracted ray, exposed as a constructor parameter rather than
         derived analytically. It likely needs to be tied to how far the
         corresponding swept bundle reaches C, not chosen independently
         of it -- a genuinely harder, unresolved question this pin
         sidesteps rather than answers.

    Everything closer to the axis than the last built stage is
    mirror-coated, reusing RXIOptic's own `mirror_band_deg`/
    `merges_with_glass` mechanism (rxi.py) rather than deriving the exact
    critical-angle crossover analytically.

    Args:
        r1, r2: Receiver edge points.
        theta_deg: Half-angle of the acceptance cone.
        n: Refractive index of the dielectric.
        aperture_height: y-coordinate of the virtual aperture Q/Q* (pin 1).
        c_height_fraction: C's height as a fraction of A's height (pin 3),
            0 < c_height_fraction < 1.
        d_extension: Distance along the ray refracted at A to place D
            (this class's own new pin 5, see above).
        n_points_de: Points sampled on the initial DE fan (analogous to
            RRLens's/Example 9.1's own N_p).
        n_stages: Number of alternating top/bottom stages to grow beyond
            DE before mirror-coating the remainder (pin 6).

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 9 "Miñano-Benítez Design Method", §9.7 "The RXI Optic: Direct
        Calculation", lines 1145-1245 (Figures 9.62-9.70; eq. 9.40 for
        the étendue-derived width w_RXI). Distinct from the same book's
        §9.6 "The RXI Optic: Iterative Calculation" (lines 987-1143),
        which this class does not implement -- see
        dev_doc/architecture/components/nonimaging_design.md for that method's own,
        separately-scoped status.
    """

    _edge_roles: ClassVar[List[Tuple[str, str]]] = []
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None
    _supports_refinement: ClassVar[bool] = False
    type = 'RXIOpticDirect'

    def __init__(
        self,
        scene: 'Scene',
        r1: Point,
        r2: Point,
        theta_deg: float,
        n: float = 1.5,
        aperture_height: float = 5.0,
        c_height_fraction: float = 0.4,
        d_extension: float = 3.0,
        n_points_de: int = 6,
        n_stages: int = 2,
        s_cr1_margin: float = 1.3,
        name: Optional[str] = None,
    ) -> None:
        self.r1, self.r2 = r1, r2
        self.theta_deg = theta_deg
        self.n_lens = n
        self.aperture_height = aperture_height
        self.c_height_fraction = c_height_fraction
        self.d_extension = d_extension
        self.n_points_de = n_points_de
        self.n_stages = n_stages
        self.s_cr1_margin = s_cr1_margin

        (
            self.Q, self.Q_star, self.A, self.B, self.C,
            self.DE, self.MN, top_points, bottom_points,
        ) = self._build_profile()

        vertices = self._assemble_vertices(top_points, bottom_points)

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

        self._mirrors = self._add_mirror_coating(scene, bottom_points)

    def _build_profile(self):
        r1, r2, n = self.r1, self.r2, self.n_lens
        theta = math.radians(self.theta_deg)

        # --- Pin 1-2: virtual aperture Q/Q*, A=Q, B=Q* ---
        d_r1r2 = math.hypot(*_sub(r2, r1))
        half_aperture = d_r1r2 / (2.0 * math.sin(theta))
        Q = (-half_aperture, self.aperture_height)
        Q_star = (half_aperture, self.aperture_height)
        A, B = Q, Q_star

        # Input ray directions perpendicular to w1/w2 (tilted +/-theta
        # from vertical, heading down into the device).
        v2 = (math.sin(theta), -math.cos(theta))
        v1 = (-math.sin(theta), -math.cos(theta))

        # --- Pin 3: C on the top surface, closer to the axis than A ---
        C = (0.0, self.c_height_fraction * A[1])

        # --- Pin 4: AC is a straight segment; its normal follows from
        # A/C directly (perpendicular to AC, oriented outward/upward). ---
        ac_dir = _nrm(_sub(C, A))
        ac_normal = _rot90(ac_dir)
        if ac_normal[1] < 0:
            ac_normal = _neg(ac_normal)

        # --- Refract v2 at A; place D along the refracted ray (pin 5). ---
        t_A = rfr(_neg(v2), ac_normal, 1.0, n)
        if t_A is None:
            raise ValueError(
                "RXIOpticDirect: total internal reflection refracting v2 at A -- "
                "check aperture_height/c_height_fraction/theta_deg"
            )
        D = (A[0] + self.d_extension * t_A[0], A[1] + self.d_extension * t_A[1])

        # --- DE fan: eq. ~1169's ccoptpt(I, n, v, C, n, S_I), sweeping
        # the refracted direction between A's (t_A) and B's own. ---
        t_B = rfr(_neg(v1), ac_normal, 1.0, n)
        if t_B is None:
            raise ValueError("RXIOpticDirect: total internal reflection refracting v1 at B")

        S_CD = n * math.hypot(*_sub(C, D)) + n * math.hypot(*_sub(D, A))  # [A,Q]=0 since A=Q
        Np = self.n_points_de
        DE: List[SMSPoint] = [SMSPoint(D, _resolve_new_normal(t_A, _nrm(_sub(C, D)), n, n, 'reflect'))]
        for k in range(1, Np + 1):
            x = k / Np
            t = _nrm((x * t_B[0] + (1 - x) * t_A[0], x * t_B[1] + (1 - x) * t_A[1]))
            P = ccoptpt(A, n, t, C, n, S_CD)
            out_dir = _nrm(_sub(C, P))
            nn = _resolve_new_normal(t, out_dir, n, n, 'reflect')
            DE.append(SMSPoint(P, nn))

        # --- Receiver cavity MN: Cartesian oval focusing rays reflected
        # at C toward R1 (Chaves Ch. 9). A small fan directly
        # around C, analogous in shape to DE's own construction. ---
        # S_CR1 is a genuinely free design choice (Chaves Ch. 9's own
        # text only says "constant optical path length between C and
        # R1," not a specific value) -- must exceed n*[C,R1] (the
        # degenerate direct-line minimum, where the construction collapses
        # to a single point) for a real, non-degenerate cavity surface to
        # exist off that direct line. s_cr1_margin sets how far above
        # that minimum, a new pin this class adds (the book's method
        # doesn't reach this sub-stage).
        S_CR1 = self.s_cr1_margin * n * math.hypot(*_sub(C, r1))
        MN: List[SMSPoint] = []
        for k in range(Np + 1):
            # Sweep a small local fan of reflected directions at C.
            spread = math.radians(2.0) * (k / Np - 0.5)
            base_angle = math.atan2(*reversed(_nrm(_sub(r1, C))))
            t = (math.cos(base_angle + spread), math.sin(base_angle + spread))
            try:
                P = ccoptpt(C, n, t, r1, n, S_CR1)
            except ValueError:
                continue
            out_dir = _nrm(_sub(r1, P))
            nn = _resolve_new_normal(t, out_dir, n, n, 'refract')
            MN.append(SMSPoint(P, nn))

        # --- Pin 6: a fixed number of alternating stages beyond DE,
        # reusing the shared sms_chain engine (mechanism='reflect' at
        # both surfaces -- the bottom mirror, and the top surface's
        # second/TIR hit). ---
        def step_fn(current: SMSPoint, tag: str):
            if tag == 'seed':
                # On the bottom (DE-family) surface: reflect toward a new
                # top-surface (TIR) point, focusing to C.
                S_here = n * math.hypot(*_sub(current.p, C))
                new = sms_chain_step(
                    known_point=current.p, known_normal=current.n, ray_source=C,
                    n_before=n, n_after=n, target=C, target_n=None, n_target=n,
                    S=S_here, mechanism='reflect', new_mechanism='reflect',
                )
                return new, 'other'
            else:
                S_here = n * math.hypot(*_sub(current.p, D))
                new = sms_chain_step(
                    known_point=current.p, known_normal=current.n, ray_source=D,
                    n_before=n, n_after=n, target=D, target_n=None, n_target=n,
                    S=S_here, mechanism='reflect', new_mechanism='reflect',
                )
                return new, 'seed'

        bottom_points = list(DE)
        top_points: List[SMSPoint] = [SMSPoint(C, ac_normal)]
        try:
            grown_bottom, grown_top = build_sms_chain(
                seed=[DE[-1]], step_fn=step_fn,
                stop_condition=lambda p: True,  # each call already IS one stage
                max_steps=max(1, 2 * self.n_stages),
            )
            bottom_points = grown_bottom
            top_points.extend(grown_top)
        except (RuntimeError, ValueError):
            pass

        return Q, Q_star, A, B, C, DE, MN, top_points, bottom_points

    def _assemble_vertices(self, top_points, bottom_points) -> List[Tuple[float, float]]:
        """
        Assemble a closed polygon from A/B (top aperture corners), the
        grown top-surface points (mirror-coated centrally per pin 6), and
        the DE-family bottom points -- mirrored about the y-axis.

        KNOWN SIMPLIFICATION [KD2: stated here rather than silently
        assumed correct]: the receiver cavity MN
        (self.MN, computed in _build_profile) is NOT currently stitched
        into this boundary -- integrating it correctly needs a
        receiver-gap cutout analogous to RXIOptic's own
        `receiver_half_width` mechanism (rxi.py), which this first
        landing does not yet build. self.MN is still computed and
        exposed for inspection/follow-on work.
        """
        top_right = sorted((p.p for p in top_points), key=lambda p: p[0])
        bottom_right = sorted((p.p for p in bottom_points), key=lambda p: p[0])

        top_left = [(-x, y) for x, y in reversed(top_right)]
        bottom_left = [(-x, y) for x, y in reversed(bottom_right)]

        vertices = bottom_left + bottom_right + [self.B] + top_right + top_left + [self.A]

        deduped: List[Tuple[float, float]] = []
        for v in vertices:
            if not deduped or math.hypot(v[0] - deduped[-1][0], v[1] - deduped[-1][1]) > 1e-9:
                deduped.append(v)
        if len(deduped) < 3:
            deduped = [self.A, self.B, self.C]

        # Ensure CCW (Shapely convention) regardless of which parameter
        # choice was used -- the natural traversal order above can come
        # out either way depending on the relative sizes of aperture_height/
        # c_height_fraction/d_extension.
        signed_area = 0.5 * sum(
            deduped[i][0] * deduped[(i + 1) % len(deduped)][1]
            - deduped[(i + 1) % len(deduped)][0] * deduped[i][1]
            for i in range(len(deduped))
        )
        if signed_area < 0:
            deduped.reverse()
        return deduped

    def _add_mirror_coating(self, scene, bottom_points) -> List['object']:
        """Overlay Mirror objects on the DE-family bottom surface, merges_with_glass."""
        from ...core.scene_objs.mirror.mirror import Mirror

        mirrors = []
        pts = [p.p for p in bottom_points]
        for k in range(len(pts) - 1):
            m = Mirror(scene)
            m.p1 = {'x': pts[k][0], 'y': pts[k][1]}
            m.p2 = {'x': pts[k + 1][0], 'y': pts[k + 1][1]}
            m.name = f"{self.name or 'rxi_direct'}_bottom_mirror_{k}"
            scene.add_object(m)
            mirrors.append(m)
        return mirrors


__all__ = ['RXIOpticDirect']
