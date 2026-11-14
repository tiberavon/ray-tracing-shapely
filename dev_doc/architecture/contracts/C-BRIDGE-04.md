---
id: C-BRIDGE-04
title: An uncapped ExtrudedPolygonSolid is not a closed solid — off-plane ray motion escapes past the nominal extrusion boundary undetected by the trace; end caps close it, and the containment check finds it
parties:
  provides: a caller placing a source/detector with any world-y component on an uncapped solid
  relies:   optiland_nsq_viewer, optiland_nsq_run_registry, notebooks/agentic callers
binds: optiland_scene_bridge
port: P-NSQ-SCENE
viewpoint: physical
status: documented
failure_mode: silent
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_end_caps_and_import.py::test_containment_check_catches_the_tilted_source_leak
witness: src-python/ray_tracing_shapely_optiland/tests/test_end_caps_and_import.py::test_detector_and_caps_agree_ray_for_ray; test_end_caps_close_the_leak; test_grazing_light_tirs_off_a_refracting_cap
tracked_by: null
conflicts_with: null
refines: null
rationale: KD3
since: 0.1
---

# C-BRIDGE-04 — An open-ended extruded solid leaks off-plane light, and nothing in the trace says so

The solid this bridge builds is a prism stretched along one axis, the
*extrusion axis*. Its side walls are the outline's edges. Its two ends —
the *end caps* — are only there if asked for.

**Assumptions.** For a solid built without end caps (the default), anyone
aiming a source or placing a detector keeps it within the plane of the
profile. A source tilted toward the extrusion axis, even slightly, is
outside what that solid promises.

**Guarantees.** The side faces are correctly placed and oriented. Built
with `end_caps="refract"` or `"absorb"`, the solid is closed: both ends
are flat faces cut to exactly the outline, built from the same points as
the side faces, facing inward like them. A ray reaching an end then meets
a surface — glass it may leave through or reflect inside, or a black face
that absorbs it — instead of empty space. Whatever the solid, a trace run
with its path record on can be checked afterwards: `check_containment`
reports every ray whose path passed through an end-cap position.

**Invariants.** Optiland's own closed-solid check (`Volume`) is never run
on this solid, capped or not. It recognises a flat face only as a
rectangle or a disc, so it would judge a cap by its bounding rectangle and
refuse it; closure here is by construction, not by that check. For the
same reason a scene holding a capped solid must not be saved through
Optiland's own scene serialisation, which would also write the rectangle.

**Units and frames.** Positions in the profile's length unit. The
extrusion axis is world `y`; the caps sit at `y = ±length/2`.

**If the assumption is violated.** Silent, for an uncapped solid nobody
checks: a ray with any component along the extrusion axis eventually
leaves through the missing end. The tracer's energy-conservation figure
stays at machine precision, because it accounts for light among the
surfaces it knows about and the escaped light is simply gone. Reproduced
with a source tilted by 0.15 radians: 197 of 20,000 rays passed through an
end. `check_containment` turns this into a warning naming the count and
the flux lost; it only sees rays whose paths were recorded. With caps,
the same 197 rays reach a cap and nothing passes through.

**Checked by.** `test_end_caps_and_import.py::test_containment_check_catches_the_tilted_source_leak`
for detection; `test_end_caps_close_the_leak` and
`test_detector_and_caps_agree_ray_for_ray` for closure;
`test_caps_face_into_the_solid` and `test_grazing_light_tirs_off_a_refracting_cap`
for the caps' orientation, which, wrong, would let light out through a
cap that is present.
