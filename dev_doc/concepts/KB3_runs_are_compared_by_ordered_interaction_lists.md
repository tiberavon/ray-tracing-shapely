---
key: KB3
title: Why runs are compared by ordered interaction lists
one_line: A path reduces to a tuple of `(surface, edge, interaction)` triples and a run to an energy-weighted distribution over those tuples, because two runs share no identifiers and their individual rays are samples.
status: active
informs: [analysis_signature, analysis_run_registry, analysis_bidirectional, C-SIG-01, C-SIG-02]
since: 0.1
---

Two runs of a simulation have nothing in common that a computer could match
up directly. Every ray and every surface gets a fresh internal identity each
time, and the rays themselves are a random sample. So the program compares
runs by *structure*: each route a ray took is reduced to an ordered list of
*(which surface, which edge of it, what happened there)*, and a whole run
becomes a table of those lists with the light energy each one carried.

## Why the numbers alone will not do

Identifiers differ between runs, so nothing can be matched by name. And
because rays are sampled, two runs of the *same* design at different
sampling densities produce different individual rays — any comparison that
depends on which rays happened to be drawn is measuring the sampler, not
the optic.

What survives both problems is structure. *Entered at the entrance face,
reflected off wall segment three, reached the absorber* means the same thing
in both runs. It is a property of the device, not of the draw.

## The route is the thing, the rays are instances

Many distinct rays reduce to one route description. That is the point: the
description is the *route*, and the rays are examples of it. A change to
the design then shows up as routes appearing, disappearing, or shifting
energy between them — which a person can read, in a way that a shift across
thousands of individual brightnesses is not.

It only works if the labels are stable and shared between runs, which is
why "names stay the same" is a checked promise rather than a habit.

## What the energies mean, and do not

They rank. A route carrying more energy than another is the more important
route. They are *not* physical amounts of light: the number comes from
brightness ratios along a path, and a run's overall scale depends on how
densely it was sampled and how the source was modelled. Reading a route's
energy as a physical efficiency is a mistake, and a written promise says so.

## What this does not claim

That structure is enough. Two designs can have identical route tables and
different performance — focus is about where rays land, and a spot size does
not appear in a list of surfaces. Structural comparison narrows the question
to *which routes exist and which carry the light*. How well any of them
performs is a separate question.

## Read also

- **KA1** — [edges_carry_a_functional_and_a_cardinal_label](KA1_edges_carry_a_functional_and_a_cardinal_label.md) — the vocabulary a signature is written in
- **KB1** — [ray_lineage_is_a_graph_not_a_hand_rolled_tree](KB1_ray_lineage_is_a_graph_not_a_hand_rolled_tree.md) — where the paths being reduced come from
- **KC3** — [physical_and_numerical_parameters_are_stored_separately](KC3_physical_and_numerical_parameters_are_stored_separately.md) — telling a real difference from a sampling artefact
