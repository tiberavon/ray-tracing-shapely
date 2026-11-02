---
key: KC5
title: Why every exposure limit in the standard is implemented
one_line: The hazard modules implement the limits the standards define rather than the subset the current examples exercise, because an unimplemented limit produces a complete-looking pass.
status: active
informs: [eye_safety, eye_safety_classification_flow, C-EYE-02, C-EYE-06]
since: 0.1
---

The modules that evaluate whether a light source is safe to look at
implement every exposure limit the safety standards define — not only the
ones the current examples happen to need. A limit that no test reaches is
still implemented, and leaving one out is recorded as a gap, not as a
scoping decision.

## Why this is the exception to "build what you need"

Leaving out unused functionality is ordinarily good practice. It stops
being good practice when the consequence of the gap is a safety number that
reads as authoritative.

A retinal limit for *photochemical* damage — light chemically altering the
retina, as opposed to heating it — was once left out because neither worked
example needed it. In the blue part of the spectrum that limit is about ten
times stricter than the thermal limit the module *was* reporting. Nothing
in the output said that a kind of damage had not been evaluated. A reader
would have seen a pass.

That asymmetry is the whole point. In ordinary code a missing feature is
absent and visible. Here a missing limit produces a complete-looking
answer that is wrong in the unsafe direction.

## What "complete" means here

- Every hazard the standard defines for the wavelength range, not only the
  ones the examples exercise.
- Both halves where a limit has two: an ultraviolet exposure of the cornea
  is both thermal and photochemical, and which one binds depends on how
  long the exposure lasts.
- The neighbouring hazards too. A source that can damage a retina can
  usually damage skin, and a module that answers about one while silently
  ignoring the other invites the reader to assume the other was checked.

## Checked against the standard, not against ourselves

The limits are implemented from the published tables, and the
classification logic is verified against the standard's own worked
examples. A test suite written from the same understanding as the code
confirms the understanding, not the physics.

## What this does not claim

That the implementation is complete now. Gaps exist and are named where
they are. The claim is about how a gap is recorded: as a defect with a
consequence, not as a decision that was made and closed.

## Read also

- **KC6** — [when_two_standards_coexist_neither_gets_the_bare_name](KC6_when_two_standards_coexist_neither_gets_the_bare_name.md) — the same caution about defaults
- **KD5** — [correctness_is_checked_against_an_external_number](KD5_correctness_is_checked_against_an_external_number.md) — what the limits are verified against
- **KD3** — [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) — why a missing chain is the worst kind of gap
