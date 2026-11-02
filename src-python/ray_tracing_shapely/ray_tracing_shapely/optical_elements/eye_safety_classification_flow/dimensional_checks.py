"""
Python-specific module: dimensional consistency checks at FRAME_INPUT

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
PYTHON-SPECIFIC MODULE: dimensional_checks
===============================================================================
This is the seam between the unit-checked layer and the plain-float hazard
formulas: a pint.Quantity gets checked at this boundary and reduced to a
plain float in a documented SI unit immediately before `eye_safety`'s
functions are called. `eye_safety` itself stays plain float, untouched --
this module is the FRAME_INPUT-side validation layer, not a rework of the
functions it feeds.

    [KC4: the hazard formulas work in plain SI units internally and are
    checked at their edges, not inside every formula.]
    [KA9: this is the boundary a caller's input crosses, so it is checked
    here, once, and a bare number is refused rather than assumed.]

**Mandatory, not opt-in.** An earlier version of this module accepted a
plain `int`/`float` as a silent pass-through, trusted as already correct
-- reasoned, on reflection, to defeat the point: a careless caller could
always bypass every check below just by not typing a unit. Every
physical value FRAME_INPUT accepts (every hazard value, and IEC 60825-1's
own `measured_power_W`/`wavelength_nm`/`alpha_rad`/`duration_s_class1`
when not `None`) must now be a `pint.Quantity` or a Pint-formatted
string -- a bare number is rejected outright, with a `ValueError` naming
which field and what was expected. `validate_dimensions` (both flows'
own dedicated FSM state, immediately after `frame_input`) exists so this
is not just an internal function call but a visible, self-contained step
in the run -- its own node in `state.svg`, its own entry in
`events.jsonl` -- and so a run that never had its physical inputs stated
with explicit units never gets there: `submit_input`'s `before` callback
enforces this before the transition into `validate_dimensions` is even
allowed to happen (the FSM stays in `frame_input`, per `transitions`'
own semantics, confirmed directly in `flow_base.py`'s docstring).

Two things this buys, concretely, that a plain
`isinstance(value, (int, float))` check could not:

1. **Catches a dose passed where a rate is expected** (e.g. J/cm^2 where
   W/m^2 is expected) -- an ordinary Pint dimensionality check
   (`ensure_quantity`) already does this, since energy and power are
   genuinely different SI dimensions.
2. **Catches a radiance passed where an irradiance is expected, or vice
   versa** -- Pint's default registry treats radian/steradian as
   dimensionless (the SI convention), so a *plain* dimensionality check
   cannot tell W/m^2 (irradiance) from W/(m^2*sr) (radiance) apart; both
   report the identical `.dimensionality`. `optical_elements.units`'
   `ensure_radiometric_quantity`/`parse_radiometric_quantity` (added
   alongside this module) close that gap via a stricter, exact-unit-family
   check -- see that module's own docstring for the verified mechanism.

`blue_light`'s expected dimensionality genuinely depends on `alpha_rad`
(`mpe_blue_light` dispatches radiance vs. irradiance at the standard's own
11 mrad boundary) -- `expected_dimensionality_for_hazard` below implements
that dispatch explicitly, rather than leaving it as an undocumented
assumption a caller has to already know. `retinal_thermal` does not have
this dispatch: after the `C-EYE-06` correction to
`iec62471.classify_measurement` (see that module's own docstring), its
risk-group comparison is always radiance-typed, at every group, so its
expected dimensionality here is fixed.
===============================================================================
"""

from __future__ import annotations

from typing import Any

from ..units import (
    Quantity,
    ensure_quantity,
    parse_quantity,
    ensure_radiometric_quantity,
    parse_radiometric_quantity,
    IRRADIANCE,
    RADIANCE,
)
from ..eye_safety.iec62471 import ALPHA_BLUE_LIGHT_BOUNDARY_RAD
from ..eye_safety.radiometry_conversions import (
    radiance_from_irradiance as _radiance_from_irradiance,
    irradiance_from_radiance as _irradiance_from_radiance,
)

