---
id: C-CORE-03
title: The simulator queues a new ray only above a floor that never cuts finer than the scene's own threshold, and can be set
parties:
  provides: core_simulator (Simulator)
  relies:   core_scene_objects, analysis_run_registry
port: P-RAY-LINEAGE
viewpoint: radiometric
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_simulator_new_ray_floor.py::test_a_fine_scene_threshold_is_traced_to; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_simulator_new_ray_floor.py::test_the_default_floor_is_unchanged_at_coarser_thresholds; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_simulator_new_ray_floor.py::test_an_explicit_floor_overrides_the_scene
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC1
since: 0.4
---

# C-CORE-03 — The dimmest new ray the queue keeps

**Two thresholds.** An object decides which of the rays it makes are bright
enough to keep: a glass drops a reflected or refracted ray dimmer than the
scene's threshold (`min_brightness_exp`, or the colour mode's default). The
engine then applies a floor of its own to every new ray, whatever object made
it, before queueing it. The JavaScript simulator has only the first: it queues
whatever an object returns. The floor is a safety net added in the Python
translation, for objects that do not filter (a mirror, a detector, a filter),
so near-dark rays do not fill the queue.

**Assumptions.** The scene's threshold is the dimmest light a run is meant to follow.

**Guarantees.** A new ray is queued when its total brightness is above the
floor. By default the floor is the smaller of `Simulator.NEW_RAY_FLOOR`
(`1e-6`) and the scene's threshold, read when the run starts: it never drops
a ray the scene's threshold keeps. `Simulator(new_ray_floor=...)` sets it
outright (`0` keeps every ray with any brightness); a negative value is
refused. `Simulator.effective_new_ray_floor()` says which floor a run uses.

**Invariants.** At a threshold of `10^-6` or coarser (every
`min_brightness_exp` up to 6, and the colour modes' defaults) the floor is
`1e-6`, as it always was, so those runs trace the same rays as before.

**If the assumption is violated.** Silent. Before the floor followed the
scene, it was fixed at `1e-6`, so a scene asking for `min_brightness_exp`
above 6 was traced to `1e-6` all the same: a glass slab's transmittance came
out `8e-8` short of `(1 - R)/(1 + R)` at `n = 1.3`, the third transmitted
ray dropped, with nothing to say so.

**Checked by.** `test_simulator_new_ray_floor.py`: a slab traced at
`min_brightness_exp=14` keeps `(1 - R)/(1 + R)` of the power to `1e-12`; at
6 and below the floor is unchanged; an explicit floor of `1e-3` leaves only
the direct pass.
