"""
Python-specific module: IEC 62471 broadband (lamp/LED) exposure limits and risk-group classification (Eye safety framework)

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
PYTHON-SPECIFIC MODULE: IEC 62471 exposure limits / risk-group classification
===============================================================================
Six hazard chains (Directive 2006/25/EC Annex I indices in parentheses,
IEC 62471 equation numbers alongside), all transcribed and cross-checked
against Annex I to that Directive as reproduced in the Commission's 2010
non-binding guide to good practice for implementing it.
[KD9: the standards texts these limits come from are read privately; the
code cites the standard, never the transcription.]

- **Actinic UV** (a), 180-400 nm, S(lambda)-weighted. `mpe_actinic_uv`.
- **Near-UV / UVA** (b), 315-400 nm, unweighted. `mpe_near_uv`.
- **Blue light** (c-f), 300-700 nm, B(lambda)-weighted. Dispatches on
  angular subtense at the 11 mrad large/small-source boundary the
  Directive itself specifies: radiance-based for alpha>=11mrad,
  irradiance-based for alpha<11mrad. `mpe_blue_light`.
- **Retinal thermal** (g,h and, separately, j,k), 380-1400 nm (combined
  visible+IRA) or 780-1400 nm (IRA-only, when a source has no visible
  content), R(lambda)-weighted. `mpe_retinal_thermal`,
  `mpe_retinal_thermal_ira`.
- **IR (cornea/lens)** (m,n), 780-3000 nm, unweighted. `mpe_ir_eye`.
- **Skin thermal** (o), 380-3000 nm, unweighted. `mpe_skin_thermal`.

Then `classify_measurement`: Exempt / RG1 / RG2 / RG3, per the duration
thresholds in the Directive's guide Sec. 8.1.2
[Directive 2006/25/EC guide].

**C-EYE-04** (dev_doc/architecture/contracts/C-EYE-04.md): this module's
public names deliberately mirror `iec60825_1.py`'s (`mpe_retinal_thermal`,
`mpe_skin_thermal`, `classify_measurement`) for the *same hazard concept*
under a *different standard* with different formulas, bands, and angular
conventions. Neither module's functions are flattened into this package's
top-level namespace -- callers must write `iec62471.mpe_retinal_thermal(...)`
or `iec60825_1.mpe_retinal_thermal(...)`, explicitly, at every call site.
(This was briefly asymmetric -- only the laser standard's functions were
flattened -- which left the *bare* name silently resolving to the laser standard by
default; symmetrized once pointed out, since a privileged bare name for
either standard is itself the footgun, not just an asymmetry. [KC6: the
easiest-to-type name is a default whether or not anyone chose it.]) This is
deliberate, not an oversight: it is the concrete enforcement mechanism for
C-EYE-04's guarantee (no accidental cross-standard name collision, and no
accidental wrong-standard default, via a flat import), decided at
implementation time rather than left as a prose-only warning.

**What is deliberately not implemented -- an honest, narrower-than-the-
full-standard first pass, with each gap named [KC5: in a safety library an
unnamed gap reads as a pass]:**

- Retinal-thermal pulses shorter than 10 microseconds (bracket (i)/(l), the
  standard's ultrashort-pulse regime) -- irrelevant to the continuous
  LED/lamp sources this project models, mirrors `iec60825_1.py`'s own
  `_MIN_SUPPORTED_DURATION_S` scoping.
- `mpe_retinal_thermal_ira`'s short-pulse bracket (k): the source table's
  OCR extraction for this cell is ambiguous and could not be resolved by
  the continuity check that successfully resolved the equivalent
  combined-band bracket (h) -- see that function's docstring. Only the
  long-duration branch (j, t>10s) is implemented; `mpe_retinal_thermal_ira`
  is also not wired into `classify_measurement` (which uses the combined-
  band `mpe_retinal_thermal` only, matching how the Directive's own
  Sec. 8.1.2 risk-group criteria name a single generic "Retinal Thermal
  hazard," not an IRA-specific variant).
- The "IR hazard without a strong visual stimulus" sixth Exempt/RG1/RG2
  criterion (Sec. 8.1.2): this requires a judgement about whether a
  source's visible content is strong enough to trigger aversion, not a
  pure radiometric threshold with its own Annex I formula -- not modelled.
- `mpe_skin_thermal` beyond its single stated bracket (t<=10 s) -- the
  source table gives no separate longer-duration branch for skin, unlike
  every eye hazard here.

**A correction (`C-EYE-06`), found while adding dimensional checks to the
inputs, not while working on this module directly** [KD4: making the
comparison print itself is what exposed it]:
`classify_measurement`'s retinal-thermal risk-group comparison used to
look up a "reference duration" the same way it does for every other
hazard and call `mpe_retinal_thermal(duration, alpha)` directly --
comparing the caller's single continuous-radiance measurement against
three *different kinds* of quantity across the three risk groups (a
radiant exposure, J/(m^2*sr), at Exempt's and RG2's short-branch
durations; a radiance, W/(m^2*sr), only at RG1's). Worse, RG1's own
"100 s reference duration" had no basis in either primary source: the
Directive guide's Sec. 8.1.2 (the Directive 2006/25/EC guide)
lists no Retinal Thermal criterion for RG1 at all, and IEC 62471's own
Table 6.1 (IEC 62471) resolves the resulting
ambiguity unambiguously -- RG1's limit is *the same as Exempt's*, not
absent, not a separately-invented one. Fixed against Table 6.1 directly;
see `_retinal_thermal_classification_limit_w_m2_sr`'s own docstring for
the full derivation. No existing worked-example test's classification
outcome changed (every one of them was Exempt by a wide margin on every
hazard, so which mismatched unit got compared never flipped the answer)
-- this was a real, unexercised gap, not one any prior test could have
caught, precisely the failure mode dimensional checking exists to catch.
===============================================================================
"""

