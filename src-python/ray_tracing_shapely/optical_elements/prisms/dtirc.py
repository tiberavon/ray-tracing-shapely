"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
DIELECTRIC TOTAL INTERNAL REFLECTION CONCENTRATOR (DTIRC)
===============================================================================
A dielectric CPC with a curved (circular-arc) entrance aperture, per Chaves,
"Introduction to Nonimaging Optics" ch. 3, Example 3.6.

The entrance aperture is a circular arc between P1 (left) and P2 (right),
symmetric about the y-axis. Edge rays parallel to r1 (tilted `theta_deg` from
vertical) entering at the aperture's own edge point refract straight through
to the OPPOSITE exit corner with no wall bounce -- the boundary/critical ray
that anchors the constant-optical-path-length S. Every other entrance point,
swept by phi over (-phi_edge, +phi_edge), refracts and then reflects once off
a sidewall (built via the constant-optical-path-length `coptpt` construction,
crossed-focus per the standard CPC convention: the right wall is built toward
the LEFT receiver edge R1, and vice versa) before reaching the receiver.

`theta_deg` (acceptance half-angle) and `phi_edge_deg` (entrance-aperture
angular half-width) are independent design inputs -- the book states
"we choose angle phi = 50 deg" as a free choice, not a value derived from
theta.

Vertex layout (before rotation, CCW, at unit radius before `size` scaling):

    R1 -> R2 -> [right wall, wall_segments edges] -> P2
       -> [entrance arc, entrance_arc_segments edges] -> P1
       -> [left wall, wall_segments edges] -> back to R1

Functional labels (edge_index ranges, per the CCW order above):
    0:                                  EX  Exit Aperture (Role.ABSORBER)
    1 .. wall_segments:                 W   Side Wall, right (Role.WALL)
    wall_segments+1 .. +arc_segments:   EN  Entrance Aperture (Role.ENTRANCE)
    ... .. 2*wall_segments+arc_segments: W  Side Wall, left (Role.WALL)
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, Dict, List, Tuple, Union, TYPE_CHECKING

from .base_prism import BasePrism
from ..roles import Role

if TYPE_CHECKING:
    from ...core.scene import Scene


