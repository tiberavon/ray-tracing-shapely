---
key: KB2
title: Why tracing runs in both directions
one_line: In a concentrator only a tiny fraction of source rays reach the detector, so a second pass is emitted from the detector and joined to the forward pass at shared surfaces.
status: active
informs: [analysis_bidirectional, core_scene_objects, C-MATCH-01]
since: 0.1
---

A simulation can trace light in two directions: forward from the sources,
as usual, and *backward* from a detector. The two traces are then joined
wherever they touched the same surface, so that a complete route from
source to detector is one path through a single network.

## Why one direction is not enough

In a concentrator — an optic that gathers light from a wide range of angles
onto a small target — most rays from the source never reach the target.
Tracing forward means paying for every one that misses, and the fraction
that hits can be small enough that the useful sample is a rounding error on
the cost.

Starting from the detector turns that around. Backward rays begin where the
answer is, and they are aimed back along the directions the forward rays
actually arrived from, so the effort is spent near the routes that matter.

## The physics did not need changing

Whether a ray is entering or leaving a piece of glass is worked out from
the geometry — which side of the surface it is on — not from which way the
simulation happens to be running. So a backward ray meeting a surface from
the far side gets the right refraction with no special code. The splitting
of light into reflected and transmitted parts is the same in both
directions. This was confirmed by test rather than assumed: fire a ray,
reverse it, and it retraces its own path.

## Joining the two traces

A match is not two rays landing on exactly the same point — with rays
sampled at discrete positions, that never happens. A forward hit and a
backward hit match when they are *close* along the same surface, measured
along the surface rather than in a straight line, and when the forward
ray's next leg points *nearly opposite* to the backward ray's arrival.

How close, and how nearly opposite, are two numbers the caller supplies.
The right values depend on how densely the rays were sampled, so a helper
reports typical distances between neighbouring hits on each surface and
the numbers are chosen from the run rather than guessed.

Sampling also produces many near-identical matches for one forward ray.
Keeping all of them would make the path search return the same physical
route many times over, so the matches are thinned to one best per forward
ray before any paths are extracted.

## What this does not claim

That backward tracing replaces forward tracing. The backward rays are aimed
using where the forward rays arrived, so a forward trace has to have
happened. The two are one method, and the backward half on its own answers
nothing.

## Read also

- **KB1** — [ray_lineage_is_a_graph_not_a_hand_rolled_tree](KB1_ray_lineage_is_a_graph_not_a_hand_rolled_tree.md) — why joining two passes needs a graph rather than a tree
- **KB3** — [runs_are_compared_by_ordered_interaction_lists](KB3_runs_are_compared_by_ordered_interaction_lists.md) — what the joined paths are reduced to
- **KB4** — [quantities_computed_while_tracing_are_recorded_not_discarded](KB4_quantities_computed_while_tracing_are_recorded_not_discarded.md) — the surface geometry the match is made on