from __future__ import annotations

from typing import Optional

from .angular_subtense import ALPHA_MAX_RAD, ALPHA_MIN_IEC62471_RAD, clip_alpha
from .result import LimitResult

#: Blue-light large/small-source boundary, Directive Annex I indices (c)-(f)
#: [Directive 2006/25/EC guide]. Coincides with `alpha_eff_iec62471`'s
#: own 0.011 rad breakpoint (exposure_duration.py) -- not a coincidence, both
#: derive from the same IEC 62471 Sec. 4.2 geometry, but kept as its own
#: named constant here since the two functions serve different equations.
_ALPHA_BLUE_LIGHT_BOUNDARY_RAD: float = 0.011

#: Public alias of the above, for external callers that need to know which
#: dimensionality `mpe_blue_light`/`classify_measurement`'s `blue_light_value`
#: expects at a given alpha (radiance above this boundary, irradiance below)
#: without duplicating the constant -- see
#: `eye_safety_classification_flow/dimensional_checks.py`.
ALPHA_BLUE_LIGHT_BOUNDARY_RAD: float = _ALPHA_BLUE_LIGHT_BOUNDARY_RAD

#: Retinal-thermal (IRA-only) C_alpha lower bound, Directive Annex I index
#: (j) [Directive 2006/25/EC guide] -- distinct from the combined-band
#: (g)/(h) bound, which is IEC 62471's usual ALPHA_MIN_IEC62471_RAD (1.7 mrad).
_ALPHA_MIN_IRA_RETINAL_THERMAL_RAD: float = 0.011

#: Below this duration, `mpe_retinal_thermal`/`mpe_retinal_thermal_ira` do
#: not cascade into the ultrashort-pulse bracket -- see module docstring.
_MIN_SUPPORTED_RETINAL_THERMAL_DURATION_S: float = 10e-6

#: Sentinel for LimitResult.wavelength_nm on every function in this module:
#: none of these hazards are evaluated at a single wavelength -- each is
#: already a spectrally-weighted sum over its own band. 0.0 is not a valid
#: physical wavelength, making this unambiguous at a glance.
_BROADBAND_WAVELENGTH_SENTINEL: float = 0.0

#: Reference exposure durations per risk group, Directive guide Sec. 8.1.2
#: [Directive 2006/25/EC guide]. Order matters: `classify_measurement`
#: checks ascending severity and returns the first group whose criteria all
#: pass, mirroring `iec60825_1.classify_measurement`'s dispatch shape.
#: `retinal_thermal` is deliberately absent from every group here -- unlike
#: every other hazard, it is not a duration lookup at all. See
#: `_retinal_thermal_classification_limit_w_m2_sr` and the correction note
#: on `classify_measurement` below (`C-EYE-06`; fixed against IEC 62471's
#: own Table 6.1, not just this Directive guide's paraphrase of it).
_RISK_GROUP_DURATIONS_S = {
    'Exempt': {'uv': 28800.0, 'near_uv': 1000.0, 'blue': 10000.0, 'ir': 1000.0},
    'RG1': {'uv': 10000.0, 'near_uv': 300.0, 'blue': 100.0, 'ir': 100.0},
    'RG2': {'uv': 1000.0, 'near_uv': 100.0, 'blue': 0.25, 'ir': 10.0},
}


