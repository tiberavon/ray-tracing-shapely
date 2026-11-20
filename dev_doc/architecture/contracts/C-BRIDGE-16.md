---
id: C-BRIDGE-16
title: From profile files alone, a rayfile's 2D slice against its own records in 3D is a flow whose two traces are jobs, on any executor, and its table equals compare_slice_3d's
parties:
  provides: optiland_scene_bridge (compare.slice_main_paths_2d, trace_slice_records_3d, compare_slice_paths; compare_jobs.slice_2d_job, slice_3d_job, slice_of; slice_comparison_flow.SliceCompareFlow)
  relies:   an agent, through the generic flow tools (`compare_slice_3d` kind); a profile whose rayfile source the slicing flow wrote (`C-SOURCE-03`); an executor that runs the two jobs, here or elsewhere
port: P-COMPARISON-RUN
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_slice_comparison_flow.py::test_the_flow_gives_compare_slice_3d_table; src-python/ray_tracing_shapely_optiland/tests/test_slice_comparison_flow.py::test_an_agent_drives_it_by_name_on_worker_jobs; src-python/ray_tracing_shapely_optiland/tests/test_slice_comparison_flow.py::test_wrong_answers_are_refused; src-python/ray_tracing_shapely_optiland/tests/test_rayfile_slice_3d.py::test_meridional_records_trace_the_same_in_2d_and_3d
witness: src-python/ray_tracing_shapely_optiland/tests/test_slice_comparison_flow.py::test_every_asking_box_has_a_field
tracked_by: null
conflicts_with: null
refines: C-BRIDGE-15
rationale: KB7
since: 0.3
---

# C-BRIDGE-16 — A slice comparison from files, run as jobs

**Assumptions.**
- The profiles are solids or sheets, as for `C-BRIDGE-15`, and one of them
  carries a `rayfile` source with its `slice` (written by the slicing flow).
- The rayfile is found from that profile's folder, and is the file the
  spec recorded (its digest).

**Guarantees.**
- **Three steps, plain data.** `compare_slice_3d` is `slice_main_paths_2d`
  (every `every`-th kept ray, its 2D main path), `trace_slice_records_3d`
  (the same records, unturned, `repeats` Monte Carlo rays each, in one
  trace) and `compare_slice_paths` (the table). Its result is unchanged.
- **Two jobs.** `slice_2d_job` and `slice_3d_job` take the profiles by path,
  the source spec with its rayfile's path absolute, and the options, and
  return JSON. Each checks the rayfile against the spec's digest before
  slicing it, so a job run elsewhere slices the same file.
- **The flow.** `SliceCompareFlow` (kind `compare_slice_3d`) is the
  comparison flow (`C-BRIDGE-15`) with the rays replaced by the source:
  - **the source:** its name, or `{profile, source}`. The question's context
    lists the profiles' sliced rayfile sources. A source that is not there,
    or is not a sliced rayfile, is refused in place, saying what to give;
  - **the options:** `every` (default: enough to keep `max_compared`, 1000,
    rays), `repeats`, `max_depth`, `seed`, `max_rays_2d`;
  - **the executor, the estimate and the go-ahead:** as `C-BRIDGE-15`'s,
    the 3D side at the rayfile rate.
- **The same table.** The flow's per-ray table (`slice.json`) equals
  `compare_slice_3d`'s on the same files and options: the records, the
  offsets, the paths, the ends and the shares exactly, the angles to 1e-9,
  since the flow's 2D section is rebuilt from the profile.
- **The summary.** The rays compared; how many had 3D rays on the same
  faces; the meridional rays' (|h| within 1e-6 mm) largest exit-angle
  difference; and the difference's mean and largest in four bands of |h|.

**Invariants.** As `C-BRIDGE-15`'s: what crosses into a job is a path, a
number, a list or a source spec, never a live object.

**Units and frames.** Angles in degrees from the source's axis, h in mm.

**If the assumption is violated.** Loud: a rayfile that is not the spec's
file, or missing, is refused when the source is answered; a job that fails
ends the run `failed`, with its log's tail.

**Checked by.**
- **The flow, in process:** a revolved singlet whose profile carries a
  sliced synthetic LED; its table equal to `compare_slice_3d`'s; the
  difference growing with h.
- **Through the generic tools by name,** its jobs in worker processes.
- **The refusals** of the source and the options.
