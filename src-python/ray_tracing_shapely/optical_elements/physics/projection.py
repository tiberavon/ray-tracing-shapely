"""
Python-specific module: Projection models (Photometry Framework)

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
PYTHON-SPECIFIC MODULE: ProjectionModel family
===============================================================================
Defines how a specific 3D source or detector geometry projects onto the 2D
simulation plane. The 2D simulator produces power in W/m (per unit out-of-plane
length z); a ProjectionModel converts between that and real 3D irradiance
(W/m^2) or total power (W).

See dev_doc/roadmap/proposed/physical_scene_photometry.md.
===============================================================================
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..physical_scene import PhysicalScene


class ProjectionModel:
    """Abstract base for 2D <-> 3D power projection.

    All concrete subclasses must implement to_irradiance() and to_power_per_m().
    """

    def to_irradiance(self, power_per_m: float, phys_scene: 'PhysicalScene') -> float:
        """Convert 2D simulator power (W/m) to 3D irradiance (W/m^2).

        Used on the detector side: pixel_data x Phi gives W/m per bin; this
        method converts that to W/m^2 at the pixel.
        """
        raise NotImplementedError

    def to_power_per_m(self, total_power_W: float, phys_scene: 'PhysicalScene') -> float:
        """Convert 3D source power (W) to the 2D simulator equivalent (W/m).

        Used on the source side: given the real emitted power, what W/m quantity
        should the 2D simulation represent?
        """
        raise NotImplementedError


class CylindricalPerpendicularProjection(ProjectionModel):
    """Source or detector extends uniformly and infinitely in z (perpendicular
    to the simulation plane).

    Examples: a discharge lamp with axis perpendicular to the plane, a fibre
    viewed end-on, a strip LED viewed along its length, or a linear detector
    array whose active height is the full scene depth.

    This is the only geometry where the 2D simulation is an exact
    representation: L_z cancels on both source and detector sides. When both
    source and detector use it, relative measurements need no calibration.

    Args:
        height_m: Physical z-extent of the source or detector (m). For a source,
            the emitter length in z; for a detector, the pixel height in z.
    """

    def __init__(self, height_m: float) -> None:
        if height_m <= 0:
            raise ValueError("height_m must be positive.")
        self._height_m = height_m

    @property
    def height_m(self) -> float:
        """Physical z-extent in metres."""
        return self._height_m

    def to_irradiance(self, power_per_m: float, phys_scene: 'PhysicalScene') -> float:
        # W/m / m = W/m^2
        return power_per_m / self._height_m

    def to_power_per_m(self, total_power_W: float, phys_scene: 'PhysicalScene') -> float:
        # W / m = W/m
        return total_power_W / self._height_m


class PointSourceProjection(ProjectionModel):
    """Source is a point emitter (LED, small lamp), or the detector subtends a
    small solid angle at the source.

    The 2D simulation treats a point source as an infinite line source in z. The
    projection is exact only at the calibration distance; elsewhere it is an
    approximation. ``effective_depth_m`` is the physical z-extent of the scene
    the 2D cross-section represents (e.g. LED package height, aperture diameter).

    Args:
        effective_depth_m: z-extent of the scene in metres.
    """

    def __init__(self, effective_depth_m: float) -> None:
        if effective_depth_m <= 0:
            raise ValueError("effective_depth_m must be positive.")
        self._depth = effective_depth_m

    @property
    def effective_depth_m(self) -> float:
        """Effective scene z-extent in metres."""
        return self._depth

    def to_irradiance(self, power_per_m: float, phys_scene: 'PhysicalScene') -> float:
        # At the calibration distance: W/m / effective_depth = W/m^2
        return power_per_m / self._depth

    def to_power_per_m(self, total_power_W: float, phys_scene: 'PhysicalScene') -> float:
        # W / effective_depth = W/m (effective line-source strength)
        return total_power_W / self._depth


class LambertianStripProjection(ProjectionModel):
    """Extended Lambertian emitter (LED chip, diffuse surface) or a strip
    detector with a known active height.

    Models cos(theta)-weighted solid-angle projection. STUB: to_irradiance and
    to_power_per_m raise NotImplementedError until the LED roadmap provides the
    full Lambertian solid-angle integration.

    Args:
        height_m: Out-of-plane physical dimension (m).
    """

    def __init__(self, height_m: float) -> None:
        self._height_m = height_m

    @property
    def height_m(self) -> float:
        """Out-of-plane physical dimension in metres."""
        return self._height_m

    def to_irradiance(self, power_per_m: float, phys_scene: 'PhysicalScene') -> float:
        raise NotImplementedError(
            "LambertianStripProjection is not yet implemented. "
            "See the LED light-source roadmap."
        )

    def to_power_per_m(self, total_power_W: float, phys_scene: 'PhysicalScene') -> float:
        raise NotImplementedError(
            "LambertianStripProjection is not yet implemented. "
            "See the LED light-source roadmap."
        )
