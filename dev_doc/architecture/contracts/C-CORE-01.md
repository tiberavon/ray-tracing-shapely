---
id: C-CORE-01
title: Scene objects own their physics; the simulator only processes a ray queue
parties:
  provides: core_scene_objects (every concrete scene object)
  relies:   core_simulator (Simulator._process_rays, the sole caller)
port: P-SCENE-PROTOCOL
viewpoint: structural
status: documented
failure_mode: silent
checked_by: null
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC1
since: 0.1
---

# C-CORE-01 — Objects own their physics; the engine only moves rays along a queue

**Assumptions.** Every optical object — glass, mirror, detector, blocker,
source — answers the engine's three questions itself: *get ready*, *does
this ray hit you*, and *it hit you, what happens next*. The physics of the
answer lives inside the object.

**Guarantees.** The engine never needs to know what kind of object it is
talking to. It takes the next ray off the queue, asks each object whether
the ray hits it, takes the nearest, asks that object what happens, and puts
whatever comes back on the queue. A new kind of object that answers the
three questions works without any change to the engine.

**Invariants.** The engine decides what to do next based only on the
*shape* of the answer it gets back — nothing, one ray, or a list of rays —
and not on the object's type. One exception is documented rather than
hidden: when two glasses share a surface, the engine checks whether an
object is a glass to decide which one owns the boundary.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. An object that reaches into the
engine, or an engine that reaches into an object, would still trace rays.
It would just make the next object harder to add and the next change to
the engine riskier, with nothing to say so.

**Checked by.** Not by a test. The invariant is held by the engine's loop
being written the way it is.