#: Hazards whose expected dimensionality never depends on alpha_rad --
#: matches classify_measurement's own kwargs, all always irradiance.
_FIXED_IRRADIANCE_HAZARDS = frozenset({"actinic_uv", "near_uv", "ir"})

#: retinal_thermal is fixed too (always radiance, since the C-EYE-06
#: correction) -- listed separately from the irradiance set above for
#: clarity at the call site, not because the check differs mechanically.
_FIXED_RADIANCE_HAZARDS = frozenset({"retinal_thermal"})

#: blue_light is the one hazard whose expected dimensionality genuinely
#: depends on alpha_rad -- see module docstring.
_ALPHA_DEPENDENT_HAZARDS = frozenset({"blue_light"})


def expected_dimensionality_for_hazard(hazard_key: str, alpha_rad: float) -> str:
    """The `optical_elements.units` unit string a hazard's FRAME_INPUT
    value must be the same radiometric *family* as, given this run's
    `alpha_rad`.

    Args:
        hazard_key: One of `"actinic_uv"`, `"near_uv"`, `"blue_light"`,
            `"retinal_thermal"`, `"ir"` (`iec62471_flow.py`'s own hazard keys).
        alpha_rad: This run's angular subtense, in radians -- only
            consulted for `"blue_light"`.

    Returns:
        `IRRADIANCE` or `RADIANCE` (from `optical_elements.units`).

    Raises:
        ValueError: If `hazard_key` is not one of the five above.
    """
    if hazard_key in _FIXED_IRRADIANCE_HAZARDS:
        return IRRADIANCE
    if hazard_key in _FIXED_RADIANCE_HAZARDS:
        return RADIANCE
    if hazard_key in _ALPHA_DEPENDENT_HAZARDS:
        return RADIANCE if alpha_rad >= ALPHA_BLUE_LIGHT_BOUNDARY_RAD else IRRADIANCE
    raise ValueError(
        f"Unknown hazard key: {hazard_key!r}. Expected one of "
        f"{sorted(_FIXED_IRRADIANCE_HAZARDS | _FIXED_RADIANCE_HAZARDS | _ALPHA_DEPENDENT_HAZARDS)}."
    )


def checked_hazard_value(hazard_key: str, value: Any, alpha_rad: float, *, name: str) -> float:
    """Validate and reduce a FRAME_INPUT hazard value to a plain float in
    the expected SI base unit.

    **Mandatory**: `value` must be a `pint.Quantity` or a Pint-formatted
    string (e.g. `"55 mW/(m^2*sr)"`) -- a bare `int`/`float` is rejected,
    not silently trusted (see module docstring for why an earlier,
    opt-in version of this function defeated its own purpose). Validated
    against `expected_dimensionality_for_hazard` via
    `ensure_radiometric_quantity`/`parse_radiometric_quantity` (catching
    both a dose-vs-rate mistake and an irradiance-vs-radiance one) and
    converted to the expected unit's magnitude.

    Raises:
        ValueError: `value` is a bare `int`/`float` (or any other
            non-Quantity, non-string type), has the wrong dimensionality
            or radiometric family, or is an unparseable string.
    """
    expected = expected_dimensionality_for_hazard(hazard_key, alpha_rad)
    if isinstance(value, bool) or not isinstance(value, (Quantity, str)):
        raise ValueError(
            f"{name} must be a pint.Quantity or a Pint-formatted string "
            f"(e.g. \"55 {expected}\") -- a bare number is not accepted, "
            f"so its unit is never assumed. Got {type(value).__name__}: {value!r}."
        )
    if isinstance(value, str):
        q = parse_radiometric_quantity(value, expected)
    else:
        q = ensure_radiometric_quantity(value, expected, name=name)
    return q.to(expected).magnitude