def _retinal_thermal_classification_limit_w_m2_sr(group: str, alpha_rad: float) -> float:
    """Retinal-thermal risk-group classification limit, W/(m^2*sr).

    **Correction (`C-EYE-06`), fixed against the authoritative primary
    source rather than this module's own prior (incorrect) approach**
    [KD5: the standard's own table is the judge, not this module's
    earlier understanding of it]. `classify_measurement`
    used to look up a "reference duration" for `retinal_thermal` the same
    way it does for every other hazard (`_RISK_GROUP_DURATIONS_S`) and
    call `mpe_retinal_thermal(duration, alpha)` directly. That is wrong in
    two ways, both traced to the authoritative primary source, IEC 62471's
    own Table 6.1 "Emission limits for risk groups of continuous wave
    lamps" (IEC 62471), not just this Directive
    guide's Sec. 8.1.2 paraphrase of it (the Directive 2006/25/EC guide), which omits Retinal Thermal from Risk Group 1's own
    criteria list entirely -- ambiguous on its own about whether that
    means "no limit at RG1" or "same limit as Exempt"; Table 6.1 resolves
    it unambiguously:

    | Risk group | `L_R` limit, Table 6.1 | = `2.8e7`-style constant |
    |---|---|---|
    | Exempt | `28000 / alpha_rad` | `2.8e7 / alpha_mrad` |
    | RG1    | `28000 / alpha_rad` (**same as Exempt**) | `2.8e7 / alpha_mrad` |
    | RG2    | `71000 / alpha_rad` | `7.1e7 / alpha_mrad` |

    All three are stated in the table's own Units column as
    `W . m^-2 . sr^-1` (radiance) -- confirmed against
    `mpe_retinal_thermal`'s own two branches directly [verified]:

    1. `mpe_retinal_thermal(t, alpha)` for any `t > 10 s` (the "long
       branch") does not depend on `t` at all -- `value = 2.8e7 /
       C_alpha_mrad`, exactly Table 6.1's Exempt/RG1 constant. The old
       code evaluated Exempt at `duration_s = 10.0` -- since the branch
       condition is the *strict* `duration_s > 10.0`, this landed in the
       *short* branch instead (`unit = "J/(m^2*sr)"`, a radiant exposure,
       not a radiance), silently comparing a caller-supplied continuous
       radiance against the wrong *kind* of quantity. RG1's old lookup
       (`100.0` s) happened to land in the correct long branch by
       accident, but was still framed as "RG1's own reference duration"
       rather than "the same limit as Exempt, because Table 6.1 says so."
    2. `mpe_retinal_thermal(0.25, alpha)` (the "short branch", RG2's own
       duration) returns a numeric value matching Table 6.1's RG2 constant
       to within the same <1% rounding tolerance this module's docstring
       already documents for the standard's own published constants
       elsewhere -- but its `unit` field, `"J/(m^2*sr)"`, is correct for
       that function's own general-purpose, duration-dependent MPE role
       (Sec. 4.3.5/Eq. 4.9), not for this classification use, where
       Table 6.1 states the units column as `W . m^-2 . sr^-1` throughout.
       The *number* is reused here (not re-derived independently, so this
       function cannot drift out of sync with `mpe_retinal_thermal`'s own
       formula), reinterpreted as an equivalent continuous-wave radiance
       for classification purposes only, per Table 6.1's own convention.

    Args:
        group: One of `"Exempt"`, `"RG1"`, `"RG2"`.
        alpha_rad: Angular subtense of the apparent source, in radians.

    Returns:
        The classification limit, W/(m^2*sr).

    Raises:
        ValueError: If `group` is not one of the three above.
    """
    return retinal_thermal_classification_limit(group, alpha_rad).value


