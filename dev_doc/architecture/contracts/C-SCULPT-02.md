---
id: C-SCULPT-02
title: The first-order change of a ray's optical path length and direction, for a small move of a designed surface, agrees with a re-trace to second order
parties:
  provides: analysis_flux_tubes (first_order.predict, first_order.turn_factor, edge_bundles.predict)
  relies:   a live preview of an edit (the builder's sculpt mode, an agent's preview of a move), which shows the estimate instead of tracing
binds: analysis_flux_tubes (first_order.py, edge_bundles.py)
port: null
viewpoint: behavioural
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_first_order.py::test_the_change_of_s_is_right_to_first_order; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_first_order.py::test_the_turn_of_the_outgoing_ray_is_right_to_first_order_curvature_included; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_first_order.py::test_a_flat_mirror_tilted_turns_the_reflection_by_twice_the_tilt; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_first_order.py::test_a_flat_glass_face_tilted_turns_the_refraction_as_snell_says; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_edge_bundles.py::test_the_first_order_of_s_to_the_target_is_right
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_first_order.py::test_an_arrival_that_misses_the_edge_is_unchanged
tracked_by: null
conflicts_with: null
refines: null
rationale: KD5
since: 0.4
---

# C-SCULPT-02 — A preview is the first order of the re-trace

**Assumptions.** The move is of an interior Hermite point of a spline edge: a
point along the glass's outward normal, or its tangent turned. The ray keeps
its route: the same surfaces and edges, the same events. The move is small:
its drag ratio (the move over the shorter adjacent chord, or the turn in
radians) is below `PREVIEW_LIMIT` for the estimate to be read as a number.

**Guarantees.**
- **Path length.** For each ray that meets the moved edge, the estimate of S at
  the ray's old end point is the sum, over its hits on that edge, of
  ``(p_in - p_out) . dx``. Here dx is the surface's displacement at the hit,
  taken from the spline itself, the chord rescaling of its tangents included.
  Against a re-trace, with S brought back to the old end point along the
  receiver, the residual is second order: it quadruples when the move doubles.
  Its size relative to the largest change, per unit drag ratio, measured on the
  Example 9.1 RR lens (top surface, receiver at R2's focus): 12 for a point
  moved, 11 for a tangent turned. The test holds it below 15.
- **Direction.** The outgoing direction turns by
  ``dphi (1 - n1 cos t1 / (n2 cos t2))`` at a refraction and ``2 dphi`` at a
  reflection. Here dphi is the normal's turn where the ray now meets the moved
  surface: the turn at the hit's parameter plus the curvature times the hit's
  parameter shift. The residual is second order (relative 2.7e-4 at a drag
  ratio of 4e-4). Without the curvature term the error would be first order
  (2e-2, whatever the move).
- **S to a target point** (an edge bundle's ray, `edge_bundles.predict`). The
  change of S completed to the target is ``(p_in - p_out) . dx`` at the entry
  when the entrance moves, plus ``(p_glass - p_t) . dx_exit`` at the exit, p_t
  the momentum toward the target and dx_exit the exit point's whole movement
  (the inside ray shifted and turned, the exit surface moved). No end-point
  correction is needed: the target is fixed. The residual is second order
  (×4.00 per doubling, every handle measured). Relative error per unit drag
  ratio, on the Example 9.1 lens: 4–29 for a point of the entrance surface
  moved, 9–92 for its tangent turned (the inside ray turns, and the lens's
  thickness is its lever arm); 0.1–0.6 on the exit surface. The tests hold
  them below 120 and 1. Without the exit's slide the error is first order
  where the ray is aberrated (near the axis, ×2 per doubling).
- **Flat surfaces.** A flat mirror tilted by dphi turns the reflection by
  2 dphi, and a flat glass face turns the refraction by Snell's factor. Both
  are checked against real traces to 1e-6.
- A ray that does not meet the moved edge is estimated unchanged.

**Invariants.** Nothing is traced: the estimate reads the hits recorded when
the tubes were cut (`C-SCULPT-01`).

**Units and frames.** Lengths in scene units; turns in radians,
counter-clockwise; a ``"normal"`` handle's move in degrees.

**If the assumption is violated.** Silent: past the limit the estimate is
only qualitative. On this lens, at a drag ratio of 0.02, it still correlates
at 0.99 with the re-trace and is within about 20% in size; by 0.05 a sign can
be wrong. A ray that changes route is not estimated. Only the re-trace on
release (`flux_tubes.replay`) gives the answer there.

**Checked by.** `test_first_order.py`: finite differences on the RR lens, at
delta and 2 delta, for both kinds of handle; flat mirror and glass traces.
