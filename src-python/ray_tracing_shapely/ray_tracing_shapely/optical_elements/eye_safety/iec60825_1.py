"""
Python-specific module: IEC 60825-1 retinal-thermal MPE, AEL, and classification (Eye safety framework)

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
PYTHON-SPECIFIC MODULE: IEC 60825-1 MPE / AEL / classification
===============================================================================
Four hazard chains, covering 180 nm-1400 nm (no far-IR, >1400 nm, yet):

- **Retinal thermal** (400-1400 nm, 18 us and up -- no ultrashort/
  single-fs-to-ns pulse cascade). `mpe_retinal_thermal`.
- **Retinal photochemical** (400-600 nm, above 10 s -- not defined below
  10 s, where thermal governs exclusively). `mpe_retinal_photochemical`.
  Henderson & Schulmeister Sec. 3.12.7: "in order that an exposure ... be
  safe, the exposure level needs to be below the MPE for both the thermal
  and the photochemical case" -- `ael_class_1` takes the more restrictive
  (lower) of the two wherever both apply; `ael_class_2`/`ael_class_3r`
  never need this (their 0.25 s duration is below the photochemical
  hazard's 10 s floor).
- **Corneal/lens UV** (180-400 nm, 1 ns-30000 s), protecting against
  photokeratitis (cornea) and cataractogenesis (lens). `mpe_cornea_uv`.
  A genuine dual limit: photochemical below 315 nm (a hard 30 J/m^2 floor
  from 180-302.5 nm, then a steep exponential rise via C2 from 302.5-315 nm
  crossing over a thermal limit C1 at a wavelength-dependent time T1), and
  a duration-only (no further wavelength dependence) three-bracket
  function from 315-400 nm. `ael_class_1` dispatches to this for
  wavelength_nm < 400.
- **Skin thermal** (400-1400 nm; below 400 nm and above 1400 nm, Henderson
  Sec. 3.8 states the skin MPE is set identical to the eye's -- i.e.
  `mpe_cornea_uv`'s value applies to skin too in the UV, no separate
  function needed there). `mpe_skin_thermal`, `ael_skin`.

Not implemented: far-IR (>1400 nm) eye/skin MPE, ultrashort/short-pulse
retinal-thermal regimes below 18 us, and the full 3-measurement-condition +
"M"-designation classification procedure (Henderson table 4.4) --
`classify_measurement()` below answers "which class does this ONE
already-measured accessible-emission value fall under," not "what is this
product's overall class," which additionally needs knowledge of the
apparent source's location and which physical measurement condition
(naked eye / eye loupe / telescope) produced each number. See
dev_doc/architecture/components/eye_safety.md.

**C-EYE-04** (dev_doc/architecture/contracts/C-EYE-04.md): this module's
functions are not re-exported at `eye_safety`'s top level -- call them via
`eye_safety.iec60825_1.mpe_retinal_thermal(...)` etc., explicitly, never a
bare package-level name. `iec62471.py` defines a `mpe_retinal_thermal`/
`mpe_skin_thermal`/`classify_measurement` of its own, for lamp/LED sources,
with different formulas, bands, and angular conventions -- symmetric
submodule-qualified access is what keeps neither standard a silently
privileged default.

**A note on source ambiguity, resolved rather than guessed at**: Henderson
table 3.9's markdown extraction shows the 315-400 nm / 1 ns-10 s cell as
"C2" (photochemical, wavelength-dependent), directly contradicting the
surrounding prose [Chaves Ch. 3:816]: "The thermal limit of C1 J/m^2
applies also to the wavelength range 315-400 nm, for pulse (exposure)
durations of 1 ns to 10 s." The prose is followed here (pure time
dependence, no further wavelength dependence past 315 nm), confirmed
numerically: T1 evaluated at exactly 315 nm equals exactly 10 s, and C1(t=10s)
= 9958 J/m^2 while C2(315 nm) = 10000 J/m^2 -- the two formulas meet almost
exactly at that boundary, consistent with a continuous handoff from the
302.5-315 nm dual-limit region into a pure-C1 315-400 nm region, not with
C2 continuing to apply past 315 nm (which would give absurd values, e.g.
C2(400 nm) = 10^21 J/m^2).
===============================================================================
"""

from __future__ import annotations

import math
from typing import Dict, Optional

