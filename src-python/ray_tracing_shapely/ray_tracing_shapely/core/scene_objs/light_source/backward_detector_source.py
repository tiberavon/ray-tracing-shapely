"""
Python-specific module: Backward Detector Source (Ray Lineage Step C)

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
PYTHON-SPECIFIC MODULE: Backward Detector Source
===============================================================================
Emits rays *from a detector line* into an acceptance cone, for the backward
pass of bidirectional ray tracing -- see
dev_doc/architecture/components/analysis_bidirectional.md. Design rationale:
dev_doc/concepts/KB2_tracing_runs_forward_from_sources_and_backward_from_the_detector.md,
sub-problem C.1.

Deliberately NOT a BaseSceneObj subclass: it is a transient helper the simulator
instantiates only for the backward pass, so it never pollutes scene
serialization or the forward run. It produces plain Ray objects (already tagged
as backward roots) that the simulator feeds into its normal _process_rays loop.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if __name__ == "__main__":
    from ray_tracing_shapely.core.ray import Ray
else:
    from ...ray import Ray

if TYPE_CHECKING:
    from ...ray_lineage import RayLineage


def _unit(dx: float, dy: float) -> Optional[Tuple[float, float]]:
    """Return (dx, dy) normalised to unit length, or None if degenerate."""
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return None
    return dx / length, dy / length


def backward_central_direction(
    detector: object,
    forward_lineage: 'RayLineage',
) -> Optional[Tuple[float, float]]:
    """Mean reverse direction of the forward rays that hit the detector.

    A backward ray retraces a forward ray, so the natural centre of the backward
    emission cone is the average of the *reversed* arrival directions of the
    forward rays that actually reached the detector. This concentrates the
    backward pass along the directions that matter (the payoff described in the
    Step C roadmap) and fixes the emission-cone sign unambiguously.

    Args:
        detector: A detector-like object exposing get_hit_uuids() (e.g. the core
            Detector, or LinearSensor.detector).
        forward_lineage: The RayLineage from the completed forward pass.

    Returns:
        A unit (dx, dy) pointing back into the scene (toward the optics), or None
        if the detector recorded no usable forward hits.
    """
    if not hasattr(detector, 'get_hit_uuids'):
        return None
    sum_x = 0.0
    sum_y = 0.0
    n = 0
    for uuid in detector.get_hit_uuids():
        seg = forward_lineage.get_segment(uuid)
        if seg is None:
            continue
        arrival = _unit(seg.p2['x'] - seg.p1['x'], seg.p2['y'] - seg.p1['y'])
        if arrival is None:
            continue
        # Backward = reverse of the forward arrival direction.
        sum_x -= arrival[0]
        sum_y -= arrival[1]
        n += 1
    if n == 0:
        return None
    return _unit(sum_x, sum_y)


class BackwardDetectorSource:
    """Emits backward rays from a detector line into an acceptance cone.

    Origins are sampled along the detector segment p1->p2; directions span
    ``acceptance_angle_deg`` symmetrically about ``central_direction``. Every
    emitted ray is a backward-tree root: ``interaction_type='source'``,
    ``parent_uuid=None``, and a ``direction='backward'`` marker so downstream
    code never confuses it with a forward segment.

    This is a transient helper (not a scene object). The simulator calls
    :meth:`emit_rays` and seeds the backward pass with the result.
    """

    def __init__(
        self,
        detector: object,
        *,
        central_direction: Optional[Tuple[float, float]] = None,
        acceptance_angle_deg: float = 20.0,
        origin_samples: int = 25,
        direction_samples: int = 15,
        brightness: float = 1.0,
    ) -> None:
        """Configure the backward source.

        Args:
            detector: A detector-like object with ``p1``/``p2`` dicts.
            central_direction: Unit (dx, dy) at the centre of the emission cone.
                If None, the geometric perpendicular ``(-dy, dx)`` of the
                detector line is used (sign is then arbitrary -- callers that
                have a forward lineage should pass
                :func:`backward_central_direction` instead).
            acceptance_angle_deg: Full angular spread of the cone; rays fan
                +/- acceptance_angle_deg/2 about the central direction.
            origin_samples: Number of emission points along the detector line.
            direction_samples: Number of directions emitted per origin.
            brightness: Per-ray total brightness (split equally s/p).

        Raises:
            ValueError: If the detector endpoints coincide, or if
                origin_samples / direction_samples are not positive.
        """
        p1 = detector.p1
        p2 = detector.p2
        axis = _unit(p2['x'] - p1['x'], p2['y'] - p1['y'])
        if axis is None:
            raise ValueError("Detector p1 and p2 must be distinct points.")
        if origin_samples < 1 or direction_samples < 1:
            raise ValueError(
                "origin_samples and direction_samples must be >= 1 "
                f"(got {origin_samples}, {direction_samples})."
            )

        self._p1 = {'x': float(p1['x']), 'y': float(p1['y'])}
        self._p2 = {'x': float(p2['x']), 'y': float(p2['y'])}
        self._axis = axis

        if central_direction is None:
            # Geometric perpendicular; sign is arbitrary without a forward pass.
            central_direction = (-axis[1], axis[0])
        else:
            normalised = _unit(central_direction[0], central_direction[1])
            if normalised is None:
                raise ValueError("central_direction must be a non-zero vector.")
            central_direction = normalised
        self._central = central_direction

        self.acceptance_angle_deg = float(acceptance_angle_deg)
        self.origin_samples = int(origin_samples)
        self.direction_samples = int(direction_samples)
        self.brightness = float(brightness)

    @property
    def central_direction(self) -> Tuple[float, float]:
        """Unit vector at the centre of the emission cone."""
        return self._central

    def _origins(self) -> List[Dict[str, float]]:
        """Sample emission points strictly inside the detector segment."""
        p1, p2 = self._p1, self._p2
        n = self.origin_samples
        origins = []
        for i in range(n):
            # (i + 0.5)/n keeps origins off the exact endpoints, avoiding the
            # collinear edge blockers of a LinearSensor.
            t = (i + 0.5) / n
            origins.append({
                'x': p1['x'] + t * (p2['x'] - p1['x']),
                'y': p1['y'] + t * (p2['y'] - p1['y']),
            })
        return origins

    def _direction_angles(self) -> List[float]:
        """Emission angles (radians), spread symmetrically about the centre."""
        centre = math.atan2(self._central[1], self._central[0])
        m = self.direction_samples
        if m == 1:
            return [centre]
        half = math.radians(self.acceptance_angle_deg) / 2.0
        return [centre - half + (2.0 * half) * (j / (m - 1)) for j in range(m)]

    def emit_rays(self) -> List[Ray]:
        """Build the backward-tree root rays.

        Returns:
            A list of ``origin_samples * direction_samples`` Ray objects, each
            tagged as a backward source root.
        """
        angles = self._direction_angles()
        per_ray = 0.5 * self.brightness
        rays: List[Ray] = []
        for origin in self._origins():
            for ang in angles:
                dx, dy = math.cos(ang), math.sin(ang)
                ray = Ray(
                    p1={'x': origin['x'], 'y': origin['y']},
                    p2={'x': origin['x'] + dx, 'y': origin['y'] + dy},
                    brightness_s=per_ray,
                    brightness_p=per_ray,
                )
                # Backward-tree root markers.
                ray.interaction_type = 'source'
                ray.parent_uuid = None
                ray.direction = 'backward'
                ray.source_label = 'backward_detector'
                rays.append(ray)
        return rays
