---
id: C-MATCH-01
title: A forward/backward connection requires an explicit spatial and angular tolerance; there is no tolerance-free notion of "the same surface point"
parties:
  provides: whoever calls connect_trees / Simulator.run_bidirectional and chooses spatial_tolerance / angular_tolerance_deg (a design author)
  relies:   analysis_bidirectional (connect_trees, build_combined_graph), analysis_signature (signatures built from the combined graph)
binds:      analysis_bidirectional (bidirectional.py)
port: null
viewpoint: numerical
status: documented
failure_mode: silent
checked_by: null
witness: dev_doc/architecture/04_worked_example.md
tracked_by: null
conflicts_with: null
refines: null
rationale: KB2
since: 0.1
---

# C-MATCH-01 — Joining a forward and a backward ray needs two tolerances, chosen by you

**Assumptions.** A forward hit and a backward hit on the same surface are
never at exactly the same spot or exactly opposite in direction — two
independently sampled fans of rays guarantee a gap. So `connect_trees`
takes two numbers from the caller: how far apart along the surface still
counts as the same place (`spatial_tolerance`, in scene units), and how
far from exactly opposite still counts as head-on
(`angular_tolerance_deg`). Choosing them is deciding what "the same point"
means for this run, not discovering it.

**Guarantees.** With tolerances suited to the sampling density, the joined
graph contains one connection per physically distinct route, and the
route ranking is meaningful.

**Invariants.** There are defaults, and they are wrong for some sampling
densities without saying so. A helper reports typical nearest-neighbour
distances along each surface so the tolerances can be chosen from the run.

**Units and frames.** Scene length units; degrees.

**If the assumption is violated.** Silent in both directions. Too tight,
and real routes are missed. Too loose, and one route appears many times
and drowns the ranking.

**Checked by.** Nothing yet.
