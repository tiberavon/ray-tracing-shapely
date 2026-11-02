---
key: KC6
title: Why neither standard is reachable by the unqualified name
one_line: Two standards define same-named functions with different meanings, so both are reached through their own namespace and neither is flattened to the top level, because the easiest name to type becomes a silent default.
status: active
informs: [eye_safety, eye_safety_classification_flow, C-EYE-04]
since: 0.1
---

Two safety standards live side by side here — one for lasers, one for lamps
and LEDs. Both define exposure limits and a classification function, with
overlapping names and different meanings. Each is reached through its own
module name, and neither is made available as the short, unqualified name
at the top of the package.

## Why symmetry matters more than convenience

Making one standard's functions reachable by the short name and the other's
only by the long one looks like a small inconsistency. It is a decision
about behaviour: the short name — the one nobody has to think about, the
one that appears first when typing — becomes the standard you get without
choosing.

For a while that was the laser standard, in a project whose stated audience
works with lamps and LEDs into concentrators. A caller who never chose a
standard got one chosen for them by an import convention.

## Making the choice visible

Requiring both names to be spelled out means the choice of standard appears
at every point of use. A reader of that line knows which limits are being
applied without checking what a short name happens to resolve to, and a
caller cannot reach the wrong standard without typing its name.

The same reasoning drives the layer above: the step-by-step classification
flow is two separate classes, one per standard, rather than one class that
takes the standard as a setting. The standard is chosen when the object is
created, and the flow's shape never depends on it.

## The general form

Where two implementations of the same idea exist and one is more often
wanted, the preference goes in the documentation and the examples — not in
which one gets the short name. A shortcut is a default whether or not
anyone decided it was.

## What this does not claim

That convenience is worthless. Qualified names are longer and appear
everywhere, a real cost paid on every line. It is accepted here because the
wrong choice produces a safety number computed against the wrong standard,
and the cost worth paying scales with how bad that outcome is. Where the
mistake is cheap, the trade goes the other way.

## Read also

- **KC5** — [every_exposure_limit_in_the_standard_is_implemented](KC5_every_exposure_limit_in_the_standard_is_implemented.md) — the same caution about safety-relevant silence
- **KD10** — [classification_runs_as_a_state_machine_with_one_fixed_diagram](KD10_classification_runs_as_a_state_machine_with_one_fixed_diagram.md) — why the flow is two classes, not one parameterised one
- **KD3** — [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) — what a silent default produces
