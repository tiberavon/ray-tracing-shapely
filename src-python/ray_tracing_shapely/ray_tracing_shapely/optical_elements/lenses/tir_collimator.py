"""
Python-specific module: tir_collimator
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
A TIR LED collimator: the section of US 7,762,697 B2, FIG. 3
===============================================================================
One piece of glass with two channels for the light of a point F on its axis:

- **central lens 12:** a flat rear face 12b and a front face 12a designed so
  that light from F leaves parallel to the axis;
- **ring 22 around it:** an incident face 22b (the wall of the cavity the LED
  sits in, a line with a small draft), a reflection face 22c (total internal
  reflection, designed so that light from F leaves parallel after the exit
  face), an exit face 22a (flat, possibly tilted), and a mounting protrusion
  22d.

The patent's lens is not a surface of revolution (fan-shaped areas, diffusing
stripes, a split front face); this is the rotationally symmetric collimator
its design starts from.

Design: constant optical path length (Malus-Dupin). A ray from F meets a fixed
face (12b, 22b), refracts, and travels a distance s to the designed face; s is
the one value that keeps the optical path from F to the outgoing plane
wavefront constant. The path length is linear in s, so every point is exact,
and its normal follows from the two ray directions (rfnrm, rfxnrm). Points and
normals become a spline edge (core.glass_curves), whose tangents are those exact
normals turned by 90 degrees. 12a can instead be fitted as a conic, which
Optiland's ConicGeometry takes as it is.

Conventions are the light's, as SingletLens's: the axis is +x rotated by
``rotation`` degrees, and ``position`` is F. Dimensions are in the unit of the
chip (FIG. 3 read with the chip's height as 1 mm).

Edges, in counter-clockwise path order (14 spans, 15 without the steps):

    12b        central rear face     entrance  refract
    22b        cavity wall (lower)   entrance  refract
    22d-back   mount, rear face      blocker   (none)
    22d-side   mount, outer side     blocker   (none)
    22c        TIR face (lower)      wall      tir
    22a        exit face (lower)     exit      refract
    ST         step 22a -> 12a       blocker   (none; only when 22a misses 12a's edge)
    12a        central front face    exit      refract
    ST, 22a, 22c, 22d-side, 22d-back, 22b   the upper half, in reverse
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, Dict, List, Optional, Tuple, TYPE_CHECKING

from ...core.glass_curves import ConicCurve
from ..prisms.base_prism import BasePrism
from ..prisms.nonimaging_geometry import isl, rfr, rfxnrm
from ..roles import Mechanism, Role
from .collimator_design import collimating_face, dot as _dot, fit_conic, spline_descriptor, unit as _unit

if TYPE_CHECKING:
    from ...core.scene import Scene

XY = Tuple[float, float]


class TIRCollimator(BasePrism):
    """The FIG. 3 LED collimator of US 7,762,697 B2, rotationally symmetric.

    Defaults are FIG. 3 read at 18.5 px per mm (the chip's drawn height as
    1 mm); every one is a parameter.

    Args:
        scene: The scene this collimator belongs to.
        n: Refractive index (the patent names no material; 1.49 is PMMA).
        lens_distance: F to the flat rear face 12b, along the axis.
        cavity_radius: The cavity wall 22b's distance from the axis at 12b.
        cavity_draft_deg: 22b's draft: it widens towards the LED by this angle.
        cavity_depth: Axial position of the cavity's rear end (22b's start
            and the mount's rear face), from F.
        center_thickness: 12b to the vertex of 12a.
        mount_radius: Outer radius of the mounting protrusion 22d.
        mount_length: Axial length of 22d's outer side; 22c starts at its end.
        exit_tilt_deg: Tilt of the flat exit face 22a: its outer edge lies
            further forward by this angle (0: a plane, an annulus in 3D).
        outer_radius: Where 22c ends (FIG. 2: about 33.5). Light through the
            front part of 22b then reaches 22a without total internal
            reflection (``phi_corner`` to ``phi_end``), as in the patent.
            None: 22c extends until it collects all of 22b's light.
        central: ``"spline"`` (12a exact, as designed) or ``"conic"`` (12a
            the best-fit conic, which Optiland's ConicGeometry takes as it is).
        points: Spline points per designed half-curve.
        position: F.
        rotation: Direction of the optical axis, degrees counter-clockwise from +x.

    Attributes:
        design: Numbers from the design (angles in degrees from the axis at F):
            ``phi_corner`` (the ray to 12b's rim, the split between the
            channels), ``phi_start`` (the ray to 22c's rear end), ``phi_top``
            (the ray to 22b's rear end; light between it and phi_start
            reaches the mount, not 22c), ``phi_end`` (the ray to 22c's front
            end; light between phi_corner and it misses 22c), ``tir_margin_deg`` (the smallest
            excess over the critical angle on 22c), ``outer_radius``, and,
            for a conic 12a, ``conic_R``, ``conic_K`` and ``conic_sag_error``.

    Raises:
        ValueError: For a geometry the design cannot meet (22c's start not
            reachable through 22b, no total internal reflection on 22c, a
            ray from 22b leaving through 22a before it reaches 22c).
    """

    type = 'TIRCollimator'

    _edge_mechanisms: ClassVar[Dict[str, Optional[Mechanism]]] = {
        "12b": Mechanism.REFRACT,
        "12a": Mechanism.REFRACT,
        "22b": Mechanism.REFRACT,
        "22c": Mechanism.TIR,
        "22a": Mechanism.REFRACT,
        "22d-back": None,
        "22d-side": None,
        "ST": None,
    }

    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None

    def __init__(
        self,
        scene: 'Scene',
        *,
        n: float = 1.49,
        lens_distance: float = 25.9,
        cavity_radius: float = 18.2,
        cavity_draft_deg: float = 4.2,
        cavity_depth: float = 5.35,
        center_thickness: float = 15.8,
        mount_radius: float = 21.8,
        mount_length: float = 2.95,
        exit_tilt_deg: float = 14.0,
        outer_radius: Optional[float] = 33.5,
        central: str = "spline",
        points: int = 33,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
    ) -> None:
        if central not in ("spline", "conic"):
            raise ValueError(f"central must be 'spline' or 'conic', got {central!r}")
        if points < 3:
            raise ValueError(f"points must be at least 3, got {points}")
        for name, value in (("lens_distance", lens_distance), ("cavity_radius", cavity_radius),
                            ("center_thickness", center_thickness), ("mount_length", mount_length)):
            if value <= 0.0:
                raise ValueError(f"{name} must be positive, got {value}")
        if not 0.0 < cavity_depth < lens_distance:
            raise ValueError(f"cavity_depth must lie in (0, lens_distance), got {cavity_depth}")
        if not 0.0 <= exit_tilt_deg < 60.0:
            raise ValueError(f"exit_tilt_deg must lie in [0, 60), got {exit_tilt_deg}")
        self.lens_distance = float(lens_distance)
        self.cavity_radius = float(cavity_radius)
        self.cavity_draft_deg = float(cavity_draft_deg)
        self.cavity_depth = float(cavity_depth)
        self.center_thickness = float(center_thickness)
        self.mount_radius = float(mount_radius)
        self.mount_length = float(mount_length)
        self.exit_tilt_deg = float(exit_tilt_deg)
        self.outer_radius = None if outer_radius is None else float(outer_radius)
        self.central = central
        self.points = int(points)
        self.design: Dict[str, float] = {}
        self._n_design = float(n)
        super().__init__(scene, size=2.0 * mount_radius, position=position, rotation=rotation, n=n)

    # --- placement -------------------------------------------------------------

    @property
    def axis_direction(self) -> XY:
        """Unit vector along the optical axis, the way the light travels."""
        theta = math.radians(self._rotation)
        return (math.cos(theta), math.sin(theta))

    @property
    def focal_point(self) -> XY:
        """F, the point both channels collimate."""
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

    # --- design ----------------------------------------------------------------

    def _design_central(self, points: Optional[int] = None) -> Tuple[List[XY], List[XY]]:
        """12a, upper half, from the vertex out: points and normals (canonical frame)."""
        return collimating_face(self._n_design, self.lens_distance, self.center_thickness,
                                math.atan2(self.cavity_radius, self.lens_distance), points or self.points)

    def _design_ring(self, points: Optional[int] = None) -> Tuple[List[XY], List[XY], XY]:
        """22c, upper half, from its rear end P0 to its front end: points, normals, and d_in."""
        n, f = self._n_design, self.lens_distance
        count = points or self.points
        rb, at = self.cavity_radius, self.cavity_depth
        rt = rb + (f - at) * math.tan(math.radians(self.cavity_draft_deg))
        top, corner = (at, rt), (f, rb)
        ell = _unit((corner[0] - top[0], corner[1] - top[1]))
        n_b = (-ell[1], ell[0])                   # into the glass (away from the axis)
        tau = math.radians(self.exit_tilt_deg)
        back = rfr((1.0, 0.0), (-math.cos(tau), math.sin(tau)), 1.0, n)
        d_in = (-back[0], -back[1])               # inside, before 22a: leaves along +x

        def through_22b(phi: float) -> Tuple[XY, XY]:
            i = (math.cos(phi), math.sin(phi))
            q = isl((0.0, 0.0), i, top, ell)
            r = rfr((-i[0], -i[1]), n_b, 1.0, n)
            return q, r

        p0 = (at + self.mount_length, self.mount_radius)
        phi_c, phi_top = math.atan2(rb, f), math.atan2(rt, at)

        def miss(phi: float) -> float:
            q, r = through_22b(phi)
            return r[0] * (p0[1] - q[1]) - r[1] * (p0[0] - q[0])

        lo, hi = phi_c, phi_top
        if (miss(lo) > 0.0) == (miss(hi) > 0.0):
            raise ValueError(
                "TIRCollimator: no ray from F through 22b reaches 22c's rear end "
                f"(mount corner {p0}); move the mount or the cavity.")
        for _ in range(64):                   # halvings past double precision
            mid = 0.5 * (lo + hi)
            if (miss(mid) > 0.0) == (miss(lo) > 0.0):
                lo = mid
            else:
                hi = mid
        phi_start = 0.5 * (lo + hi)
        q0, _ = through_22b(phi_start)
        c = math.hypot(q0[0], q0[1]) + n * math.dist(q0, p0) - n * _dot(d_in, p0)
        def on_22c(phi: float) -> Tuple[XY, XY]:
            q, r = through_22b(phi)
            s = (c - math.hypot(q[0], q[1]) + n * _dot(d_in, q)) / (n * (1.0 - _dot(d_in, r)))
            return (q[0] + s * r[0], q[1] + s * r[1]), r

        phi_end = phi_c
        if self.outer_radius is not None:
            full = on_22c(phi_c)[0][1]
            if not self.mount_radius < self.outer_radius <= full:
                raise ValueError(f"TIRCollimator: outer_radius must lie in ({self.mount_radius:.4g}, "
                                 f"{full:.4g}], the radii 22c can reach; got {self.outer_radius}")
            lo, hi = phi_c, phi_start             # 22c's radius falls as phi rises
            for _ in range(64):                   # halvings past double precision
                mid = 0.5 * (lo + hi)
                if on_22c(mid)[0][1] > self.outer_radius:
                    lo = mid
                else:
                    hi = mid
            phi_end = 0.5 * (lo + hi)
        crit = math.asin(1.0 / n)
        margin = math.inf
        pts, nrms = [], []
        for k in range(count):
            phi = phi_start + (phi_end - phi_start) * k / (count - 1)
            p, r = on_22c(phi)
            nrm = rfxnrm(r, d_in)
            incidence = math.acos(min(1.0, abs(_dot(r, nrm))))
            margin = min(margin, incidence - crit)
            pts.append(p)
            nrms.append(nrm)
        if margin <= 0.0:
            raise ValueError(f"TIRCollimator: 22c falls {math.degrees(-margin):.2f} deg short of total "
                             "internal reflection; reduce the exit tilt or change the cavity.")
        self.design.update(phi_corner=math.degrees(phi_c), phi_start=math.degrees(phi_start),
                           phi_top=math.degrees(phi_top), phi_end=math.degrees(phi_end),
                           tir_margin_deg=math.degrees(margin))
        return pts, nrms, d_in

    def _compute_path(self) -> List[Dict[str, Any]]:
        f, rb, at = self.lens_distance, self.cavity_radius, self.cavity_depth
        rt = rb + (f - at) * math.tan(math.radians(self.cavity_draft_deg))
        lens_pts, lens_nrms = self._design_central()
        ring_pts, ring_nrms, d_in = self._design_ring()
        tau = math.radians(self.exit_tilt_deg)

        edge = lens_pts[-1]                       # 12a's rim, reached by the ray to 12b's rim
        vertex_x = lens_pts[0][0]
        lens_desc: Dict[str, Any]
        if self.central == "conic":
            big_r, big_k, err = fit_conic(lens_pts, vertex_x)
            self.design.update(conic_R=big_r, conic_K=big_k, conic_sag_error=err)
            cc = ConicCurve((vertex_x, 0.0), (-1.0, 0.0), big_r, big_k, 0.0, 1e-300)
            edge = cc.point(-edge[1])             # same rim radius, on the conic
            lens_desc = {"type": "conic", "vertex": list(self._world((vertex_x, 0.0))),
                         "axis": list(self._world_vec((-1.0, 0.0))), "radius": big_r, "conic": big_k}
        else:
            full_pts = [(x, -y) for x, y in reversed(lens_pts[1:])] + lens_pts
            full_nrms = [(nx, -ny) for nx, ny in reversed(lens_nrms[1:])] + lens_nrms
            lens_desc = spline_descriptor([self._world(p) for p in full_pts],
                                          [self._world_vec(v) for v in full_nrms])

        front = ring_pts[-1]                      # 22c's front end, where 22a starts
        exit_inner = (front[0] - (front[1] - edge[1]) * math.tan(tau), edge[1])
        self.design["outer_radius"] = front[1]
        self._check_ring_clearance(ring_pts, d_in, exit_inner, front, edge)

        # 22c lower half runs P0 -> front; the upper half front -> P0.
        lower_ring = [(x, -y) for x, y in ring_pts]
        lower_nrms = [(nx, -ny) for nx, ny in ring_nrms]
        ring_lower = spline_descriptor([self._world(p) for p in lower_ring],
                                       [self._world_vec(v) for v in lower_nrms])
        ring_upper = spline_descriptor([self._world(p) for p in reversed(ring_pts)],
                                       [self._world_vec(v) for v in reversed(ring_nrms)])

        step = math.dist(exit_inner, edge) > 1e-9 * self.mount_radius
        def low(p: XY) -> XY:
            return (p[0], -p[1])

        entries: List[Tuple[XY, Optional[Dict[str, Any]], Tuple[str, str, Role]]] = [
            ((f, rb), None, ("12b", "Central Rear Face", Role.ENTRANCE)),
            ((f, -rb), None, ("22b", "Cavity Wall", Role.ENTRANCE)),
            (low((at, rt)), None, ("22d-back", "Mount Rear Face", Role.BLOCKER)),
            (low((at, self.mount_radius)), None, ("22d-side", "Mount Side", Role.BLOCKER)),
            (low(ring_pts[0]), ring_lower, ("22c", "TIR Face", Role.WALL)),
            (low(front), None, ("22a", "Exit Face", Role.EXIT)),
        ]
        if step:
            entries.append((low(exit_inner), None, ("ST", "Step", Role.BLOCKER)))
        entries.append((low(edge), lens_desc, ("12a", "Central Front Face", Role.EXIT)))
        if step:
            entries.append((edge, None, ("ST", "Step", Role.BLOCKER)))
        entries += [
            (exit_inner, None, ("22a", "Exit Face", Role.EXIT)),
            (front, ring_upper, ("22c", "TIR Face", Role.WALL)),
            (ring_pts[0], None, ("22d-side", "Mount Side", Role.BLOCKER)),
            ((at, self.mount_radius), None, ("22d-back", "Mount Rear Face", Role.BLOCKER)),
            ((at, rt), None, ("22b", "Cavity Wall", Role.ENTRANCE)),
        ]
        self._edge_roles = [role for _, _, role in entries]
        path = []
        for p, desc, _ in entries:
            x, y = self._world(p)
            entry: Dict[str, Any] = {"x": x, "y": y, "arc": False}
            if desc is not None:
                entry["curve"] = desc
            path.append(entry)
        return path

    def section_faces(self, points: Optional[int] = None) -> Dict[str, Tuple[List[XY], List[XY]]]:
        """The upper half-section's optical faces in the canonical frame (F at the
        origin, the axis along +x, r = y >= 0), for building the same collimator in
        another engine (Optiland's sequential engine:
        ray_tracing_shapely_optiland.sequential_collimator).

        Args:
            points: Points per designed face (default: the spline's own count).

        Returns:
            {label: (points, unit normals)}: ``12b``, ``22b`` and ``22a`` as their two
            ends; ``12a`` from the vertex out and ``22c`` from its rear end to its
            front end, each designed point with its exact normal.
        """
        f, rb, at = self.lens_distance, self.cavity_radius, self.cavity_depth
        rt = rb + (f - at) * math.tan(math.radians(self.cavity_draft_deg))
        lens = self._design_central(points)
        ring_pts, ring_nrms, _ = self._design_ring(points)
        rim = self._rim_12a()
        front = ring_pts[-1]
        tau = math.radians(self.exit_tilt_deg)
        inner = (front[0] - (front[1] - rim[1]) * math.tan(tau), rim[1])

        def line(p: XY, q: XY) -> Tuple[List[XY], List[XY]]:
            d = _unit((q[0] - p[0], q[1] - p[1]))
            return [p, q], [(-d[1], d[0])] * 2

        return {"12b": line((f, 0.0), (f, rb)), "22b": line((at, rt), (f, rb)),
                "12a": lens, "22c": (ring_pts, ring_nrms), "22a": line(inner, front)}

    def _rim_12a(self) -> XY:
        """12a's rim, as the outline has it, in the canonical frame (r >= 0)."""
        ux, uy = self.axis_direction
        for i, e in enumerate(self.path):
            if self._edge_roles[i][0] == "12a":
                dx, dy = e["x"] - self.focal_point[0], e["y"] - self.focal_point[1]
                return (dx * ux + dy * uy, abs(-dx * uy + dy * ux))
        raise RuntimeError("TIRCollimator: no 12a edge in the outline")

    def _check_ring_clearance(self, ring_pts: List[XY], d_in: XY, exit_inner: XY, front: XY,
                              edge: XY) -> None:
        """Every ring ray reflected by 22c must reach 22a, not 12a or the step."""
        along = _unit((front[0] - exit_inner[0], front[1] - exit_inner[1]))
        for p in ring_pts[:-1]:                   # the last point lies on 22a itself
            hit = isl(p, d_in, exit_inner, along)
            if hit[1] < exit_inner[1] - 1e-9 * self.mount_radius:
                raise ValueError(
                    f"TIRCollimator: light reflected at 22c (r = {p[1]:.4g}) meets 22a's line at "
                    f"r = {hit[1]:.4g}, inside 12a's rim (r = {edge[1]:.4g}); it would reach 12a.")

    def __repr__(self) -> str:
        return (f"TIRCollimator(f={self.lens_distance:g}, rb={self.cavity_radius:g}, "
                f"T={self.center_thickness:g}, n={self.refIndex:g}, central={self.central!r})")


__all__ = ["TIRCollimator"]
