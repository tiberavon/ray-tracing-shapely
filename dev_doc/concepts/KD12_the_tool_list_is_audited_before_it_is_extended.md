---
key: KD12
title: Why the tool list is audited before it is extended
one_line: One maintainer carries every tool, contract and concept permanently, so the existing surface is inventoried before being added to, and a superseded name is deprecated rather than removed.
status: active
informs: [agentic_layer, analysis_run_registry, optiland_scene_bridge]
since: 0.1
---

Everything this project exposes — every tool an assistant can call, every
written promise, every one of these concepts — is carried by one person,
for as long as it exists. A tool has to keep working. A promise has to
keep being true. A concept has to keep describing the code. That makes
adding anything a decision, not a reflex.

## Look at what is there before adding to it

Before a new tool is designed, the existing ones are listed and examined
for what already covers the need. When the tool list passed twenty
entries, it was audited this way before anything was added: the audit found
four tools that a newer one had made redundant, and three convenience tools
worth keeping for a stated reason.

The audit is cheap and its findings are not obvious. Whether three
"filter and draw" shortcuts duplicate a general tool is a judgement, and
making it on purpose leaves a recorded decision instead of an unexamined
pile.

## Retire by hiding, not by deleting

A tool that a newer one has replaced is marked so nothing new reaches for
it, and left in place. Deleting a published name breaks any assistant
configuration that still holds it, and the gain is a slightly shorter list.
Making it less visible achieves the real goal — steering new use elsewhere
— at no cost to anyone.

## Refuse the near-duplicate

A second component was once proposed whose name differed from an existing
one only in word order. It was refused; the existing one gained a second
entry point instead. The two names would have been indistinguishable in
conversation, in code, and in a search, forever, in exchange for a
tidier-looking split on the day.

## The same guard, three times over

The rule generalises. The tool list, the list of contracts, and this list
of concepts all fail the same way — too many entries to hold in one head,
each individually defensible. Each has the same guard: a written test for
inclusion, applied at the moment of adding, so that adding something means
saying why it passes.

## What this does not claim

That fewer is always better. A list too short to be useful is its own
failure, and one of these lists has already been cut and then partly
restored when a second user for a removed entry turned up. The rule is
that addition is *argued*, not that it is resisted.

## Read also

- **KA7** — [a_tool_is_registered_in_three_places_or_it_is_unreachable](KA7_a_tool_is_registered_in_three_places_or_it_is_unreachable.md) — the counterweight pushing the other way
- **KD11** — [component_boundaries_carry_assume_guarantee_contracts](KD11_component_boundaries_carry_assume_guarantee_contracts.md) — the second surface this guards
- **KD6** — [three_doc_trees_current_state_reasoning_and_decisions](KD6_three_doc_trees_current_state_reasoning_and_decisions.md) — why the third one exists at all
