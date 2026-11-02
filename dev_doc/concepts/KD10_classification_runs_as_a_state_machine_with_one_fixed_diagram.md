---
key: KD10
title: Why classification runs as a state machine with a fixed diagram
one_line: A classification's sequence — what was evaluated, in what order, what was skipped and why — is made an explicit artefact instead of invisible call-stack recursion, and the diagram never varies with the input.
status: active
informs: [eye_safety_classification_flow, eye_safety, C-EYE-04, C-EYE-05]
since: 0.1
---

Deciding whether a light source is safe to look at means checking it
against several limits in a fixed order. Here that check runs as a **state
machine**: a fixed diagram of boxes joined by arrows, where the program
moves from box to box, and each box writes down what it checked, against
what, and why. The underlying function that decides the answer is
unchanged. What is added is that the run can be watched.

## Why the diagram must not change shape

The diagram is what a reader checks against the standard. If its shape
depended on the input — a checklist that only asks follow-up questions when
an answer was yes — every run would have a different diagram, and no single
picture could be verified.

So every box is visited on every run. A hazard that does not apply to this
source still enters its box and leaves at once with a note saying *not
applicable*. The shape is constant; only the notes differ.

That has consequences that look like waste. Five hazards checked against
three risk groups is fifteen boxes rather than five, because one box
showing one result would not match what the underlying function actually
does. Two standards get two separate machines rather than one that chooses
at runtime, because a shared machine's diagram would look different
depending on which standard was picked.

## What being watchable buys

**A record.** The list of boxes entered, in order, with what was skipped
and why. A verdict alone cannot be audited; a sequence can.

**An explanation at every step.** Each box can say what it is asking and
why, citing the table and row it draws on. Doing that turned up defects
that comparing bare numbers had hidden.

**A restart.** Someone watching the result head the wrong way can reset the
machine from any box and start again with different inputs, with the
attempt number recorded so the log shows every attempt.

**A place for checking the inputs.** Confirming that each input is the
right kind of quantity is its own box, between reading the inputs and the
first evaluation, so a caller can see the check happen and see it fail.

## One source of truth for the answer

The narration never becomes a second implementation. The classification
function decides the result; the machine reports what that function did. A
test confirms that every recorded verdict agrees with what the function
says directly, so the explanation cannot drift from the answer it explains.

## What this does not claim

That state machines suit everything. This one earned its place because the
*sequence* is the thing being audited and the standard defines the order.
A calculation nobody needs to audit gains nothing from being cut into
boxes.

## Read also

- **KD4** — [states_render_the_full_comparison_not_just_the_verdict](KD4_states_render_the_full_comparison_not_just_the_verdict.md) — what the explanations found
- **KC6** — [when_two_standards_coexist_neither_gets_the_bare_name](KC6_when_two_standards_coexist_neither_gets_the_bare_name.md) — why there are two flows
- **KA9** — [every_argument_is_parsed_and_checked_at_the_agent_boundary](KA9_every_argument_is_parsed_and_checked_at_the_agent_boundary.md) — why validation is its own state
