---
id: C-UNITS-02
title: Radiometric-layer physical quantities are Pint-typed and dimensionality-checked
parties:
  provides: optical_elements_units (ureg, parse_quantity, ensure_quantity, ensure_radiometric_quantity, parse_radiometric_quantity)
  relies:   optical_elements_physics (PhysicalScene, ProjectionModel, Photoconversion), eye_safety_classification_flow (validate_dimensions), agentic_layer (planned eye_safety wrappers)
binds:      optical_elements_physics, optical_elements_units, eye_safety_classification_flow
port: P-QUANTITY-PARSING
viewpoint: radiometric
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_physical_scene.py::test_set_calibration_rejects_plain_float,::test_set_calibration_rejects_wrong_dimensionality,::test_cylindrical_height_rejects_plain_float,::test_cylindrical_height_rejects_wrong_dimensionality,::test_cylindrical_to_irradiance_rejects_wrong_dimensionality,::test_photoconversion_rejects_plain_float_photosensitivity,::test_photoconversion_rejects_wrong_dimensionality_integration_time,::test_photoconversion_rejects_wrong_dimensionality_dark_output_voltage,src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_eye_safety_classification_flow.py::test_checked_radiance_from_irradiance_rejects_plane_angle_as_solid_angle,::test_checked_radiance_from_irradiance_rejects_degrees_as_solid_angle,::test_checked_radiance_from_irradiance_rejects_dimensionless_solid_angle,::test_checked_irradiance_from_radiance_rejects_plane_angle_as_solid_angle,::test_checked_conversion_solid_angle_rejects_bad_unit_as_string_too
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC4
since: 0.2
---

# C-UNITS-02 — Physical quantities carry their unit and are checked on entry

**Assumptions.** Every physical parameter handed to `PhysicalScene`, a
projection model or a photoconversion is a number-with-unit — constructed
explicitly, for example `Quantity(30, "mW/cm^2")` — not a bare number
whose unit is only implied by the parameter's name.

**Guarantees.** Every constructor and setter that takes one checks it is
the right *kind* of quantity before using it: an irradiance where an
irradiance is expected, whatever unit it was written in. Across the
agentic boundary, a quantity arrives as one string containing both number
and unit and is parsed into the same checked form.

*Kind*, not dimensionality, is the operative word, and it extends to
angles. Pint's registry treats radian and steradian alike as
dimensionless, so a dimensionality check alone cannot tell an irradiance
from a radiance, nor a plane angle from a solid angle. Where the expected
unit is `sr`, a value in `rad`, `mrad` or `deg`, or a bare dimensionless
magnitude, is rejected — see *Solid angles* below.

**Invariants.** Scene geometry — coordinates, endpoints, pixel pitch —
stays a plain number and is explicitly outside this contract. The
hazard formulas work internally in documented base units and are checked
at their edges, not inside.

**Units and frames.** Whatever the quantity says, converted as needed.

**If the assumption is violated.** Loud. A bare number, or a quantity of
the wrong kind, raises a `ValueError` naming what was expected.

**Checked by.** Tests in `test_physical_scene.py`: a plain number is
rejected, a wrong dimensionality is rejected, a right one in a different
unit is accepted.

---

**Solid angles.** A solid angle is checked by kind like every other
quantity: the checked radiance conversions in `dimensional_checks`
(`checked_radiance_from_irradiance` and its inverse) put every argument,
`solid_angle` included, through the strict same-kind check
(`ensure_radiometric_quantity`), and there is no switch that selects a
looser one. The `solid_angle` slot once took only the ordinary
dimensionality check, on the reasoning that a solid angle carries no
irradiance-or-radiance ambiguity. True, and beside the point: the
ambiguity that matters for that argument is steradian against radian. Then
`3.025 mrad` where `3.025 msr` was meant was accepted and happened to return
the right number (the milli- prefixes coincide), and `0.1733 deg` was
accepted and returned a value 17 times too low. The defect is registered as
`KW-UNITS-01`, closed (`KD13`); it had been disclosed to an external
reviewer before it was fixed. Five tests in `checked_by` pin the
rejections.

**Note for anyone extending this contract's reach.** The guard is only as
good as its *expected unit*: any new checked parameter whose expectation is
`sr` must use `ensure_radiometric_quantity`/`parse_radiometric_quantity`,
never `ensure_quantity`/`parse_quantity`. `checked_scalar` remains correct
for plane angles, lengths, times and powers, and its docstring says why.