from .angular_subtense import ALPHA_MIN_IEC60825_1_RAD
from .correction_factors import c3_iec60825_1, c4_iec60825_1, c6_iec60825_1, c7_iec60825_1
from .exposure_duration import t2_iec60825_1
from .pupil_aperture import limiting_aperture_diameter_iec60825_1
from .result import LimitResult

#: Below this duration, the MPE cascades through ultrashort/short-pulse
#: regimes (table 3.10's <100 fs / 100 fs-10 ps / 10 ps-1 ns rows, plus a
#: near-IR-specific factor-of-2 tightening below 18-50 us) that this module
#: does not implement -- see the module docstring.
_MIN_SUPPORTED_DURATION_S: float = 18e-6


def _resolve_class1_duration(wavelength_nm: float, duration_s: Optional[float]) -> float:
    """C-EYE-02: the Class 1/1M (and non-visible Class 3R) time base is
    30000 s for UV (Table 4.3) and 100 s for visible/near-IR -- not one
    number a caller can safely default everywhere. `ael_class_1`/
    `ael_class_3r`/`classify_measurement` all resolve this automatically
    when `duration_s` is `None`, so getting it right never depends on a
    caller (human or agent) having read this far. An explicit `duration_s`
    is still honoured -- this only fills in the standard-mandated default,
    it never overrides a caller's own choice."""
    if duration_s is not None:
        return duration_s
    return 30000.0 if wavelength_nm < 400.0 else 100.0


def mpe_retinal_thermal(
    wavelength_nm: float,
    duration_s: float,
    alpha_rad: float = ALPHA_MIN_IEC60825_1_RAD,
) -> LimitResult:
    """Retinal-thermal maximum permissible exposure (MPE).

    Henderson & Schulmeister table 3.10 [Chaves Ch. 3:89-109] for
    `18 us <= duration_s <= 10 s` (radiant exposure, J/m^2):

        MPE = C6 * 18 * duration_s^0.75 * C4 * C7

    and Sec. 3.12.4.2 [Chaves Ch. 3:200-206] for `duration_s > 10 s`
    (irradiance, W/m^2), using the break time T2 (`t2_iec60825_1`):

        t_eff = min(duration_s, T2(alpha))
        MPE = C6 * 18 * t_eff^-0.25 * C4 * C7

    Both branches are multiplied by C4 and C7 uniformly, per Sec. 3.12.3:
    "For wavelengths above 700 nm, all of the above values need to be
    multiplied with both wavelength correction factors C4 and C7" -- C4=C7=1
    below 700 nm, so this is a no-op there.

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [400, 1400) --
            the retinal-thermal hazard region.
        duration_s: Exposure duration in seconds. Must be >= 18 us (see
            module docstring for why shorter durations are out of scope).
        alpha_rad: Angular subtense of the apparent source, in radians.
            Default is IEC 60825-1's alpha_min (small-source, C6=1).

    Returns:
        A `LimitResult` with `unit` "J/m^2" (duration_s <= 10 s) or "W/m^2"
        (duration_s > 10 s), `region="retinal_thermal"`, and `factors`
        holding C4, C6, C7.

    Raises:
        ValueError: If `wavelength_nm` is outside [400, 1400).
        NotImplementedError: If `duration_s < 18 us` (ultrashort/short-pulse
            regimes not implemented).
    """
    if not (400.0 <= wavelength_nm < 1400.0):
        raise ValueError(
            f"wavelength_nm={wavelength_nm} is outside the retinal-thermal "
            "hazard region of [400, 1400) nm."
        )
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")
    if duration_s < _MIN_SUPPORTED_DURATION_S:
        raise NotImplementedError(
            f"mpe_retinal_thermal does not implement the ultrashort/"
            f"short-pulse MPE regimes below {_MIN_SUPPORTED_DURATION_S} s "
            "(Henderson & Schulmeister table 3.10's <100 fs / 100 fs-10 ps / "
            "10 ps-1 ns rows, plus the near-IR factor-of-2 tightening for "
            "pulses shorter than 18-50 us). Only continuous-wave and "
            "longer-pulse exposures are supported."
        )

    c4 = c4_iec60825_1(wavelength_nm)
    c7 = c7_iec60825_1(wavelength_nm)
    c6 = c6_iec60825_1(alpha_rad)
    factors: Dict[str, float] = {"C4": c4, "C6": c6, "C7": c7}

    if duration_s <= 10.0:
        value = c6 * 18.0 * (duration_s ** 0.75) * c4 * c7
        return LimitResult(
            value=value, unit="J/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=alpha_rad,
            region="retinal_thermal", time_regime="18 us <= t <= 10 s",
            equation="Henderson & Schulmeister table 3.10",
            factors=factors,
        )

    t2 = t2_iec60825_1(alpha_rad)
    t_eff = min(duration_s, t2)
    value = c6 * 18.0 * (t_eff ** -0.25) * c4 * c7
    return LimitResult(
        value=value, unit="W/m^2", wavelength_nm=wavelength_nm,
        duration_s=duration_s, alpha_rad=alpha_rad,
        region="retinal_thermal",
        time_regime="t > 10 s" + (" (capped at T2)" if duration_s > t2 else ""),
        equation="Henderson & Schulmeister Sec. 3.12.4.2, eq. (3.9)",
        factors=factors,
        notes=f"T2={t2:.1f} s",
    )