def retinal_thermal_classification_limit(group: str, alpha_rad: float) -> LimitResult:
    """Public, `LimitResult`-returning equivalent of
    `_retinal_thermal_classification_limit_w_m2_sr`, added for the
    per-risk-group comparison-explanation states -- which need the same
    citation/equation/time_regime provenance every other hazard's
    `mpe_*` function already carries, not just the bare float
    `classify_measurement` uses internally. Calls the exact same
    `mpe_retinal_thermal` invocations that float-only function does (see
    its own docstring for the full derivation against IEC 62471's Table
    6.1) -- a single source of truth for which duration proxy each group
    maps to, not a second, independently-maintained one.

    Args:
        group: One of `"Exempt"`, `"RG1"`, `"RG2"`.
        alpha_rad: Angular subtense of the apparent source, in radians.

    Returns:
        A `LimitResult` with `unit="W/(m^2*sr)"` in every case, per Table
        6.1 -- **found while building the comparison-explanation layer,
        not while writing this function originally** [KD4: a wrong unit
        beside a right number is invisible until something prints both]: `mpe_
        retinal_thermal(0.25, alpha_rad)`'s own `LimitResult` (RG2's
        duration proxy) carries `unit="J/(m^2*sr)"` (a radiant exposure,
        that function's own general-purpose short-pulse branch), which is
        exactly correct for `mpe_retinal_thermal` itself but would render
        a visibly wrong-looking comparison once surfaced in an explanation
        (`"0.255 W/(m^2*sr) <= 707107 J/(m^2*sr)"`) -- mismatched units
        that are only numerically compatible because of the classification
        reinterpretation documented above. RG2's `LimitResult` is
        relabelled here, once, so every caller of this function (not just
        `classify_measurement`'s float-only internal use) sees the unit
        Table 6.1 actually states (`W . m^-2 . sr^-1`), not the donor
        function's own general-purpose unit.

    Raises:
        ValueError: If `group` is not one of the three above.
    """
    if group in ("Exempt", "RG1"):
        return mpe_retinal_thermal(100.0, alpha_rad)  # long branch; already W/(m^2*sr), duration-independent for any t > 10 s
    if group == "RG2":
        short_branch = mpe_retinal_thermal(0.25, alpha_rad)  # J/(m^2*sr) -- correct for mpe_retinal_thermal, not for Table 6.1's own units column
        return LimitResult(
            value=short_branch.value,
            unit="W/(m^2*sr)",
            wavelength_nm=short_branch.wavelength_nm,
            duration_s=short_branch.duration_s,
            alpha_rad=alpha_rad,
            region="retinal_thermal",
            time_regime="RG2 classification (0.25 s aversion response)",
            equation=f"{short_branch.equation}; value reused as an "
                     f"equivalent CW radiance per IEC 62471 Table 6.1",
            factors=dict(short_branch.factors),
            notes="Numeric value from mpe_retinal_thermal's t<=10s (radiant exposure) branch, "
                  "relabelled W/(m^2*sr) -- Table 6.1 states all three risk groups' retinal-thermal "
                  "limits are radiance-typed, never a dose.",
        )
    raise ValueError(f"Unknown risk group: {group!r}")


def risk_group_reference_duration_s(group: str, hazard: str) -> float:
    """Public read access to `_RISK_GROUP_DURATIONS_S`, for the
    per-group comparison-explanation states in `eye_safety_classification_
    flow`, which need to recompute the exact same per-group limit
    `classify_measurement` uses internally -- purely for observability,
    never a second source of truth for what the reference duration *is*.

    Args:
        group: One of `"Exempt"`, `"RG1"`, `"RG2"`.
        hazard: One of `"uv"`, `"near_uv"`, `"blue"`, `"ir"` --
            `retinal_thermal` has no entry here (it is not a duration
            lookup at all, see `retinal_thermal_classification_limit`).

    Raises:
        KeyError: If `group`/`hazard` is not one of the above.
    """
    return _RISK_GROUP_DURATIONS_S[group][hazard]

#: Daily reference duration (8 hours), the fixed basis for the actinic-UV
#: and near-UV "daily value" limits (a)/(b) -- there is no shorter-duration
#: branch for these two hazards in Annex I, unlike every other hazard here.
_DAILY_REFERENCE_DURATION_S: float = 28800.0


def mpe_actinic_uv(duration_s: float) -> LimitResult:
    """Actinic UV (S(lambda)-weighted) exposure limit, 180-400 nm.

    Directive 2006/25/EC Annex I index (a) / IEC 62471 Eq. 4.1
    [Directive 2006/25/EC guide]: `H_eff = 30 J/m^2`, a fixed daily
    (8 hour) value -- not a function of exposure duration the way every
    other hazard in this module is. Expressed here as an equivalent
    effective-irradiance limit for a given assumed continuous exposure
    duration up to the 8 h reference: `E_eff = 30 / duration_s`.

    Args:
        duration_s: Assumed continuous exposure duration, in seconds.
            Must be in (0, 28800] (8 hours) -- the standard's own
            reference period; it states no limit for a shorter or longer
            single continuous exposure, only the daily total.

    Returns:
        LimitResult with `value` = the effective-irradiance limit in
        W/m^2, `unit` = "W/m^2".

    Raises:
        ValueError: If `duration_s` is not in (0, 28800].
    """
    if not (0.0 < duration_s <= _DAILY_REFERENCE_DURATION_S):
        raise ValueError(
            f"mpe_actinic_uv is defined for 0 < duration_s <= {_DAILY_REFERENCE_DURATION_S} "
            f"s (the standard's 8-hour daily reference); got {duration_s}."
        )
    return LimitResult(
        value=30.0 / duration_s,
        unit="W/m^2",
        wavelength_nm=_BROADBAND_WAVELENGTH_SENTINEL,
        duration_s=duration_s,
        alpha_rad=0.0,
        region="actinic_uv",
        time_regime="daily (8 h reference)",
        equation="Directive 2006/25/EC Annex I (a) / IEC 62471 Eq. 4.1",
        factors={},
        notes="S(lambda)-weighted effective irradiance, 180-400 nm.",
    )


