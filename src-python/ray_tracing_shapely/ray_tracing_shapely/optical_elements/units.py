"""
Python-specific module: dimensional analysis for the radiometric layer.

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
PYTHON-SPECIFIC MODULE: optical_elements_units
===============================================================================
Shared Pint plumbing for the radiometric/detector-physics layer: one
UnitRegistry, one string-parsing entry point (parse_quantity, for the
agentic/MCP string boundary), one Quantity-validation entry point
(ensure_quantity, for class constructors that already receive a real
pint.Quantity), and named dimensionality constants for the quantities this
layer actually uses.

Scope, and what stays out of it: PhysicalScene, the ProjectionModel family,
and Photoconversion (and their agentic wrappers, planned) are the
consumers. Scene-geometry coordinates (p1/p2, pixel_pitch,
PhysicalScene.scene_unit) are core/'s hot-loop convention and stay plain
float -- this module does not touch them. eye_safety's own mpe_*/ael_*/
classify_measurement routines are already `status: enforced` (C-EYE-01,
C-EYE-04) against exact published worked examples in plain float, SI base
units -- an agentic wrapper around them extracts `.to(<SI base>).magnitude`
from a Quantity at the point of call rather than re-typing those functions.

P-QUANTITY-PARSING, see dev_doc/architecture/components/
optical_elements_units.md and C-UNITS-02
(dev_doc/architecture/contracts/C-UNITS-02.md). Design rationale:
dev_doc/architecture/components/optical_elements_units.md.
===============================================================================
"""

from __future__ import annotations

from typing import Any

import pint

#: One registry for the whole radiometric layer -- classes and agentic
#: wrappers alike import `ureg`/`Quantity` from here rather than each
#: constructing their own UnitRegistry, so Quantity objects created in one
#: module are always compatible with those created in another.
ureg = pint.UnitRegistry()
Quantity = ureg.Quantity

# ---------------------------------------------------------------------------
# Named dimensionalities in actual use across this layer.
#
# Each is a reference *unit* string, not a bare dimensionality string
# ('[power]/[length]**2') -- pint.Quantity.check() accepts either, and unit
# strings read the same way the datasheets/docstrings already do (a
# maintainer can see at a glance that IRRADIANCE means "W/m^2", not decode
# a dimensionality expression).
# ---------------------------------------------------------------------------

POWER = "W"
POWER_PER_LENGTH = "W/m"            #: the 2D simulator's own convention (per unit z)
IRRADIANCE = "W/m^2"
RADIANCE = "W/(m^2 * sr)"
RADIANT_EXPOSURE = "J/m^2"          #: dose -- distinguishes J/cm^2 from mJ/m^2
LENGTH = "m"
TIME = "s"
VOLTAGE = "V"
PHOTOSENSITIVITY = "V/(lx*s)"       #: Sw, sensor datasheet convention
SOLID_ANGLE = "sr"                  #: steradian -- radiance<->irradiance conversions
ANGLE = "rad"                       #: angular subtense inputs -- note radian is
                                     #: dimensionless in Pint's default registry, so this
                                     #: mainly buys unit *conversion* (e.g. deg -> rad),
                                     #: not a real dimensionality check against, say, a length


def parse_quantity(spec: str, expected_dimensionality: str) -> 'pint.Quantity':
    """Parse a Pint-formatted quantity string, validating its dimensionality.

    This is the agentic/MCP boundary entry point: one string parameter per
    quantity (e.g. "30 mW/cm^2"), the shape an LLM agent or a human already
    writes naturally and the one Pint's own parser consumes directly.

    Args:
        spec: A quantity string, e.g. "30 mW/cm^2", "1.4 V", "771 us".
        expected_dimensionality: A unit string (one of this module's named
            constants, e.g. IRRADIANCE) or any Pint dimensionality string
            this quantity must be compatible with.

    Returns:
        The parsed pint.Quantity, unconverted -- callers decide whether they
        need it as a Quantity (passed straight into a radiometric-layer
        class) or a plain float in a specific unit (`.to(unit).magnitude`,
        e.g. immediately before calling an eye_safety function).

    Raises:
        ValueError: If `spec` cannot be parsed as a quantity, or its
            dimensionality does not match `expected_dimensionality`. Both
            failure modes are normalised to ValueError -- not
            pint.errors.UndefinedUnitError, which subclasses AttributeError,
            not ValueError -- so every existing agentic tool wrapper's
            CONTRIBUTING.md-mandated `except (ValueError, KeyError,
            RuntimeError)` block catches this with no new plumbing.
    """
    if not isinstance(spec, str):
        raise ValueError(
            f"Expected a quantity string (e.g. '30 mW/cm^2'), "
            f"got {type(spec).__name__}: {spec!r}"
        )
    try:
        q = ureg.Quantity(spec)
    except Exception as e:
        raise ValueError(f"Could not parse {spec!r} as a physical quantity: {e}") from e
    if not q.check(expected_dimensionality):
        raise ValueError(
            f"{spec!r} has dimensionality {q.dimensionality}, expected "
            f"dimensionality compatible with {expected_dimensionality!r}."
        )
    return q


