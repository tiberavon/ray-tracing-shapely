"""
Python-specific module: IEC 60825-1 wavelength/angle correction factors (Eye safety framework)

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
PYTHON-SPECIFIC MODULE: IEC 60825-1 correction factors C3, C4, C6, C7
===============================================================================
The wavelength- and angular-subtense-dependent multipliers Henderson &
Schulmeister's MPE tables (table 3.10, table 3.12) are expressed in terms
of, quoted directly rather than referenced by heading -- see each
function's docstring for the exact equation and its source line range.

T2 (the retinal-thermal break time) and gamma_ph/gamma_th (the
photochemical/thermal angles of acceptance) already exist in
`exposure_duration.py` -- they are exposure-*duration* dependent,
not wavelength/alpha dependent, so they were built as shared scaffolding
rather than here. This module only holds the four correction factors that
are genuinely specific to IEC 60825-1's MPE/AEL derivation.

See dev_doc/architecture/components/eye_safety.md
===============================================================================
"""

from __future__ import annotations

from .angular_subtense import ALPHA_MIN_IEC60825_1_RAD, ALPHA_MAX_RAD, clip_alpha


def c4_iec60825_1(wavelength_nm: float) -> float:
    """Retinal-thermal wavelength correction factor C4.

    Henderson & Schulmeister eq. (3.7) [Chaves Ch. 3:87]:

        C4 = 1                          for lambda < 700 nm
           = 10^(0.002*(lambda-700))     for 700 <= lambda < 1050 nm
           = 5                           for 1050 <= lambda < 1400 nm

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [0, 1400)
            (the retinal-thermal hazard region's upper bound); no lower
            bound is enforced since C4 is a no-op (1.0) below 700 nm.

    Returns:
        The dimensionless correction factor (1.0 to 5.0).

    Raises:
        ValueError: If `wavelength_nm` is negative or >= 1400.
    """
    if wavelength_nm < 0.0 or wavelength_nm >= 1400.0:
        raise ValueError("wavelength_nm must be in [0, 1400) nm for C4.")
    if wavelength_nm < 700.0:
        return 1.0
    if wavelength_nm < 1050.0:
        return 10.0 ** (0.002 * (wavelength_nm - 700.0))
    return 5.0


def c7_iec60825_1(wavelength_nm: float) -> float:
    """Retinal-thermal wavelength correction factor C7.

    Henderson & Schulmeister eq. (3.8) [Chaves Ch. 3:111]:

        C7 = 1                          for lambda < 1150 nm
           = 10^(0.018*(lambda-1150))    for 1150 <= lambda < 1200 nm
           = 8                           for 1200 <= lambda < 1400 nm

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [0, 1400).

    Returns:
        The dimensionless correction factor (1.0 to 8.0).

    Raises:
        ValueError: If `wavelength_nm` is negative or >= 1400.
    """
    if wavelength_nm < 0.0 or wavelength_nm >= 1400.0:
        raise ValueError("wavelength_nm must be in [0, 1400) nm for C7.")
    if wavelength_nm < 1150.0:
        return 1.0
    if wavelength_nm < 1200.0:
        return 10.0 ** (0.018 * (wavelength_nm - 1150.0))
    return 8.0


def c6_iec60825_1(
    alpha_rad: float,
    alpha_min_rad: float = ALPHA_MIN_IEC60825_1_RAD,
    alpha_max_rad: float = ALPHA_MAX_RAD,
) -> float:
    """Retinal-thermal angular-subtense correction factor C6.

    Henderson & Schulmeister eq. (3.10) [Chaves Ch. 3:224]:
    `C6 = alpha / alpha_min`, with alpha clamped to [alpha_min, alpha_max]
    first. Ranges from C6=1 (small source, alpha <= alpha_min) to
    C6=66.67 (large source, alpha >= alpha_max=100 mrad, alpha_min=1.5 mrad).
    The ratio is dimensionless, so alpha_rad may be passed in radians
    directly -- no mrad conversion needed, unlike `t2_iec60825_1`.

    Args:
        alpha_rad: Angular subtense of the apparent source, in radians.
        alpha_min_rad: IEC 60825-1's alpha_min (default 0.0015 rad).
        alpha_max_rad: Shared alpha_max (default 0.1 rad).

    Returns:
        The dimensionless correction factor.
    """
    return clip_alpha(alpha_rad, alpha_min_rad, alpha_max_rad) / alpha_min_rad


def c3_iec60825_1(wavelength_nm: float) -> float:
    """Retinal-photochemical wavelength correction factor C3.

    Henderson & Schulmeister Sec. 3.12.6.1 / eq. (3.16)-adjacent
    [Chaves Ch. 3:558-560,624]: "the wavelength correction factor C3
    ... increases the retinal photochemical limit exponentially, so that
    it changes from the lowest value of 1 W/m^2 valid in the wavelength
    range 400-450 nm up to a value of 1000 W/m^2 for a wavelength of
    600 nm":

        C3 = 1                          for 400 <= lambda < 450 nm
           = 10^(0.02*(lambda-450))      for 450 <= lambda <= 600 nm

    Note: this factor is not yet consumed by any MPE/AEL function in this
    package -- `iec60825_1.py` implements only the retinal
    *thermal* hazard chain, not the retinal *photochemical* one. Included
    here because it was explicitly scoped into `correction_factors.py`
    and is independently useful/testable now.

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [400, 600]
            (the photochemical hazard's defined wavelength range).

    Returns:
        The dimensionless correction factor (1.0 to 1000.0).

    Raises:
        ValueError: If `wavelength_nm` is outside [400, 600].
    """
    if not (400.0 <= wavelength_nm <= 600.0):
        raise ValueError(
            f"wavelength_nm={wavelength_nm} is outside C3's defined domain "
            "of [400, 600] nm (the retinal photochemical hazard range)."
        )
    if wavelength_nm < 450.0:
        return 1.0
    return 10.0 ** (0.02 * (wavelength_nm - 450.0))
