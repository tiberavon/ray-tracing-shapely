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

Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
RX CONCENTRATOR -- Miñano-Benítez RX SMS Optic
===============================================================================
Single Glass polygon: a refractive top surface (facing the receiver) and a
mirror-coated bottom surface, built with the shared sms_chain engine
(sms_chain.py) -- the same "one engine, four device families" architecture
Chaves Ch. 9's own text establishes (§9.4 lines 647/743/826).

No RX-specific worked numeric example exists in the source book (confirmed
by reading all of Chaves Ch. 9's Examples 9.1-9.3); this class's
construction sequence instead reproduces Example 9.2's (XR, the same
shared engine's mechanism='reflect' code path) equation by equation
(eq. 9.67-9.79), generalized to arbitrary r1/r2/n/theta_deg/p0/n0 rather
than that example's own fixed numbers -- see
developer_tests/test_sms_chain.py's own Example-9.2 validation of the
exact primitives this class calls.

See dev_doc/architecture/components/nonimaging_design.md
===============================================================================
"""

from __future__ import annotations

import math
from typing import ClassVar, List, Optional, Tuple

from .base_prism import BasePrism
from .nonimaging_geometry import Point, rfr, rfxnrm
from .sms_chain import (
    SMSPoint,
    build_sms_chain,
    reflect,
    seed_arc,
    sms_chain_step,
)


def _nrm(v: Point) -> Point:
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


def _neg(v: Point) -> Point:
    return (-v[0], -v[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


class RXConcentrator(BasePrism):
    """
    RX SMS optic (Chaves Ch. 9 §9.4, lines 741-784): a refractive top
    surface (R) and a mirror-coated bottom surface (X), with the receiver
    R1R2 immersed in the dielectric near the refractive surface. Built by
    generalizing Example 9.2's (XR) own construction sequence
    (eq. 9.67-9.79) -- the shared engine's mechanism='reflect' code path,
    the exact code this class depends on.

    Args:
        r1, r2: Receiver edge points, immersed in the medium of index n.
        n: Refractive index of the dielectric.
        theta_deg: Half-angle of the two input wavefronts w1/w2
            (Chaves Ch. 9's own theta).
        p0, n0: A seed point and its normal on the refractive top surface
            (Chaves Ch. 9's own free choice -- the simpler
            P0-seeded variant, matching how the book's own RX-family
            example (9.2, structurally XR) is described, rather than the
            hyperbola-seeded variant RRLens uses -- there is no RX-specific
            worked example to instead match the other variant against).
        p1_extension: Distance along the refracted ray from p0 to place
            the mirror seed point P1 (Chaves Ch. 9 eq. 9.68's own free
            "10" multiplier, exposed as a parameter rather than hardcoded).
        wavefront_offset: Distance along s1/s2 from P1 to place the
            wavefront reference points W1/W2 (eq. 9.69's own free "15").
        n_points_on_seed_circle: Points sampled on the initial mirror
            seed circle between Q1 and P1, INCLUSIVE of both endpoints
            (Chaves Ch. 9's own N_p=5 refers to the count AFTER dropping
            the repeated P1 endpoint, line 1970 -- pass 6 here to
            reproduce the book's own 5-point list exactly, confirmed
            against its published values).
        n_stages: Number of alternating refract/reflect stages to grow
            outward from the seed circle before stopping (a fixed,
            finite bound -- Chaves Ch. 9's own termination is physical,
            not numerical (line 1979's critical-angle crossover), which
            this class does not attempt to derive analytically; see
            RXIOpticDirect's docstring for the same pin applied there).
        n: Refractive index of the dielectric (default 1.5).

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press,
        Ch. 9 "Miñano-Benítez Design Method", §9.4, lines 741-784, eq.
        9.34, Figures 9.37-9.39; Example 9.2 (structurally XR, lines
        1909-2025) supplies this class's only available numeric
        cross-check, for the shared engine's mechanism='reflect' path.
    """

    _edge_roles: ClassVar[List[Tuple[str, str]]] = []
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None
    _supports_refinement: ClassVar[bool] = False
    type = 'RXConcentrator'

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
        n_stages: int = 4,
        name: Optional[str] = None,
    ) -> None:
        self.r1, self.r2 = r1, r2
        self.theta_deg = theta_deg
        self.p0, self.n0 = p0, n0
        self.n_lens = n
        self.n_stages = n_stages

        (
            self.mirror_points, self.lens_points,
            self.C, self.W1, self.W2, self.S,
        ) = self._build_profile(p1_extension, wavefront_offset, n_points_on_seed_circle)

        vertices = self._assemble_vertices()

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

        self._mirrors = self._add_mirror_coating(scene)

    def _build_profile(self, p1_extension, wavefront_offset, n_points_on_seed_circle):
        r1, r2, n, theta = self.r1, self.r2, self.n_lens, math.radians(self.theta_deg)
        p0, n0 = self.p0, self.n0

        # eq. 9.67-9.71: seed mirror point P1, its normal, the seed circle
        # center C, wavefront reference points, and the shared OPL S.
        t = rfr(_neg(_nrm(_sub(p0, r2))), n0, n, 1.0)
        p1 = (p0[0] + p1_extension * t[0], p0[1] + p1_extension * t[1])
        s1 = (math.cos(math.pi / 2 + theta), math.sin(math.pi / 2 + theta))
        n1 = rfxnrm(t, s1)

        w1 = (p1[0] + wavefront_offset * s1[0], p1[1] + wavefront_offset * s1[1])
        v1 = (math.cos(theta), math.sin(theta))
        w2 = (-w1[0], w1[1])
        v2 = (math.cos(-theta), math.sin(-theta))

        S = math.hypot(*_sub(w1, p1)) + math.hypot(*_sub(p1, p0)) + n * math.hypot(*_sub(p0, r2))

        q1 = (-p1[0], p1[1])
        n1_mirrored = (-n1[0], n1[1])
        from .nonimaging_geometry import isl as _isl
        center = _isl((0.0, 0.0), (0.0, 1.0), p1, n1)
        seed_circle = seed_arc(q1, n1_mirrored, p1, n1, n_points_on_seed_circle)
        # Drop the last point (== p1) to avoid a repeated point in the
        # chain, matching Chaves Ch. 9's own stated practice.
        mirror_seed = seed_circle[:-1]

        s2 = (-v2[1], v2[0])  # ray direction of the w2 bundle: v2 rotated +90deg

        from .nonimaging_geometry import isl

        def step_fn(current: SMSPoint, tag: str):
            if tag == 'seed':
                # On the mirror: ray from w2 -> reflect -> new lens point, focus R1.
                p_w2 = isl(current.p, s2, w2, v2)
                S_here = S - math.hypot(*_sub(current.p, p_w2))
                new = sms_chain_step(
                    known_point=current.p, known_normal=current.n, ray_source=p_w2,
                    n_before=1.0, n_after=1.0, target=r1, target_n=None, n_target=n,
                    S=S_here, mechanism='reflect', new_mechanism='refract',
                )
                return new, 'other'
            else:
                # On the lens: ray from r2 -> refract -> new mirror point, focus w1.
                S_here = S - n * math.hypot(*_sub(r2, current.p))
                new = sms_chain_step(
                    known_point=current.p, known_normal=current.n, ray_source=r2,
                    n_before=n, n_after=1.0, target=w1, target_n=s1, n_target=1.0,
                    S=S_here, mechanism='refract', new_mechanism='reflect',
                )
                return new, 'seed'

        stage_count = [0]

        def stop_condition(_point):
            stage_count[0] += 1
            return stage_count[0] >= self.n_stages

        mirror_points = list(mirror_seed)
        lens_points: List[SMSPoint] = []
        try:
            grown_mirror, grown_lens = build_sms_chain(
                seed=mirror_seed, step_fn=step_fn, stop_condition=stop_condition,
                max_steps=self.n_stages + 1,
            )
            mirror_points = grown_mirror
            lens_points = grown_lens
        except RuntimeError:
            pass

        return mirror_points, lens_points, center, w1, w2, S

    def _assemble_vertices(self) -> List[Tuple[float, float]]:
        """
        Assemble a closed polygon. The chain grows in one direction only
        (matching Chaves Ch. 9's own Example 9.2 point list, which is
        predominantly negative-x -- confirmed empirically: seeding
        build_sms_chain from the seed circle's own last point pushes the
        chain toward the SAME side that point is already on, not outward
        symmetrically in both directions), so the canonical half built
        here is "everything at x <= 0" -- the seed circle's own
        right-of-axis points (x > 0) are discarded from this half and
        regenerated by mirroring the left half instead, exactly like
        RRLens's own single-sided-growth-plus-mirror assembly (rr_lens.py
        _assemble_vertices), just with the opposite sign convention since
        this device grows outward from a central seed rather than inward
        toward a symmetry axis.
        """
        lens_left = sorted(
            (p.p for p in self.lens_points if p.p[0] <= 1e-9), key=lambda p: p[0]
        )
        mirror_left = sorted(
            (p.p for p in self.mirror_points if p.p[0] <= 1e-9), key=lambda p: p[0]
        )
        lens_right = [(-x, y) for x, y in reversed(lens_left)]
        mirror_right = [(-x, y) for x, y in reversed(mirror_left)]

        # CCW (confirmed by signed-area check in the test suite): top
        # curve right->left, then bottom curve left->right.
        vertices = list(reversed(lens_right)) + list(reversed(lens_left)) + mirror_left + mirror_right
        if len(vertices) < 3:
            # Degenerate (n_stages too small to grow past the seed) --
            # fall back to a minimal closed triangle around the receiver
            # so from_vertices-style assembly never receives < 3 points.
            vertices = [self.r1, self.r2, self.C]
        return vertices

    def _add_mirror_coating(self, scene) -> List['object']:
        """Overlay Mirror objects on the bottom (mirror) surface's edges, merges_with_glass."""
        from ...core.scene_objs.mirror.mirror import Mirror

        mirrors = []
        pts = [p.p for p in self.mirror_points]
        for k in range(len(pts) - 1):
            m = Mirror(scene)
            m.p1 = {'x': pts[k][0], 'y': pts[k][1]}
            m.p2 = {'x': pts[k + 1][0], 'y': pts[k + 1][1]}
            m.name = f"{self.name or 'rx_concentrator'}_mirror_{k}"
            scene.add_object(m)
            mirrors.append(m)
        return mirrors


__all__ = ['RXConcentrator']
