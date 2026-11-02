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
checked_by: src-python/ray_tracing_shapely/developer_tests/test_physical_scene.py::test_set_calibration_rejects_plain_float,::test_set_calibration_rejects_wrong_dimensionality,::test_cylindrical_height_rejects_plain_float,::test_cylindrical_height_rejects_wrong_dimensionality,::test_cylindrical_to_irradiance_rejects_wrong_dimensionality,::test_photoconversion_rejects_plain_float_photosensitivity,::test_photoconversion_rejects_wrong_dimensionality_integration_time,::test_photoconversion_rejects_wrong_dimensionality_dark_output_voltage
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