def mpe_retinal_photochemical(wavelength_nm: float, duration_s: float) -> LimitResult:
    """Retinal-photochemical maximum permissible exposure (MPE).

    Henderson & Schulmeister table 3.12 [Chaves Ch. 3:543-548] and
    Sec. 3.12.6.2's text [Chaves Ch. 3:568] ("for cw radiation, the
    maximum permissible irradiance level is given by 100*C3*(1/t) W/m^2
    ... For exposure durations greater than 100 s, the retinal
    photochemical MPE assumes a constant irradiance value of 1 W/m^2"
    -- i.e. 1*C3 W/m^2, since C3=1 is the reference at 400-450 nm):

        10 s <= t <= 100 s:  MPE = 100 * C3 J/m^2   (radiant exposure)
        t > 100 s:           MPE = 1 * C3 W/m^2     (irradiance, constant)

    Unlike the retinal-thermal MPE, this has **no angular-subtense (C6)
    dependence** -- the photochemical limit itself does not depend on
    source size; only the *measurement* angle of acceptance
    (`gamma_ph_iec60825_1`, already in `exposure_duration.py`) does, for
    correctly measuring an extended source's exposure level, which is a
    measurement-geometry concern this function does not model (same
    scope boundary as `mpe_retinal_thermal`'s C6/alpha handling for a
    caller who already knows the correctly-measured exposure level).

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [400, 600] --
            C3's defined domain and the retinal-photochemical hazard's
            wavelength range.
        duration_s: Exposure duration in seconds. Must be >= 10 s -- the
            photochemical hazard is not defined below 10 s (the thermal
            hazard governs there exclusively).

    Returns:
        A `LimitResult` with `unit` "J/m^2" (10 s <= duration_s <= 100 s)
        or "W/m^2" (duration_s > 100 s), `region="retinal_photochemical"`,
        and `factors={"C3": ...}`.

    Raises:
        ValueError: If `wavelength_nm` is outside [400, 600], or
            `duration_s` is not positive or is below 10 s.
    """
    if not (400.0 <= wavelength_nm <= 600.0):
        raise ValueError(
            f"wavelength_nm={wavelength_nm} is outside the retinal-"
            "photochemical hazard's domain of [400, 600] nm."
        )
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")
    if duration_s < 10.0:
        raise ValueError(
            "mpe_retinal_photochemical is not defined for t < 10 s -- the "
            "retinal thermal hazard governs exclusively there (Henderson & "
            "Schulmeister Sec. 3.12.4); use mpe_retinal_thermal instead."
        )

    c3 = c3_iec60825_1(wavelength_nm)
    if duration_s <= 100.0:
        value = 100.0 * c3
        return LimitResult(
            value=value, unit="J/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=0.0,
            region="retinal_photochemical", time_regime="10 s <= t <= 100 s",
            equation="Henderson & Schulmeister table 3.12",
            factors={"C3": c3},
        )

    value = 1.0 * c3
    return LimitResult(
        value=value, unit="W/m^2", wavelength_nm=wavelength_nm,
        duration_s=duration_s, alpha_rad=0.0,
        region="retinal_photochemical", time_regime="t > 100 s",
        equation="Henderson & Schulmeister Sec. 3.12.6.2",
        factors={"C3": c3},
    )


