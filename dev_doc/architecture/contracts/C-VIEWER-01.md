---
id: C-VIEWER-01
title: build_vtk_renderer must read the caller's own configured renderer registry, never a fresh or default one
parties:
  provides: optiland_nsq_viewer
  relies:   a caller displaying a custom compound component (e.g. ExtrudedPolygonSolid) inline
port: P-NSQ-SCENE
viewpoint: structural
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_jupyter_viewer.py::test_build_vtk_renderer_matches_nsqviewer3d_registry
witness: src-python/ray_tracing_shapely_optiland/tests/test_jupyter_viewer.py::test_build_vtk_renderer_geometry_only_actor_count
tracked_by: null
conflicts_with: null
refines: null
rationale: KC7
since: 0.1
---

# C-VIEWER-01 — The viewer draws with the renderers the caller set up, not a fresh set

**Assumptions.** A caller displaying a custom solid has registered a
renderer for it in their own configuration.

**Guarantees.** `build_vtk_renderer` reads that configuration and draws
the custom solid with the registered renderer.

**Invariants.** The function never creates a new default registry. Doing
so would draw only the built-in shapes and silently omit the custom one.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent — the scene draws, minus the
solid you were looking for.

**Checked by.** `test_jupyter_viewer.py::test_build_vtk_renderer_matches_nsqviewer3d_registry`.
