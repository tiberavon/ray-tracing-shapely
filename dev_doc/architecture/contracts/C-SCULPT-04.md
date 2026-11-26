---
id: C-SCULPT-04
title: An edit that breaks a sculpted glass's outline, or names no handle, is refused with the reason, and the scene is left as it was
parties:
  provides: analysis_flux_tubes (sculpted_glass.SculptedGlass)
  relies:   the builder (a refused change leaves the scene unchanged), an agent applying a move, a sweep over a delta
binds: analysis_flux_tubes (sculpted_glass.py)
port: null
viewpoint: behavioural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_an_edit_that_breaks_the_outline_or_names_no_handle_is_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_a_refused_edit_in_the_builder_leaves_the_scene_as_it_was; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_a_base_that_is_not_a_designed_glass_is_refused
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_an_edit_moves_one_point_as_the_estimate_s_edit_does
tracked_by: null
conflicts_with: null
refines: null
rationale: KC2
since: 0.4
---

# C-SCULPT-04 — A broken edit is refused, not drawn

**Guarantees.** `SculptedGlass` raises `SculptError`, naming the edit and the
reason, before the glass exists, when:
- the base is not a registered recipe, is itself a sculpted glass, cannot be
  built from its arguments, or builds no glass with an outline;
- an edit names no edge of the glass, an edge that is not a spline, a point
  that is not interior (an end point is the outline's vertex, shared with the
  next edge), a kind other than ``"position"`` or ``"normal"``, or a delta that
  is not a finite number;
- after the edits, an edge's spline cannot be built, or the outline is no
  longer a simple closed curve (an edge pushed through another, a tangent
  turned until the edge crosses itself).

Through the scene file the refusal is a `SceneFileError` carrying the same
reason; in the builder it is the reply's error, and the scene is the one before
the change.

**Not refused.** A kinked but simple outline (a tangent turned by 170° on the
Example 9.1 lens): its quality is for the preview and the re-trace to judge,
not the recipe.

**Checked by.** `test_sculpted_glass.py`: each refusal by its reason, with the
scene unchanged; a refused edit sent to the builder leaves the scene file as it
was, and a valid one then applies.
