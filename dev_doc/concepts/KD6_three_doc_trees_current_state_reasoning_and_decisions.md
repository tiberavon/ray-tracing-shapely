---
key: KD6
title: Why there are three documentation trees
one_line: Current state, timeless reasoning and dated decisions answer different questions and go stale differently, so each has its own tree and none does another's job.
status: active
informs: [agentic_layer, analysis_run_registry]
since: 0.1
---

This project keeps three separate sets of documents, because there are
three different questions a reader can ask, and the answers go stale in
three different ways.

**What is true now.** The components, what crosses between them, and the
promises that can be checked. Edited in place; either accurate or a bug.

**Why it is shaped this way.** The reasoning, written so that it does not
depend on when the decision was made — this set. Revisited only when the
reasoning changes, which is rarely.

**What was decided, and when.** The record of decisions in the order they
happened. Never edited, because the point of it is what was known at the
time. Not published.

## Why not one set

Put the three in one document and it inherits the worst property of each:
a reader cannot tell whether a paragraph describes the code as it is now,
the reasoning behind it, or the state of a discussion at some point in the
past. Each kind of sentence is right in its own place and misleading in
the others.

## The failure this avoids

Without a "what is true now" set, learning what a component does means
reading the decision record from the start and mentally discarding
whatever a later entry overturned. That is slow, error-prone, and gets
worse as the record grows.

The project arrived at this split by instinct before it was a rule. For one
large piece of work, a single summary document was written to replace seven
design documents *as the place to check what shipped*, while pointing back
at them for the reasoning — read those for why, read this for what. That
is the three-set split, reached under pressure.

## The numbering carries the same idea

The decision record's numbered series each mean a *kind* of work, not a
period of time. A new series means a genuinely different kind of work, and
a document that borrows an existing series for convenience says so, so that
the numbers do not drift into meaning "whatever was done at the time".

## What gets published

The first two sets. The third does not: it is dated, narrative, and full
of things that were true for a week. Material from it can become public
writing by being *edited*, which is a different act from publishing it.

## What this does not claim

That three is the right number for every project. It is the number of
distinct questions that turned out to need answering here, each with its
own way of going stale. A smaller project with no history worth keeping
needs fewer.

## Read also

- **KD11** — [component_boundaries_carry_assume_guarantee_contracts](KD11_component_boundaries_carry_assume_guarantee_contracts.md) — what the current-state tree is made of
- **KD2** — [divergences_from_the_plan_are_written_down_with_their_reason](KD2_divergences_from_the_plan_are_written_down_with_their_reason.md) — what the decision log is for
- **KD9** — [transcribed_book_chapters_never_leave_the_private_repo](KD9_transcribed_book_chapters_never_leave_the_private_repo.md) — the other reason something stays private