def mpe_cornea_uv(wavelength_nm: float, duration_s: float) -> LimitResult:
    """Corneal/lens UV maximum permissible exposure (MPE).

    Henderson & Schulmeister table 3.9 [Chaves Ch. 3:824-830] and the
    surrounding text [Chaves Ch. 3:784,802,816] -- a dual limit
    protecting the cornea (photokeratitis) and lens (cataractogenesis):

        180 <= lambda < 302.5 nm:  MPE = 30 J/m^2                (photochemical, constant)

        302.5 <= lambda < 315 nm:  T1 = 10^(0.8*(lambda-295)) * 1e-15 s
                                    if t <  T1: MPE = 5600*t^0.25 J/m^2   (thermal, C1)
                                    if t >= T1: MPE = 10^(0.2*(lambda-295)) J/m^2  (photochemical, C2)

        315 <= lambda < 400 nm:    t <  10 s:          MPE = 5600*t^0.25 J/m^2   (C1, no further
                                                                                   wavelength dependence
                                                                                   -- see module
                                                                                   docstring's note on
                                                                                   resolving a source
                                                                                   ambiguity here)
                                    10 s <= t < 1000 s: MPE = 10000 J/m^2
                                    t >= 1000 s:        MPE = 10 W/m^2

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [180, 400).
        duration_s: Exposure duration in seconds. Must be in
            [1e-9, 30000] -- the standard's own stated domain (`1 ns` to
            `30 000 s`); unlike the retinal-thermal chain, no sub-range is
            deferred here, since no further sub-bracket complexity was
            found in the source for this hazard.

    Returns:
        A `LimitResult` with `unit` "J/m^2" or "W/m^2" depending on branch,
        `region="cornea_uv"`.

    Raises:
        ValueError: If `wavelength_nm` is outside [180, 400), or
            `duration_s` is outside [1e-9, 30000].
    """
    if not (180.0 <= wavelength_nm < 400.0):
        raise ValueError(
            f"wavelength_nm={wavelength_nm} is outside the corneal/lens UV "
            "hazard's domain of [180, 400) nm."
        )
    if not (1e-9 <= duration_s <= 30000.0):
        raise ValueError(
            f"duration_s={duration_s} is outside the corneal UV MPE's "
            "defined domain of [1e-9, 30000] s."
        )

    if wavelength_nm < 302.5:
        return LimitResult(
            value=30.0, unit="J/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=0.0, region="cornea_uv",
            time_regime="1 ns <= t <= 30000 s",
            equation="Henderson & Schulmeister table 3.9 (180-302.5 nm)",
            factors={},
        )

    if wavelength_nm < 315.0:
        t1 = 10.0 ** (0.8 * (wavelength_nm - 295.0)) * 1e-15
        if duration_s < t1:
            c1 = 5600.0 * (duration_s ** 0.25)
            return LimitResult(
                value=c1, unit="J/m^2", wavelength_nm=wavelength_nm,
                duration_s=duration_s, alpha_rad=0.0, region="cornea_uv",
                time_regime=f"t < T1 (thermal); T1={t1:.3e} s",
                equation="Henderson & Schulmeister table 3.9, C1 (302.5-315 nm)",
                factors={"C1": c1, "T1_s": t1},
            )
        c2 = 10.0 ** (0.2 * (wavelength_nm - 295.0))
        return LimitResult(
            value=c2, unit="J/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=0.0, region="cornea_uv",
            time_regime=f"t >= T1 (photochemical); T1={t1:.3e} s",
            equation="Henderson & Schulmeister table 3.9, C2 (302.5-315 nm)",
            factors={"C2": c2, "T1_s": t1},
        )

    # 315 <= wavelength_nm < 400
    if duration_s < 10.0:
        value = 5600.0 * (duration_s ** 0.25)
        return LimitResult(
            value=value, unit="J/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=0.0, region="cornea_uv",
            time_regime="1 ns <= t < 10 s (thermal, C1)",
            equation="Henderson & Schulmeister Sec. 3.11 text (315-400 nm)",
            factors={"C1": value},
        )
    if duration_s < 1000.0:
        return LimitResult(
            value=10000.0, unit="J/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=0.0, region="cornea_uv",
            time_regime="10 s <= t < 1000 s",
            equation="Henderson & Schulmeister Sec. 3.11 (315-400 nm)",
            factors={},
        )
    return LimitResult(
        value=10.0, unit="W/m^2", wavelength_nm=wavelength_nm,
        duration_s=duration_s, alpha_rad=0.0, region="cornea_uv",
        time_regime="1000 s <= t <= 30000 s",
        equation="Henderson & Schulmeister Sec. 3.11 (315-400 nm)",
        factors={},
    )


