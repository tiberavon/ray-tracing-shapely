---
key: KD9
title: Why transcribed source material stays private
one_line: Chapters transcribed from copyrighted books are kept in the private repository and never published; the reasoning and the code derived from them ship, the text does not.
status: active
informs: [nonimaging_design]
since: 0.1
---

The design methods implemented here come from published books. Working
from a book means having the text at hand, so the relevant chapters are
typed out in the private repository, cited by line number, and used both
as the reference and as the source of expected answers for tests. Those
typed-out chapters are never copied to the public repository.

## Two reasons for keeping something private, not one

The decision record is private because it is dated, narrative, and full of
things that were true for a week. That is an editorial reason, and editing
could in principle reverse it.

A typed-out chapter is private for a different reason, and no editing
changes it. It is someone else's text, reproduced at length for working
purposes. The reasoning built on top of it being original does not make
the reproduction publishable.

The distinction matters because the two are governed by different rules.
A publishing decision that thinks only about narrative and dates will
correctly conclude that a chapter transcription is not narrative — and
then ship it.

## What crosses and what does not

**Published:** the code, the concept explaining why a method was chosen,
the citation naming book, chapter and section, and a test comparing
against a published worked value.

**Not published:** the transcribed text, and any quotation long enough to
stand in for it.

A reader who wants to follow the derivation is pointed at the book. That
is the normal arrangement for work built on published methods.

## Summaries are cited, never substituted

A readable summary of a method — written by someone else, or generated —
is cited where it puts something more clearly. It does not replace checking
the original, and a claim traced only to a summary is a weaker claim,
marked as such.

## What this does not claim

That this is only about copyright. The same rule covers anything whose
reproduction is not ours to authorise: vendor documentation, a component
datasheet, the text of a standard. A standard's *numbers* are used and
cited; its text is not reproduced.

## Read also

- **KD5** — [correctness_is_checked_against_an_external_number](KD5_correctness_is_checked_against_an_external_number.md) — what the private material is used for
- **KD6** — [three_doc_trees_current_state_reasoning_and_decisions](KD6_three_doc_trees_current_state_reasoning_and_decisions.md) — the other reason something stays unpublished
- **KC5** — [every_exposure_limit_in_the_standard_is_implemented](KC5_every_exposure_limit_in_the_standard_is_implemented.md) — the same arrangement for standards
