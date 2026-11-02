"""
Python-specific module: Photoemission (Photometry Framework) -- STUB

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

STUB: reserves the interface. Full implementation is deferred to the LED
light-source roadmap. See dev_doc/architecture/components/optical_elements_physics.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .projection import ProjectionModel

if TYPE_CHECKING:
    from ..physical_scene import PhysicalScene
    from .liv_curve import LIVCurve


class Photoemission:
    """Physical model for a photoemitter (LED, laser, broadband source).

    Converts optical power (W) to a simulator brightness value that a source
    should carry. STUB: the constructor raises NotImplementedError until the LED
    light-source roadmap is implemented.

    Args:
        peak_wavelength: Dominant emission wavelength in nm.
        spectral_fwhm: Full-width-half-maximum of the emission spectrum in nm.
        emission_half_angle: Half-angle of the emission cone in degrees
            (60 for a Lambertian LED, 0 for a laser).
        emitter_width_scene: Physical width of the emitter in scene units.
        projection: How this source's out-of-plane geometry maps 3D power (W)
            to 2D W/m.
    """

    def __init__(
        self,
        peak_wavelength: float,
        spectral_fwhm: float,
        emission_half_angle: float,
        emitter_width_scene: float,
        projection: ProjectionModel,
    ) -> None:
        raise NotImplementedError(
            "Photoemission is not yet implemented. "
            "See the LED light-source roadmap."
        )

    def compute_brightness(
        self,
        optical_power_W: float,
        phys_scene: 'PhysicalScene',
    ) -> float:
        """Convert optical power (W) to simulator brightness (0-1).

        Raises:
            NotImplementedError: Always, until the LED roadmap is implemented.
        """
        raise NotImplementedError

    def compute_optical_power(
        self,
        current_A: float,
        liv_curve: 'LIVCurve',
    ) -> float:
        """Obtain optical power from a LIV curve at a given forward current.

        Raises:
            NotImplementedError: Always, until the LED roadmap is implemented.
        """
        raise NotImplementedError
