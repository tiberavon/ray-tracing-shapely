---
id: C-BRIDGE-02
title: Only extrusion along a fixed axis convention, and revolution built from exact surfaces of revolution, are supported — anything else raises rather than silently building the wrong solid
parties:
  provides: optiland_scene_bridge
  relies:   optiland_nsq_viewer, optiland_nsq_run_registry, notebooks/agentic callers
port: P-NSQ-SCENE
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py::test_unsupported_symmetry_kind_raises_not_implemented; src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_spans_no_analytic_geometry_describes_raise
witness: src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py::test_unsupported_extrude_axis_raises_not_implemented; src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py::test_curved_span_raises_not_implemented; src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_the_extruded_solid_refuses_a_revolve_profile
tracked_by: null
conflicts_with: null
refines: null
rationale: null
since: 0.1
---

# C-BRIDGE-02 — Two ways of making a solid are supported, and only exact surfaces

**Assumptions.** The profile declares one of two things.

- An **extrusion** along the fixed axis this bridge uses, with every span a
  straight line between two points.
- A **revolution** about a declared axis, with every span of the
  half-section one of: a circular arc whose centre is on the axis and which
  runs from the axis outward, no further than its sphere's widest point (a
  lens face); a line across the axis or from it (a flat face, a disc); a
  line across the axis direction but away from it (a flat ring, an
  annulus); any other line (a cylinder, a cone, or a cone with its tip cut
  off).

**Guarantees.** Given that, each span becomes one of Optiland's own exact
surfaces — a sphere-shaped surface, a disc, a ring, a cylinder or cone
wall — placed and oriented correctly. Nothing is approximated by flat
facets.

**Invariants.** Any other symmetry, an extrusion along a different axis, a
curved span in an extrusion, and in a revolution an arc whose centre is off
the axis (it would revolve into a doughnut shape), an arc that does not
reach the axis (a ring-shaped zone of a sphere: Optiland's closed-solid
check cannot see its inner rim; a mirror sheet may have one, `C-BRIDGE-12`), an arc reaching past its sphere's widest point, or any curve
other than a circle — all raise `NotImplementedError`, saying which.
`ExtrudedPolygonSolid` refuses a revolve profile; `RevolvedProfileSolid`
is the class for it.

**Units and frames.** The profile's own length unit. For a revolution the
axis becomes the world z axis through the origin, and the outline's plane
the world x–z plane.

**If the assumption is violated.** Loud, by design. A revolved profile
silently built as an extrusion would be a completely different solid that
still traces.

**Checked by.** `test_scene_bridge.py::test_unsupported_symmetry_kind_raises_not_implemented`
and `test_revolve.py::test_spans_no_analytic_geometry_describes_raise`.
