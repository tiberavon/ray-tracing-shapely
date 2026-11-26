---
id: C-SCULPT-03
title: A sculpted glass with no edits is its base recipe's glass, and with edits it is rebuilt from the base and the edits alone
parties:
  provides: analysis_flux_tubes (sculpted_glass.SculptedGlass)
  relies:   the scene file and every reader of a scene (the builder, the tubes' and bundles' scene copies, a sweep), and whatever names an edge by its label (C-LABEL-01)
binds: analysis_flux_tubes (sculpted_glass.py)
port: null
viewpoint: behavioural
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_with_no_edits_the_glass_is_its_base; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_the_scene_file_holds_the_edits_and_rebuilds_the_glass; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_an_edit_moves_one_point_as_the_estimate_s_edit_does
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_tubes_cut_on_a_sculpted_lens_replay_exactly; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_sculpted_glass.py::test_the_builder_moves_a_sculpted_glass_whole_by_its_base
tracked_by: null
conflicts_with: null
refines: null
rationale: KC2
since: 0.4
---

# C-SCULPT-03 — A sculpted glass is its base plus its edits, and nothing else

**Assumptions.** The base is a registered recipe that builds a glass with an
outline. Each edit names a spline edge (by its functional label or index), an
interior Hermite point, a kind (``"position"`` or ``"normal"``) and a delta.

**Guarantees.**
- With an empty edit list the glass has its base's outline, functional labels,
  roles, mechanisms and index, and the same profile (`export_profile`).
- An edit changes exactly one point (along the glass's outward normal there, by
  delta in scene units) or one tangent (turned counter-clockwise by delta
  degrees): the edit `first_order.edited_path` makes for the same handle. Edits
  apply in order.
- The scene file holds the base and the edit list, not the edited outline;
  reading it rebuilds the same glass. Changing a delta in the file changes the
  shape accordingly, so edits can be swept as any argument (`KD8`).
- The labels, roles and mechanisms are the base's, so a route or a handle names
  the same edge before and after an edit (`C-LABEL-01`).
- Moving the glass whole moves its base's placement; the edits, being along
  its own normals and of its own tangents, are unchanged.

**Checked by.** `test_sculpted_glass.py`: the empty edit list against the base
`RRLens` (outline, labels, roles, mechanisms, profile); one edit against
`first_order.edited_path`; the file round trip and a delta changed in it.
Witnesses: tubes cut on a sculpted lens replay exactly through the tubes'
own scene copy; the builder's move.
