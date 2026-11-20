---
id: C-AGENT-07
title: A re-simulation sent out in chunks is the run in the kernel; the scene goes as plain data and comes back mapped by name, or is refused by name
parties:
  provides: 'analysis_run_registry (portable_scene.py, ray_jobs.simulate_rays_2d_segments_job and merge_segment_results, the targeted_resimulation flow''s executors)'
  relies:   'the assistant reading a re-simulation run on local_process or Modal as it would read one run in the kernel'
binds: analysis_run_registry (portable_scene.py, ray_jobs.py, targeted_resimulation_flow.py), flows (flow_base.submit_group)
port: P-KERNEL-CONTEXT
viewpoint: numerical
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_chunks_merged_are_the_one_run; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_the_portable_route_is_the_live_route; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_a_designed_element_travels_as_its_profile; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_a_scene_that_cannot_be_mapped_back_is_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_the_job_needs_a_threshold_and_the_merge_known_names; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_the_flow_in_chunks_gives_the_kernels_result; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_an_unportable_scene_is_refused_for_the_executors_not_the_kernel
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_a_failed_chunk_ends_the_run; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_portable_resimulation.py::test_the_modal_estimate_counts_chunks_and_cost
tracked_by: null
conflicts_with: null
refines: C-AGENT-06
rationale: KA5
since: 0.2
---

# C-AGENT-07 — The same run, wherever its chunks ran

The `targeted_resimulation` flow's `executor` option sends the re-run away
from the kernel: `in_process`, `local_process` or `modal`. A live `Scene`
cannot be a job's input, and a rebuilt object has a new uuid, so the scene
goes as plain data and the segments come back to be mapped by name. This
contract says that the mapping loses nothing: the result answers as the run
in the kernel would.

**Assumptions.** Every optical object other than the sources has a name,
unique in the scene (`C-LABEL-01`). Each is a designed element (a
`BasePrism`, sent as its profile) or an object the 2D engine builds from its
own `serialize()` (glass, detectors, mirrors). The brightness threshold is
fixed (`min_brightness_exp`; the flow always sets one).

**Guarantees.**
- **The scene is checked where it is described** (`portable_scene`): each
  object is rebuilt once here and compared with the original (its
  `serialize()`, or its outline for a profile). An unnamed object, a shared
  name, or an object that does not export or does not come back the same is
  refused, naming it; the flow refuses the executor with that reason and
  offers `kernel`.
- **The chunks merged are the one run**, within the segment limit. With the
  threshold fixed, a ray dimmer than it is dropped whatever ran before, so
  the chunks' segments and detector hits, merged (`merge_segment_results`),
  are those of all the rays in one job. A run that reaches its limit is
  flagged `truncated`, and is not the truncated run in the kernel: each
  chunk stops at its own share of the limit. The limit is sized from the
  rays by default (the run's segments per ray, four times over), so a run
  is not truncated by a default; past 2,000,000 segments it is refused.
- **The portable route is the live route**, segment for segment: the same
  ends, brightness, interactions and objects hit, and the same detector
  hits, on the slab and on a designed element sent as its profile.
- **Mapped back by name, or refused.** Each segment gets a new uuid; its
  parent, the object it hit and its detector hits are mapped to the live
  scene's objects by name, and its source is the narrow source. A name the
  live scene does not have is an error, not a segment hitting nothing.
- **The job refuses no threshold** (`simulate_rays_2d_segments_job`): the
  chunks would not merge into one run.
- **The flow's result is the kernel's**: the same groups, roots and hits,
  in a new context, saved as a bundle (`C-AGENT-06`).

**Invariants.** The objects keep their order in the rebuilt scene.

**Units and frames.** The scene's own.

**If the assumption is violated.** Loud where it can be seen here: the
names, the export and the rebuild are checked before anything is sent.
Silent past that: a scene changed between the description and the merge (an
object renamed into another's name) would map hits to the wrong object.

**Checked by.** `test_portable_resimulation.py`: chunks merged against one
job; the portable route against the live one on the slab and on a
refractometer prism sent as its profile; the refusals (an unnamed and a
shared name, no threshold, a name the live scene lacks); the flow on
`local_process` and `in_process` against the kernel, its bundle reloaded;
an unportable scene refused for the executors and accepted for the kernel.
