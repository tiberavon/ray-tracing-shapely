"""
Python-specific module: LimitResult (Eye safety framework)

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
PYTHON-SPECIFIC MODULE: LimitResult
===============================================================================
The common return type for every hazard/limit calculation in this package
(the AEL/MPE functions and, in future phases, other exposure-limit
functions) -- part of P-HAZARD-ROUTINES, see
dev_doc/architecture/components/eye_safety.md. Kept close
to the shape sketched in dev_doc/architecture/components/agentic_layer.md:
a hazard classification is exactly the kind of output a human or an agent
will want justified, not just stated, so the inputs and the equation used
travel with the number.
===============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class LimitResult:
    """A single exposure-limit or emission-limit value, with provenance.

    Args:
        value: The limit value, in `unit`.
        unit: Unit string for `value` (e.g. "W/m^2", "J/m^2", "W/(m^2*sr)", "W").
        wavelength_nm: Wavelength the limit was evaluated at.
        duration_s: Exposure/emission duration the limit was evaluated at.
        alpha_rad: Angular subtense of the apparent source used, if applicable
            (0.0 if not applicable to this limit).
        region: Short label for which hazard this is (e.g. "retinal_thermal",
            "blue_light", "actinic_uv").
        time_regime: Short label for which piecewise time branch was used
            (e.g. "t <= 10 s", "10 s < t <= T2").
        equation: Human-readable citation of the source equation (e.g.
            "IEC 62471 Eq. 4.9" or "Henderson & Schulmeister eq. (3.10)").
        factors: Named correction-factor values applied (e.g. {"C6": 12.3}).
        notes: Free-text caveats (e.g. which pupil diameter was assumed).
    """

    value: float
    unit: str
    wavelength_nm: float
    duration_s: float
    alpha_rad: float
    region: str
    time_regime: str
    equation: str
    factors: Dict[str, float] = field(default_factory=dict)
    notes: str = ""

    def as_power_W(self) -> float:
        """Convert to an equivalent average power in watts, where meaningful.

        Only defined when `unit` is already "W" (returned unchanged) or "J"
        (divided by `duration_s`). Per-area units (W/m^2, J/m^2,
        W/(m^2*sr), ...) cannot become a power without a limiting-aperture
        area, which this type does not carry -- multiply by the aperture
        area (see `pupil_aperture.py`) first.

        Raises:
            ValueError: If `unit` is not "W" or "J".
        """
        if self.unit == "W":
            return self.value
        if self.unit == "J":
            return self.value / self.duration_s
        raise ValueError(
            f"as_power_W() is undefined for unit '{self.unit}'. It only "
            "converts an energy (J) to an average power (W) via duration_s, "
            "or returns an already-power (W) value unchanged. Per-area "
            "units need a limiting-aperture area to become a power -- "
            "multiply by that area first."
        )
