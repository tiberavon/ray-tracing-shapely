---
id: C-AGENT-06
title: A targeted re-simulation goes into a new context, leaves the run it came from as it was, and is saved
parties:
  provides: 'the targeted_resimulation flow (TargetedResimulationFlow), run_targeted_resimulation'
  relies:   'the assistant comparing one path at high density against the broad run; whoever reloads the result after a restart'
binds: agentic_layer (agentic_tools.py), analysis_run_registry (targeted_resimulation.py, targeted_resimulation_flow.py)
port: P-KERNEL-CONTEXT
viewpoint: agentic
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_targeted_resimulation_flow.py::test_the_flow_makes_a_new_context_and_leaves_the_run_it_came_from; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_targeted_resimulation_flow.py::test_its_groups_are_rank_detector_paths_grouped_by_hand; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_targeted_resimulation_flow.py::test_the_bundle_reloads_after_the_kernel; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_targeted_resimulation_flow.py::test_the_density_starts_the_rays_asked; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_targeted_resimulation_flow.py::test_the_other_sources_are_silenced_and_put_back; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_targeted_resimulation_flow.py::test_left_emitting_they_stay_out_of_the_summary; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_targeted_resimulation_flow.py::test_the_segment_limit_is_sized_from_the_rays
witness: null
tracked_by: null
conflicts_with: null
refines: C-AGENT-04
rationale: KA5
since: 0.2
---

# C-AGENT-06 — One path again, at high density, beside the run it came from

The `targeted_resimulation` flow re-runs one path of a bidirectional run
alone: a narrow source where the path starts, many rays in it. It is the
case `C-AGENT-04` exists for: a run whose answers, read by mistake as the
broad run's, would look like a finding.

**Assumptions.** The context holds a live scene and a bidirectional result
with its lineages and graph (not a saved run). Nothing else uses the scene
while the re-simulation runs: by default it runs in the kernel, on the same
scene. Sent out in chunks instead (the `executor` option), the scene goes as
plain data and the result comes back mapped by name (`C-AGENT-07`).

**Guarantees.**
- **The result is a new named context, never the active one.** The context
  it came from stays active and answers as before.
- **Only the narrow source emits.** The scene's other sources are silenced
  for the run (they stay in the scene and emit nothing): the ray density is
  a scene setting, so one left emitting would emit at the raised density,
  spend the segment limit and mix its rays into the result. Sources are
  incoherent and the optics linear, so silencing them changes nothing about
  the path's own rays.
- **The summary counts only the narrow source's rays** (by `source_uuid`),
  even when the others are left emitting (`silence_other_sources=False`).
- **The scene is restored whole:** its source, the other sources'
  emission, its ray density and brightness threshold, and what its
  detectors measured. The re-simulation's
  detector hits are its result's (`SimulationResult.detector_hits`), and
  each context keeps its own (`C-AGENT-04`).
- **The rays asked are the rays started.** The option is a number of rays,
  not a density: the density is worked out from the cone so that at least
  that many start.
- **The segment limit follows the rays.** By default it is the rays times
  the source's segments per ray in the run it came from, times four; a run
  that would need more than 2,000,000 is refused, with the rays that fit. A
  limit given is kept, and the estimate says when it may truncate.
- **The cost is stated before the run, the whole of it.** A pilot of about a
  hundred of the run's own rays (sampled at the run's density, so as bright
  as the run's) runs here first and gives the segments a ray and this
  machine's seconds a segment. The estimate counts the simulation where it
  runs and the work here once the rays are back (merging, the context's
  database, saving), and shows each part. An estimate over a minute is asked;
  the estimate also names the other sources it silences.
- **The result is saved** as a run bundle in the flow's run folder
  (`C-AGENT-05`), so `load_run_context` reloads it after a restart.
- **The summary is the rays that reached the detector grouped by the
  interactions along their path**, as `rank_detector_paths` over the new
  context, grouped by hand, gives them.

**Invariants.** The new context's `run_dir` is its bundle.

**Units and frames.** The cone's half-angle in degrees; the brightness
threshold as a power of ten (`min_brightness_exp`).

**If the assumption is violated.** A saved run or a context without a
bidirectional result is refused, loudly. The other case is silent: a scene
used elsewhere while the re-simulation runs would see the narrow source in
place of the original.

**Checked by.** `test_targeted_resimulation_flow.py`: the active context,
the scene's settings and the detectors' hits are unchanged after a run, and
the new context reads its own hits; the groups equal `rank_detector_paths`
grouped by hand; the bundle reloads with the run's own detector hits; the
density starts the rays asked; with a second source in the scene, only the
narrow one's rays start and the second emits as before afterwards, and left
emitting, its rays stay out of the summary.
