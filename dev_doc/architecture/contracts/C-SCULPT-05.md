---
id: C-SCULPT-05
title: Map A's optical path length is summed with the index each segment carries; a segment without one is reported and its ray left out, never counted with n = 1
parties:
  provides: analysis_flux_tubes (edge_bundles.edge_bundles, edge_bundles.trace_bundles)
  relies:   whoever reads Map A to judge or sculpt an SMS design (the builder's sculpt layer, an agent's sculpt report)
binds: analysis_flux_tubes (edge_bundles.py)
port: P-RAY-LINEAGE
viewpoint: behavioural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_edge_bundles.py::test_a_segment_without_an_index_is_reported_not_counted; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_edge_bundles.py::test_refusals_say_why
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_edge_bundles.py::test_rays_through_designed_points_have_the_designs_s
tracked_by: null
conflicts_with: null
refines: null
rationale: KD5
since: 0.4
---

# C-SCULPT-05 — Map A reads every index, and assumes none

**Assumptions.** The bundle's rays are traced by the simulator, whose segments
carry `medium_index` (`P-RAY-LINEAGE`). No gradient-index glass is in the
scene: its segments carry the index of the medium they started in, not the
one they travel through.

**Guarantees.**
- A bundle ray's S is the sum, over its segments up to the exit point, of the
  segment's own `medium_index` times its length, plus the target medium's
  index times the distance from the exit point to the target.
- A segment that carries no `medium_index` is not given 1. Its ray's S is
  None, the positions of such segments are listed in the ray's
  `unindexed`, and the ray is out of the bundle's mean, spread and Map A. The
  bundle set's `map_a()` lists those rays per bundle.
- A scene holding a gradient-index glass is refused before anything is traced,
  with the reason.

**Why.** `lineage_analysis.optical_path_length` falls back to n = 1 for a
segment without an index, silently. In Map A that would be a wrong colour of
the size of (n − 1) times the segment's length: far larger than the spreads
Map A is read for (2.8e-4 on the Example 9.1 lens).

**Checked by.** `test_edge_bundles.py`: a segment's index removed inside the
lens is reported and its ray is out of the map; the gradient-index refusal.
The witness: on the unedited lens, the rays through the designed points have
the design's S to 1e-12, which a wrong index anywhere would break.
