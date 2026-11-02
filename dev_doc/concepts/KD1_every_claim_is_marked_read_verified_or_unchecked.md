---
key: KD1
title: Why every claim carries its evidence class
one_line: A claim confirmed by running code, one read from a source file, and one taken from a third party's documentation are different kinds of thing, so each is marked and a document states which it is doing.
status: active
informs: [agentic_layer, optiland_scene_bridge, optiland_nsq_viewer]
since: 0.1
---

Documents in this project mark each claim with how it was established.
*Read from the source code.* *Confirmed by running it.* *Read from a third
party's documentation and not confirmed.* *Proposed but not yet built.*
*Flagged as unchecked.*

## The distinction that matters

"The renderer supports this projection" can mean three different things:
the documentation says so, the code says so, or someone ran it and it
worked. Those go stale differently. Documentation drifts. Code can be
misread. Only the third survives the library being upgraded underneath.

Without the marks, a reader cannot tell a verified claim from a plausible
one — and neither can the author, six months on. With them, re-checking a
document means re-running the small number of claims that were ever run,
and re-reading the ones that were only read.

## Each document says what it did not check, at the top

A review written from the documentation alone says so in its first
paragraph: *the source was not read, so nothing here is a claim about how
the code behaves*. A design document says *nothing here has been built;
treat it as a plan to validate, not a result*.

That line carries weight. Without it, a careful plan and a confirmed pilot
read identically, and the difference between them is the whole question of
whether to trust the conclusions.

## Claims about other people's code name the version

Where a claim is about a library this project depends on, the document
names the exact version — the commit — it was checked against. What a
dependency does at an unspecified version is not a fact about anything.

## Why this is a concept and not a style rule

It changes what gets written. An author who has to mark a claim as
*unchecked* usually checks it instead, because the mark is visible and the
check is often a minute's work. The convention's main effect is on the
work before the document, not on the document.

## What this does not claim

That marked claims are true. A claim marked *read from source* can still
be a misreading. The marks say what kind of checking was done, which is
what lets a later reader redo the right check rather than all of them.

## Read also

- **KD2** — [divergences_from_the_plan_are_written_down_with_their_reason](KD2_divergences_from_the_plan_are_written_down_with_their_reason.md) — the same honesty applied to outcomes
- **KD5** — [correctness_is_checked_against_an_external_number](KD5_correctness_is_checked_against_an_external_number.md) — what verification is done against
- **KD6** — [three_doc_trees_current_state_reasoning_and_decisions](KD6_three_doc_trees_current_state_reasoning_and_decisions.md) — why status and rationale are separated