def checked_scalar(value: Any, expected_unit: str, *, name: str) -> float:
    """Like `checked_hazard_value`, for a single quantity with no
    radiometric irradiance/radiance ambiguity to worry about (power,
    length, time, angle, ...) -- ordinary `ensure_quantity`/`parse_quantity`
    dimensionality checking is already sufficient for these, since only
    steradian-bearing quantities have the "dimensionless in Pint" problem
    `ensure_radiometric_quantity` exists to work around. Used by both
    flows' `alpha_rad`, and `iec60825_1_flow.py`'s
    `measured_power_W`/`wavelength_nm`/`duration_s_class1`.

    **Mandatory**: `value` must be a `pint.Quantity` or a Pint-formatted
    string -- see `checked_hazard_value`'s own docstring for why a bare
    number is rejected rather than trusted.

    Raises:
        ValueError: `value` is a bare `int`/`float` (or any other
            non-Quantity, non-string type), has the wrong dimensionality,
            or is an unparseable string.
    """
    if isinstance(value, bool) or not isinstance(value, (Quantity, str)):
        raise ValueError(
            f"{name} must be a pint.Quantity or a Pint-formatted string "
            f"(e.g. \"1 {expected_unit}\") -- a bare number is not accepted, "
            f"so its unit is never assumed. Got {type(value).__name__}: {value!r}."
        )
    if isinstance(value, str):
        q = parse_quantity(value, expected_unit)
    else:
        q = ensure_quantity(value, expected_unit, name=name)
    return q.to(expected_unit).magnitude


def checked_radiance_from_irradiance(irradiance: Any, solid_angle: Any) -> 'Quantity':
    """Pint-checked wrapper around `eye_safety.radiance_from_irradiance`.

    Validates that `irradiance` really is an irradiance (not, say, a dose
    or an already-radiance value) and `solid_angle` really is a solid
    angle, performs the *same* plain-float division the tested function
    already does (this never re-implements the arithmetic), and returns a
    dimensionally-labelled `Quantity` -- confirming, by construction via
    Pint's own unit arithmetic, that `W/m^2 / sr` really is `W/(m^2*sr)`,
    not silently miscomputed.

    Args:
        irradiance: A `pint.Quantity` or Pint-formatted string, dimensionally
            an irradiance (`W/m^2`).
        solid_angle: A `pint.Quantity` or Pint-formatted string, dimensionally
            a solid angle (`sr`).

    Returns:
        A `pint.Quantity`, dimensionality `W/(m^2*sr)`.

    Raises:
        ValueError: If either argument is not the expected kind of quantity.
    """
    irradiance_q = _as_quantity(irradiance, IRRADIANCE, name="irradiance", radiometric=True)
    solid_angle_q = _as_quantity(solid_angle, "sr", name="solid_angle", radiometric=False)
    value = _radiance_from_irradiance(
        irradiance_q.to("W/m^2").magnitude, solid_angle_q.to("sr").magnitude,
    )
    return Quantity(value, "W/m^2/sr")


def checked_irradiance_from_radiance(radiance: Any, solid_angle: Any) -> 'Quantity':
    """Pint-checked wrapper around `eye_safety.irradiance_from_radiance` --
    the inverse of `checked_radiance_from_irradiance`, same guarantees.

    Raises:
        ValueError: If either argument is not the expected kind of quantity.
    """
    radiance_q = _as_quantity(radiance, RADIANCE, name="radiance", radiometric=True)
    solid_angle_q = _as_quantity(solid_angle, "sr", name="solid_angle", radiometric=False)
    value = _irradiance_from_radiance(
        radiance_q.to("W/(m^2*sr)").magnitude, solid_angle_q.to("sr").magnitude,
    )
    return Quantity(value, "W/m^2")


def _as_quantity(value: Any, expected_unit: str, *, name: str, radiometric: bool) -> 'Quantity':
    """Shared string-or-Quantity acceptance for the two checked conversion
    wrappers above. `radiometric=True` routes through the stricter
    irradiance/radiance-distinguishing check; `radiometric=False` (used
    for the plain solid-angle argument, which has no such ambiguity) uses
    the ordinary dimensionality check.
    """
    if isinstance(value, str):
        return (parse_radiometric_quantity if radiometric else parse_quantity)(value, expected_unit)
    return (ensure_radiometric_quantity if radiometric else ensure_quantity)(value, expected_unit, name=name)
