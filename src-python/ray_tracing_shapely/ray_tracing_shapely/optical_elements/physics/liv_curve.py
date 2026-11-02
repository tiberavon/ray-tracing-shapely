"""
Python-specific module: LIV Curve (Photometry Framework) -- STUB

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

from typing import List


class LIVCurve:
    """Current-Voltage-Power (LIV) characteristic of an LED.

    Stores tabulated (I, V, P) data and interpolates on demand. STUB: all
    methods raise NotImplementedError until the LED light-source roadmap is
    implemented.

    Args:
        currents: Array of forward currents (A).
        voltages: Array of forward voltages (V).
        powers: Array of optical powers (W).
    """

    def __init__(
        self,
        currents: List[float],
        voltages: List[float],
        powers: List[float],
    ) -> None:
        raise NotImplementedError(
            "LIVCurve is not yet implemented. See the LED light-source roadmap."
        )

    def power_at(self, current_A: float) -> float:
        """Interpolated optical power at the given forward current (W)."""
        raise NotImplementedError

    def voltage_at(self, current_A: float) -> float:
        """Interpolated forward voltage at the given forward current (V)."""
        raise NotImplementedError
