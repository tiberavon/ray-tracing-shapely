---
key: KD2
title: Why divergences from the plan are written down with their reason
one_line: Where the built thing differs from what was scoped, the difference and its cause stay in the record, because the plan usually undersold a constraint that only building revealed.
status: active
informs: [analysis_bidirectional, nonimaging_design, eye_safety_classification_flow]
since: 0.1
---

When what was built turns out different from what was planned, the plan is
not quietly updated to match. The difference is written down: what was
specified, what was built instead, and what was found in between.

## The difference is the valuable part

A plan is written with less information than the implementation has. When
they differ, the difference is usually where the plan was wrong — and the
reason is a real constraint that only building revealed.

One optical element was planned as a shape built by an iterative method
from a textbook. What shipped was a simpler shape with a closed formula.
Editing the plan to describe the simpler shape would have lost the finding:
the simpler shape already produced the physical behaviour the machinery
needed to exercise, so the iterative method was not needed for that
purpose. That is worth more than a tidy plan, and it only shows up as a
difference.

A rule for reconstructing which surfaces a route touched was planned as
"look at the next step". Building it revealed that this is right for one
of the two traces and backwards for the other, because their records are
stored in opposite directions — and applying it uniformly would have
silently mispaired every step of the backward trace while producing
plausible output.

## The honest form

State what was planned, what was built, and why. Where the built thing is
less than planned, say what it cannot do — a test fixture that is not a
physically accurate device says so, rather than being described in terms
that imply it is. Where a decision was made against real code rather than
in advance, say that too: it tells a later reader that the decision has
evidence behind it.

## Not a changelog

The record belongs with the plan, in the document that made it. A page
describing the current state of the code does not narrate how it got there,
and neither does a concept. Version control keeps the sequence of changes;
the divergence note keeps the *reason*, which version control does not.

## What this does not claim

That all divergence is fine. Some is a mistake and should be fixed rather
than documented. The rule applies once the difference is settled: at that
point the choice is to record why, or to pretend the plan always said this
— and the second throws away what was learned.

## Read also

- **KD1** — [every_claim_is_marked_read_verified_or_unchecked](KD1_every_claim_is_marked_read_verified_or_unchecked.md) — the same discipline applied to claims
- **KD6** — [three_doc_trees_current_state_reasoning_and_decisions](KD6_three_doc_trees_current_state_reasoning_and_decisions.md) — which tree the record belongs in
- **KD4** — [states_render_the_full_comparison_not_just_the_verdict](KD4_states_render_the_full_comparison_not_just_the_verdict.md) — another way implementation corrects a plan
