---
id: C-BRIDGE-09
title: A revolved solid is checked to be closed, with Optiland's two Volume() checks, when it is built
parties:
  provides: optiland_scene_bridge (RevolvedProfileSolid)
  relies:   optiland_nsq_run_registry, notebooks/agentic callers
port: P-NSQ-SCENE
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_a_boundary_with_a_gap_fails_volume; src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_the_parity_check_really_runs_from_the_point_given; src-python/ray_tracing_shapely_optiland/tests/test_revolve_zones_in_solids.py::test_a_solid_with_a_gap_is_still_refused
witness: src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_a_lens_becomes_two_conics_and_a_cylinder_that_pass_volume; test_flat_faces_and_steps_become_discs_and_annuli; test_a_steep_meniscus_is_validated_from_a_point_inside_it; src-python/ray_tracing_shapely_optiland/tests/test_revolve_zones_in_solids.py::test_a_conic_zone_in_a_solid_focuses_exactly; test_a_cone_with_its_tip_on_the_axis_is_a_solid; test_optilands_volume_rejects_both_solids
tracked_by: null
conflicts_with: C-BRIDGE-04
refines: null
rationale: KD3
since: 0.3
---

# C-BRIDGE-09 — A round solid is checked to be closed before any ray is traced

**Assumptions.** Optiland has a check for solids, `Volume()`. It confirms
that neighbouring surfaces meet along their edges with no gap. It also
casts rays from a point inside in many directions and confirms each leaves
the solid an odd number of times, which a closed surface always gives.

**Guarantees.** `RevolvedProfileSolid` runs that check on its faces as it
is built and keeps the result. A solid with a gap raises
`NonWatertightVolumeError` there, before it can trace and quietly lose
light through the gap.

The rays start from a point the profile proves is inside: the pole of
inaccessibility of the half-section (`interior_point(profile)`).
`Volume()` itself starts them from the mean of the rim points, which for a
steep meniscus is in the hollow, outside the glass, so `Volume()` rejects
a valid lens (`KW-OPTILAND-04`).

The bridge builds the `Volume` unvalidated and runs
its own versions of the two checks (`revolve._validated_volume`), with the
same tolerance, directions, seed and errors as Optiland's:

- **Rims meet:** every rim each face has, read from the face's own
  geometry, including a zone's inner rim and a spline surface's rims, and
  none at an end of radius 0. Optiland samples only a conic's outer rim
  (`KW-OPTILAND-07`) and treats a cone's tip as a rim (`KW-OPTILAND-06`).
- **Parity:** traced through the live faces. Optiland traces plain-conic
  copies of every conic subclass (`KW-OPTILAND-07`), which would put the
  hole of a zone, or a spline surface, back to a conic.

So a solid may have zones (conic or spline) and cone tips on its axis.

**Invariants.** Every `RevolvedProfileSolid` that exists has passed the
check.

**Units and frames.** The profile's own length unit.

**If the assumption is violated.** Loud, at construction.

**Checked by.** `test_revolve_zones_in_solids.py::test_a_solid_with_a_gap_is_still_refused`:
a stepped lens with its step removed raises. A stepped lens (a conic cap,
a step, a conic zone) and a cone on a disc build, and Optiland's own
`Volume` rejects the same faces. `test_revolve.py::test_a_boundary_with_a_gap_fails_volume`:
shrinking a lens's cylindrical edge by half a unit, so it no longer meets
the faces, raises. A meniscus with a 1.99 centre and a 5.5 rim
sag (Shafer's first element) builds, while Optiland's `Lens` refuses it;
and the same faces checked from the rim mean fail, so the check really
runs from the point given.

This is the closed-solid guarantee the extruded solid cannot give
(`C-BRIDGE-04`): Optiland's check sees an extruded solid's flat end caps
as rectangles and cannot validate them. A revolved solid is built only
from surfaces the check understands.

Status: the checks are the bridge's own versions of Optiland's, not
Optiland's functions.