class DTIRCPrism(BasePrism):
    """
    Dielectric TIR concentrator with a circular-arc entrance aperture.

    Attributes:
        theta_deg: Half-acceptance angle in degrees.
        phi_edge_deg: Entrance-aperture angular half-width in degrees --
            an independent design input, not derived from theta_deg.
        wall_segments: Number of straight segments approximating each
            sidewall -- the mesh-resolution knob for this class.
        entrance_arc_segments: Number of straight segments approximating
            the (circular) entrance aperture.

    Example:
        >>> from ray_tracing_shapely.core.scene import Scene
        >>> scene = Scene()
        >>> prism = DTIRCPrism(scene, theta_deg=10.0, n=1.5)
    """

    _apex_vertex_index: ClassVar[None] = None
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []

    type = 'DTIRCPrism'

    def __init__(
        self,
        scene: 'Scene',
        theta_deg: float,
        n: float,
        phi_edge_deg: float = 50.0,
        size: float = 1.0,
        wall_segments: int = 16,
        entrance_arc_segments: int = 8,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        **kwargs: Any
    ) -> None:
        """
        Create a DTIRC prism from physics parameters.

        Args:
            scene: The scene this prism belongs to.
            theta_deg: Half-acceptance angle in degrees (0 < theta_deg < 90).
            n: Refractive index of the prism material.
            phi_edge_deg: Entrance-aperture angular half-width in degrees.
            size: Scale factor (the entrance aperture's radius of curvature).
            wall_segments: Number of straight segments per sidewall.
            entrance_arc_segments: Number of straight segments for the
                entrance aperture.
            position: Reference point coordinates.
            rotation: Rotation angle in degrees.

        Raises:
            ValueError: If theta_deg/phi_edge_deg are out of range, or if
                wall_segments/entrance_arc_segments < 1.
        """
        if not (0.0 < theta_deg < 90.0):
            raise ValueError(f"theta_deg must be in (0, 90), got {theta_deg}")
        if not (0.0 < phi_edge_deg < 90.0):
            raise ValueError(f"phi_edge_deg must be in (0, 90), got {phi_edge_deg}")
        if wall_segments < 1 or entrance_arc_segments < 1:
            raise ValueError("wall_segments and entrance_arc_segments must be >= 1")

        self.theta_deg = theta_deg
        self.phi_edge_deg = phi_edge_deg
        self.wall_segments = wall_segments
        self.entrance_arc_segments = entrance_arc_segments

        # _edge_roles' length depends on wall_segments/entrance_arc_segments,
        # so (unlike every other BasePrism subclass) it is an instance
        # attribute, built before super().__init__() triggers
        # _apply_functional_labels().
        self._edge_roles = self._build_edge_roles()

        super().__init__(
            scene=scene,
            size=size,
            position=position,
            rotation=rotation,
            n=n,
            anchor='centroid',
            **kwargs
        )

    def _build_edge_roles(self) -> List[Tuple[str, str, Role]]:
        """Build the instance-specific _edge_roles list (see module docstring)."""
        roles: List[Tuple[str, str, Role]] = [("EX", "Exit Aperture", Role.ABSORBER)]
        roles += [("W", "Side Wall (right)", Role.WALL) for _ in range(self.wall_segments)]
        roles += [("EN", "Entrance Aperture", Role.ENTRANCE) for _ in range(self.entrance_arc_segments)]
        roles += [("W", "Side Wall (left)", Role.WALL) for _ in range(self.wall_segments)]
        return roles

    def _compute_path(self) -> List[Dict[str, Union[float, bool]]]:
        """
        Compute vertex path for the DTIRC, per chapter_03.md Example 3.6.

        Built at unit radius (matching the book's "unit radius [C,P1]=1,
        as this is just a scale factor"), then scaled by self.size.

        Returns:
            List of vertex dictionaries with 'x', 'y', 'arc' keys.
        """
        from .nonimaging_geometry import isl, rfr, coptpt

        theta = math.radians(self.theta_deg)
        phi_edge = math.radians(self.phi_edge_deg)
        n = self.refIndex

        def P_of(phi: float) -> Tuple[float, float]:
            return (math.cos(math.pi / 2 + phi), math.sin(math.pi / 2 + phi))

        P1 = P_of(phi_edge)
        P2 = P_of(-phi_edge)
        v2 = (math.sin(theta), -math.cos(theta))
        v_W = (v2[1], -v2[0])
        W1 = (P1[0] - v2[0], P1[1] - v2[1])

        v1_prime = rfr((-v2[0], -v2[1]), (-P1[0], -P1[1]), 1.0, n)
        if v1_prime is None:
            raise ValueError(
                "DTIRCPrism: the boundary edge ray at P1 undergoes TIR instead "
                "of refracting -- check theta_deg/n."
            )
        R = math.hypot(P2[0] - P1[0], P2[1] - P1[1]) * math.sin(theta) / n
        e2 = (0.0, 1.0)
        R2 = isl(P1, v1_prime, (R / 2.0, 0.0), e2)
        R1 = (-R2[0], R2[1])
        S = (
            math.hypot(P1[0] - W1[0], P1[1] - W1[1])
            + n * math.hypot(P1[0] - R2[0], P1[1] - R2[1])
            + n * R
        )

        def wall_point(phi: float) -> Tuple[float, float]:
            P = P_of(phi)
            vstar = rfr((-v2[0], -v2[1]), (-P[0], -P[1]), 1.0, n)
            if vstar is None:
                raise ValueError(
                    f"DTIRCPrism: entrance ray at phi={math.degrees(phi):.2f} deg "
                    "undergoes TIR instead of refracting -- check theta_deg/n."
                )
            W = isl(W1, v_W, P, v2)
            S_param = S - math.hypot(P[0] - W[0], P[1] - W[1])
            return coptpt(P, vstar, R1, n, S_param)

        # Right wall: interior points only, phi sweeping from just below
        # +phi_edge (near R2) to just above -phi_edge (near P2).
        right_wall_pts: List[Tuple[float, float]] = []
        for i in range(1, self.wall_segments):
            frac = i / self.wall_segments
            phi = phi_edge - frac * (2 * phi_edge)
            right_wall_pts.append(wall_point(phi))

        # Entrance arc: interior points only, phi sweeping from -phi_edge (P2) to +phi_edge (P1).
        entrance_arc_pts: List[Tuple[float, float]] = []
        for i in range(1, self.entrance_arc_segments):
            frac = i / self.entrance_arc_segments
            phi = -phi_edge + frac * (2 * phi_edge)
            entrance_arc_pts.append(P_of(phi))

        # Left wall: mirror image of the right wall, reversed to go P1 -> R1.
        left_wall_pts = [(-x, y) for (x, y) in reversed(right_wall_pts)]

        vertices = (
            [R1, R2]
            + right_wall_pts
            + [P2]
            + entrance_arc_pts
            + [P1]
            + left_wall_pts
        )
        vertices = [(x * self.size, y * self.size) for x, y in vertices]

        return self._apply_rotation_and_translation(vertices)
