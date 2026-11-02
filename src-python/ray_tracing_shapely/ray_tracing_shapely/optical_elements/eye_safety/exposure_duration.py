"""
Python-specific module: Exposure-duration time-regime helpers (Eye safety framework)

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
PYTHON-SPECIFIC MODULE: Exposure-duration time regimes
===============================================================================
Both governing standards let eye movements grow the "effective" area/angle
used to assess a retinal hazard as exposure duration increases, but they
express this as two genuinely different state machines -- not one shared
formula. This module implements each standard's own piecewise functions
directly, rather than a single dispatcher, per
dev_doc/architecture/components/eye_safety.md.

IEC 62471 varies the *angular subtense used to average retinal radiance*
with duration (`alpha_eff_iec62471`). IEC 60825-1 instead varies (a) the
duration at which the retinal-thermal MPE stops decreasing and becomes a
constant irradiance (`t2_iec60825_1`, a function of alpha, not of t) and
(b) the *angle of acceptance* used for retinal-photochemical measurements
(`gamma_ph_iec60825_1`, a function of t). The retinal-thermal angle of
acceptance is fixed at 100 mrad regardless of duration
(`GAMMA_TH_IEC60825_1_RAD`).
===============================================================================
"""

from __future__ import annotations

from .angular_subtense import (
    ALPHA_MIN_IEC62471_RAD,
    ALPHA_MIN_IEC60825_1_RAD,
    ALPHA_MAX_RAD,
    clip_alpha,
)


#: Henderson & Schulmeister Sec. 3.6.1 / 3.12.5.2: the retinal-thermal angle
#: of acceptance is a fixed 100 mrad, independent of exposure duration.
GAMMA_TH_IEC60825_1_RAD: float = 0.1


def alpha_eff_iec62471(
    duration_s: float,
    alpha_min_rad: float = ALPHA_MIN_IEC62471_RAD,
    alpha_max_rad: float = ALPHA_MAX_RAD,
) -> float:
    """Effective angular subtense to average retinal radiance over, IEC 62471.

    Piecewise per Sec. 4.2.2 [IEC 62471]:

    - t <= 0.25 s: alpha_min (measurement FOV for point/pulsed sources at
      the 0.25 s blink-reflex time).
    - 0.25 s < t <= 10 s: grows from alpha_min to 0.011 rad as the square
      root of time, `alpha_min * sqrt(t / 0.25)` -- the standard states
      this reaches "about 0,011 radian" at t=10 s (an approximation the
      standard itself flags: "little data is available to support this
      time dependence").
    - 10 s < t <= 100 s: held at 0.011 rad (the blue-light-hazard
      measurement angle "for times less than 100 s").
    - 100 s < t < 10000 s: grows from 0.011 to alpha_max as
      `0.011 * sqrt(t / 100)`.
    - t >= 10000 s: alpha_max (0.1 rad).

    Args:
        duration_s: Exposure duration in seconds. Must be positive.
        alpha_min_rad: IEC 62471's alpha_min (default 0.0017 rad).
        alpha_max_rad: Shared alpha_max (default 0.1 rad).

    Returns:
        Effective angular subtense in radians.

    Raises:
        ValueError: If `duration_s` is not positive.
    """
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")

    if duration_s <= 0.25:
        return alpha_min_rad
    if duration_s <= 10.0:
        return alpha_min_rad * (duration_s / 0.25) ** 0.5
    if duration_s <= 100.0:
        return 0.011
    if duration_s < 10000.0:
        return 0.011 * (duration_s / 100.0) ** 0.5
    return alpha_max_rad


def t2_iec60825_1(
    alpha_rad: float,
    alpha_min_rad: float = ALPHA_MIN_IEC60825_1_RAD,
    alpha_max_rad: float = ALPHA_MAX_RAD,
) -> float:
    """Break time T2: exposure duration beyond which the retinal-thermal MPE
    becomes a constant irradiance rather than continuing to decrease.

    Henderson & Schulmeister eq. (3.9) [Chaves Ch. 3:180]:
    `T2 = 10 * 10^((alpha_mrad - 1.5) / 98.5)`, with alpha clamped to
    [alpha_min, alpha_max] (1.5-100 mrad) before use. T2 ranges from 10 s
    (small sources, alpha <= alpha_min) to 100 s (alpha >= alpha_max).

    Args:
        alpha_rad: Angular subtense of the apparent source, in radians.
        alpha_min_rad: IEC 60825-1's alpha_min (default 0.0015 rad).
        alpha_max_rad: Shared alpha_max (default 0.1 rad).

    Returns:
        T2 in seconds (10.0 to 100.0).
    """
    alpha_clamped_mrad = clip_alpha(alpha_rad, alpha_min_rad, alpha_max_rad) * 1000.0
    alpha_min_mrad = alpha_min_rad * 1000.0
    alpha_max_mrad = alpha_max_rad * 1000.0
    exponent = (alpha_clamped_mrad - alpha_min_mrad) / (alpha_max_mrad - alpha_min_mrad)
    return 10.0 * (10.0 ** exponent)


def gamma_ph_iec60825_1(duration_s: float) -> float:
    """Retinal-photochemical angle of acceptance, IEC 60825-1.

    Henderson & Schulmeister table 3.12 [Chaves Ch. 3:543-548]:

    - 10 s <= t <= 100 s: 11 mrad (0.011 rad), constant.
    - 100 s < t <= 10000 s: `1.1 * sqrt(t)` mrad -- continuous with the
      11 mrad value at t=100 s and the 110 mrad value at t=10000 s.
    - t > 10000 s: 110 mrad (0.110 rad).

    Args:
        duration_s: Exposure duration in seconds.

    Returns:
        Angle of acceptance in radians.

    Raises:
        ValueError: If `duration_s` is not positive, or is below 10 s --
            retinal photochemical limits do not apply below 10 s (the
            retinal thermal limit governs there instead), so this function
            has no defined value in that domain.
    """
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")
    if duration_s < 10.0:
        raise ValueError(
            "gamma_ph_iec60825_1 is defined for t >= 10 s only -- retinal "
            "photochemical limits do not apply below 10 s (Henderson & "
            "Schulmeister Sec. 3.12.6); the retinal thermal limit applies "
            "instead."
        )
    if duration_s <= 100.0:
        return 0.011
    if duration_s <= 10000.0:
        return 1.1e-3 * (duration_s ** 0.5)
    return 0.110
