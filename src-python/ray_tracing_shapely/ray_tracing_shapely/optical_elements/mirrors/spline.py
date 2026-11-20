"""
Python-specific module: spline mirror
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
SPLINE MIRROR -- an exact freeform mirror in 2D
===============================================================================
A mirror on a cubic Hermite curve through given points with given normals:
the same ``SplineCurve`` a glass's spline edge is, so a mirror designed point
by point (an SMS mirror, a freeform reflector) is exact between its points,
with the designed normal at each. A ray meets it where the curve's cubic
segments cross the ray (found exactly, not on a sampled polyline) and
reflects about the curve's normal there. Nothing is sampled except the
drawing.

Both faces reflect, as the flat ``Mirror`` and ``ConicMirror`` do.
Reflectivity is 1 in 2D.

Labels: the object's ``name`` is its short label, its ``role`` defaults to
``Role.WALL``, its mechanism is ``Mechanism.REFLECT`` (C-LABEL-02).
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

from ...core.geometry import geometry
from ...core.glass_curves import SplineCurve
from ...core.scene_objs.base_scene_obj import BaseSceneObj
from ..roles import Mechanism, Role

if TYPE_CHECKING:
    from ...core.scene import Scene

XY = Tuple[float, float]


class SplineMirror(BaseSceneObj):
    """A mirror on a cubic Hermite spline through ``points``, normal to ``normals`` there.

    Args:
        scene: The scene this mirror belongs to.
        points: The spline's points, in order along the mirror (at least two, none repeated).
        normals: A normal at each point (either sign; need not be unit). The spline's
            tangent at each point is its normal turned by 90 degrees.
        name: Short label (used as the span label on export).
        role: Defaults to ``Role.WALL``.

    Raises:
        ValueError: For fewer than two points, a count of normals that differs from the
            points', a zero normal, or two consecutive points that coincide.
    """

    type = 'SplineMirror'
    is_optical = True
    merges_with_glass = False
    mechanism = Mechanism.REFLECT
    serializable_defaults: Dict[str, Any] = {}     # serialize() writes the points and normals

    def __init__(
        self,
        scene: 'Scene',
        points: Sequence[XY],
        normals: Sequence[XY],
        *,
        name: Optional[str] = None,
        role: Optional[Role] = Role.WALL,
    ) -> None:
        super().__init__(scene, None)
        if len(points) != len(normals):
            raise ValueError(f"one normal per point: {len(points)} points, {len(normals)} normals")
        tangents = []
        for nx, ny in normals:
            if math.hypot(nx, ny) == 0.0:
                raise ValueError("a normal must be non-zero")
            tangents.append((ny, -nx))
        # a consistent direction along the curve: each tangent points toward the next point
        for k in range(len(points)):
            a, b = (points[k], points[k + 1]) if k + 1 < len(points) else (points[k - 1], points[k])
            if tangents[k][0] * (b[0] - a[0]) + tangents[k][1] * (b[1] - a[1]) < 0.0:
                tangents[k] = (-tangents[k][0], -tangents[k][1])
        self.curve = SplineCurve(points, tangents, 0.0, float(len(points) - 1))
        self.name = name
        self.role = role
        self._hits: Dict[XY, float] = {}     # the curve parameter of each point the last rays met

    @property
    def points(self) -> List[XY]:
        return list(self.curve.points)

    @property
    def tangents(self) -> List[XY]:
        return list(self.curve.tangents)

    def normal_at(self, p: float) -> XY:
        """Unit normal at curve parameter ``p`` (to the left of the direction of the points)."""
        return self.curve.left_normal(p)

    def descriptor(self) -> Dict[str, Any]:
        """The profile.json ``curve`` descriptor of the whole curve."""
        return self.curve.descriptor()

    def sample_points(self, max_sag: float = 1e-4) -> List[XY]:
        """Points along the mirror, close enough to draw it (sag below ``max_sag``)."""
        return self.curve.coords(max_sag)

    # --- the simulator's interface ------------------------------------------------

    def check_ray_intersects(self, ray) -> Optional[Any]:
        """The nearest point where the ray meets the mirror, beyond the simulator's minimum
        segment length (so a ray leaving the mirror does not meet it again where it starts)."""
        from ...core.simulator import Simulator  # noqa: PLC0415  (circular at import time)

        p = (ray.p1['x'], ray.p1['y'])
        d = (ray.p2['x'] - p[0], ray.p2['y'] - p[1])
        length = math.hypot(*d)
        if length == 0.0:
            return None
        for t, u in self.curve.line_hits(p, d):
            if t * length >= Simulator.MIN_RAY_SEGMENT_LENGTH:
                hit = (p[0] + t * d[0], p[1] + t * d[1])
                if len(self._hits) > 4096:
                    self._hits.clear()
                self._hits[hit] = u
                return geometry.point(*hit)
        return None

    def on_ray_incident(self, ray, ray_index: int, incident_point, surface_merging_objs=None,
                        verbose: int = 0) -> None:
        """Specular reflection about the exact normal at the incident point."""
        q = (incident_point['x'], incident_point['y'])
        dx, dy = ray.p2['x'] - ray.p1['x'], ray.p2['y'] - ray.p1['y']
        length = math.hypot(dx, dy)
        dx, dy = dx / length, dy / length
        p = self._hits.pop(q, None)
        if p is None:                       # a point this mirror did not compute: find it on the curve
            _, p = self.curve.nearest(q)
        nx, ny = self.normal_at(p)
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
        return {'type': self.type, 'points': [list(p) for p in self.points],
                'normals': [list(self.normal_at(float(k))) for k in range(len(self.points))]}

    def move(self, diff_x: float, diff_y: float) -> bool:
        pts = [(x + diff_x, y + diff_y) for x, y in self.curve.points]
        self.curve = SplineCurve(pts, self.curve.tangents, self.curve.p_start, self.curve.p_end)
        return True

    def get_default_center(self):
        x, y = self.curve.point(0.5 * (self.curve.p_start + self.curve.p_end))
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


__all__ = ['SplineMirror']