def ensure_quantity(value: Any, expected_dimensionality: str, *, name: str = "value") -> 'pint.Quantity':
    """Validate that `value` is already a pint.Quantity with the expected
    dimensionality.

    Used by radiometric-layer class constructors/setters (PhysicalScene,
    ProjectionModel, Photoconversion), which take real Quantity objects, not
    strings -- parse_quantity is for the agentic/string boundary; the
    classes above it are the idiomatic-Pint layer, matching how Pint is
    used directly in Python/notebook code.

    Args:
        value: The object a caller passed in place of a quantity.
        expected_dimensionality: A unit string this quantity must be
            compatible with (see this module's named constants).
        name: The parameter name, for the error message.

    Returns:
        `value`, unchanged, once validated.

    Raises:
        ValueError: If `value` is not a pint.Quantity, or has the wrong
            dimensionality.
    """
    if not isinstance(value, Quantity):
        raise ValueError(
            f"{name} must be a pint.Quantity (e.g. "
            f"ray_tracing_shapely.optical_elements.units.ureg.Quantity(30, 'mW/cm^2')), "
            f"got {type(value).__name__}: {value!r}"
        )
    if not value.check(expected_dimensionality):
        raise ValueError(
            f"{name} has dimensionality {value.dimensionality}, expected "
            f"dimensionality compatible with {expected_dimensionality!r}."
        )
    return value


def _base_units_match(value: 'pint.Quantity', reference_unit: str) -> bool:
    """Whether `value`'s base units exactly match `reference_unit`'s --
    stricter than `.check()`/`.dimensionality`, and necessarily so: Pint's
    default registry treats radian/steradian as dimensionless (the SI
    convention), so `.check()` alone **cannot** distinguish an irradiance
    (`W/m^2`) from a radiance (`W/(m^2*sr)`) -- both report the identical
    `.dimensionality`, `[mass]/[time]**3`, confirmed directly:
    `ureg.Quantity(1, "W/m^2").check("W/(m^2*sr)")` is `True`. Comparing
    `.to_base_units().units` for exact equality does distinguish them,
    because Pint preserves radian/steradian as a real (if dimensionless)
    unit *symbol* through base-unit conversion rather than simplifying it
    away -- also confirmed directly in this environment. This is the
    mechanism `ensure_radiometric_quantity`/`parse_radiometric_quantity`
    are built on.
    """
    return value.to_base_units().units == ureg.Quantity(1.0, reference_unit).to_base_units().units


def ensure_radiometric_quantity(value: Any, expected_unit: str, *, name: str = "value") -> 'pint.Quantity':
    """Like `ensure_quantity`, but for radiometric quantities where plain
    dimensionality compatibility is not a strong enough check -- see
    `_base_units_match`'s docstring for exactly why `ensure_quantity`
    alone would silently accept a radiance where an irradiance was
    intended (or vice versa). Additionally requires exact unit-*family*
    agreement, not just dimensionality compatibility.

    Args:
        value: The object a caller passed in place of a quantity.
        expected_unit: A unit string identifying the *exact* radiometric
            family expected (e.g. `IRRADIANCE` or `RADIANCE` -- not a bare
            dimensionality string, since the whole point is to check the
            unit family, not just the SI dimensionality).
        name: The parameter name, for the error message.

    Returns:
        `value`, unchanged, once validated.

    Raises:
        ValueError: If `value` is not a pint.Quantity, has the wrong
            dimensionality, or is dimensionally compatible but the wrong
            radiometric family (e.g. a radiance where an irradiance was
            expected).
    """
    value = ensure_quantity(value, expected_unit, name=name)
    if not _base_units_match(value, expected_unit):
        raise ValueError(
            f"{name} has dimensionality compatible with {expected_unit!r} but "
            f"is not the same *kind* of radiometric quantity -- Pint treats "
            f"radian/steradian as dimensionless, so plain dimensionality "
            f"compatibility cannot catch this (e.g. a radiance, W/(m^2*sr), "
            f"passed where an irradiance, W/m^2, is expected, or vice versa). "
            f"Got units {value.units!r}, expected the same family as {expected_unit!r}."
        )
    return value


def parse_radiometric_quantity(spec: str, expected_unit: str) -> 'pint.Quantity':
    """String-boundary counterpart to `ensure_radiometric_quantity` --
    parses `spec` (`parse_quantity`'s own job) and additionally requires
    exact radiometric-family agreement (`ensure_radiometric_quantity`'s
    own job), not just dimensionality compatibility.

    Raises:
        ValueError: If `spec` cannot be parsed, has the wrong
            dimensionality, or is the wrong radiometric family.
    """
    q = parse_quantity(spec, expected_unit)
    return ensure_radiometric_quantity(q, expected_unit, name=f"{spec!r}")


def checked_scalar(value: Any, expected_unit: str, *, name: str) -> float:
    """A quantity of the expected kind, as a plain float in `expected_unit`:
    the check every flow applies to an answer with a unit. Like
    `eye_safety_classification_flow.checked_hazard_value`, for a single quantity with no
    radiometric irradiance/radiance ambiguity to worry about (power,
    length, time, plane angle, ...) -- ordinary
    `ensure_quantity`/`parse_quantity` dimensionality checking is
    sufficient for these. Used by both flows' `alpha_rad`, and
    `iec60825_1_flow.py`'s
    `measured_power_W`/`wavelength_nm`/`duration_s_class1`.

    **"Sufficient" here means: none of these expectations is a solid
    angle.** An earlier version of this docstring justified the ordinary
    check by saying that "only steradian-bearing quantities have the
    'dimensionless in Pint' problem" -- correct, and it is exactly why
    anything whose *expected* unit is `sr` must not come through here.
    `alpha_rad` is a plane angle and is safe: a caller who supplies `deg`
    gets it converted correctly, and `sr` in an `alpha_rad` slot is a
    units error this check cannot see but which no caller has a reason to
    make. A solid-angle expectation is the reverse case and goes through
    `ensure_radiometric_quantity`/`parse_radiometric_quantity` instead: the two conversion wrappers'
    `solid_angle` argument was once routed here by this same reasoning
    (`KW-UNITS-01`, closed; `C-UNITS-02`).

    **Mandatory**: `value` must be a `pint.Quantity` or a Pint-formatted
    string -- see `eye_safety_classification_flow.checked_hazard_value`'s docstring for why a bare
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
