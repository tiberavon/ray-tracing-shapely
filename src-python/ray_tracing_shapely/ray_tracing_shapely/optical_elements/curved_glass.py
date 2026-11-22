"""
Python-specific module: curved glass
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
CurvedGlass -- a glass whose edges may be exact conics, aspheres or splines
===============================================================================
The JavaScript simulator's `Glass` has straight edges and circular arcs, and
so does this package's. A `CurvedGlass` is a `Glass` whose path entries may
also carry a ``curve`` descriptor (`core.glass_curves`): the edge from that
entry to the next is then that curve, intersected exactly, with its exact
normal. It is saved under its own type, ``CurvedGlass``, so a file the
JavaScript simulator reads never holds a format it cannot.

Everything else is `Glass`'s: straight and arc edges, refraction, surface
merging. The designed elements (`BasePrism` and its subclasses) are
`CurvedGlass`es. `core.glass_spans` counts and draws curve spans from the path
alone, so the renderer and the analysis layer need nothing from this class.
===============================================================================
"""

import math
from typing import Any, Dict

from ..core import geometry
from ..core.constants import EDGE_DETECTION_THRESHOLD_SQUARED, MIN_RAY_SEGMENT_LENGTH
from ..core.glass_curves import curve_from_descriptor, transform_descriptor
from ..core.scene_objs.glass.glass import Glass


