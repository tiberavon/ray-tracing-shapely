---
key: KC4
title: Why radiometric quantities are typed rather than documented
one_line: A float whose correctness depends on a docstring being read is unchecked, so every quantity in the radiometric layer carries its unit and is dimensionality-checked where it enters.
status: active
informs: [optical_elements_units, optical_elements_physics, eye_safety, agentic_layer, C-UNITS-01, C-UNITS-02]
since: 0.1
---

Every quantity in the physical layer — an irradiance, a sensor's
sensitivity, a calibration factor — is a number *with its unit attached*,
checked on arrival for being the right kind of thing. Across the boundary
where an AI assistant sends values, a quantity arrives as one piece of text
like `"30 mW/cm^2"` and is read into the same checked form.

## A unit in the documentation is not a unit that is checked

A function that takes a plain number and says in its documentation "this
is in watts per square metre" is correct only as long as every caller
reads that line and converts. Nothing notices a caller passing watts per
square *centimetre*. The result is a number of the right magnitude in the
wrong unit, and it passes every test that checks for a plausible value.

This is not hypothetical. One class here carried two different unit
conventions in two of its own methods, told apart only by a suffix in the
name, with nothing checking either.

## The check is on the kind, not the spelling

An irradiance is accepted whether it is written in W/m² or mW/cm²; a
radiance — light per area *per direction* — is refused in either. That is
the useful strictness. Converting between units is arithmetic and the
library does it. Confusing a quantity-per-area with a quantity-per-area-
per-direction is a physics mistake, and arithmetic will not catch it.

## Where it applies, and where it deliberately does not

The physical layer, the detector models, and the assistant boundary. Not
the geometry: positions, ray endpoints and pixel spacing stay plain
numbers, because the engine runs that code once per ray per surface and
the mistake being prevented cannot happen there — the engine never sees a
unit.

The hazard formulas also work in plain documented SI units internally.
They are dense numerical code copied from published tables, and the
checking is done where their inputs are assembled rather than inside every
formula.

## The boundary gets the strictest version

A value from an AI assistant is one string with the number and the unit
together. A bare number is refused rather than given an assumed unit — a
plausible default is exactly how a wrong unit stays invisible — and the
check is a visible step that can be seen to fail, not something buried in
the next operation.

## What this does not claim

That checked units make the physics right. They catch one specific mistake:
a value used as the wrong kind of quantity. A correctly-labelled irradiance
computed from the wrong geometry is still wrong, and no unit check notices.

## Read also

- **KA9** — [every_argument_is_parsed_and_checked_at_the_agent_boundary](KA9_every_argument_is_parsed_and_checked_at_the_agent_boundary.md) — why the strictest version is at that boundary
- **KC1** — [physics_and_rendering_are_layers_above_core_never_inside_it](KC1_physics_and_rendering_are_layers_above_core_never_inside_it.md) — why the geometry is exempt
- **KD3** — [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) — the failure mode this targets
