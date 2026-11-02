---
key: KD11
title: Why boundaries carry assume/guarantee contracts
one_line: An obligation with no named holder is not an obligation, so each boundary states what it assumes, what it guarantees in return, what happens when the assumption is violated, and what checks it.
status: active
informs: [agentic_layer, analysis_run_registry, optical_elements_units, C-SYSTEM-01]
since: 0.1
---

Wherever two parts of this program meet and something important crosses
between them, there is a written **contract**: what the receiving side
assumes about what it is given, what it promises in return, what happens if
the assumption is broken, and which test — if any — checks it. Each is a
separate file with an identifier, cited from the pages on both sides of the
boundary.

## What a contract fixes that ordinary description does not

**It names who can break it.** The party that has to satisfy an assumption
is the one that can violate it, and that is often not the part of the
program the contract is *about*. A component that reads a settings file
cannot violate an assumption about that file — whoever wrote the file can.
Naming that party gives the obligation an owner, and the list of
obligations whose owner is *a person* is the list of things a user of this
software has to know.

**It names how it fails.** Loudly — an error — or silently, with a wrong
number that looks right. That one word decides where checking effort goes,
because a silent contract without a check is the next defect waiting.

**It separates what can be tested from what can only be argued.** What can
be checked becomes a contract with a test. What cannot is reasoning, and
lives here in the concepts rather than dressed up as a specification.

## Why not just describe the boundary in prose

Prose cannot say which party is obliged, cannot be walked by a program,
and drifts from the code with nothing to say so. A contract with an
identifier and a named test does not: the identifier can be searched for,
the test either exists or the contract says it does not, and a component
page listing the contracts it is party to can be checked against the
contracts themselves.

## What it is not

Not a mathematical proof, and not a formal language. There is no
verification step. The discipline is in stating the obligation precisely,
naming its owner, and pointing at the test. Borrowing the apparatus of
formal methods without the proofs would be the form without the substance.

Not every boundary, either. A contract is worth writing where something
crossing can be wrong in a way that matters. The rest is ordinary code.

## What this does not claim

That a contract with a test is reasoning. It states what must hold; the
argument for *why* it must hold usually lives in a concept, often one cited
by several contracts at once. A contract having a check does not mean its
reasoning is written down anywhere.

## Read also

- **KD6** — [three_doc_trees_current_state_reasoning_and_decisions](KD6_three_doc_trees_current_state_reasoning_and_decisions.md) — the tree contracts live in, and why this one is separate
- **KD3** — [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) — what the failure-mode field is for
- **KD12** — [the_tool_list_is_audited_before_it_is_extended](KD12_the_tool_list_is_audited_before_it_is_extended.md) — why "not every boundary"
