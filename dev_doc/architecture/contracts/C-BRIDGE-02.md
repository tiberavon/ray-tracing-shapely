---
id: C-BRIDGE-02
title: Only extrude symmetry along a fixed axis convention, and only straight two-point spans, are supported — anything else raises rather than silently building the wrong solid
parties:
  provides: optiland_scene_bridge
  relies:   optiland_nsq_viewer, optiland_nsq_run_registry, notebooks/agentic callers
port: P-NSQ-SCENE
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py::test_unsupported_symmetry_kind_raises_not_implemented
witness: src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py::test_unsupported_extrude_axis_raises_not_implemented; test_curved_span_raises_not_implemented
tracked_by: null
conflicts_with: null
refines: null
rationale: null
since: 0.1
---

# C-BRIDGE-02 — Only one way of extruding, and only straight spans, are supported

**Assumptions.** The profile declares extrusion along the fixed axis this
bridge uses, and every span is a straight line between two points.

**Guarantees.** Given that, the faces are built and placed correctly.

**Invariants.** Any other symmetry — revolved, or extruded along a
different axis — and any curved span raise `NotImplementedError`. Nothing
is approximated.

**Units and frames.** The profile's own length unit.

**If the assumption is violated.** Loud, by design. A revolved profile
silently built as an extrusion would be a completely different solid that
still traces.

**Checked by.** `test_scene_bridge.py::test_unsupported_symmetry_kind_raises_not_implemented`.