def mpe_near_uv(duration_s: float) -> LimitResult:
    """Near-UV (UVA) exposure limit, 315-400 nm, unweighted.

    Directive Annex I index (b) / IEC 62471 Eq. 4.3
    [Directive 2006/25/EC guide]: `H_UVA = 10^4 J/m^2`, a fixed daily
    (8 hour) value, same shape as `mpe_actinic_uv`.

    Args:
        duration_s: Assumed continuous exposure duration, in seconds.
            Must be in (0, 28800].

    Returns:
        LimitResult with `value` = the irradiance limit in W/m^2.

    Raises:
        ValueError: If `duration_s` is not in (0, 28800].
    """
    if not (0.0 < duration_s <= _DAILY_REFERENCE_DURATION_S):
        raise ValueError(
            f"mpe_near_uv is defined for 0 < duration_s <= {_DAILY_REFERENCE_DURATION_S} "
            f"s (the standard's 8-hour daily reference); got {duration_s}."
        )
    return LimitResult(
        value=1.0e4 / duration_s,
        unit="W/m^2",
        wavelength_nm=_BROADBAND_WAVELENGTH_SENTINEL,
        duration_s=duration_s,
        alpha_rad=0.0,
        region="near_uv",
        time_regime="daily (8 h reference)",
        equation="Directive 2006/25/EC Annex I (b) / IEC 62471 Eq. 4.3",
        factors={},
        notes="Unweighted irradiance, 315-400 nm.",
    )


def mpe_blue_light(duration_s: float, alpha_rad: float) -> LimitResult:
    """Blue-light (photochemical retinal) exposure limit, 300-700 nm,
    B(lambda)-weighted.

    Directive Annex I indices (c)-(f) / IEC 62471 Eq. 4.5/4.7
    [Directive 2006/25/EC guide]. Dispatches on `alpha_rad` at the
    standard's own 11 mrad large/small-source boundary:

    - `alpha_rad >= 0.011` (large source, index c/d): radiance limit
      `L_B = 1e6/duration_s` W/(m^2*sr) for `duration_s <= 10000 s`, else
      `100` W/(m^2*sr).
    - `alpha_rad < 0.011` (small source, index e/f): irradiance limit
      `E_B = 100/duration_s` W/m^2 for `duration_s <= 10000 s`, else
      `0.01` W/m^2.

    Args:
        duration_s: Exposure duration, in seconds. Must be positive.
        alpha_rad: Angular subtense of the apparent source, in radians.
            Must be non-negative.

    Returns:
        LimitResult with `value` in W/(m^2*sr) (large source) or W/m^2
        (small source) -- check `unit` before comparing a measured value.

    Raises:
        ValueError: If `duration_s` is not positive or `alpha_rad` is
            negative.
    """
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")
    if alpha_rad < 0.0:
        raise ValueError("alpha_rad must be non-negative.")

    large_source = alpha_rad >= _ALPHA_BLUE_LIGHT_BOUNDARY_RAD
    if large_source:
        value = 1.0e6 / duration_s if duration_s <= 10000.0 else 100.0
        unit = "W/(m^2*sr)"
        region_note = "large source (alpha >= 11 mrad): radiance limit L_B"
    else:
        value = 100.0 / duration_s if duration_s <= 10000.0 else 0.01
        unit = "W/m^2"
        region_note = "small source (alpha < 11 mrad): irradiance limit E_B"

    return LimitResult(
        value=value,
        unit=unit,
        wavelength_nm=_BROADBAND_WAVELENGTH_SENTINEL,
        duration_s=duration_s,
        alpha_rad=alpha_rad,
        region="blue_light",
        time_regime="t <= 10000 s" if duration_s <= 10000.0 else "t > 10000 s",
        equation=(
            "Directive 2006/25/EC Annex I (c)/(d) / IEC 62471 Eq. 4.5"
            if large_source else
            "Directive 2006/25/EC Annex I (e)/(f) / IEC 62471 Eq. 4.7"
        ),
        factors={},
        notes=f"B(lambda)-weighted, 300-700 nm. {region_note}.",
    )