def mpe_skin_thermal(wavelength_nm: float, duration_s: float) -> LimitResult:
    """Skin thermal maximum permissible exposure (MPE), 400-1400 nm.

    Henderson & Schulmeister table 3.6 [Chaves Ch. 3:562-571] -- a
    genuinely distinct formula from the retinal-thermal MPE (no `C6`/
    angular-subtense dependence at all: the skin does not focus light):

        1 ns  <= t <= 100 ns:  MPE = 200*C4 J/m^2       (held constant below 1 ns too,
                                                          per Sec. "Ultrashort pulses")
        100 ns < t <= 10 s:    MPE = 11000*C4*t^0.25 J/m^2
        10 s   < t <= 30000 s: MPE = 2000*C4 W/m^2

    Below 400 nm and above 1400 nm, Henderson Sec. 3.8 [Chaves Ch. 3:575]
    states the skin MPE is set identical to the eye's -- i.e. for UV,
    `mpe_cornea_uv`'s value applies to skin too (a different limiting
    aperture is used when deriving an AEL from it, via
    `limiting_aperture_diameter_iec60825_1(..., tissue='skin')`, but the
    MPE value itself is the same number). No separate function is needed
    for that case.

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [400, 1400).
        duration_s: Exposure duration in seconds. Must be positive and
            <= 30000 (the standard's stated upper domain).

    Returns:
        A `LimitResult` with `unit` "J/m^2" (t <= 10 s) or "W/m^2"
        (t > 10 s), `region="skin_thermal"`, `factors={"C4": ...}`.

    Raises:
        ValueError: If `wavelength_nm` is outside [400, 1400), or
            `duration_s` is not positive or exceeds 30000 s.
    """
    if not (400.0 <= wavelength_nm < 1400.0):
        raise ValueError(
            f"wavelength_nm={wavelength_nm} is outside the skin-thermal "
            "hazard's domain of [400, 1400) nm."
        )
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")
    if duration_s > 30000.0:
        raise ValueError("duration_s must be <= 30000 s (skin MPE's defined domain).")

    c4 = c4_iec60825_1(wavelength_nm)

    if duration_s < 1e-9:
        # Held at the 1 ns irradiance value ("Ultrashort pulses",
        # Chaves Ch. 3:614-616): 200*C4 J/m^2 expressed as a constant
        # irradiance by dividing by 1 ns.
        value = 200.0 * c4 * 1e9
        return LimitResult(
            value=value, unit="W/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=0.0, region="skin_thermal",
            time_regime="t < 1 ns (clamped at the 1 ns value)",
            equation="Henderson & Schulmeister table 3.6",
            factors={"C4": c4},
        )
    if duration_s <= 100e-9:
        return LimitResult(
            value=200.0 * c4, unit="J/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=0.0, region="skin_thermal",
            time_regime="1 ns <= t <= 100 ns",
            equation="Henderson & Schulmeister table 3.6",
            factors={"C4": c4},
        )
    if duration_s <= 10.0:
        value = 11000.0 * c4 * (duration_s ** 0.25)
        return LimitResult(
            value=value, unit="J/m^2", wavelength_nm=wavelength_nm,
            duration_s=duration_s, alpha_rad=0.0, region="skin_thermal",
            time_regime="100 ns < t <= 10 s",
            equation="Henderson & Schulmeister table 3.6",
            factors={"C4": c4},
        )
    return LimitResult(
        value=2000.0 * c4, unit="W/m^2", wavelength_nm=wavelength_nm,
        duration_s=duration_s, alpha_rad=0.0, region="skin_thermal",
        time_regime="10 s < t <= 30000 s",
        equation="Henderson & Schulmeister table 3.6",
        factors={"C4": c4},
    )


