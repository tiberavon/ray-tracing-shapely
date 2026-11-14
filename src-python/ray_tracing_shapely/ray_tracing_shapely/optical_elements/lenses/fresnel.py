"""
Python-specific module: fresnel
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
A Fresnel collimator for a point source
===============================================================================
A flat plate with one grooved face: a curved central cap and straight facets
in equal-width zones, separated by risers. It collimates the light of a point
F on its axis, as the TIR collimator does, so the two can be compared.

Design, zone by zone, not by collapsing a base surface: collapsing moves each
zone along the axis, which changes the angle at which the light of F meets it,
so a collapsed lens is not exact even at a zone's middle. Instead:

- **the cap** is exact. Grooves facing F: the hyperbola K = -n^2 with
  R = (n - 1) d turns the light of F, d from its vertex, into a plane wave in
  the glass, which the flat face lets out unchanged. Grooves facing away: the
  Cartesian oval behind the flat face (collimator_design.collimating_face), a
  spline, or its best-fit conic (``cap="conic"``, for a model that takes a
  plain conic);
- **each facet** is a straight line through its zone's valley, tilted so that
  the ray of F through the facet's middle leaves along the axis (a fixed
  point: the middle moves as the tilt changes). Rays through the rest of the
  facet leave within a small angle, which shrinks with the zone width;
- **each riser** rises from the valley at the zone's inner radius, leaning
  outwards by ``riser_draft_deg`` (0: parallel to the axis).

Conventions are the light's, as TIRCollimator's: the axis is +x rotated by
``rotation`` degrees, and ``position`` is F. ``focal_distance`` runs from F to
the face the light meets first (the cap's vertex, or the flat face).

Edges (labels; the lower half repeats them, mirrored):

    FLAT        the flat face                    refract
    CAP         the central cap                  refract
    F1 .. Fm    facets, inner to outer           refract
    R1 .. Rm    risers, inner to outer           refract (stray light, kept as glass)
    RIM         the outer edge                   (none: absorbing in 3D)
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ...core.glass_curves import ConicCurve
from ..prisms.base_prism import BasePrism
from ..prisms.nonimaging_geometry import isl, rfnrm
from ..roles import Mechanism, Role
from .collimator_design import (AXIS, collimating_face, fit_conic, ray_through_flat_to,
                                spline_descriptor, unit)

if TYPE_CHECKING:
    from ...core.scene import Scene

XY = Tuple[float, float]


class FresnelLens(BasePrism):
    """A straight-facet Fresnel collimator for a point source F.

    Args:
        scene: The scene this lens belongs to.
        focal_distance: F to the first face the light meets, along the axis.
        semi_diameter: The lens's radius.
        zones: Number of zones, the cap included (at least 2).
        thickness: The plate's thickness at the valleys (flat face to the
            groove bottoms).
        grooves: ``"entrance"`` (the grooved face towards F) or ``"exit"``
            (the flat face towards F).
        riser_draft_deg: Risers lean outwards by this angle from the axis.
        cap: ``"exact"`` or ``"conic"``; only matters for ``grooves="exit"``,
            whose exact cap is a spline (``"entrance"``'s exact cap is a conic).
        points: Spline points for an exact ``"exit"`` cap.
        n: Refractive index.
        position: F.
        rotation: Direction of the optical axis, degrees counter-clockwise from +x.

    Attributes:
        design: ``cap_R``, ``cap_K`` (when the cap is a conic), ``depth`` (the
            deepest groove), ``facet_angles`` (each facet's tilt from the
            plate's plane, degrees, inner to outer).

    Raises:
        ValueError: For parameters out of range.
    """

    type = 'FresnelLens'

    _vertex_roles: List[Tuple[str, str]] = []
    _apex_vertex_index: Optional[int] = None

    def __init__(
        self,
        scene: 'Scene',
        *,
        focal_distance: float,
        semi_diameter: float,
        zones: int,
        thickness: float = 1.0,
        grooves: str = "entrance",
        riser_draft_deg: float = 0.0,
        cap: str = "exact",
        points: int = 17,
        n: float = 1.49,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
    ) -> None:
        if grooves not in ("entrance", "exit"):
            raise ValueError(f"grooves must be 'entrance' or 'exit', got {grooves!r}")
        if cap not in ("exact", "conic"):
            raise ValueError(f"cap must be 'exact' or 'conic', got {cap!r}")
        if zones < 2:
            raise ValueError(f"zones must be at least 2 (a cap and a facet), got {zones}")
        for name, value in (("focal_distance", focal_distance), ("semi_diameter", semi_diameter),
                            ("thickness", thickness)):
            if value <= 0.0:
                raise ValueError(f"{name} must be positive, got {value}")
        if not 0.0 <= riser_draft_deg < 45.0:
            raise ValueError(f"riser_draft_deg must lie in [0, 45), got {riser_draft_deg}")
        self.focal_distance = float(focal_distance)
        self.semi_diameter = float(semi_diameter)
        self.zones = int(zones)
        self.thickness = float(thickness)
        self.grooves = grooves
        self.riser_draft_deg = float(riser_draft_deg)
        self.cap = cap
        self.points = int(points)
        self.design: Dict[str, Any] = {}
        self._n_design = float(n)
        labels = ["FLAT", "CAP", "RIM"] + [f"{p}{k}" for k in range(1, zones) for p in ("F", "R")]
        self._edge_mechanisms = {lab: (None if lab == "RIM" else Mechanism.REFRACT) for lab in labels}
        super().__init__(scene, size=2.0 * semi_diameter, position=position, rotation=rotation, n=n)

    # --- placement ---------------------------------------------------------------

    @property
    def axis_direction(self) -> XY:
        """Unit vector along the optical axis, the way the light travels."""
        theta = math.radians(self._rotation)
        return (math.cos(theta), math.sin(theta))

    @property
    def focal_point(self) -> XY:
        """F, the point the lens collimates."""
        return (float(self._position[0]), float(self._position[1]))

    def revolve_axis(self) -> Dict[str, List[float]]:
        """The optical axis as profile.json's ``symmetry.axis`` for a revolve export."""
        return {"point": list(self.focal_point), "direction": list(self.axis_direction)}

    def _world(self, p: XY) -> XY:
        ux, uy = self.axis_direction
        fx, fy = self.focal_point
        return (fx + p[0] * ux - p[1] * uy, fy + p[0] * uy + p[1] * ux)

    def _world_vec(self, v: XY) -> XY:
        ux, uy = self.axis_direction
        return (v[0] * ux - v[1] * uy, v[0] * uy + v[1] * ux)

    # --- design ------------------------------------------------------------------

    def _cap(self, r1: float) -> Tuple[float, Dict[str, Any], XY, Optional[Tuple[List[XY], List[XY]]]]:
        """The cap out to r1: (the valley plane's x, its descriptor, its edge, its spline data)."""
        n, d = self._n_design, self.focal_distance
        if self.grooves == "entrance":
            big_r = (n - 1.0) * d
            curve = ConicCurve((d, 0.0), (1.0, 0.0), big_r, -n * n, 0.0, 1e-300)
            edge = curve.point(r1)                # s is the distance left of +x: y
            self.design.update(cap_R=big_r, cap_K=-n * n)
            desc = {"type": "conic", "vertex": list(self._world((d, 0.0))),
                    "axis": list(self._world_vec((1.0, 0.0))), "radius": big_r, "conic": -n * n}
            return edge[0], desc, edge, None
        # Exit grooves: the oval behind the flat face x = d, its edge on the valley
        # plane x = d + thickness, found by adjusting the cap's height.
        valley = d + self.thickness

        def oval(height: float) -> Tuple[List[XY], List[XY]]:
            lo, hi = 0.0, math.atan2(r1, d)
            for _ in range(64):                    # the ray whose oval point lies at radius r1
                mid = 0.5 * (lo + hi)
                pts, _ = collimating_face(n, d, self.thickness + height, mid, 2)
                if pts[-1][1] < r1:
                    lo = mid
                else:
                    hi = mid
            return collimating_face(n, d, self.thickness + height, 0.5 * (lo + hi), self.points)

        lo, hi = 0.0, r1                          # the cap's height above the valley plane
        for _ in range(64):                   # halvings past double precision
            mid = 0.5 * (lo + hi)
            if oval(mid)[0][-1][0] < valley:
                lo = mid
            else:
                hi = mid
        pts, nrms = oval(0.5 * (lo + hi))
        pts[-1] = (valley, r1)                    # the end on the valley plane, to the bisection's 1e-16
        if self.cap == "conic":
            big_r, big_k, err = fit_conic(pts, pts[0][0])
            self.design.update(cap_R=big_r, cap_K=big_k, cap_sag_error=err)
            curve = ConicCurve((pts[0][0], 0.0), (-1.0, 0.0), big_r, big_k, 0.0, 1e-300)
            desc = {"type": "conic", "vertex": list(self._world((pts[0][0], 0.0))),
                    "axis": list(self._world_vec((-1.0, 0.0))), "radius": big_r, "conic": big_k}
            return valley, desc, curve.point(-r1), None
        return valley, {}, (valley, r1), (pts, nrms)

    def _facet_normal(self, mid: XY) -> XY:
        """The facet normal at ``mid`` that sends the ray of F through it along the axis."""
        n = self._n_design
        if self.grooves == "entrance":
            return rfnrm(unit(mid), AXIS, 1.0, n)
        _, _, inside = ray_through_flat_to(mid, n, self.focal_distance)
        return rfnrm(inside, AXIS, n, 1.0)

    def _facets(self, valley_x: float, cap_edge: XY) -> List[Tuple[XY, XY]]:
        """Each facet's inner (riser top) and outer (valley) ends, inner zone first."""
        width = self.semi_diameter / self.zones
        sense = 1.0 if self.grooves == "exit" else -1.0      # the grooves rise along sense * x
        beta = math.radians(self.riser_draft_deg)
        riser = (sense * math.cos(beta), math.sin(beta))
        facets, angles = [], []
        start = cap_edge
        for k in range(1, self.zones):
            outer = (valley_x, (k + 1) * width)
            mid = (valley_x, (k + 0.5) * width)
            for _ in range(50):                   # the facet's middle depends on its tilt
                nrm = self._facet_normal(mid)
                along = unit((-nrm[1], nrm[0]))
                if along[1] > 0.0:
                    along = (-along[0], -along[1])  # from the valley inwards
                top = isl(outer, along, start, riser)
                new_mid = (0.5 * (top[0] + outer[0]), 0.5 * (top[1] + outer[1]))
                if math.dist(new_mid, mid) < 1e-13 * self.semi_diameter:
                    break
                mid = new_mid
            if sense * (top[0] - valley_x) <= 0.0 or top[1] < start[1]:  # a guard: a collimator's
                raise ValueError(f"FresnelLens: facet {k} does not rise from its valley.")  # facets rise
            facets.append((top, outer))
            angles.append(math.degrees(math.atan2(abs(top[0] - outer[0]), outer[1] - top[1])))
            start = outer
        self.design["facet_angles"] = angles
        self.design["depth"] = max(abs(top[0] - valley_x) for top, _ in facets)
        return facets

    def _compute_path(self) -> List[Dict[str, Any]]:
        width = self.semi_diameter / self.zones
        valley_x, cap_desc, cap_edge, spline = self._cap(width)
        facets = self._facets(valley_x, cap_edge)
        if spline is not None:
            pts, nrms = spline
            full_pts = [(x, -y) for x, y in reversed(pts[1:])] + pts
            full_nrms = [(nx, -ny) for nx, ny in reversed(nrms[1:])] + nrms
            cap_desc = spline_descriptor([self._world(p) for p in full_pts],
                                         [self._world_vec(v) for v in full_nrms])
        flat_x = self.focal_distance if self.grooves == "exit" else valley_x + self.thickness

        # The grooved face, upper half, from the cap's edge outwards: (vertex, label of the
        # edge that starts there).
        upper: List[Tuple[XY, Tuple[str, str, Role]]] = []
        face_role = Role.ENTRANCE if self.grooves == "entrance" else Role.EXIT
        prev = cap_edge
        for k, (top, outer) in enumerate(facets, start=1):
            upper.append((prev, (f"R{k}", f"Riser {k}", Role.WALL)))
            upper.append((top, (f"F{k}", f"Facet {k}", face_role)))
            prev = outer
        rim_corner = prev                          # the last valley, at the semi-diameter

        def low(p: XY) -> XY:
            return (p[0], -p[1])

        cap_role = ("CAP", "Central Cap", face_role)
        flat_role = ("FLAT", "Flat Face", Role.EXIT if self.grooves == "entrance" else Role.ENTRANCE)
        rim_role = ("RIM", "Edge", Role.BLOCKER)
        entries: List[Tuple[XY, Optional[Dict[str, Any]], Tuple[str, str, Role]]] = []
        if self.grooves == "exit":
            # Counter-clockwise: the flat face downwards, the grooved face upwards.
            entries.append(((flat_x, self.semi_diameter), None, flat_role))
            entries.append(((flat_x, -self.semi_diameter), None, rim_role))
            entries += self._lower_inwards(upper, rim_corner, low)
            entries.append((low(cap_edge), cap_desc, cap_role))
            entries += [(p, None, role) for p, role in upper]
            entries.append((rim_corner, None, rim_role))
        else:
            # Counter-clockwise: the grooved face downwards, the flat face upwards.
            entries += [(p, None, role) for p, role in self._upper_inwards(upper, rim_corner)]
            entries.append((cap_edge, cap_desc, cap_role))
            entries += [(low(p), None, role) for p, role in upper]
            entries.append((low(rim_corner), None, rim_role))
            entries.append(((flat_x, -self.semi_diameter), None, flat_role))
            entries.append(((flat_x, self.semi_diameter), None, rim_role))
        self._edge_roles = [role for _, _, role in entries]
        path = []
        for p, desc, _ in entries:
            x, y = self._world(p)
            entry: Dict[str, Any] = {"x": x, "y": y, "arc": False}
            if desc is not None:
                entry["curve"] = desc
            path.append(entry)
        return path

    @staticmethod
    def _upper_inwards(upper: List[Tuple[XY, Tuple[str, str, Role]]],
                       rim_corner: XY) -> List[Tuple[XY, Tuple[str, str, Role]]]:
        """The upper grooved face from the rim to the cap's edge: each vertex with the
        label of the edge that leaves it towards the axis."""
        verts = [p for p, _ in upper] + [rim_corner]       # inner to outer
        roles = [role for _, role in upper]                # roles[i]: edge verts[i] -> verts[i+1]
        return [(verts[i + 1], roles[i]) for i in reversed(range(len(roles)))]

    def _lower_inwards(self, upper, rim_corner, low):
        """The lower grooved face from the rim to the cap's edge, mirrored."""
        return [(low(p), None, role) for p, role in self._upper_inwards(upper, rim_corner)]

    def __repr__(self) -> str:
        return (f"FresnelLens(d={self.focal_distance:g}, D={self.semi_diameter:g}, "
                f"zones={self.zones}, grooves={self.grooves!r}, n={self.refIndex:g})")


__all__ = ["FresnelLens"]