def mpe_retinal_thermal(duration_s: float, alpha_rad: float) -> LimitResult:
    """Retinal-thermal exposure limit, 380-1400 nm (visible + IRA combined),
    R(lambda)-weighted.

    Directive Annex I indices (g)/(h) / IEC 62471 Eq. 4.9
    [Directive 2006/25/EC guide]:

        C_alpha = clip(alpha_mrad, 1.7, 100)                    [mrad]
        L_R = 2.8e7 / C_alpha                    for t > 10 s
        L_R = 5e7 / (C_alpha * t^0.25)           for 10 us <= t <= 10 s

    The second bracket's exponent is transcribed as `t^0.25` despite the
    source table's OCR extraction reading "e^{0.25}" -- resolved by
    continuity, not assumed: at t=10 s the first bracket gives
    `2.8e7/C_alpha`, and `5e7/(C_alpha * 10^0.25) = 2.81e7/C_alpha`, a
    <1% difference consistent with the standard's own rounding of its
    published constants (the same resolution method
    `iec60825_1.py`'s module docstring already used for an equivalent
    OCR ambiguity in a different standard's table).

    Args:
        duration_s: Exposure duration, in seconds. Must be
            >= 10 microseconds (see module docstring -- ultrashort pulses
            are not implemented).
        alpha_rad: Angular subtense of the apparent source, in radians.

    Returns:
        LimitResult with `value` in W/(m^2*sr) (t>10s) or J/(m^2*sr)
        (10us<=t<=10s, a radiant exposure, not an irradiance) -- check
        `unit`.

    Raises:
        ValueError: If `duration_s` is below 10 microseconds.
    """
    if duration_s < _MIN_SUPPORTED_RETINAL_THERMAL_DURATION_S:
        raise ValueError(
            f"mpe_retinal_thermal does not implement pulses shorter than "
            f"{_MIN_SUPPORTED_RETINAL_THERMAL_DURATION_S} s (see module "
            f"docstring); got duration_s={duration_s}."
        )

    c_alpha_mrad = clip_alpha(alpha_rad, ALPHA_MIN_IEC62471_RAD, ALPHA_MAX_RAD) * 1000.0

    if duration_s > 10.0:
        value = 2.8e7 / c_alpha_mrad
        unit = "W/(m^2*sr)"
        time_regime = "t > 10 s"
        equation = "Directive 2006/25/EC Annex I (g) / IEC 62471 Eq. 4.9"
    else:
        value = 5.0e7 / (c_alpha_mrad * (duration_s ** 0.25))
        unit = "J/(m^2*sr)"
        time_regime = "10 us <= t <= 10 s"
        equation = "Directive 2006/25/EC Annex I (h) / IEC 62471 Eq. 4.9"

    return LimitResult(
        value=value,
        unit=unit,
        wavelength_nm=_BROADBAND_WAVELENGTH_SENTINEL,
        duration_s=duration_s,
        alpha_rad=alpha_rad,
        region="retinal_thermal",
        time_regime=time_regime,
        equation=equation,
        factors={"C_alpha_mrad": c_alpha_mrad},
        notes="R(lambda)-weighted, 380-1400 nm (visible + IRA combined).",
    )


def mpe_retinal_thermal_ira(duration_s: float, alpha_rad: float) -> LimitResult:
    """Retinal-thermal exposure limit, 780-1400 nm (IRA only, no visible
    content -- a narrower alternative to `mpe_retinal_thermal` for sources
    with no visible emission), R(lambda)-weighted.

    Directive Annex I index (j) / IEC 62471 Eq. 4.10
    [Directive 2006/25/EC guide]:

        C_alpha = clip(alpha_mrad, 11, 100)                     [mrad]
        L_R = 6e6 / C_alpha                      for t > 10 s

    **Only the t > 10 s bracket is implemented.** The source table's
    short-pulse bracket (index k, 10us<=t<=10s) is transcribed identically
    to `mpe_retinal_thermal`'s own short-pulse bracket (h) in the raw OCR
    extraction, which cannot be correct: unlike (g)/(h), which agree to
    <1% at their t=10s boundary (confirming (h)'s transcription), applying
    (h)'s exact formula to (j)/(k) would be discontinuous at t=10s by a
    factor of ~4.7 (2.8e7/C_alpha vs 6e6/C_alpha). This means (k)'s
    source-table cell is genuinely ambiguous, not merely differently
    formatted -- transcribing a guessed correction would be worse than
    leaving the gap explicit. Not wired into `classify_measurement`
    (which uses the combined-band `mpe_retinal_thermal` instead, matching
    the Directive guide's own Sec. 8.1.2 criteria, which name a single
    generic "Retinal Thermal hazard").

    Args:
        duration_s: Exposure duration, in seconds. Must be > 10 s.
        alpha_rad: Angular subtense of the apparent source, in radians.

    Returns:
        LimitResult with `value` in W/(m^2*sr).

    Raises:
        ValueError: If `duration_s` is not greater than 10 s.
    """
    if duration_s <= 10.0:
        raise ValueError(
            "mpe_retinal_thermal_ira only implements the t > 10 s bracket "
            "(index (j)) -- the short-pulse bracket (k) is not transcribed "
            "due to a genuine source-table ambiguity; see the function "
            "docstring."
        )

    c_alpha_mrad = clip_alpha(alpha_rad, _ALPHA_MIN_IRA_RETINAL_THERMAL_RAD, ALPHA_MAX_RAD) * 1000.0
    return LimitResult(
        value=6.0e6 / c_alpha_mrad,
        unit="W/(m^2*sr)",
        wavelength_nm=_BROADBAND_WAVELENGTH_SENTINEL,
        duration_s=duration_s,
        alpha_rad=alpha_rad,
        region="retinal_thermal_ira",
        time_regime="t > 10 s",
        equation="Directive 2006/25/EC Annex I (j) / IEC 62471 Eq. 4.10",
        factors={"C_alpha_mrad": c_alpha_mrad},
        notes="R(lambda)-weighted, 780-1400 nm (IRA only, no visible content).",
    )


