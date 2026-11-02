---
id: C-LINEAGE-01
title: RayLineage is a well-founded forest — single parent, fresh uuid per segment, always registered parent-before-child
parties:
  provides: core_simulator (Simulator._process_rays, RayLineage.register)
  relies:   analysis_lineage, analysis_signature, analysis_bidirectional, svg_renderer, agentic_layer
port: P-RAY-LINEAGE
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: >-
  src-python/ray_tracing_shapely/developer_tests/test_ray_lineage.py::test_get_ancestors_raises_on_cycle,
  ::test_get_full_path_raises_on_cycle,
  ::test_get_tree_depth_raises_on_cycle,
  ::test_get_descendants_raises_on_cycle,
  ::test_get_subtree_uuids_raises_on_cycle,
  ::test_acyclic_tree_is_unaffected
witness: src-python/ray_tracing_shapely/developer_tests/test_bidirectional.py::test_backward_lineage_valid_and_acyclic
tracked_by: null
conflicts_with: null
refines: null
rationale: KB1
since: 0.1
---

# C-LINEAGE-01 — The family tree of rays is a proper tree

Every ray segment records which segment it came from. This promise is
that following those records always leads somewhere and never round in a
circle.

**Assumptions.** Every segment is registered with the lineage exactly once,
with a parent that is either *none* (it came straight from a source) or a
segment that was already registered. Every segment gets a fresh identifier
when it is created — never reused, never copied from its parent.

**Guarantees.** Following parents from any segment reaches a source in a
finite number of steps. Every segment has exactly one parent. Asking for a
segment's ancestors, its descendants, or its whole path always finishes.

**Invariants.** The engine registers a segment before that segment can
produce a child, because the queue is first-in-first-out: a child's parent
is always a segment that has already been taken off the queue and
registered. This holds for the whole tree by construction, not by a
separate check.

One detail is here because it once went wrong. When the engine hands a
segment to a detector, it passes the segment's identifier under a
*different* name, `incident_uuid`, rather than `uuid`. The helper that
turns a detector's answer back into a ray copies a `uuid` field if it finds
one — so using the plain name would have made a ray that continued past a
detector inherit its own parent's identifier and then record itself as its
own parent. Following parents from that segment never terminated.

**Units and frames.** Not applicable.

**If the assumption is violated.** Loud, now: the walk that never
terminated is the loud form. Silent would be a segment with two parents,
which nothing currently checks for.

**Checked by.** Tests in `test_detector_hit_records.py` that a recorded
identifier resolves to a real segment and that a path from a detector hit
reaches a source.
