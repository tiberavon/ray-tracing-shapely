"""
Original work Copyright 2024 The Ray Optics Simulation authors and contributors
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

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
Mouse: the pointer as the scene objects' editing hooks see it (Mouse.js)
===============================================================================
The construction and drag hooks (`on_construct_mouse_*`, `check_mouse_over`,
`on_drag`) receive a `Mouse`: the pointer's position in scene coordinates, and
the tests and snaps the hooks need. "On a point" and "on a segment" mean
within a click extent of 10 screen pixels, so the scene's `scale` (screen
pixels per scene unit) enters; snapping uses the scene's grid.

PYTHON-SPECIFIC: the hooks, as ported, read points both as attributes
(``p.x``, through `geometry`) and as dict entries (``p['x']``, how objects
store them), and assign what the mouse returns straight into an object's
``p1``. So every point the mouse returns is a `MousePoint`: a ``{'x', 'y'}``
dict that also has ``.x`` and ``.y``. Points given to it may be either kind.
===============================================================================
"""

import math
from typing import Any, Dict, List, Optional


class MousePoint(dict):
    """A point that is both ``{'x': .., 'y': ..}`` and has ``.x`` and ``.y`` (PYTHON-SPECIFIC)."""

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x=x, y=y)

    @property
    def x(self) -> float:
        return self["x"]

    @property
    def y(self) -> float:
        return self["y"]

    def to_dict(self) -> Dict[str, float]:
        return {"x": self["x"], "y": self["y"]}


def _xy(p: Any) -> MousePoint:
    """Any point, dict or object, as a MousePoint."""
    if isinstance(p, dict):
        return MousePoint(p["x"], p["y"])
    return MousePoint(p.x, p.y)


def _distance_squared(a: Any, b: Any) -> float:
    a, b = _xy(a), _xy(b)
    return (a.x - b.x) ** 2 + (a.y - b.y) ** 2


class Mouse:
    """The pointer, for the editing hooks.

    Args:
        pos: The position, in scene coordinates.
        scene: The scene, for its ``scale`` (screen pixels per unit),
            ``snap_to_grid`` and ``grid_size``.
        is_touch: A touch rather than a mouse, whose extent is larger.
        override_grid: 0 to follow the scene's grid setting, 1 to invert it
            (upstream: the alt key held).
    """

    CLICK_EXTENT_LINE = 10
    CLICK_EXTENT_POINT = 10
    TOUCHSCREEN_EXTENT_RATIO = 2
    SNAP_TO_DIRECTION_LOCK_LIMIT = 30

    def __init__(self, pos: Any, scene: Any, is_touch: bool = False, override_grid: int = 0) -> None:
        self.pos = _xy(pos)
        self.scene = scene
        self.is_touch = is_touch
        self.override_grid = override_grid

    def _scale(self) -> float:
        return getattr(self.scene, "scale", 1.0) or 1.0

    def get_click_extent(self, is_point: bool = False) -> float:
        """How far, in scene units, the pointer reaches for a point or a line."""
        extent = (self.CLICK_EXTENT_POINT if is_point else self.CLICK_EXTENT_LINE) / self._scale()
        if self.is_touch:
            extent *= self.TOUCHSCREEN_EXTENT_RATIO
        return extent

    def is_on_point(self, point: Any) -> bool:
        """Whether the pointer is on `point`."""
        return _distance_squared(self.pos, point) < self.get_click_extent(True) ** 2

    def snaps_on_point(self, point: Any) -> bool:
        """Whether the pointer, snapped to the grid, is on `point`."""
        return _distance_squared(self.get_pos_snapped_to_grid(), point) < self.get_click_extent(True) ** 2

    def is_on_segment(self, segment: Any) -> bool:
        """Whether the pointer is on the segment ``segment.p1``–``segment.p2``."""
        p1, p2, pos = _xy(segment.p1), _xy(segment.p2), self.pos
        den = (p1.y - p2.y) ** 2 + (p2.x - p1.x) ** 2
        if den == 0:
            return self.is_on_point(p1)
        d_per = ((pos.x - p1.x) * (p1.y - p2.y) + (pos.y - p1.y) * (p2.x - p1.x)) ** 2 / den
        d_par = (p2.x - p1.x) * (pos.x - p1.x) + (p2.y - p1.y) * (pos.y - p1.y)
        return d_per < self.get_click_extent() ** 2 and 0 <= d_par <= den

    def is_on_line(self, line: Any) -> bool:
        """Whether the pointer is on the infinite line through ``line.p1`` and ``line.p2``."""
        p1, p2, pos = _xy(line.p1), _xy(line.p2), self.pos
        den = (p1.y - p2.y) ** 2 + (p2.x - p1.x) ** 2
        if den == 0:
            return self.is_on_point(p1)
        d_per = ((pos.x - p1.x) * (p1.y - p2.y) + (pos.y - p1.y) * (p2.x - p1.x)) ** 2 / den
        return d_per < self.get_click_extent() ** 2

    def get_pos_snapped_to_grid(self) -> MousePoint:
        """The position, on the grid if the scene snaps to it (or the override says so)."""
        snap = bool(getattr(self.scene, "snap_to_grid", False))
        if (self.override_grid == 0 and snap) or (self.override_grid == 1 and not snap):
            g = getattr(self.scene, "grid_size", 20)
            return MousePoint(round(self.pos.x / g) * g, round(self.pos.y / g) * g)
        return MousePoint(self.pos.x, self.pos.y)

    def get_pos_snapped_to_direction(self, base_point: Any, directions: List[Any],
                                     snap_context: Optional[Dict[str, Any]] = None) -> MousePoint:
        """The position projected onto the nearest of `directions` through `base_point`.

        With a `snap_context`, the direction chosen is locked once the pointer
        is far enough from the base point, and kept while the context is.
        """
        pos = self.get_pos_snapped_to_grid()
        base = _xy(base_point)
        dirs = [_xy(d) for d in directions]
        x, y = pos.x - base.x, pos.y - base.y
        if snap_context and snap_context.get("locked"):
            d = dirs[snap_context["i0"]]
        else:
            i0, best = 0, math.inf
            for i, d in enumerate(dirs):
                d_sq = (d.y * x - d.x * y) ** 2 / (d.x * d.x + d.y * d.y)
                if d_sq < best:
                    best, i0 = d_sq, i
            limit = self.SNAP_TO_DIRECTION_LOCK_LIMIT / self._scale()
            if snap_context is not None and x * x + y * y > limit * limit:
                snap_context["locked"] = True
                snap_context["i0"] = i0
            d = dirs[i0]
        k = (d.x * x + d.y * y) / (d.x * d.x + d.y * d.y)
        return MousePoint(base.x + k * d.x, base.y + k * d.y)


__all__ = ["Mouse", "MousePoint"]
