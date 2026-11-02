---
key: KB1
title: Why the ray lineage is a NetworkX graph, not a hand-rolled tree
one_line: Ray segments form a directed graph so reachability, path enumeration and structural comparison are library calls over a standard data structure, rather than bespoke traversals this project would have to write and re-verify itself.
status: active
informs: [core_simulator, analysis_lineage, analysis_bidirectional, analysis_signature, P-RAY-LINEAGE, C-LINEAGE-01, C-SIG-01, C-MATCH-01]
since: 0.1
---

Every straight piece of a ray's path — a **segment** — records three
things: its own identifier, the identifier of the segment it came from, and
what event created it (emitted by a source, refracted, reflected, or bounced
by total internal reflection). Those three fields turn the output of a
simulation from a list into a **graph**: a network of segments joined by
"this one came from that one".

The program keeps that graph using NetworkX, a standard library for working
with networks. It is a required dependency, not an optional one.

## What was considered and turned down

A home-made version — a lookup from each segment to its parent, and a
hand-written shortest-path search over it — would have served the first
device this project studied. A refractometer is a fixed arrangement of
glass with one number, an angle, sliding through it. The *shape* of the ray
paths barely changes from run to run, so almost any search would do.

That device is the easy case, and building for it would have meant building
for the easy case. Two ordinary questions in optics need real network
algorithms:

- **Does a concentrator collect light at this input angle?** That is a
  *reachability* question: is there any path from a source to the absorber?
  *How well* it collects is a distribution of path lengths — how many wall
  bounces before the exit. Light being rejected is a path that ends back at
  the entrance instead. Three different questions, three standard library
  calls.
- **Is an imaging lens in focus?** Trickier, and it is the question that
  argues for tracing in both directions. Traced forward only, the network
  has the same shape in and out of focus — focus is about *where* rays land,
  not *which* rays connect. But the imaging relationship itself is a network
  between object points and pixels: in focus, each pixel's backward fan
  connects to rays converging from one object point; out of focus, from
  several.

Neither is a shortest path. Writing those algorithms by hand would mean
writing them *and* proving them correct, against a library where both are
already done.

## Why a network rather than a tree

A tree — one parent, many children — is accurate for a single forward
trace. It stops being accurate the moment a backward trace is joined on:
connecting the two produces segments with more than one predecessor, which
a tree cannot hold. Add one artificial starting point in front of every
source and one artificial end behind the detector, weight each connection
by how much brightness was lost across it, and "the route carrying the most
light from any source to the detector" becomes a single shortest-path
query. That needs a weighted network.

The same thing shows up elsewhere: a beam splitter gives one segment two
successors; some elements give one segment two predecessors. A tree holds
neither.

## What the network is for beyond finding paths

The raw record of every segment is too large to read. What a reader wants
is a *filtered* view — only the paths reaching the absorber, only the ones
being rejected, only the ones carrying more than some fraction of the light
— and that vocabulary exists only if the record is a network to begin with.

It also makes runs comparable. Each segment carries stable descriptive
labels rather than only this run's internal identifiers, so a path
collapses to a list of *(surface, edge, what happened)* and a whole run
collapses to a table of those lists with the energy each carried. That
reduction is a concept of its own, and it is only reachable from here.

## Where the idea came from

Three ray tracers in other fields settled on the same representation, each
contributing a distinct idea:

- **Geant4**, used in particle physics, records the history of every
  particle as a network and gets its analytical value from *isolating
  sub-networks* — showing only the tracks that deposit energy in a chosen
  volume.
- **femtoPro**, used for ultrafast lasers, builds its whole engine on a
  network solver, with optical elements as nodes and beam segments as
  connections, and keeps enumeration finite in mirror cavities by capping
  the number of reflections.
- **PyLayers**, used for radio propagation, uses NetworkX directly and
  supplies the sharpest idea: a *signature*, the ordered list of surfaces a
  path touches, under which many distinct rays are one and the same route.

## What this does not claim

That the network is the physics. It is bookkeeping over a simulation whose
correctness lives elsewhere — in how surfaces bend and split light. A
perfectly well-formed network built on wrong physics is quietly wrong,
which is why the structural properties that *can* be checked are checked
as separate promises.

## Read also

- **KB2** — [tracing_runs_forward_from_sources_and_backward_from_the_detector](KB2_tracing_runs_forward_from_sources_and_backward_from_the_detector.md) — the second pass that makes a tree insufficient
- **KB3** — [runs_are_compared_by_ordered_interaction_lists](KB3_runs_are_compared_by_ordered_interaction_lists.md) — the reduction this representation makes possible
- **KB4** — [quantities_computed_while_tracing_are_recorded_not_discarded](KB4_quantities_computed_while_tracing_are_recorded_not_discarded.md) — what the nodes have to carry for any of it to work
