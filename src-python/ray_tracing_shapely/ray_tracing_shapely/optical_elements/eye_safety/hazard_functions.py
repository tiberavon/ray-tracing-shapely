"""
Python-specific module: IEC 62471 spectral hazard-weighting functions (Eye safety framework)

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
PYTHON-SPECIFIC MODULE: S(lambda), B(lambda), R(lambda)
===============================================================================
The three broadband (lamp/LED) spectral hazard-weighting functions IEC 62471
Tables 4.1/4.2 define, transcribed here from Tables 1.2/1.3 of Annex I to
Directive 2006/25/EC, as reproduced in the Commission's 2010 non-binding
guide to good practice for implementing that Directive. The Directive's
non-coherent-radiation Annex I is IEC 62471/ICNIRP's own broadband hazard
formula set transposed into EU law -- same thresholds, same exponents, same
wavelength bands, same weighting-function names -- and every formula here
was checked against both sources term by term.
[KD9: the standards texts these numbers come from are read privately; the
code cites the standard, never the transcription.]

- **S(lambda)** -- actinic UV hazard weighting, 180-400 nm. Tabulated at
  1 nm steps (221 points), peak 1.0 at 270 nm. No closed-form tail; queried
  via `interp_log` (IEC 62471 Sec. 5.3.1's own log-space interpolation
  convention, C-EYE-01) across its entire domain.
- **B(lambda)** -- blue-light (photochemical retinal) hazard weighting,
  300-700 nm. Tabulated (log-interpolated) from 300-500 nm, a closed-form
  exponential tail `10^(-0.02*(lambda-450))` from 500-600 nm, then flat
  0.001 from 600-700 nm.
- **R(lambda)** -- retinal-thermal hazard weighting, 380-1400 nm. Tabulated
  (log-interpolated) from 380-500 nm (values exactly 10x B(lambda) in that
  sub-range), flat 1.0 from 500-700 nm, a closed-form exponential tail
  `10^(-0.002*(lambda-700))` from 700-1050 nm, flat 0.2 from 1050-1150 nm,
  a second closed-form tail `0.2*10^(-0.02*(lambda-1150))` from
  1150-1200 nm, then flat 0.02 from 1200-1400 nm.

The two closed-form tails were reconstructed from the Directive's own
(OCR-garbled) exponent notation by requiring continuity at both ends of
each sub-range against the neighbouring flat/tabulated values -- e.g. the
500-600 nm B(lambda) tail must equal 0.1 at lambda=500 (continuous with the
tabulated value) and 0.001 at lambda=600 (continuous with the flat value
that follows) -- which uniquely determines
`10^(-0.02*(lambda-450))` = `10^((450-lambda)/50)`, matching an
independent citation of IEC 62471's Table 4.2 formula
notation for the same tail (Sec. 5 of that document).
===============================================================================
"""

from __future__ import annotations

from .spectral_data import interp_log

