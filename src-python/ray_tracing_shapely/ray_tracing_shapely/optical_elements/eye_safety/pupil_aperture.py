"""
Python-specific module: Limiting-aperture selection and averaging (Eye safety framework)

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
PYTHON-SPECIFIC MODULE: Pupil / limiting-aperture handling
===============================================================================
The two standards select a limiting-aperture diameter by different rules --
IEC 62471 by source luminance and exposure duration, IEC 60825-1 by
wavelength (and, in one band, duration) -- so this module exposes two
separate selection functions rather than one shared constant, plus a single
shared numerical-averaging utility that operates on whichever diameter was
selected.

See dev_doc/architecture/components/eye_safety.md
===============================================================================
"""

from __future__ import annotations

from typing import List, Sequence


def limiting_aperture_diameter_iec62471(duration_s: float, luminance_cd_m2: float) -> float:
    """Limiting (pupil) aperture diameter for IEC 62471, in metres.

    Per Sec. 4.2.1 [IEC 62471]:

    - A 3 mm pupil diameter is used "when the luminance of the source is
      adequately high (> 10 cd/m^2), and the exposure duration is greater
      than 0,25 s."
    - A 7 mm pupil diameter is used "when the luminance of the source is
      low ... The 7 mm diameter is also assumed when evaluating the
      photobiological hazard from pulsed sources and/or for exposure
      durations of less than 0,25 s."

    Args:
        duration_s: Exposure duration in seconds. Must be positive.
        luminance_cd_m2: Source luminance in cd/m^2. Must be non-negative.

    Returns:
        Aperture diameter in metres: 0.003 or 0.007.

    Raises:
        ValueError: If `duration_s` is not positive or `luminance_cd_m2` is
            negative.
    """
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")
    if luminance_cd_m2 < 0.0:
        raise ValueError("luminance_cd_m2 must be non-negative.")

    if duration_s < 0.25:
        return 0.007
    if luminance_cd_m2 > 10.0:
        return 0.003
    return 0.007


def limiting_aperture_diameter_iec60825_1(
    wavelength_nm: float,
    duration_s: float,
    tissue: str = 'eye',
) -> float:
    """Limiting aperture diameter for IEC 60825-1, in metres.

    Per Henderson & Schulmeister table 3.1 [Chaves Ch. 3:296-304]:

    | Spectral region  | Eye aperture                                    | Skin aperture |
    |------------------|--------------------------------------------------|---------------|
    | 180-400 nm       | 1 mm                                              | 3.5 mm        |
    | 400-1400 nm      | 7 mm                                              | 3.5 mm        |
    | 1.4-100 um       | 1 mm (t<=0.35s); 1.5*t^(3/8) mm (0.35s<t<10s);   | 3.5 mm        |
    |                  | 3.5 mm (t>=10s)                                   |               |
    | 0.1-1 mm         | 11 mm                                             | 11 mm         |

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [180, 1e6]
            (180 nm to 1 mm, the table's domain).
        duration_s: Exposure duration in seconds. Only used in the
            1.4-100 um eye band; ignored (but still validated) elsewhere.
        tissue: 'eye' or 'skin'.

    Returns:
        Aperture diameter in metres.

    Raises:
        ValueError: If `wavelength_nm` is outside [180, 1e6], `duration_s`
            is not positive, or `tissue` is not 'eye' or 'skin'.
    """
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")
    if tissue not in ('eye', 'skin'):
        raise ValueError(f"tissue must be 'eye' or 'skin', got {tissue!r}.")
    if not (180.0 <= wavelength_nm <= 1.0e6):
        raise ValueError(
            f"wavelength_nm={wavelength_nm} is outside the limiting-aperture "
            "table's domain of 180 nm to 1e6 nm (1 mm)."
        )

    if wavelength_nm < 400.0:
        return 0.0035 if tissue == 'skin' else 0.001
    if wavelength_nm < 1400.0:
        return 0.0035 if tissue == 'skin' else 0.007
    if wavelength_nm < 1.0e5:  # 1.4 um to 100 um
        if tissue == 'skin':
            return 0.0035
        if duration_s <= 0.35:
            return 0.001
        if duration_s < 10.0:
            return 1.5e-3 * (duration_s ** 0.375)
        return 0.0035
    return 0.011  # 0.1 mm to 1 mm, both tissues


def average_over_aperture(
    positions_m: Sequence[float],
    values: Sequence[float],
    aperture_diameter_m: float,
    center_position_m: float = 0.0,
) -> float:
    """Mean of `values` whose `positions_m` fall within the aperture.

    A 1-D windowed mean over a line of samples at known positions -- e.g.
    `Photoconversion.compute_irradiance`'s per-pixel W/m^2 output, each at
    its pixel's position along a `LinearSensor`. This is a genuine
    limitation, not a simplification made for convenience: the 2D
    ray-tracing core only ever produces a 1-D irradiance profile along a
    detector line, so a true 2-D circular-pupil integral is not
    representable without an anatomical eye model, which is deferred to
    the 3-D work. This function averages over the 1-D projection of
    that aperture instead -- correct when the detector line is aligned
    with the direction the pupil would sweep, an approximation otherwise.

    Args:
        positions_m: Sample positions along the detector line, in metres.
        values: Sample values (e.g. irradiance in W/m^2) at each position.
            Must be the same length as `positions_m`.
        aperture_diameter_m: Aperture diameter in metres (from
            `limiting_aperture_diameter_iec62471` or
            `limiting_aperture_diameter_iec60825_1`). Must be positive.
        center_position_m: Centre of the aperture along the detector line,
            in metres. Default 0.0.

    Returns:
        The arithmetic mean of the `values` whose `positions_m` lie within
        `aperture_diameter_m / 2` of `center_position_m`.

    Raises:
        ValueError: If `positions_m` and `values` differ in length, if
            `aperture_diameter_m` is not positive, or if no sample position
            falls within the aperture (the aperture is narrower than the
            sample spacing at `center_position_m`).
    """
    if len(positions_m) != len(values):
        raise ValueError("positions_m and values must be the same length.")
    if aperture_diameter_m <= 0.0:
        raise ValueError("aperture_diameter_m must be positive.")

    radius_m = aperture_diameter_m / 2.0
    windowed: List[float] = [
        v for p, v in zip(positions_m, values)
        if abs(p - center_position_m) <= radius_m
    ]
    if not windowed:
        raise ValueError(
            f"No sample position falls within the aperture "
            f"(diameter={aperture_diameter_m} m, centre={center_position_m} m) "
            "-- the aperture is narrower than the sample spacing there."
        )
    return sum(windowed) / len(windowed)