class CurvedGlass(Glass):
    """A `Glass` whose path entries may carry a ``curve`` descriptor.

    Args:
        scene: The scene it belongs to.
        json_obj: Its `serialize()` dict: `Glass`'s, with ``curve`` allowed on
            a path entry (the edge from that entry to the next).
    """

    type = 'CurvedGlass'

    # --- transforms: the curve descriptors move with their end points -------

    @classmethod
    def _path_item_schema(cls):
        """Glass's path entry, and the curve descriptor of the edge that starts there."""
        from ray_tracing_shapely.core.scene_objs.base_scene_obj import schema_entry as e
        return [*super()._path_item_schema(),
                e('curve', 'curve', 'Curved edge to the next vertex', python_only=True)]

    def move(self, diff_x, diff_y):
        super().move(diff_x, diff_y)
        for point in self.path:
            if point.get('curve'):
                point['curve'] = transform_descriptor(
                    point['curve'], lambda q: (q[0] + diff_x, q[1] + diff_y), lambda v: v)
        return True

    def rotate(self, angle, center=None):
        if center is None:
            center = self.get_default_center()
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        def turn(q):
            dx, dy = q[0] - center['x'], q[1] - center['y']
            return (center['x'] + dx * cos_a - dy * sin_a, center['y'] + dx * sin_a + dy * cos_a)

        super().rotate(angle, center)
        for point in self.path:
            if point.get('curve'):
                point['curve'] = transform_descriptor(
                    point['curve'], turn, lambda v: (v[0] * cos_a - v[1] * sin_a, v[0] * sin_a + v[1] * cos_a))
        return True

    def scale(self, scale_factor, center=None):
        if center is None:
            center = self.get_default_center()

        def stretch(q):
            return (center['x'] + (q[0] - center['x']) * scale_factor,
                    center['y'] + (q[1] - center['y']) * scale_factor)

        super().scale(scale_factor, center)
        for point in self.path:
            if point.get('curve'):
                point['curve'] = transform_descriptor(point['curve'], stretch, lambda v: v, scale_factor)
        return True

    # --- the two per-edge dispatch points ----------------------------------

    def _check_segment_intersection(self, ray, i):
        if self.path[i].get('curve') and not self.path[i].get('arc'):
            # An exact conic or spline edge from path[i] to path[i+1]
            return self._check_curve_intersection(ray, i, (i + 1) % len(self.path))
        return super()._check_segment_intersection(ray, i)

    def _get_segment_incident_data(self, ray, ray2, i):
        if self.path[i].get('curve') and not self.path[i].get('arc'):
            result: Dict[str, Any] = {
                'point': None,
                'distance_sq': float('inf'),
                'normal_x': 0,
                'normal_y': 0,
                'near_edge': False,
                'ray2_intersect_count': 0
            }
            self._process_curve_segment(ray, ray2, i, (i + 1) % len(self.path), result)
            return result
        return super()._get_segment_incident_data(ray, ray2, i)

    # --- the curve itself (moved unchanged from Glass) -----------------------

    def _curve(self, i, next_i):
        """The exact curve of the edge from path[i] to path[next_i] (cached per descriptor
        and end points, which move, rotate and scale replace)."""
        desc = self.path[i]['curve']
        start = (self.path[i]['x'], self.path[i]['y'])
        end = (self.path[next_i]['x'], self.path[next_i]['y'])
        key = (id(desc), start, end)
        cache = self.__dict__.setdefault('_curve_cache', {})
        hit = cache.get(i)
        if hit is None or hit[0] != key or hit[2] is not desc:
            hit = (key, curve_from_descriptor(desc, start, end), desc)
            cache[i] = hit
        return hit[1]

    def _curve_hits(self, ray_p1, ray_p2, i, next_i):
        """Points where a ray meets the curve edge, farther than the minimum segment
        length from its start, nearest first: [(dist_sq, point)]."""
        curve = self._curve(i, next_i)
        direction = (ray_p2.x - ray_p1.x, ray_p2.y - ray_p1.y)
        min_seg_len_sq = MIN_RAY_SEGMENT_LENGTH ** 2 * self.scene.length_scale ** 2
        out = []
        for t, _ in curve.line_hits((ray_p1.x, ray_p1.y), direction, slack=1e-12):
            if t <= 0.0:
                continue
            q = geometry.point(ray_p1.x + t * direction[0], ray_p1.y + t * direction[1])
            dist_sq = geometry.distance_squared(ray_p1, q)
            if dist_sq > min_seg_len_sq:  # per root: a ray starting on the curve keeps its far root
                out.append((dist_sq, q))
        return sorted(out, key=lambda h: h[0])

    def _check_curve_intersection(self, ray, i, next_i):
        """Nearest intersection of a ray with an exact curve edge, or None."""
        ray_p1 = geometry.point(ray.p1['x'], ray.p1['y']) if isinstance(ray.p1, dict) else ray.p1
        ray_p2 = geometry.point(ray.p2['x'], ray.p2['y']) if isinstance(ray.p2, dict) else ray.p2
        hits = self._curve_hits(ray_p1, ray_p2, i, next_i)
        return hits[0][1] if hits else None

    def _process_curve_segment(self, ray, ray2, i, next_i, result):
        """Process an exact curve edge for incident data.

        The normal points back towards the side the ray comes from, as for a
        line or an arc; a hit within the edge threshold of either end point
        is flagged as near an edge; the test ray's crossings are counted for
        the inside/outside parity.
        """
        ray_p1 = geometry.point(ray.p1['x'], ray.p1['y']) if isinstance(ray.p1, dict) else ray.p1
        ray_p2 = geometry.point(ray.p2['x'], ray.p2['y']) if isinstance(ray.p2, dict) else ray.p2
        hits = self._curve_hits(ray_p1, ray_p2, i, next_i)
        if hits:
            dist_sq, rp = hits[0]
            result['point'] = rp
            result['distance_sq'] = dist_sq
            curve = self._curve(i, next_i)
            _, param = curve.nearest((rp.x, rp.y))
            nx, ny = curve.left_normal(param)
            if nx * (ray_p2.x - ray_p1.x) + ny * (ray_p2.y - ray_p1.y) > 0.0:
                nx, ny = -nx, -ny
            result['normal_x'], result['normal_y'] = nx, ny
            edge_threshold_sq = EDGE_DETECTION_THRESHOLD_SQUARED * self.scene.length_scale ** 2
            for k in (i, next_i):
                end = geometry.point(self.path[k]['x'], self.path[k]['y'])
                if geometry.distance_squared(rp, end) < edge_threshold_sq:
                    result['near_edge'] = True
        r2p1 = geometry.point(ray2.p1['x'], ray2.p1['y']) if isinstance(ray2.p1, dict) else ray2.p1
        r2p2 = geometry.point(ray2.p2['x'], ray2.p2['y']) if isinstance(ray2.p2, dict) else ray2.p2
        result['ray2_intersect_count'] += len(self._curve_hits(r2p1, r2p2, i, next_i))


__all__ = ["CurvedGlass"]
