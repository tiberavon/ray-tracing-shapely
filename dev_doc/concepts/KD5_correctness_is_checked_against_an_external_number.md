---
key: KD5
title: Why correctness is checked against something outside the change
one_line: A result is verified against a published table, a book's own worked example, or a previously recorded anomaly — never against a case constructed to make it pass.
status: active
informs: [nonimaging_design, eye_safety, analysis_bidirectional, C-EYE-01, C-EYE-06]
since: 0.1
---

Where something outside this project can say what the right answer is, it
is used as the judge. The geometric building blocks are tested against the
intermediate values a textbook publishes for its worked examples. The
safety limits are tested against the standards' own tables and worked
cases. A fix is checked against the actual failure it was written for.

## The trouble with testing against yourself

A test written alongside a piece of code encodes the same understanding as
the code. If that understanding is wrong, both are wrong together, and the
test passes. This is not hypothetical here: a safety comparison passed its
tests while using a limit computed for the wrong exposure duration, because
the test and the code agreed about what the duration should be.

A published number cannot agree with you like that. The textbook's value
for a construction step either matches or it does not.

## Three kinds of outside judge

- **A published number.** A worked example from the source that defines the
  method, used directly as the expected answer. Unusual and valuable — the
  reference material doubles as the test.
- **A standard's own table.** For safety limits, the table *is* the
  definition, so a value copied from it can be checked against the document
  rather than against whoever copied it.
- **A recorded failure.** Where the program once gave a wrong answer and the
  wrongness was written down, the fix is checked against that exact case. A
  detector that had been counting light from both sides was validated
  against the real, previously observed curve that had gone negative — not
  against a tidy example built to show the fix working.

## Reproduce rather than reason

Where a failure is suspected but has not been seen, it is provoked. A 3D
solid with no end caps was *shown* to leak by aiming a source along the
axis the caps would have closed, rather than argued about. The leak was
then a number, and the number was the finding.

## What this does not claim

That an outside judge is always available. Much of this program has no
published answer to check against — there is no textbook value for the
table of routes through a concentrator. Where none exists, the honest
position is that the test guards against the code changing behaviour, not
against the behaviour being wrong, and those are different claims.

## Read also

- **KD1** — [every_claim_is_marked_read_verified_or_unchecked](KD1_every_claim_is_marked_read_verified_or_unchecked.md) — how the strength of a check is recorded
- **KD9** — [transcribed_book_chapters_never_leave_the_private_repo](KD9_transcribed_book_chapters_never_leave_the_private_repo.md) — where the published numbers live
- **KC5** — [every_exposure_limit_in_the_standard_is_implemented](KC5_every_exposure_limit_in_the_standard_is_implemented.md) — the same standard, used as scope
