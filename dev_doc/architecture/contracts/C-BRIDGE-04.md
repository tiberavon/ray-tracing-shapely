---
id: C-BRIDGE-04
title: ExtrudedPolygonSolid claims correctly-placed faces only, never a validated closed solid — off-plane ray motion can escape past the nominal extrusion boundary undetected
parties:
  provides: a caller placing a source/detector with any world-y component
  relies:   optiland_nsq_viewer, optiland_nsq_run_registry, notebooks/agentic callers
binds: optiland_scene_bridge
port: P-NSQ-SCENE
viewpoint: physical
status: documented
failure_mode: silent
checked_by: null
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KD3
since: 0.1
---

# C-BRIDGE-04 — The extruded solid has faces in the right places and nothing more

**Assumptions.** Anyone aiming a source or placing a detector keeps it
within the plane of the profile. A source tilted toward the extrusion
axis, even slightly, is outside what this solid promises.

**Guarantees.** The side faces are correctly placed and oriented.

**Invariants.** The solid has no end caps. It is four walls with no floor
or ceiling along the extrusion direction, and it is never checked for
being closed. Optiland's own closed-volume check would refuse it; this
solid is built as a compound of faces precisely so that check is not run.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent, and the report says otherwise.
A ray with any component along the extrusion axis eventually leaves
through the missing end. The tracer's energy-conservation figure stays at
machine precision, because it accounts for light among the surfaces it
knows about and the escaped light is simply gone. This was reproduced on
purpose with a source tilted by 0.15 radians against the same solid the
tests use.

**Checked by.** Nothing. This is a recorded limit, not a guarded one.
