---
key: KD3
title: Why assertions go where a failure would be silent
one_line: Most defects here have produced a plausible wrong number rather than an exception, so checks are placed where nothing would otherwise fire, and an unmapped case raises instead of defaulting.
status: active
informs: [optical_elements_physics, optical_elements_units, eye_safety, optiland_scene_bridge, analysis_run_registry]
since: 0.1
---

A crash is a bad outcome with a stack trace attached. A wrong number that
looks right is a bad outcome that gets used. The defects that have actually
happened in this project are overwhelmingly the second kind, so that is
where the checks go.

## What silence looks like here

- A detector reporting the *net* of light crossing it in both directions,
  rather than what it absorbed. Its acceptance curve went negative at some
  angles and was read as a physical result for months.
- A safety classification comparing a measurement against a limit computed
  for the wrong exposure duration — in code that had tests, and passed
  them.
- A unit label on a limit that contradicted the standard's own table. It
  changed nothing, because only the bare number was ever compared.
- A 3D solid with no end caps. Light leaves through the open end, and the
  tracer reports perfect energy conservation, because the escaped rays are
  simply gone and it only accounts for the surfaces it knows about.

None of these raised an error. Each produced output of the right shape and
the right order of magnitude.

## What follows

**Prefer loud where there is a choice.** A surface label the 3D bridge does
not recognise is an error, not a default. A comparison across runs whose
object names differ refuses to run. A quantity arriving without a unit is
refused rather than assumed.

**Spend checks on silence.** A check on something that would have crashed
anyway buys little. A check on something that would have produced a
plausible number buys the whole defect.

**Distrust clean reports.** An energy-conservation figure of one part in
ten thousand trillion says the light is accounted for *among the surfaces
being tracked*. It says nothing about light that left through a boundary
nobody modelled.

## What this does not claim

That everything should crash. A question that legitimately matches no rays
is a finding, not a failure, and raising an error on it would train the
caller to work around the error. The distinction is between *no result*
and *a result that cannot be trusted*: the first is data, the second is the
thing that must never pass quietly.

## Read also

- **KC4** — [physical_quantities_are_unit_checked_not_docstring_documented](KC4_physical_quantities_are_unit_checked_not_docstring_documented.md) — the largest single source of silent wrongness
- **KD4** — [states_render_the_full_comparison_not_just_the_verdict](KD4_states_render_the_full_comparison_not_just_the_verdict.md) — how several of these were found
- **KD5** — [correctness_is_checked_against_an_external_number](KD5_correctness_is_checked_against_an_external_number.md) — what catches them before they ship
