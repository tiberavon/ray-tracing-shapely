"""
Python-specific module: Photoconversion (Photometry Framework)

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
PYTHON-SPECIFIC MODULE: Photoconversion
===============================================================================
Physical model for a photodetector pixel array, composed into detector objects
(e.g. LinearSensor). Converts the simulator's dimensionless pixel_data into
physical quantities.

compute_irradiance (pixel_data -> W/m^2) is implemented. compute_vout
(pixel_data -> volts) is DEFERRED: it needs a radiometric->photometric step
(a luminous-efficacy constant, lm/W, that depends on wavelength) which is left
open until that convention is pinned. See
dev_doc/roadmap/proposed/physical_scene_photometry.md.
===============================================================================
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from .exceptions import PhysicsContextError
from .projection import ProjectionModel, CylindricalPerpendicularProjection

if TYPE_CHECKING:
    from ..physical_scene import PhysicalScene


# Datasheet electrical parameters for supported sensor models.
_CATALOGUE: Dict[str, Dict[str, float]] = {
    'S13131-1536': {
        'photosensitivity': 280.0,        # Sw, V/(lx.s)
        'pixel_height_m': 63.5e-6,        # active pixel height in z
        'dark_output_voltage': 0.0015,    # VD, V
        'saturation_output_voltage': 1.4,  # Vsat, V
        'output_offset_voltage': 0.6,     # Voffset, V
        'readout_noise': 4e-4,            # Nread, V rms
    },
}


class Photoconversion:
    """Physical model for a photodetector pixel array.

    Composed into detector objects (e.g. LinearSensor). Requires a PhysicalScene
    with a calibration factor to perform any conversion.

    Args:
        pixel_pitch_scene: Pixel centre-to-centre spacing in scene units.
        photosensitivity: Sw in V/(lx.s).
        integration_time: Exposure time in seconds.
        projection: How this detector's out-of-plane geometry maps 2D W/m to 3D
            W/m^2 (typically a CylindricalPerpendicularProjection(pixel_height_m)).
        dark_output_voltage: VD in V (relative to Voffset).
        saturation_output_voltage: Vsat in V (relative to Voffset).
        output_offset_voltage: Voffset in V.
        readout_noise: Nread in V rms (default 0).
    """

    def __init__(
        self,
        pixel_pitch_scene: float,
        photosensitivity: float,
        integration_time: float,
        projection: ProjectionModel,
        dark_output_voltage: float = 0.0,
        saturation_output_voltage: float = 1.0,
        output_offset_voltage: float = 0.0,
        readout_noise: float = 0.0,
    ) -> None:
        self.pixel_pitch_scene = pixel_pitch_scene
        self.photosensitivity = photosensitivity
        self.integration_time = integration_time
        self.projection = projection
        self.dark_output_voltage = dark_output_voltage
        self.saturation_output_voltage = saturation_output_voltage
        self.output_offset_voltage = output_offset_voltage
        self.readout_noise = readout_noise

    # -------------------------------------------------------------------------
    # Conversions
    # -------------------------------------------------------------------------

    def compute_irradiance(
        self,
        pixel_data: Optional[List[float]],
        phys_scene: 'PhysicalScene',
    ) -> List[float]:
        """Convert pixel_data to irradiance per pixel in W/m^2.

        Chain:
            pixel_data[i] x Phi              -> power per bin (W/m)
            projection.to_irradiance(...)     -> irradiance (W/m^2)

        Args:
            pixel_data: Per-pixel simulator values (from LinearSensor.pixel_data).
            phys_scene: The calibrated PhysicalScene (provides calibration_factor).

        Returns:
            Irradiance per pixel in W/m^2.

        Raises:
            PhysicsContextError: If the scene is not a calibrated PhysicalScene,
                or pixel_data is None (simulation not run).
        """
        phi = self._require_calibration(phys_scene)
        if pixel_data is None:
            raise PhysicsContextError(
                "pixel_data is None. Run the simulation (and enable the "
                "detector's irradiance map) before computing irradiance."
            )
        return [self.projection.to_irradiance(value * phi, phys_scene)
                for value in pixel_data]

    def compute_vout(
        self,
        pixel_data: Optional[List[float]],
        phys_scene: 'PhysicalScene',
    ) -> List[float]:
        """Convert pixel_data to output voltage per pixel (V). DEFERRED.

        The remaining chain (irradiance -> lux.s -> V) requires a
        radiometric->photometric conversion whose luminous-efficacy constant
        (lm/W, wavelength dependent) is not yet fixed. Until then this raises.

        Raises:
            NotImplementedError: Always, pending the luminous-efficacy convention.
        """
        raise NotImplementedError(
            "compute_vout is deferred: it needs a radiometric->photometric "
            "luminous-efficacy constant (lm/W, wavelength dependent) that is not "
            "yet pinned. Use compute_irradiance for W/m^2 in the meantime. "
            "See dev_doc/roadmap/proposed/physical_scene_photometry.md."
        )

    # -------------------------------------------------------------------------
    # Factory
    # -------------------------------------------------------------------------

    @classmethod
    def for_sensor(
        cls,
        model: str,
        pixel_pitch_scene: float,
        integration_time: float,
        projection: Optional[ProjectionModel] = None,
    ) -> 'Photoconversion':
        """Create a Photoconversion from a catalogue sensor model.

        Electrical parameters come from the datasheet; pixel_pitch_scene and
        integration_time are supplied by the caller (layout- and
        condition-dependent). If ``projection`` is None, a
        CylindricalPerpendicularProjection is created from the datasheet pixel
        height.

        Supported models:
            'S13131-1536' - Hamamatsu CMOS, Sw=280 V/(lx.s), Vsat=1.4 V,
                            pixel_height = 63.5 um.

        Raises:
            ValueError: If the model is unknown.
        """
        if model not in _CATALOGUE:
            raise ValueError(
                f"Unknown sensor model '{model}'. Known models: {list(_CATALOGUE)}"
            )
        params = _CATALOGUE[model]
        if projection is None:
            projection = CylindricalPerpendicularProjection(params['pixel_height_m'])
        return cls(
            pixel_pitch_scene=pixel_pitch_scene,
            photosensitivity=params['photosensitivity'],
            integration_time=integration_time,
            projection=projection,
            dark_output_voltage=params['dark_output_voltage'],
            saturation_output_voltage=params['saturation_output_voltage'],
            output_offset_voltage=params['output_offset_voltage'],
            readout_noise=params['readout_noise'],
        )

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    @staticmethod
    def _require_calibration(phys_scene: 'PhysicalScene') -> float:
        """Return the scene's calibration factor, or raise PhysicsContextError."""
        sentinel = object()
        cal = getattr(phys_scene, 'calibration_factor', sentinel)
        if cal is sentinel:
            raise PhysicsContextError(
                "This computation requires a PhysicalScene. Replace Scene() with "
                "PhysicalScene(scene_unit='mm')."
            )
        if cal is None:
            raise PhysicsContextError(
                "calibration_factor is None. Call "
                "phys_scene.set_calibration(brightness, power_per_m_W) first."
            )
        return cal
