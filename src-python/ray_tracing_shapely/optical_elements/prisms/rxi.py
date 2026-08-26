"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
RXI-INSPIRED MESH-REFINEMENT FIXTURE
===============================================================================
A simplified, purely-geometric stand-in for the RXI optic of Chaves,
"Introduction to Nonimaging Optics" ch. 9, §9.6-9.7. This is Tier 1 of
15_p3_cpc_and_sms_optical_elements.md §4.3: "a correctly-shaped RXI to refine, not
a general-purpose RXI design tool." It does NOT reimplement the book's
iterative Cartesian-oval SMS chain (Tier 2, explicitly out of scope) --
instead it builds a shape with the one structural property
15_p7_mesh_refinement_and_convergence.md's worked example actually needs: a top
surface s1 whose *mechanism* genuinely varies by position, discoverable by
tracing, not read off a formula.

Why a plain dome + mirrored flat bottom already produces this, with no SMS
solver required: light entering through s1 refracts in (an R event, ordinary
Fresnel physics -- no special handling needed), reflects off the
fully-mirrored bottom s2, and travels back up to hit s1 again *from inside*.
On that second hit, incidence angle grows with distance from the arc's
center -- so central hits refract back out (a lossy escape) while hits far
enough from center exceed the critical angle and undergo genuine TIR. That
refract-to-TIR flip, positioned exactly where geometry puts it, is a real,
traceable transition -- exactly what estimate_role_transition
(15_p7_mesh_refinement_and_convergence.md §4.2) is built to locate. An optional
`mirror_band_deg` additionally mirror-coats a central patch of s1 (the
book's own fix for the central escape), overlaying Mirror objects on that
span (merges_with_glass, forcing full reflection there regardless of angle)
-- the R/X boundary this way is a build-time design choice, per
15_p3_cpc_and_sms_optical_elements.md §4.3, while the reflect/TIR (X/I-analogous)
boundary further out stays undiscovered until estimate_role_transition finds
it.

Vertex layout (before rotation, CCW, s1_segments base resolution, no receiver cavity):

    BL -> BR -> [right side] -> R -> [s1, right to left] -> L -> [left side] -> BL

    BL/BR: bottom-left/right (s2, the mirrored flat back)
    L/R:   s1's left/right endpoints (phi = +/-phi_edge_deg)

With `receiver_half_width` given, s2 gains a receiver cavity -- a gap in the
mirror coating at its center, exactly like DTIRCPrism's exit aperture (R1-R2):
not mirror-coated, so light reaching it just refracts out into air, where a
Detector can sit:

    BL -> RL -> RR -> BR -> [right side] -> R -> [s1, right to left] -> L -> [left side] -> BL

    RL/RR: receiver aperture corners (left/right), at y = -depth, |x| < BL/BR's
    S2 is then two mirror-coated segments (BL-RL, RR-BR) either side of the
    uncoated RL-RR gap, instead of one continuous mirrored edge.

`refinement_spans` entries are (phi_start_deg, phi_end_deg, n_subsegments) --
phi in degrees, the same convention __init__'s phi_edge_deg/mirror_band_deg
already use, pinning down the open convention question
15_p7_mesh_refinement_and_convergence.md §6 left unresolved.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

from .base_prism import BasePrism
from ..roles import Role

if TYPE_CHECKING:
    from ...core.scene import Scene
    from ...core.scene_objs.mirror.mirror import Mirror


class RXIOptic(BasePrism):
    """
    RXI-inspired mesh-refinement fixture: a dielectric dome (s1) over a
    mirror-coated flat back (s2), with an optional mirror-coated central
    band on s1.

    Attributes:
        phi_edge_deg: s1's angular half-width in degrees.
        depth: Vertical distance from the arc's center to s2.
        s1_segments: Base number of straight segments approximating s1.
        mirror_band_deg: Optional (start_deg, end_deg) central span of s1
            that gets mirror-coated (forced full reflection).
        receiver_half_width: Optional half-width of an uncoated receiver
            gap centered in s2 (None: s2 stays one continuous mirror, the
            original Tier-0 fixture with no exit at all).

    Example:
        >>> from ray_tracing_shapely.core.scene import Scene
        >>> scene = Scene()
        >>> rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0)
    """

    _supports_refinement: ClassVar[bool] = True
    _apex_vertex_index: ClassVar[None] = None
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []

    type = 'RXIOptic'

    def __init__(
        self,
        scene: 'Scene',
        n: float,
        phi_edge_deg: float = 50.0,
        size: float = 1.0,
        depth: float = 1.5,
        s1_segments: int = 16,
        mirror_band_deg: Optional[Tuple[float, float]] = None,
        receiver_half_width: Optional[float] = None,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        refinement_spans: Optional[List[Tuple[float, float, int]]] = None,
        **kwargs: Any
    ) -> None:
        """
        Create an RXI-inspired fixture from geometric parameters.

        Args:
            scene: The scene this prism belongs to.
            n: Refractive index of the dome material.
            phi_edge_deg: s1's angular half-width in degrees (0, 90).
            size: Radius of the s1 arc.
            depth: Vertical distance from the arc's center (0,0) to s2.
                Must be > 0 (s2 sits below the arc's center).
            s1_segments: Base number of straight segments per s1, before
                any refinement_spans are applied.
            mirror_band_deg: Optional (start_deg, end_deg) central span of
                s1, within (-phi_edge_deg, phi_edge_deg), to mirror-coat.
            receiver_half_width: Optional half-width of an uncoated receiver
                gap centered in s2 (must be < size*sin(radians(phi_edge_deg)),
                s2's own half-width, so RL/RR stay strictly between BL/BR).
                None (default): s2 stays one continuous mirror, no exit at
                all -- the original Tier-0 fixture.
            position: Reference point coordinates.
            rotation: Rotation angle in degrees.
            refinement_spans: [(phi_start_deg, phi_end_deg, n_subsegments), ...]
                -- see module docstring.

        Raises:
            ValueError: If phi_edge_deg/depth/s1_segments/mirror_band_deg/
                receiver_half_width are out of range.
        """
        if not (0.0 < phi_edge_deg < 90.0):
            raise ValueError(f"phi_edge_deg must be in (0, 90), got {phi_edge_deg}")
        if depth <= 0.0:
            raise ValueError(f"depth must be > 0, got {depth}")
        if s1_segments < 1:
            raise ValueError("s1_segments must be >= 1")
        if mirror_band_deg is not None:
            band_a, band_b = mirror_band_deg
            if not (-phi_edge_deg <= band_a < band_b <= phi_edge_deg):
                raise ValueError(
                    f"mirror_band_deg {mirror_band_deg} must satisfy "
                    f"-phi_edge_deg <= start < end <= phi_edge_deg"
                )
        if receiver_half_width is not None:
            if receiver_half_width <= 0.0:
                raise ValueError(f"receiver_half_width must be > 0, got {receiver_half_width}")
            s2_half_width = size * math.sin(math.radians(phi_edge_deg))
            if receiver_half_width >= s2_half_width:
                raise ValueError(
                    f"receiver_half_width ({receiver_half_width}) must be < "
                    f"s2's own half-width (size*sin(phi_edge_deg)) = {s2_half_width:.4f}"
                )

        self.phi_edge_deg = phi_edge_deg
        self.depth = depth
        self.s1_segments = s1_segments
        self.mirror_band_deg = mirror_band_deg
        self.receiver_half_width = receiver_half_width

        # s2 is 1 edge (no cavity) or 3 (BL-RL mirror, RL-RR receiver gap,
        # RR-BR mirror). s1_start_edge_index lets callers (e.g. the mesh-
        # refinement driver's narrow_span_around) convert an s1 edge_index
        # back to a phi range without hardcoding where s1 begins.
        self._s2_edge_count = 3 if receiver_half_width is not None else 1
        self.s1_start_edge_index = self._s2_edge_count + 1  # +1 for the right SIDE edge

        # _edge_roles' length depends on s1_segments/refinement_spans, so
        # (as for DTIRCPrism) it is an instance attribute, built from the
        # same breakpoint list _compute_path() will use.
        breakpoints_deg = self._s1_breakpoints_deg(refinement_spans)
        self._edge_roles = self._build_edge_roles(breakpoints_deg)
        # Public: lets a caller convert an s1 edge_index (e.g. from
        # estimate_role_transition) back into its phi-degree range, via
        # s1_breakpoints_deg[edge_index - self.s1_start_edge_index] ..
        # s1_breakpoints_deg[edge_index - self.s1_start_edge_index + 1].
        self.s1_breakpoints_deg = breakpoints_deg

        super().__init__(
            scene=scene,
            size=size,
            position=position,
            rotation=rotation,
            n=n,
            anchor='centroid',
            refinement_spans=refinement_spans,
            **kwargs
        )

        self.mirrors: List['Mirror'] = self._add_mirror_coating(breakpoints_deg)

    # =========================================================================
    # s1 breakpoint / refinement machinery
    # =========================================================================

    def _s1_breakpoints_deg(
        self,
        refinement_spans: Optional[List[Tuple[float, float, int]]],
    ) -> List[float]:
        """Ascending phi breakpoints (degrees) for s1, base resolution plus
        any refinement_spans' extra subdivisions."""
        phi_edge = self.phi_edge_deg
        base = [
            -phi_edge + i * (2 * phi_edge) / self.s1_segments
            for i in range(self.s1_segments + 1)
        ]
        if not refinement_spans:
            return base

        breakpoints = set(base)
        for (a_deg, b_deg, n_sub) in refinement_spans:
            if n_sub < 1:
                raise ValueError("refinement_spans: n_subsegments must be >= 1")
            lo, hi = min(a_deg, b_deg), max(a_deg, b_deg)
            for k in range(n_sub + 1):
                breakpoints.add(lo + k * (hi - lo) / n_sub)
        return sorted(breakpoints)

    def _build_edge_roles(self, breakpoints_deg: List[float]) -> List[Tuple[str, str, Role]]:
        """s2 (1 edge, or 3 with a receiver cavity) + right side + s1 (per
        breakpoint, ENTRANCE unless inside mirror_band_deg) + left side."""
        if self.receiver_half_width is not None:
            roles: List[Tuple[str, str, Role]] = [
                ("S2L", "Bottom Mirror (s2, left)", Role.WALL),
                ("REC", "Receiver Aperture", Role.ABSORBER),
                ("S2R", "Bottom Mirror (s2, right)", Role.WALL),
            ]
        else:
            roles = [("S2", "Bottom Mirror (s2)", Role.WALL)]
        roles.append(("SIDE", "Right Side", Role.WALL))
        for i in range(len(breakpoints_deg) - 1):
            mid = (breakpoints_deg[i] + breakpoints_deg[i + 1]) / 2.0
            if self.mirror_band_deg is not None and self.mirror_band_deg[0] <= mid <= self.mirror_band_deg[1]:
                roles.append(("S1X", "s1 Mirror-Coated Band", Role.WALL))
            else:
                roles.append(("S1", "s1 (Entrance / Internal Bounce)", Role.ENTRANCE))
        roles.append(("SIDE", "Left Side", Role.WALL))
        return roles

    # =========================================================================
    # Geometry
    # =========================================================================

    def _compute_path(
        self,
        *,
        refinement_spans: Optional[List[Tuple[float, float, int]]] = None,
    ) -> List[Dict[str, Union[float, bool]]]:
        """
        Compute vertex path: [BL, BR, R, ...s1 right-to-left..., L].

        Returns:
            List of vertex dictionaries with 'x', 'y', 'arc' keys.
        """
        breakpoints_deg = self._s1_breakpoints_deg(refinement_spans)

        def P_of(phi_deg: float) -> Tuple[float, float]:
            phi = math.radians(phi_deg)
            return (-math.sin(phi) * self.size, math.cos(phi) * self.size)

        # breakpoints_deg is ascending (-phi_edge .. +phi_edge); since
        # P_of(-phi_edge) has positive x and P_of(+phi_edge) has negative x
        # (matching DTIRCPrism's own P1=P_of(+phi_edge) is LEFT convention),
        # s1_pts here already runs right-to-left.
        s1_pts = [P_of(d) for d in breakpoints_deg]
        R_end = s1_pts[0]
        L_end = s1_pts[-1]
        bottom_y = -self.depth
        BL = (L_end[0], bottom_y)
        BR = (R_end[0], bottom_y)

        if self.receiver_half_width is not None:
            RL = (-self.receiver_half_width, bottom_y)
            RR = (self.receiver_half_width, bottom_y)
            bottom_verts = [BL, RL, RR, BR]
        else:
            bottom_verts = [BL, BR]

        vertices = bottom_verts + s1_pts  # ...s2 verts..., R, ..., L (CCW)
        return self._apply_rotation_and_translation(vertices)

    # =========================================================================
    # Mirror coating (s2 always; s1's mirror_band_deg optionally)
    # =========================================================================

    def _add_mirror_coating(self, breakpoints_deg: List[float]) -> List['Mirror']:
        """Overlay Mirror objects on s2 (both flanks if there's a receiver
        cavity, never the cavity's own gap) and any mirror_band_deg span of
        s1, forcing full reflection there via merges_with_glass -- the same
        mechanism a real coated dielectric surface uses in this simulator."""
        from ...core.scene_objs.mirror.mirror import Mirror

        mirrors: List['Mirror'] = []

        def _coat_edge(edge_index: int, name: str) -> None:
            endpoints = self.get_edge_endpoints(edge_index)
            if endpoints is None:
                return
            (x1, y1), (x2, y2) = endpoints
            m = Mirror(self.scene)
            m.p1 = {'x': x1, 'y': y1}
            m.p2 = {'x': x2, 'y': y2}
            m.name = name
            m.role = Role.WALL
            self.scene.add_object(m)
            mirrors.append(m)

        if self.receiver_half_width is not None:
            # edges: 0=BL-RL (S2L), 1=RL-RR (REC, left uncoated), 2=RR-BR (S2R)
            _coat_edge(0, f"{self.name or 'rxi'}_s2_left_mirror")
            _coat_edge(2, f"{self.name or 'rxi'}_s2_right_mirror")
        else:
            _coat_edge(0, f"{self.name or 'rxi'}_s2_mirror")

        if self.mirror_band_deg is not None:
            band_a, band_b = self.mirror_band_deg
            for i in range(len(breakpoints_deg) - 1):
                mid = (breakpoints_deg[i] + breakpoints_deg[i + 1]) / 2.0
                if band_a <= mid <= band_b:
                    _coat_edge(self.s1_start_edge_index + i,
                               f"{self.name or 'rxi'}_s1_mirror_seg{i}")

        return mirrors
