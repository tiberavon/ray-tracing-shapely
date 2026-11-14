"""
Python-specific module: conic mirror
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
CONIC MIRROR -- an exact curved mirror in 2D
===============================================================================
A segment of a conic section, intersected analytically and reflected about
its exact normal. Sampling the curve (``ParamCurveObjMixin``) would put a
facet error into the very 2D-against-3D comparison these mirrors exist for,
so nothing here is sampled except the drawing.

The curve is described the way Optiland describes a conic surface, in a local
frame at the vertex:

- ``z`` along ``axis`` (a unit vector from the vertex), ``s`` across it, along
  ``axis`` rotated 90 degrees counter-clockwise;
- ``s**2 - 2 R z + (1 + K) z**2 = 0``, i.e. the sag
  ``z(s) = c s**2 / (1 + sqrt(1 - (1 + K) c**2 s**2))`` with ``c = 1/R``;
- ``R`` signed as in Optiland: positive when the centre of curvature (at the
  vertex) lies along ``+axis``. ``K = 0`` a circle, ``-1 < K < 0`` and
  ``K > 0`` ellipses, ``K = -1`` a parabola, ``K < -1`` a hyperbola.

Only the branch through the vertex is the mirror, and only where the sag is
single-valued (``(1 + K) c**2 s**2 <= 1``): exactly what Optiland's
``ConicGeometry`` describes, so a revolve export of it is exact. The mirror
spans ``s`` from ``extent[0]`` to ``extent[1]``; ``semi_diameter=h`` is
``extent=(-h, h)``.

Both faces reflect, as the flat ``Mirror`` does. Reflectivity is 1 in 2D;
a 3D export carries no reflectance (the bridge takes one per span).

Labels: the object's ``name`` is its short label, its ``role`` defaults to
``Role.WALL``, its mechanism is ``Mechanism.REFLECT`` (C-LABEL-02).

``ArcMirror`` is the circle case (``K = 0``), exported with a ``circle``
descriptor. It is not Ray Optics Simulation's three-point ``ArcMirror``,
which is not ported: that one may reach past the equator; this one is a
spherical cap that a revolve can make exact.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ...core.scene_objs.base_scene_obj import BaseSceneObj
from ...core.geometry import geometry
from ..roles import Mechanism, Role

if TYPE_CHECKING:
    from ...core.scene import Scene

XY = Tuple[float, float]


def conic_sag(s: float, radius: float, conic: float) -> float:
    """The sag ``z(s)`` of the vertex branch (Optiland's conic sag formula)."""
    c = 1.0 / radius
    root = 1.0 - (1.0 + conic) * c * c * s * s
    if root < 0.0:
        raise ValueError(f"s = {s} is beyond the conic's single-valued part (R = {radius}, K = {conic})")
    return c * s * s / (1.0 + math.sqrt(root))


def max_single_valued_s(radius: float, conic: float) -> float:
    """The largest ``|s|`` the sag is defined at: the equator of an ellipse or circle."""
    return math.inf if conic <= -1.0 else abs(radius) / math.sqrt(1.0 + conic)


class ConicMirror(BaseSceneObj):
    """A mirror whose shape is a segment of a conic section's vertex branch.

    Args:
        scene: The scene this mirror belongs to.
        vertex: The conic's vertex, scene coordinates.
        axis: Direction of the conic's axis from the vertex (need not be unit).
        radius: Vertex radius of curvature ``R``, signed (positive: the
            centre of curvature lies along ``+axis``).
        conic: Conic constant ``K``.
        semi_diameter: The mirror spans ``s`` in ``(-h, h)``.
        extent: Or the ``(s_start, s_end)`` it spans, for an off-axis piece.
        name: Short label (used as the span label on export).
        role: Defaults to ``Role.WALL``.

    Raises:
        ValueError: For a zero or infinite radius (use ``Mirror``), a zero
            axis, an empty extent, or an extent reaching past the part of
            the curve that is single-valued as ``z(s)``.
    """

    type = 'ConicMirror'
    is_optical = True
    merges_with_glass = False
    mechanism = Mechanism.REFLECT
    serializable_defaults = {'vertex': None, 'axis': None, 'radius': None, 'conic': 0.0,
                             'extent': None}

    def __init__(
        self,
        scene: 'Scene',
        vertex: XY,
        axis: XY,
        radius: float,
        conic: float = 0.0,
        *,
        semi_diameter: Optional[float] = None,
        extent: Optional[Tuple[float, float]] = None,
        name: Optional[str] = None,
        role: Optional[Role] = Role.WALL,
    ) -> None:
        super().__init__(scene, None)
        radius, conic = float(radius), float(conic)
        if radius == 0.0 or math.isinf(radius) or math.isnan(radius):
            raise ValueError(f"radius must be finite and non-zero (a flat mirror is Mirror), got {radius}")
        ax, ay = float(axis[0]), float(axis[1])
        length = math.hypot(ax, ay)
        if length == 0.0:
            raise ValueError("axis is zero")
        if (semi_diameter is None) == (extent is None):
            raise ValueError("give exactly one of semi_diameter and extent")
        if semi_diameter is not None:
            if semi_diameter <= 0.0:
                raise ValueError(f"semi_diameter must be positive, got {semi_diameter}")
            extent = (-float(semi_diameter), float(semi_diameter))
        s0, s1 = float(extent[0]), float(extent[1])
        if not s0 < s1:
            raise ValueError(f"extent must be (s_start, s_end) with s_start < s_end, got {extent}")
        limit = max_single_valued_s(radius, conic)
        if max(abs(s0), abs(s1)) > limit * (1.0 + 1e-12):
            raise ValueError(
                f"extent {extent} reaches past |s| = {limit:.6g}, where the conic (R = {radius}, "
                f"K = {conic}) stops being single-valued as z(s): that is not one mirror a "
                "revolve can make exact.")
        self.vertex: XY = (float(vertex[0]), float(vertex[1]))
        self.axis: XY = (ax / length, ay / length)
        self.radius = radius
        self.conic = conic
        self.extent: Tuple[float, float] = (s0, s1)
        self.name = name
        self.role = role

    # --- frames ---------------------------------------------------------------

    @property
    def left(self) -> XY:
        """The ``+s`` direction: ``axis`` rotated 90 degrees counter-clockwise."""
        return (-self.axis[1], self.axis[0])

    def to_local(self, p: XY) -> XY:
        """A scene point as ``(s, z)``."""
        dx, dy = p[0] - self.vertex[0], p[1] - self.vertex[1]
        return (dx * self.left[0] + dy * self.left[1], dx * self.axis[0] + dy * self.axis[1])

    def to_scene(self, s: float, z: float) -> XY:
        return (self.vertex[0] + s * self.left[0] + z * self.axis[0],
                self.vertex[1] + s * self.left[1] + z * self.axis[1])

    def point_at(self, s: float) -> XY:
        """The mirror point at transverse coordinate ``s``."""
        return self.to_scene(s, conic_sag(s, self.radius, self.conic))

    def normal_at(self, s: float) -> XY:
        """Unit normal at ``s``, on the side of the vertex's centre of curvature.

        ``-grad F`` of ``F = s**2 - 2 R z + (1 + K) z**2``: ``(-s, R - (1 + K) z)``,
        which at the vertex is ``R * axis``.
        """
        z = conic_sag(s, self.radius, self.conic)
        ns, nz = -s, self.radius - (1.0 + self.conic) * z
        length = math.hypot(ns, nz)
        return (ns / length * self.left[0] + nz / length * self.axis[0],
                ns / length * self.left[1] + nz / length * self.axis[1])

    def on_curve(self, p: XY) -> Tuple[float, bool]:
        """``(distance along the axis from the curve, whether s is in the extent)`` for ``p``."""
        s, z = self.to_local(p)
        if abs(s) > max_single_valued_s(self.radius, self.conic):
            return math.inf, False
        return abs(z - conic_sag(s, self.radius, self.conic)), self.extent[0] <= s <= self.extent[1]

    def sample_points(self, count: int = 65) -> List[XY]:
        """Points along the mirror, from ``extent[0]`` to ``extent[1]`` (for drawing)."""
        s0, s1 = self.extent
        return [self.point_at(s0 + (s1 - s0) * k / (count - 1)) for k in range(count)]

    def descriptor(self) -> Dict[str, Any]:
        """The profile.json ``curve`` descriptor of the whole curve."""
        return {"type": "conic", "vertex": list(self.vertex), "axis": list(self.axis),
                "radius": self.radius, "conic": self.conic}

    # --- the simulator's interface ------------------------------------------------

    def _hits(self, p: XY, d: XY) -> List[float]:
        """Ray parameters ``t`` (``p + t d``) where the ray meets the mirror, ascending."""
        s0, z0 = self.to_local(p)
        ds = d[0] * self.left[0] + d[1] * self.left[1]
        dz = d[0] * self.axis[0] + d[1] * self.axis[1]
        R, k1 = self.radius, 1.0 + self.conic
        a = ds * ds + k1 * dz * dz
        b = 2.0 * (s0 * ds - R * dz + k1 * z0 * dz)
        c = s0 * s0 - 2.0 * R * z0 + k1 * z0 * z0
        roots: List[float] = []
        if abs(a) <= 1e-14 * (ds * ds + dz * dz):
            if b != 0.0:
                roots = [-c / b]
        else:
            disc = b * b - 4.0 * a * c
            if disc < 0.0:
                return []
            q = -0.5 * (b + math.copysign(math.sqrt(disc), b))
            roots = [q / a] + ([c / q] if q != 0.0 else [])
        hits = []
        limit = max_single_valued_s(R, self.conic)
        for t in roots:
            s, z = s0 + t * ds, z0 + t * dz
            if abs(s) > limit * (1.0 + 1e-12):
                continue
            # the vertex branch: R - (1 + K) z has the sign of R (zero at the equator)
            if (R - k1 * z) * R < -1e-12 * R * R:
                continue
            if self.extent[0] <= s <= self.extent[1]:
                hits.append(t)
        return sorted(hits)

    def check_ray_intersects(self, ray) -> Optional[Any]:
        """The nearest point where the ray meets the mirror, beyond the
        simulator's minimum segment length (so a ray leaving the mirror does
        not meet it again where it starts, but does meet it further on)."""
        from ...core.simulator import Simulator  # noqa: PLC0415  (circular at import time)

        p = (ray.p1['x'], ray.p1['y'])
        d = (ray.p2['x'] - p[0], ray.p2['y'] - p[1])
        length = math.hypot(*d)
        if length == 0.0:
            return None
        for t in self._hits(p, d):
            if t * length >= Simulator.MIN_RAY_SEGMENT_LENGTH:
                return geometry.point(p[0] + t * d[0], p[1] + t * d[1])
        return None

    def on_ray_incident(self, ray, ray_index: int, incident_point, surface_merging_objs=None,
                        verbose: int = 0) -> None:
        """Specular reflection about the exact normal at the incident point."""
        q = (incident_point['x'], incident_point['y'])
        dx, dy = ray.p2['x'] - ray.p1['x'], ray.p2['y'] - ray.p1['y']
        length = math.hypot(dx, dy)
        dx, dy = dx / length, dy / length
        s, _ = self.to_local(q)
        nx, ny = self.normal_at(s)
        dot = dx * nx + dy * ny
        rx, ry = dx - 2.0 * dot * nx, dy - 2.0 * dot * ny

        if getattr(ray, 'record_surface_hits', False):
            ray.hit_surface_uuid = self._uuid
            ray.hit_point = {'x': q[0], 'y': q[1]}
            ray.hit_normal = {'x': nx, 'y': ny}
            ray.incident_angle = math.acos(min(1.0, abs(dot)))

        ray.p1 = {'x': q[0], 'y': q[1]}
        ray.p2 = {'x': q[0] + rx, 'y': q[1] + ry}
        return None

    # --- the rest of the scene-object interface -------------------------------------

    def serialize(self) -> Dict[str, Any]:
        return {'type': self.type, 'vertex': list(self.vertex), 'axis': list(self.axis),
                'radius': self.radius, 'conic': self.conic, 'extent': list(self.extent)}

    def move(self, diff_x: float, diff_y: float) -> bool:
        self.vertex = (self.vertex[0] + diff_x, self.vertex[1] + diff_y)
        return True

    def get_default_center(self):
        s0, s1 = self.extent
        x, y = self.point_at(0.5 * (s0 + s1))
        return geometry.point(x, y)

    def draw(self, canvas_renderer: Any, is_above_light: bool, is_hovered: bool) -> bool:
        ctx = canvas_renderer.ctx
        ctx.strokeStyle = (self.scene.highlight_color_css if is_hovered else
                           canvas_renderer.rgba_to_css_color(self.scene.theme.mirror['color']))
        ctx.lineWidth = self.scene.theme.mirror['width'] * canvas_renderer.length_scale
        pts = self.sample_points()
        ctx.beginPath()
        ctx.moveTo(*pts[0])
        for x, y in pts[1:]:
            ctx.lineTo(x, y)
        ctx.stroke()
        return True


class ArcMirror(ConicMirror):
    """A spherical-cap mirror: the circle case of ConicMirror (``K = 0``).

    Exported with a ``circle`` descriptor (centre and radius), which is what
    a circular arc is everywhere else in profile.json.
    """

    type = 'ArcMirror'

    def __init__(self, scene: 'Scene', vertex: XY, axis: XY, radius: float, *,
                 semi_diameter: Optional[float] = None,
                 extent: Optional[Tuple[float, float]] = None,
                 name: Optional[str] = None, role: Optional[Role] = Role.WALL) -> None:
        super().__init__(scene, vertex, axis, radius, 0.0, semi_diameter=semi_diameter,
                         extent=extent, name=name, role=role)

    @property
    def center(self) -> XY:
        return self.to_scene(0.0, self.radius)

    def descriptor(self) -> Dict[str, Any]:
        return {"type": "circle", "center": list(self.center), "radius": abs(self.radius)}


__all__ = ["ConicMirror", "ArcMirror", "conic_sag", "max_single_valued_s"]