# =============================================================================
# S(lambda) -- actinic UV hazard weighting, 180-400 nm, 1 nm steps.
# Directive 2006/25/EC Annex I, Table 1.2 [Directive 2006/25/EC guide].
# =============================================================================
_S_WAVELENGTHS_NM = tuple(range(180, 401))
_S_VALUES = (
    0.0120, 0.0126, 0.0132, 0.0138, 0.0144, 0.0151, 0.0158, 0.0166, 0.0173, 0.0181,
    0.0190, 0.0199, 0.0208, 0.0218, 0.0228, 0.0239, 0.0250, 0.0262, 0.0274, 0.0287,
    0.0300, 0.0334, 0.0371, 0.0412, 0.0459, 0.0510, 0.0551, 0.0595, 0.0643, 0.0694,
    0.0750, 0.0786, 0.0824, 0.0864, 0.0906, 0.0950, 0.0995, 0.1043, 0.1093, 0.1145,
    0.1200, 0.1257, 0.1316, 0.1378, 0.1444, 0.1500, 0.1583, 0.1658,  # 180-227
    0.1737, 0.1819, 0.1900, 0.1995, 0.2089, 0.2188, 0.2292, 0.2400, 0.2510, 0.2624,
    0.2744, 0.2869, 0.3000, 0.3111, 0.3227, 0.3347, 0.3471, 0.3600, 0.3730, 0.3865,
    0.4005, 0.4150, 0.4300, 0.4465, 0.4637, 0.4815, 0.5000, 0.5200, 0.5437, 0.5685,
    0.5945, 0.6216, 0.6500, 0.6792, 0.7098, 0.7417, 0.7751, 0.8100, 0.8449, 0.8812,
    0.9192, 0.9587, 1.0000, 0.9919, 0.9838, 0.9758, 0.9679, 0.9600,  # 228-275
    0.9434, 0.9272, 0.9112, 0.8954, 0.8800, 0.8568, 0.8342, 0.8122, 0.7908, 0.7700,
    0.7420, 0.7151, 0.6891, 0.6641, 0.6400, 0.6186, 0.5980, 0.5780, 0.5587, 0.5400,
    0.4984, 0.4600, 0.3989, 0.3459, 0.3000, 0.2210, 0.1629, 0.1200, 0.0849, 0.0600,
    0.0454, 0.0344, 0.0260, 0.0197, 0.0150, 0.0111, 0.0081, 0.0060, 0.0042, 0.0030,
    0.0024, 0.0020, 0.0016, 0.0012, 0.0010,
    0.000819, 0.000670, 0.000540,  # 276-323
    0.000520, 0.000500, 0.000479, 0.000459, 0.000440, 0.000425, 0.000410, 0.000396,
    0.000383, 0.000370, 0.000355, 0.000340, 0.000327, 0.000315, 0.000303, 0.000291,
    0.000280, 0.000271, 0.000263, 0.000255, 0.000248, 0.000240, 0.000231, 0.000223,
    0.000215, 0.000207, 0.000200, 0.000191, 0.000183, 0.000175, 0.000167, 0.000160,
    0.000153, 0.000147, 0.000141, 0.000136, 0.000130, 0.000126, 0.000122, 0.000118,
    0.000114, 0.000110, 0.000106, 0.000103, 0.000099, 0.000096, 0.000093, 0.000090,  # 324-371
    0.000086, 0.000083, 0.000080, 0.000077, 0.000074, 0.000072, 0.000069, 0.000066,
    0.000064, 0.000062, 0.000059, 0.000057, 0.000055, 0.000053, 0.000051, 0.000049,
    0.000047, 0.000046, 0.000044, 0.000042, 0.000041, 0.000039, 0.000037, 0.000036,
    0.000035, 0.000033, 0.000032, 0.000031, 0.000030,  # 372-400
)
assert len(_S_WAVELENGTHS_NM) == len(_S_VALUES) == 221


def S_actinic_uv(wavelength_nm: float) -> float:
    """Actinic UV hazard spectral weighting function, S(lambda).

    IEC 62471 Table 4.1 / Directive 2006/25/EC Annex I Table 1.2, 180-400 nm.
    Peak value 1.0 at 270 nm. Log-space interpolated between tabulated
    1 nm points (Sec. 5.3.1, C-EYE-01) -- the curve changes by up to 250%
    over a 3 nm span near 300 nm, where plain linear interpolation would
    misrepresent its shape.

    Args:
        wavelength_nm: Wavelength in nanometres.

    Returns:
        Dimensionless weighting factor in (0, 1].

    Raises:
        ValueError: If `wavelength_nm` is outside [180, 400] nm.
    """
    if not (180.0 <= wavelength_nm <= 400.0):
        raise ValueError(
            f"S_actinic_uv is defined for 180-400 nm only; got {wavelength_nm} nm."
        )
    return interp_log(_S_WAVELENGTHS_NM, _S_VALUES, wavelength_nm)


# =============================================================================
# B(lambda) / R(lambda) -- blue-light and retinal-thermal hazard weighting,
# 5 nm steps from 380-500 nm, closed-form tails beyond.
# Directive 2006/25/EC Annex I, Table 1.3 [Directive 2006/25/EC guide].
# =============================================================================
_BR_WAVELENGTHS_NM = (
    380, 385, 390, 395, 400, 405, 410, 415, 420, 425,
    430, 435, 440, 445, 450, 455, 460, 465, 470, 475,
    480, 485, 490, 495, 500,
)
_B_VALUES_TABLE = (
    0.01, 0.013, 0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 0.9, 0.95,
    0.98, 1.0, 1.0, 0.97, 0.94, 0.9, 0.8, 0.7, 0.62, 0.55,
    0.45, 0.32, 0.22, 0.16, 0.1,
)
_R_VALUES_TABLE = tuple(10.0 * v for v in _B_VALUES_TABLE)
assert len(_BR_WAVELENGTHS_NM) == len(_B_VALUES_TABLE) == len(_R_VALUES_TABLE) == 25