def _ael_from_mpe(mpe: LimitResult, region_label: str, tissue: str = 'eye') -> LimitResult:
    """AEL = MPE x limiting-aperture area, normalized to an average power.

    Henderson & Schulmeister Sec. 4.2.1 [Chaves Ch. 4:186-188]:
    `AEL_Class1_and_1M = MPE_eye x Area_limiting_aperture`. When `mpe.unit`
    is "J/m^2" (radiant exposure), the resulting energy is divided by
    `mpe.duration_s` to give an average power in watts -- exactly
    `LimitResult.as_power_W()`'s existing J-to-W conversion, reused rather
    than duplicated. When `mpe.unit` is "W/m^2", the result is already a
    power once multiplied by area.

    Args:
        tissue: 'eye' (default) or 'skin' -- selects which limiting
            aperture `limiting_aperture_diameter_iec60825_1` uses.
    """
    aperture_d = limiting_aperture_diameter_iec60825_1(
        mpe.wavelength_nm, mpe.duration_s, tissue=tissue,
    )
    area_m2 = math.pi * (aperture_d / 2.0) ** 2
    ael_unit = mpe.unit.replace('/m^2', '')
    intermediate = LimitResult(
        value=mpe.value * area_m2, unit=ael_unit,
        wavelength_nm=mpe.wavelength_nm, duration_s=mpe.duration_s,
        alpha_rad=mpe.alpha_rad, region=mpe.region, time_regime=mpe.time_regime,
        equation=mpe.equation, factors=dict(mpe.factors),
    )
    power_w = intermediate.as_power_W()
    return LimitResult(
        value=power_w, unit="W", wavelength_nm=mpe.wavelength_nm,
        duration_s=mpe.duration_s, alpha_rad=mpe.alpha_rad, region=region_label,
        time_regime=mpe.time_regime,
        equation=f"{mpe.equation}; AEL = MPE x limiting-aperture area (Sec. 4.2.1)",
        factors=dict(mpe.factors),
        notes=f"limiting aperture diameter = {aperture_d * 1000.0:.4f} mm",
    )


def ael_class_1(
    wavelength_nm: float,
    duration_s: Optional[float] = None,
    alpha_rad: float = ALPHA_MIN_IEC60825_1_RAD,
) -> LimitResult:
    """Accessible Emission Limit for Class 1 / 1M.

    `AEL = MPE_eye * Area_limiting_aperture` [Chaves Ch. 4:186-188].
    Dispatches by wavelength band, per Henderson & Schulmeister Sec. 4.2.1's
    own statement that Class 1/1M AELs are "defined for durations of up to
    30 000 s ... and for the full wavelength range considered optical
    radiation of 180 nm to 1 mm" [Chaves Ch. 4:198]:

    - `wavelength_nm < 400`: the corneal/lens UV AEL (`mpe_cornea_uv`).
    - `400 <= wavelength_nm < 1400`: the retinal-thermal AEL
      (`mpe_retinal_thermal`), taking the lower of it and the
      retinal-*photochemical* AEL (`mpe_retinal_photochemical`) whenever
      `wavelength_nm <= 600` and `duration_s > 10 s` -- per Sec. 3.12.7, an
      exposure must clear *both* hazards to be safe. Outside that window
      (as for both of Sec. 4.8's worked case studies, at 632.8 nm and
      670 nm), only the thermal hazard applies and this is identical to
      the original thermal-only behaviour.
    - `wavelength_nm >= 1400`: **not implemented** (far-IR eye MPE) --
      raises `NotImplementedError`.

    Args:
        wavelength_nm: Wavelength in nanometres, in [180, 1400).
        duration_s: Exposure/emission duration in seconds. **Default
            `None`, which resolves to the standard-mandated time base for
            this wavelength band** (Table 4.3): 30000 s for UV
            (`wavelength_nm < 400`), 100 s for visible/near-IR. C-EYE-02
            (dev_doc/architecture/contracts/C-EYE-02.md): this used to be
            a fixed `100.0` default that silently gave a ~300x-too-loose
            UV AEL unless the caller remembered to override it -- see that
            contract for the live worked example. Pass an explicit value
            to use a different duration deliberately; `None` no longer
            means "100 s," it means "the standard's own default for this
            band."
        alpha_rad: Angular subtense of the apparent source, in radians.
            Only affects the retinal-thermal branch -- UV and
            photochemical MPEs have no alpha/C6 dependence.

    Returns:
        A `LimitResult` with `unit="W"`, `region="AEL_class_1_1M"`, and
        `notes` stating which hazard governed whenever both were compared.

    Raises:
        NotImplementedError: If `wavelength_nm >= 1400` (far-IR eye MPE).
    """
    duration_s = _resolve_class1_duration(wavelength_nm, duration_s)
    if wavelength_nm < 400.0:
        return _ael_from_mpe(
            mpe_cornea_uv(wavelength_nm, duration_s), "AEL_class_1_1M",
        )
    if wavelength_nm >= 1400.0:
        raise NotImplementedError(
            "ael_class_1 does not implement the far-IR (>= 1400 nm) eye "
            "MPE/AEL chain yet."
        )

    thermal = _ael_from_mpe(
        mpe_retinal_thermal(wavelength_nm, duration_s, alpha_rad), "AEL_class_1_1M",
    )
    if not (400.0 <= wavelength_nm <= 600.0 and duration_s > 10.0):
        return thermal

    photochemical = _ael_from_mpe(
        mpe_retinal_photochemical(wavelength_nm, duration_s), "AEL_class_1_1M",
    )
    governing = thermal if thermal.value <= photochemical.value else photochemical
    governing_hazard = "retinal_thermal" if governing is thermal else "retinal_photochemical"
    governing.notes = (
        f"governing hazard: {governing_hazard} "
        f"(thermal={thermal.value * 1e3:.5f} mW, "
        f"photochemical={photochemical.value * 1e3:.5f} mW); {governing.notes}"
    )
    return governing