def mpe_ir_eye(duration_s: float) -> LimitResult:
    """Infrared (cornea/lens) exposure limit, 780-3000 nm, unweighted.

    Directive Annex I indices (m)/(n) / IEC 62471 Eq. 4.11
    [Directive 2006/25/EC guide]:

        E_IR = 18000 * duration_s^-0.75         for duration_s <= 1000 s
        E_IR = 100                              for duration_s > 1000 s

    Args:
        duration_s: Exposure duration, in seconds. Must be positive.

    Returns:
        LimitResult with `value` in W/m^2.

    Raises:
        ValueError: If `duration_s` is not positive.
    """
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive.")

    if duration_s <= 1000.0:
        value = 18000.0 * (duration_s ** -0.75)
        time_regime = "t <= 1000 s"
        equation = "Directive 2006/25/EC Annex I (m) / IEC 62471 Eq. 4.11"
    else:
        value = 100.0
        time_regime = "t > 1000 s"
        equation = "Directive 2006/25/EC Annex I (n) / IEC 62471 Eq. 4.11"

    return LimitResult(
        value=value,
        unit="W/m^2",
        wavelength_nm=_BROADBAND_WAVELENGTH_SENTINEL,
        duration_s=duration_s,
        alpha_rad=0.0,
        region="ir_eye",
        time_regime=time_regime,
        equation=equation,
        factors={},
        notes="Unweighted irradiance, 780-3000 nm (cornea/lens, corneal burn / cataractogenesis).",
    )


def mpe_skin_thermal(duration_s: float) -> LimitResult:
    """Skin-thermal exposure limit, 380-3000 nm, unweighted.

    Directive Annex I index (o) / IEC 62471 Eq. 4.12
    [Directive 2006/25/EC guide]: `H_skin = 20000 * duration_s^0.25`
    J/m^2, for `duration_s <= 10 s` only -- the source table gives no
    separate longer-duration branch for skin (unlike every eye hazard in
    this module).

    Args:
        duration_s: Exposure duration, in seconds. Must be in (0, 10].

    Returns:
        LimitResult with `value` in J/m^2.

    Raises:
        ValueError: If `duration_s` is not in (0, 10].
    """
    if not (0.0 < duration_s <= 10.0):
        raise ValueError(
            f"mpe_skin_thermal is defined for 0 < duration_s <= 10 s only "
            f"(no longer-duration branch is given in the source table); "
            f"got {duration_s}."
        )
    return LimitResult(
        value=20000.0 * (duration_s ** 0.25),
        unit="J/m^2",
        wavelength_nm=_BROADBAND_WAVELENGTH_SENTINEL,
        duration_s=duration_s,
        alpha_rad=0.0,
        region="skin_thermal",
        time_regime="t <= 10 s",
        equation="Directive 2006/25/EC Annex I (o) / IEC 62471 Eq. 4.12",
        factors={},
        notes="Unweighted radiant exposure, 380-3000 nm.",
    )


