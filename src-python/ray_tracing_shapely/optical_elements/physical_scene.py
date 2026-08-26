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

See dev_doc/roadmap/proposed/physical_scene_photometry.md.
===============================================================================
"""

from __future__ import annotations

from typing import Dict, Optional

from ..core.scene import Scene


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
        calibration_factor (float | None): Phi in W/m per unit of simulator
            brightness. None until set via set_calibration().
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
        self._calibration_factor: Optional[float] = None

    @property
    def calibration_factor(self) -> Optional[float]:
        """Phi in W/m per unit brightness. None until calibrated."""
        return self._calibration_factor

    def set_calibration(self, brightness: float, power_per_m_W: float) -> None:
        """Establish Phi from a reference measurement.

        Args:
            brightness: Simulator brightness at the reference point.
            power_per_m_W: Corresponding real optical power per unit out-of-plane
                length (W/m) at that point.

        Raises:
            ValueError: If the reference brightness is not positive.
        """
        if brightness <= 0:
            raise ValueError("Reference brightness must be positive.")
        self._calibration_factor = power_per_m_W / brightness

    def to_m(self, scene_value: float) -> float:
        """Convert a scene-unit length to metres."""
        return scene_value * self.scene_unit_in_m

    def from_m(self, metres: float) -> float:
        """Convert metres to scene units."""
        return metres / self.scene_unit_in_m