def ael_class_2(
    wavelength_nm: float,
    alpha_rad: float = ALPHA_MIN_IEC60825_1_RAD,
) -> LimitResult:
    """Accessible Emission Limit for Class 2 / 2M, retinal-thermal hazard.

    Visible wavelengths only, fixed 0.25 s time base [Table 4.3,
    Chaves Ch. 4:227-236] -- computed identically to `ael_class_1` but
    at that fixed duration.

    Args:
        wavelength_nm: Wavelength in nanometres. Must be in [400, 700).
        alpha_rad: Angular subtense of the apparent source, in radians.

    Returns:
        A `LimitResult` with `unit="W"`, `region="AEL_class_2_2M"`.

    Raises:
        ValueError: If `wavelength_nm` is outside [400, 700).
    """
    if not (400.0 <= wavelength_nm < 700.0):
        raise ValueError(
            f"wavelength_nm={wavelength_nm} is outside Class 2/2M's visible "
            "range of [400, 700) nm."
        )
    mpe = mpe_retinal_thermal(wavelength_nm, 0.25, alpha_rad)
    return _ael_from_mpe(mpe, "AEL_class_2_2M")


def ael_class_3r(
    wavelength_nm: float,
    duration_s: Optional[float] = None,
    alpha_rad: float = ALPHA_MIN_IEC60825_1_RAD,
) -> LimitResult:
    """Accessible Emission Limit for Class 3R.

    Henderson & Schulmeister Sec. 4.2.1 [Chaves Ch. 4:202]: "The AEL of
    Class 3R in the visible wavelength region is five times the AEL of
    Class 2 and 2M ... and outside the visible region equals five times
    the AEL of Class 1 and 1M." The non-visible branch calls `ael_class_1`,
    which as of the UV addition above also covers `wavelength_nm < 400`.

    Args:
        wavelength_nm: Wavelength in nanometres, in [180, 1400).
        duration_s: Exposure/emission duration in seconds, used only for
            the non-visible (Class 1/1M-based) branch. **Default `None`**,
            passed straight through to `ael_class_1`, which resolves it to
            the correct standard-mandated time base for the wavelength band
            (C-EYE-02) -- see that function's own docstring.
        alpha_rad: Angular subtense of the apparent source, in radians.

    Returns:
        A `LimitResult` with `unit="W"`, `region="AEL_class_3R"`.
    """
    if 400.0 <= wavelength_nm < 700.0:
        base = ael_class_2(wavelength_nm, alpha_rad)
    else:
        base = ael_class_1(wavelength_nm, duration_s, alpha_rad)
    return LimitResult(
        value=5.0 * base.value, unit="W", wavelength_nm=wavelength_nm,
        duration_s=base.duration_s, alpha_rad=alpha_rad, region="AEL_class_3R",
        time_regime=base.time_regime,
        equation=f"5 x ({base.equation})",
        factors=dict(base.factors),
        notes="Class 3R = 5x the relevant Class 1/1M or 2/2M AEL (Sec. 4.2.1).",
    )