def classify_measurement(
    alpha_rad: float,
    *,
    e_eff_w_m2: Optional[float] = None,
    e_uva_w_m2: Optional[float] = None,
    blue_light_value: Optional[float] = None,
    l_r_w_m2_sr: Optional[float] = None,
    e_ir_w_m2: Optional[float] = None,
) -> str:
    """Risk-group classification: Exempt, RG1, RG2, or RG3.

    Directive guide Sec. 8.1.2 [Directive 2006/25/EC guide]:
    each risk group requires the source to stay within every *provided*
    hazard's MPE at that group's own reference duration (Exempt is the
    least permissive/shortest set of durations relative to a plausible
    all-day exposure; RG2's durations are the aversion-response times,
    0.25 s for blue-light/retinal-thermal). Checked in ascending severity
    order; the first group whose criteria all pass is returned, matching
    `iec60825_1.classify_measurement`'s own ascending-order dispatch shape.
    A hazard argument left `None` is treated as "this source does not
    emit in that band" and excluded from every group's check -- it is the
    caller's responsibility to omit only hazards that are genuinely
    inapplicable -- a caller contract, not something this function can
    verify.

    **Not modelled**: the "IR hazard without a strong visual stimulus"
    sixth criterion (a judgement call, not a pure radiometric threshold);
    `mpe_retinal_thermal_ira`'s IRA-only variant (this function always
    uses the combined-band `mpe_retinal_thermal`, matching how the guide's
    own criteria name a single generic "Retinal Thermal hazard").

    **Retinal thermal is a special case, not a `_RISK_GROUP_DURATIONS_S`
    lookup** -- see `_retinal_thermal_classification_limit_w_m2_sr`'s own
    docstring for the correction this represents (`C-EYE-06`, fixed
    against IEC 62471's own Table 6.1): Exempt and RG1 share the *same* limit, and all three
    groups' limits are radiance-typed (W/(m^2*sr)), never a dose.

    Args:
        alpha_rad: Angular subtense of the apparent source, in radians --
            needed to evaluate `blue_light_value`/`l_r_w_m2_sr` against
            their own alpha-dependent limits.
        e_eff_w_m2: Measured S(lambda)-weighted effective irradiance
            (actinic UV), in W/m^2, or `None` if not applicable.
        e_uva_w_m2: Measured UVA irradiance, in W/m^2, or `None`.
        blue_light_value: Measured blue-light quantity -- radiance in
            W/(m^2*sr) if `alpha_rad >= 0.011`, irradiance in W/m^2
            otherwise (matching `mpe_blue_light`'s own dispatch) -- or
            `None`.
        l_r_w_m2_sr: Measured R(lambda)-weighted retinal radiance, in
            W/(m^2*sr), or `None`.
        e_ir_w_m2: Measured IR (cornea/lens) irradiance, in W/m^2, or
            `None`.

    Returns:
        One of `"Exempt"`, `"RG1"`, `"RG2"`, `"RG3"`.
    """
    for group in ("Exempt", "RG1", "RG2"):
        durations = _RISK_GROUP_DURATIONS_S[group]
        ok = True
        if e_eff_w_m2 is not None:
            ok = ok and e_eff_w_m2 <= mpe_actinic_uv(durations["uv"]).value
        if e_uva_w_m2 is not None:
            ok = ok and e_uva_w_m2 <= mpe_near_uv(durations["near_uv"]).value
        if blue_light_value is not None:
            ok = ok and blue_light_value <= mpe_blue_light(durations["blue"], alpha_rad).value
        if l_r_w_m2_sr is not None:
            ok = ok and l_r_w_m2_sr <= _retinal_thermal_classification_limit_w_m2_sr(group, alpha_rad)
        if e_ir_w_m2 is not None:
            ok = ok and e_ir_w_m2 <= mpe_ir_eye(durations["ir"]).value
        if ok:
            return group
    return "RG3"


#: Directive 2006/25/EC Annex I's own hazard-index letters, mapped
#: to the function that computes that hazard's limit. Closes a gap: this
#: mapping existed only as
#: something read from the guide's prose and typed directly into
#: `notebooks/_gen_eye_safety_iec62471_broadband_example_nb.py`'s
#: `mpe_actinic_uv`/`mpe_blue_light`/`mpe_retinal_thermal` calls -- never
#: written down anywhere a test could check it. `(k)` is deliberately
#: omitted: `mpe_retinal_thermal_ira`'s own docstring explains why that
#: bracket's source-table cell is ambiguous and not transcribed. `(i)`/`(l)`
#: (ultrashort-pulse brackets) are also omitted -- not implemented at all,
#: see the module docstring.
HAZARD_LABEL_TO_FUNCTION = {
    'a': mpe_actinic_uv,
    'b': mpe_near_uv,
    'c': mpe_blue_light,
    'd': mpe_blue_light,
    'e': mpe_blue_light,
    'f': mpe_blue_light,
    'g': mpe_retinal_thermal,
    'h': mpe_retinal_thermal,
    'j': mpe_retinal_thermal_ira,
    'm': mpe_ir_eye,
    'n': mpe_ir_eye,
    'o': mpe_skin_thermal,
}