#: B(lambda) below the tabulated range: flat 0.01 for 300 <= lambda < 380
#: [Directive 2006/25/EC guide].
_B_FLAT_UV_VALUE = 0.01
#: B(lambda) 600-700 nm: flat 0.001 [Directive 2006/25/EC guide].
_B_FLAT_RED_VALUE = 0.001
#: R(lambda) 500-700 nm: flat 1.0 [Directive 2006/25/EC guide].
_R_FLAT_VISIBLE_VALUE = 1.0
#: R(lambda) 1050-1150 nm: flat 0.2 [Directive 2006/25/EC guide].
_R_FLAT_NIR_VALUE = 0.2
#: R(lambda) 1200-1400 nm: flat 0.02 [Directive 2006/25/EC guide].
_R_FLAT_IRA_VALUE = 0.02


def B_blue_light(wavelength_nm: float) -> float:
    """Blue-light (photochemical retinal) hazard spectral weighting, B(lambda).

    IEC 62471 Table 4.2 / Directive Annex I Table 1.3, 300-700 nm:

    - 300 <= lambda < 380 nm: flat 0.01.
    - 380-500 nm: log-interpolated table, peak 1.0 at 435-440 nm.
    - 500 < lambda <= 600 nm: closed form `10^(-0.02*(lambda-450))`,
      continuous with 0.1 at 500 nm and 0.001 at 600 nm.
    - 600 < lambda <= 700 nm: flat 0.001.

    Args:
        wavelength_nm: Wavelength in nanometres.

    Returns:
        Dimensionless weighting factor in (0, 1].

    Raises:
        ValueError: If `wavelength_nm` is outside [300, 700] nm.
    """
    if wavelength_nm < 300.0 or wavelength_nm > 700.0:
        raise ValueError(
            f"B_blue_light is defined for 300-700 nm only; got {wavelength_nm} nm."
        )
    if wavelength_nm < 380.0:
        return _B_FLAT_UV_VALUE
    if wavelength_nm <= 500.0:
        return interp_log(_BR_WAVELENGTHS_NM, _B_VALUES_TABLE, wavelength_nm)
    if wavelength_nm <= 600.0:
        return 10.0 ** (-0.02 * (wavelength_nm - 450.0))
    return _B_FLAT_RED_VALUE


def R_retinal_thermal(wavelength_nm: float) -> float:
    """Retinal-thermal hazard spectral weighting, R(lambda).

    IEC 62471 Table 4.2 / Directive Annex I Table 1.3, 380-1400 nm:

    - 380-500 nm: log-interpolated table (exactly 10x B(lambda) in this
      sub-range), peak 10.0 at 435-440 nm.
    - 500 < lambda <= 700 nm: flat 1.0.
    - 700 < lambda <= 1050 nm: closed form `10^(-0.002*(lambda-700))`,
      continuous with 1.0 at 700 nm and ~0.2 at 1050 nm.
    - 1050 < lambda <= 1150 nm: flat 0.2.
    - 1150 < lambda <= 1200 nm: closed form
      `0.2 * 10^(-0.02*(lambda-1150))`, continuous with 0.2 at 1150 nm
      and 0.02 at 1200 nm.
    - 1200 < lambda <= 1400 nm: flat 0.02.

    Args:
        wavelength_nm: Wavelength in nanometres.

    Returns:
        Dimensionless weighting factor in (0, 10].

    Raises:
        ValueError: If `wavelength_nm` is outside [380, 1400] nm.
    """
    if wavelength_nm < 380.0 or wavelength_nm > 1400.0:
        raise ValueError(
            f"R_retinal_thermal is defined for 380-1400 nm only; got {wavelength_nm} nm."
        )
    if wavelength_nm <= 500.0:
        return interp_log(_BR_WAVELENGTHS_NM, _R_VALUES_TABLE, wavelength_nm)
    if wavelength_nm <= 700.0:
        return _R_FLAT_VISIBLE_VALUE
    if wavelength_nm <= 1050.0:
        return 10.0 ** (-0.002 * (wavelength_nm - 700.0))
    if wavelength_nm <= 1150.0:
        return _R_FLAT_NIR_VALUE
    if wavelength_nm <= 1200.0:
        return 0.2 * (10.0 ** (-0.02 * (wavelength_nm - 1150.0)))
    return _R_FLAT_IRA_VALUE
