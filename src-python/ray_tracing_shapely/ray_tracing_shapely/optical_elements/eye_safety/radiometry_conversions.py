"""
Python-specific module: Irradiance <-> radiance conversion (Eye safety framework)

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
PYTHON-SPECIFIC MODULE: radiometry_conversions
===============================================================================
Closes a gap: before these existed, the same arithmetic lived untested in
a notebook generator script. [KD5: a conversion between irradiance and
radiance is checkable against the definition; a copy in a notebook is not.]
`mpe_blue_light`/`mpe_retinal_thermal` (iec62471.py) dispatch to a radiance
limit once the apparent source's angular subtense exceeds the standard's
large/small-source boundary, but nothing in this codebase converted a
measured irradiance to the matching radiance via the source's solid angle.
That conversion (`L = E / Omega`) was instead done once, by hand, in
`notebooks/_gen_eye_safety_iec62471_broadband_example_nb.py` while
reproducing the non-binding guide's D.1.21/D.1.22 worked examples --
untested as a unit, and easy to get backwards (E/Omega vs E*Omega) without
a name attached to catch the mistake.
===============================================================================
"""

from __future__ import annotations


def radiance_from_irradiance(irradiance_w_m2: float, solid_angle_sr: float) -> float:
    """Convert an irradiance measurement to radiance via the source's solid angle.

    `L = E / Omega`. Used when an apparent source's angular subtense puts it
    in a standard's large-source regime (e.g. `alpha_rad >= 0.011` for
    `mpe_blue_light`/`mpe_retinal_thermal`, IEC 62471), which states its
    limit as a radiance, W/(m^2*sr), not an irradiance.

    Args:
        irradiance_w_m2: Measured irradiance, W/m^2.
        solid_angle_sr: Solid angle the source subtends at the measurement
            point, steradians. Must be positive.

    Returns:
        Radiance in W/(m^2*sr).

    Raises:
        ValueError: If `solid_angle_sr` is not positive.
    """
    if solid_angle_sr <= 0.0:
        raise ValueError("solid_angle_sr must be positive.")
    return irradiance_w_m2 / solid_angle_sr


def irradiance_from_radiance(radiance_w_m2_sr: float, solid_angle_sr: float) -> float:
    """Convert a radiance measurement to irradiance via the source's solid angle.

    `E = L * Omega` -- the inverse of `radiance_from_irradiance`. Used when a
    radiance measurement needs comparing against a small-source irradiance
    limit instead (the less common direction, but the same relation).

    Args:
        radiance_w_m2_sr: Measured radiance, W/(m^2*sr).
        solid_angle_sr: Solid angle the source subtends at the measurement
            point, steradians. Must be positive.

    Returns:
        Irradiance in W/m^2.

    Raises:
        ValueError: If `solid_angle_sr` is not positive.
    """
    if solid_angle_sr <= 0.0:
        raise ValueError("solid_angle_sr must be positive.")
    return radiance_w_m2_sr * solid_angle_sr
