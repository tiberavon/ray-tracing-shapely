---
key: KD4
title: Why a flow state renders the full comparison, not just the verdict
one_line: Printing measured value, threshold, unit and citation exposed errors that comparing the numbers alone had hidden — including a unit contradicting the standard's own table.
status: active
informs: [eye_safety_classification_flow, optiland_nsq_run_registry, agentic_layer]
since: 0.1
---

Where the program writes out its own reasoning — *which* value was compared
against *which* threshold, in *what* units, from *which* table — defects
show up that testing did not find. It has happened often enough to be a
method rather than luck.

## Two cases

A safety classification compared a measured value against a limit and
reported a verdict. The verdicts were right and the tests passed. Then the
comparison was made to print itself out in full, which meant printing the
limit's recorded unit — and for one hazard, that unit contradicted the
standard's own table. Nothing had noticed, because only the bare number
had ever been compared, and the number was right.

A check on the physical dimensions of the inputs, added at the start of a
classification flow so that the flow could *say* what it was checking,
turned up a real defect in a risk-group comparison that was already marked
as checked and covered by tests.

## Why it works

A test asserts what its author thought to assert. Making the program
explain itself forces every field into the open, including the ones nobody
had a reason to look at. A wrong unit sitting beside a right number is
invisible until something has to print both.

It also puts the reasoning where a person can disagree with it. A verdict
invites agreement. A written-out comparison — *this value, against this
threshold, from this row of this table* — invites checking, and the checking
happens against the standard rather than against the code.

## The outsider version

The same thing happens when an artefact is handed to a reader that has
only the artefact. A separate AI assistant was given a saved database of a
3D trace — no notebook, no description of the layout, and told not to read
any source that might explain it — and asked one question. It worked out
the layout from the file, answered, and its answer differed from the
notebook's. The difference was real, and tracing it found a structural fact
neither question had been written to look for.

That is a test of whether the artefact explains itself, and it works
because the outsider cannot bring the assumptions that made the original
answer look obvious.

## What this does not claim

That explanation replaces testing. It finds a different kind of defect —
things that are consistent within the code and wrong against the world.
Tests find regressions; explanation finds shared assumptions. Neither does
the other's job.

## Read also

- **KD3** — [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) — the defect class this catches
- **KD10** — [classification_runs_as_a_state_machine_with_one_fixed_diagram](KD10_classification_runs_as_a_state_machine_with_one_fixed_diagram.md) — the structure that made explaining feasible
- **KD5** — [correctness_is_checked_against_an_external_number](KD5_correctness_is_checked_against_an_external_number.md) — what the rendered comparison is checked against
