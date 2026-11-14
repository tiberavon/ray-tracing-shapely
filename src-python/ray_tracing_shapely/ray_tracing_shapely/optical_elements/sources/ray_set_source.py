"""
Python-specific module: ray_set_source
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
RAY SET SOURCE -- a 2D source that emits a given list of rays
===============================================================================
The general 2D source: each ray is given explicitly, as a start point, a
direction and a brightness, and is emitted as given, in the order given. A
fan from a source specification, a slice of a measured rayfile and a
hand-built test all reduce to this.

Unlike the built-in sources, nothing here depends on the scene's ray
density: the number of rays, their angles and their weights are the
caller's. That is what lets a 2D source match a 3D one ray for ray.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from ...core import geometry
from ...core.constants import GREEN_WAVELENGTH
from ...core.scene_objs.base_scene_obj import BaseSceneObj


class RaySetSource(BaseSceneObj):
    """A source emitting an explicit list of rays.

    Attributes:
        rays: One dict per ray: ``{"p": [x, y], "d": [dx, dy], "brightness": b}``,
            with an optional ``"wavelength"`` in nm. ``d`` need not be unit
            length; ``b`` is in (0, 1], the brightness of one ray in the 2D
            engine (split equally between s and p).
        wavelength: The wavelength in nm of rays that do not give their own
            (used only when the scene simulates colours).
        flux_per_brightness: The physical flux one unit of brightness
            carries, or None. Set by a builder that knows the source's flux
            (for example from a source specification), so a 2D result can be
            read back in physical units. Not used by the simulation.
    """

    type = 'RaySetSource'
    is_optical = True
    serializable_defaults = {
        'rays': [],
        'wavelength': GREEN_WAVELENGTH,
        'flux_per_brightness': None,
    }

    def __init__(self, scene, json_obj: Optional[Dict[str, Any]] = None):
        super().__init__(scene, json_obj)

    @classmethod
    def from_rays(cls, scene, points: Sequence[Sequence[float]], directions: Sequence[Sequence[float]],
                  brightness: Sequence[float], *, wavelength: float = GREEN_WAVELENGTH,
                  flux_per_brightness: Optional[float] = None) -> "RaySetSource":
        """Build a source from parallel sequences of points, directions and brightnesses.

        Raises:
            ValueError: If the three sequences differ in length.
        """
        if not len(points) == len(directions) == len(brightness):
            raise ValueError(f"points, directions and brightness differ in length: "
                             f"{len(points)}, {len(directions)}, {len(brightness)}")
        rays = [{"p": [float(p[0]), float(p[1])], "d": [float(d[0]), float(d[1])], "brightness": float(b)}
                for p, d, b in zip(points, directions, brightness)]
        return cls(scene, {"rays": rays, "wavelength": wavelength, "flux_per_brightness": flux_per_brightness})

    def total_brightness(self) -> float:
        """The sum of the rays' brightnesses."""
        return sum(float(r["brightness"]) for r in self.rays)

    def _check_ray(self, k: int, ray: Dict[str, Any]) -> None:
        try:
            dx, dy = float(ray["d"][0]), float(ray["d"][1])
            float(ray["p"][0]), float(ray["p"][1])
            b = float(ray["brightness"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValueError(f"RaySetSource ray {k}: needs 'p': [x, y], 'd': [dx, dy] and 'brightness', "
                             f"got {ray!r}") from None
        if math.hypot(dx, dy) == 0.0:
            raise ValueError(f"RaySetSource ray {k}: zero direction")
        if not 0.0 < b <= 1.0:
            raise ValueError(f"RaySetSource ray {k}: brightness must be in (0, 1], got {b}")

    def on_simulation_start(self):
        """Emit every ray as given.

        Raises:
            ValueError: If a ray is malformed, has a zero direction, or a
                brightness outside (0, 1]. Loud, because a ray silently
                dropped or flipped changes the result without a trace.
        """
        new_rays: List[Any] = []
        for k, r in enumerate(self.rays):
            self._check_ray(k, r)
            (x, y), (dx, dy) = r["p"], r["d"]
            ray = geometry.line(geometry.point(x, y), geometry.point(x + dx, y + dy))
            ray.brightness_s = 0.5 * float(r["brightness"])
            ray.brightness_p = 0.5 * float(r["brightness"])
            if self.scene.simulate_colors:
                ray.wavelength = r.get("wavelength", self.wavelength)
            ray.gap = True          # every ray is its own: none continues another's fan
            ray.isNew = True
            ray.source_uuid = self.uuid
            ray.source_label = self.name
            new_rays.append(ray)
        return {'newRays': new_rays}

    def move(self, diff_x: float, diff_y: float) -> bool:
        for r in self.rays:
            r["p"] = [r["p"][0] + diff_x, r["p"][1] + diff_y]
        return True

    def rotate(self, angle: float, center=None) -> bool:
        cx, cy = (center['x'], center['y']) if center is not None else self._centroid()
        c, s = math.cos(angle), math.sin(angle)
        for r in self.rays:
            px, py = r["p"][0] - cx, r["p"][1] - cy
            r["p"] = [cx + c * px - s * py, cy + s * px + c * py]
            dx, dy = r["d"]
            r["d"] = [c * dx - s * dy, s * dx + c * dy]
        return True

    def _centroid(self):
        if not self.rays:
            return 0.0, 0.0
        n = len(self.rays)
        return sum(r["p"][0] for r in self.rays) / n, sum(r["p"][1] for r in self.rays) / n

    def get_default_center(self):
        cx, cy = self._centroid()
        return {'x': cx, 'y': cy}
