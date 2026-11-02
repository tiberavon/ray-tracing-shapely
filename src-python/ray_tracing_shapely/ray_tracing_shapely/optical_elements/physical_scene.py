"""
Python-specific module: Physical Scene (Photometry Framework)

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
PYTHON-SPECIFIC MODULE: PhysicalScene
===============================================================================
A Scene subclass that adds a physical length unit and an optional calibration
factor linking the simulator's dimensionless brightness to SI irradiance.

Purely additive: it overrides nothing on Scene, so passing a PhysicalScene to
any existing constructor (Glass, Detector, BasePrism, LinearSensor, ...) works
identically. The core simulator never inspects the subclass type.

P-PHYSICAL-SCENE, see dev_doc/architecture/components/
optical_elements_physics.md and C-UNITS-01
(dev_doc/architecture/contracts/C-UNITS-01.md). Design rationale:
dev_doc/architecture/components/optical_elements_physics.md.
===============================================================================
"""

from __future__ import annotations

from typing import Dict, Optional, TYPE_CHECKING

from ..core.scene import Scene
from .units import ensure_quantity, POWER_PER_LENGTH

if TYPE_CHECKING:
    import pint


class PhysicalScene(Scene):
    """Scene subclass that adds a physical unit system and photometric calibration.

    Drop-in replacement for Scene: passing a PhysicalScene to any existing
    constructor works identically -- the simulator never inspects the subclass
    type. Optical-element classes check ``isinstance(scene, PhysicalScene)`` to
    decide whether physical features are available.

    Args:
        scene_unit: The length unit of scene coordinates. One of
            'nm', 'µm'/'um', 'mm', 'cm', 'm'. Default 'mm'.

    Attributes:
        scene_unit (str): Human-readable unit label.
        scene_unit_in_m (float): 1 scene unit expressed in metres.
        calibration_factor (pint.Quantity | None): Phi, dimensionality W/m,
            per unit of (dimensionless) simulator brightness. None until set
            via set_calibration(). Radiometric quantity, unlike scene_unit/
            scene_unit_in_m above -- see C-UNITS-02
            (dev_doc/architecture/contracts/C-UNITS-02.md) and
            dev_doc/architecture/components/optical_elements_units.md
            for why this attribute is Pint-typed and scene_unit is not.
    """

    _UNIT_TO_M: Dict[str, float] = {
        'nm': 1e-9, 'µm': 1e-6, 'um': 1e-6,
        'mm': 1e-3, 'cm': 1e-2, 'm': 1.0,
    }

    def __init__(self, scene_unit: str = 'mm') -> None:
        super().__init__()
        if scene_unit not in self._UNIT_TO_M:
            raise ValueError(
                f"Unknown scene_unit '{scene_unit}'. "
                f"Valid values: {list(self._UNIT_TO_M)}"
            )
        self.scene_unit: str = scene_unit
        self.scene_unit_in_m: float = self._UNIT_TO_M[scene_unit]
        self._calibration_factor: Optional['pint.Quantity'] = None

    @property
    def calibration_factor(self) -> Optional['pint.Quantity']:
        """Phi (dimensionality W/m) per unit brightness. None until calibrated."""
        return self._calibration_factor

    def set_calibration(self, brightness: float, power_per_m: 'pint.Quantity') -> None:
        """Establish Phi from a reference measurement.

        Args:
            brightness: Simulator brightness at the reference point
                (dimensionless -- the simulator's own raw output).
            power_per_m: Corresponding real optical power per unit
                out-of-plane length at that point, as a pint.Quantity with
                dimensionality W/m (e.g. ``units.ureg.Quantity(2.0, "W/m")``).

        Raises:
            ValueError: If the reference brightness is not positive, or
                power_per_m is not a pint.Quantity with dimensionality W/m.
        """
        if brightness <= 0:
            raise ValueError("Reference brightness must be positive.")
        power_per_m = ensure_quantity(power_per_m, POWER_PER_LENGTH, name="power_per_m")
        self._calibration_factor = power_per_m / brightness

    def to_m(self, scene_value: float) -> float:
        """Convert a scene-unit length to metres."""
        return scene_value * self.scene_unit_in_m

    def from_m(self, metres: float) -> float:
        """Convert metres to scene units."""
        return metres / self.scene_unit_in_m