def ael_skin(wavelength_nm: float, duration_s: float) -> LimitResult:
    """Skin exposure limit (skin MPE x the skin limiting aperture).

    Not one of the numbered laser safety classes -- skin exposure is
    evaluated as its own pass/fail check, orthogonal to the eye's
    Class 1/1M/2/2M/3R hierarchy (Henderson & Schulmeister's classification
    discussion in chapter 4 is built entirely around ocular hazards; skin
    only enters as a separate consideration, e.g. for Class 3B/4
    products). Dispatches by wavelength: below 400 nm, skin MPE is
    identical to the corneal UV MPE (`mpe_cornea_uv`, Sec. 3.8); from 400
    to 1400 nm, the skin's own distinct thermal formula
    (`mpe_skin_thermal`) applies. Above 1400 nm: **not implemented**
    (far-IR skin MPE) -- raises `NotImplementedError`.

    Args:
        wavelength_nm: Wavelength in nanometres, in [180, 1400).
        duration_s: Exposure duration in seconds.

    Returns:
        A `LimitResult` with `unit="W"`, `region` either "AEL_skin" (for
        consistency with the eye AEL functions' naming).

    Raises:
        NotImplementedError: If `wavelength_nm >= 1400` (far-IR skin MPE).
    """
    if wavelength_nm < 400.0:
        mpe = mpe_cornea_uv(wavelength_nm, duration_s)
    elif wavelength_nm < 1400.0:
        mpe = mpe_skin_thermal(wavelength_nm, duration_s)
    else:
        raise NotImplementedError(
            "ael_skin does not implement the far-IR (>= 1400 nm) skin MPE "
            "chain yet."
        )
    return _ael_from_mpe(mpe, "AEL_skin", tissue='skin')


def classify_measurement(
    measured_power_W: float,
    wavelength_nm: float,
    alpha_rad: float = ALPHA_MIN_IEC60825_1_RAD,
    duration_s_class1: Optional[float] = None,
) -> str:
    """Classify ONE already-measured accessible-emission value.

    Compares `measured_power_W` against the AELs in ascending order,
    following Henderson & Schulmeister table 4.4's logic
    [Chaves Ch. 4:311-336]. This answers "which class's retinal-thermal
    AEL does this measured power fall under," not "what is this product's
    overall IEC 60825-1 class" -- the latter additionally requires
    combining results from multiple measurement conditions (naked eye / eye
    loupe / telescope, each at its own aperture and distance from the
    apparent source) to arrive at a plain-vs-"M" designation, which needs
    the physical measurement geometry this function does not take as input.
    See dev_doc/architecture/components/eye_safety.md for how the
    two Sec. 4.8 case studies combine per-condition results by hand.

    Args:
        measured_power_W: Accessible-emission power measured through the
            appropriate aperture for one specific measurement condition, in
            watts. Must be non-negative.
        wavelength_nm: Wavelength in nanometres, in [180, 1400) -- the full
            domain `ael_class_1` supports, including UV.
        alpha_rad: Angular subtense of the apparent source at the
            measurement position, in radians.
        duration_s_class1: Time base to use for the Class 1/1M (and, for
            non-visible wavelengths, Class 3R) comparison. **Default
            `None`**, passed straight through to `ael_class_1`/
            `ael_class_3r`, which resolve it to the correct
            standard-mandated time base for the wavelength band (C-EYE-02)
            -- previously a fixed `100.0` default here silently produced a
            ~300x-too-permissive classification for UV wavelengths unless
            the caller explicitly overrode it.

    Returns:
        One of "Class 1 or 1M", "Class 2 or 2M", "Class 3R", or
        "above Class 3R (3B or 4)".

    Raises:
        ValueError: If `measured_power_W` is negative.
    """
    if measured_power_W < 0.0:
        raise ValueError("measured_power_W must be non-negative.")

    ael1 = ael_class_1(wavelength_nm, duration_s_class1, alpha_rad)
    if measured_power_W <= ael1.value:
        return "Class 1 or 1M"

    if 400.0 <= wavelength_nm < 700.0:
        ael2 = ael_class_2(wavelength_nm, alpha_rad)
        if measured_power_W <= ael2.value:
            return "Class 2 or 2M"

    ael3r = ael_class_3r(wavelength_nm, duration_s_class1, alpha_rad)
    if measured_power_W <= ael3r.value:
        return "Class 3R"

    return "above Class 3R (3B or 4)"
