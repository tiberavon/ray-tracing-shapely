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
open until that convention is pinned -- see
dev_doc/architecture/components/optical_elements_physics.md. Design
rationale: dev_doc/architecture/components/optical_elements_physics.md.
===============================================================================
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

import numpy as np

from .exceptions import PhysicsContextError
from .projection import ProjectionModel, CylindricalPerpendicularProjection
from ..units import ureg, ensure_quantity, TIME, VOLTAGE, PHOTOSENSITIVITY

if TYPE_CHECKING:
    import pint
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
        pixel_pitch_scene: Pixel centre-to-centre spacing in scene units
            (scene geometry -- stays plain float [KC1]).
        photosensitivity: Sw, a pint.Quantity with dimensionality V/(lx.s).
        integration_time: Exposure time, a pint.Quantity with dimensionality
            seconds.
        projection: How this detector's out-of-plane geometry maps 2D W/m to 3D
            W/m^2 (typically a CylindricalPerpendicularProjection(pixel_height_m)).
        dark_output_voltage: VD (relative to Voffset), a pint.Quantity with
            dimensionality V. Defaults to 0 V.
        saturation_output_voltage: Vsat (relative to Voffset), a pint.Quantity
            with dimensionality V. Defaults to 1 V.
        output_offset_voltage: Voffset, a pint.Quantity with dimensionality V.
            Defaults to 0 V.
        readout_noise: Nread (rms), a pint.Quantity with dimensionality V.
            Defaults to 0 V.

    Raises:
        ValueError: If any of photosensitivity/integration_time/
            dark_output_voltage/saturation_output_voltage/
            output_offset_voltage/readout_noise is not a pint.Quantity with
            the expected dimensionality.
    """

    def __init__(
        self,
        pixel_pitch_scene: float,
        photosensitivity: 'pint.Quantity',
        integration_time: 'pint.Quantity',
        projection: ProjectionModel,
        dark_output_voltage: Optional['pint.Quantity'] = None,
        saturation_output_voltage: Optional['pint.Quantity'] = None,
        output_offset_voltage: Optional['pint.Quantity'] = None,
        readout_noise: Optional['pint.Quantity'] = None,
    ) -> None:
        if dark_output_voltage is None:
            dark_output_voltage = ureg.Quantity(0.0, "V")
        if saturation_output_voltage is None:
            saturation_output_voltage = ureg.Quantity(1.0, "V")
        if output_offset_voltage is None:
            output_offset_voltage = ureg.Quantity(0.0, "V")
        if readout_noise is None:
            readout_noise = ureg.Quantity(0.0, "V")

        self.pixel_pitch_scene = pixel_pitch_scene
        self.photosensitivity = ensure_quantity(photosensitivity, PHOTOSENSITIVITY, name="photosensitivity")
        self.integration_time = ensure_quantity(integration_time, TIME, name="integration_time")
        self.projection = projection
        self.dark_output_voltage = ensure_quantity(dark_output_voltage, VOLTAGE, name="dark_output_voltage")
        self.saturation_output_voltage = ensure_quantity(saturation_output_voltage, VOLTAGE, name="saturation_output_voltage")
        self.output_offset_voltage = ensure_quantity(output_offset_voltage, VOLTAGE, name="output_offset_voltage")
        self.readout_noise = ensure_quantity(readout_noise, VOLTAGE, name="readout_noise")

    # -------------------------------------------------------------------------
    # Conversions
    # -------------------------------------------------------------------------

    def compute_irradiance(
        self,
        pixel_data: Optional[List[float]],
        phys_scene: 'PhysicalScene',
    ) -> 'pint.Quantity':
        """Convert pixel_data to irradiance per pixel in W/m^2.

        Chain:
            pixel_data x Phi               -> power per bin (W/m)
            projection.to_irradiance(...)  -> irradiance (W/m^2)

        pixel_data itself stays plain float (the simulator's dimensionless
        hot-loop output, scene-geometry-adjacent -- not unit-carrying [KC1]);
        Phi is a pint.Quantity, so the product already carries units, and
        the whole per-pixel array is returned as a single array-valued
        Quantity rather than a Quantity per pixel.

        Args:
            pixel_data: Per-pixel simulator values (from LinearSensor.pixel_data).
            phys_scene: The calibrated PhysicalScene (provides calibration_factor).

        Returns:
            A pint.Quantity wrapping a NumPy array, dimensionality W/m^2,
            one entry per pixel.

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
        power_per_m = np.asarray(pixel_data, dtype=float) * phi
        return self.projection.to_irradiance(power_per_m, phys_scene)

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
            "See dev_doc/architecture/components/optical_elements_physics.md."
        )

    # -------------------------------------------------------------------------
    # Factory
    # -------------------------------------------------------------------------

    @classmethod
    def for_sensor(
        cls,
        model: str,
        pixel_pitch_scene: float,
        integration_time: 'pint.Quantity',
        projection: Optional[ProjectionModel] = None,
    ) -> 'Photoconversion':
        """Create a Photoconversion from a catalogue sensor model.

        Electrical parameters come from the datasheet -- _CATALOGUE itself
        stays plain floats with unit comments; this is the one place they
        are wrapped into pint.Quantity objects, on the way into the
        constructor. pixel_pitch_scene and integration_time are supplied by
        the caller (layout- and condition-dependent). If ``projection`` is
        None, a CylindricalPerpendicularProjection is created from the
        datasheet pixel height.

        Supported models:
            'S13131-1536' - Hamamatsu CMOS, Sw=280 V/(lx.s), Vsat=1.4 V,
                            pixel_height = 63.5 um.

        Args:
            model: A key in _CATALOGUE.
            pixel_pitch_scene: Pixel centre-to-centre spacing in scene units.
            integration_time: Exposure time, a pint.Quantity with
                dimensionality seconds.
            projection: An existing ProjectionModel, or None to build one
                from the datasheet pixel height.

        Raises:
            ValueError: If the model is unknown, or integration_time is not
                a pint.Quantity with dimensionality seconds.
        """
        if model not in _CATALOGUE:
            raise ValueError(
                f"Unknown sensor model '{model}'. Known models: {list(_CATALOGUE)}"
            )
        params = _CATALOGUE[model]
        if projection is None:
            projection = CylindricalPerpendicularProjection(
                ureg.Quantity(params['pixel_height_m'], "m")
            )
        return cls(
            pixel_pitch_scene=pixel_pitch_scene,
            photosensitivity=ureg.Quantity(params['photosensitivity'], "V/(lx*s)"),
            integration_time=integration_time,
            projection=projection,
            dark_output_voltage=ureg.Quantity(params['dark_output_voltage'], "V"),
            saturation_output_voltage=ureg.Quantity(params['saturation_output_voltage'], "V"),
            output_offset_voltage=ureg.Quantity(params['output_offset_voltage'], "V"),
            readout_noise=ureg.Quantity(params['readout_noise'], "V"),
        )

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    @staticmethod
    def _require_calibration(phys_scene: 'PhysicalScene') -> 'pint.Quantity':
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
                "phys_scene.set_calibration(brightness, power_per_m) first."
            )
        return cal
