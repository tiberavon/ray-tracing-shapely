---
id: C-BRIDGE-15
title: From profile files alone, a 2D-against-3D comparison is a flow whose two traces are jobs; a revolve profile's section, or a sheet's mirrors, rebuilt in 2D trace as the design they were exported from, and the flow's table equals compare_2d_3d's
parties:
  provides: optiland_scene_bridge (compare_jobs.trace_2d_job, trace_3d_job; compare.trace_pencils_3d, compare_paths; comparison_flow.Compare2D3DFlow); nonimaging_design (BasePrism.from_profile, mirrors_from_sheet_profile)
  relies:   an agent, through the generic flow tools (`compare_2d_3d` kind); an executor that runs the two jobs, here or elsewhere
port: P-COMPARISON-RUN
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_from_profile_pilots.py::test_the_rebuilt_section_traces_as_the_design; src-python/ray_tracing_shapely_optiland/tests/test_from_profile_pilots.py::test_the_rebuilt_sheet_traces_as_the_design; src-python/ray_tracing_shapely_optiland/tests/test_comparison_flow.py::test_a_mirror_sheet_compares_given_its_reflectance; src-python/ray_tracing_shapely_optiland/tests/test_comparison_flow.py::test_the_traces_on_modal_give_the_same_table; src-python/ray_tracing_shapely_optiland/tests/test_comparison_flow.py::test_a_solid_with_a_mirror_face_compares_given_its_reflectance; src-python/ray_tracing_shapely_optiland/tests/test_from_profile_pilots.py::test_the_rebuilt_sms_element_traces_as_the_design; src-python/ray_tracing_shapely_optiland/tests/test_comparison_flow.py::test_the_flow_gives_compare_2d_3d_table_in_process; src-python/ray_tracing_shapely_optiland/tests/test_comparison_flow.py::test_an_agent_drives_it_by_name_and_waits_on_worker_jobs; src-python/ray_tracing_shapely_optiland/tests/test_comparison_flow.py::test_wrong_answers_are_refused_or_sent_back
witness: src-python/ray_tracing_shapely_optiland/tests/test_comparison_flow.py::test_an_estimate_over_the_minute_is_asked; src-python/ray_tracing_shapely_optiland/tests/test_from_profile_pilots.py::test_the_sheet_rebuild_joins_what_the_axis_cut; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_conic_mirror.py::test_a_rebuilt_paraboloid_is_one_mirror_with_its_focus; src-python/ray_tracing_shapely_optiland/tests/test_comparison_flow.py::test_every_asking_box_has_a_field_and_one_trigger
tracked_by: null
conflicts_with: null
refines: C-BRIDGE-14
rationale: KB7
since: 0.3
---

# C-BRIDGE-15 — A comparison from files, run as jobs

**Assumptions.**
- Each profile is a solid (`body` absent or `"solid"`), revolved or
  extruded, given with its refractive index, and with a reflectance as well
  if it has mirror-coated (`reflect`) spans; or a revolved mirror sheet
  (`body: "sheet"`), given with its reflectance. A profile carries neither.
- The rays are meridional, given in the 2D scene, as for `C-BRIDGE-14`.
- The jobs run where both packages are installed and the profile files can
  be read.

**Guarantees.**
- **The 2D side is the file's.** Each solid's section is rebuilt by
  `BasePrism.from_profile`: a revolve profile's half-section is mirrored
  about its axis and a face the axis cut is joined. Each sheet's mirrors are
  rebuilt by `mirrors_from_sheet_profile`: a line as a `Mirror`, a conic as
  a `ConicMirror`, a circle as a `CircularArcMirror`, the far side mirrored unless
  the azimuth cut removes it, and a curve or flat mirror the axis cut
  joined. The rebuild of each element of the revolved pilots, solid or
  sheet, traces as the design it was exported from: the same faces, the
  same end, the exit point to 1e-6 mm and the exit direction to 1e-9, ray
  by ray.
- **The 3D side is the file's.** A revolve profile becomes a
  `RevolvedProfileSolid`, an extruded one an `ExtrudedPolygonSolid`, in an
  ideal glass of the given index; a sheet a `RevolvedProfileSheet` of the
  given reflectance. A 2D mirror reflects everything, so a reflectance
  below one lowers the 3D share on the 2D path, not the path.
- **Two jobs, plain data.** `trace_2d_job` (the 2D main paths) and
  `trace_3d_job` (the 3D pencils) take the profiles by path, the rays and the
  options, and return JSON. The 2D job needs no Optiland. `compare_paths`
  puts their results together, and `compare_2d_3d` is the same three steps
  in one call.
- **The flow.** `Compare2D3DFlow` (kind `compare_2d_3d`, registered by the
  satellite's `agentic.register()`) asks for the profiles, the rays (or
  fans), the options and the executor (a worker process here, this
  process, or a Modal container: `modal`, refused where the Modal client is
  not installed, its estimate counting Modal's start-up and speed, with a
  cost). Each answer is checked where it
  enters (`C-FLOW-02`). A profile that cannot be built in both engines sends
  the flow back with the reason. The traces are boxes of their own, each
  following its job's handle (`C-FLOW-01`). An estimate over the minute a box
  may spend without asking is asked first, and "no" goes back to the
  options.
- **The same table.** On the same files, rays and options, the flow's
  per-ray table (`rays.json` in the run's folder) and summary
  (`result.json`) equal `compare_2d_3d`'s, whether the jobs ran in process,
  in worker processes or on Modal.

**Invariants.** The flow never holds a callable or a live object between
boxes that a job needs: what crosses into a job is a path, a number or a
list.

**Units and frames.** As `C-BRIDGE-14`: 2D values in the 2D scene, 3D
values in the world, mm.

**If the assumption is violated.** Loud.
- **A solid given a reflectance, or a sheet an index:** sent back at
  loading, "give it ...". Both, or neither, are refused where the answer
  enters.
- **A profile that does not build:** `from_profile`'s or the solid's own
  error, as the reason the flow was sent back.
- **A job that fails:** the run ends `failed`, with the job's error and its
  log's tail.

**Checked by.**
- **The rebuild, on the pilots:** the Shafer triplet's three singlets, the
  ACL25416U asphere, the US 7,762,697 TIR collimator from its focal point,
  and the US 7,255,467 headlamp's dome and lens; and the sheets: the cone
  reflector's V, the headlamp's ellipsoidal reflector (a cap short of the
  axis and a zone) cut to its upper half and whole, and a spherical mirror
  facing a flat one across the axis. Each is exported, sent through JSON,
  rebuilt, and traced against the original.
- **The flow, on a revolved V of two mirrors:** in process, its table equal
  to `compare_2d_3d`'s, every ray agreeing.
- **The flow, on a revolved singlet:** in process, its table equal to
  `compare_2d_3d`'s; through the generic tools by name, its jobs in worker
  processes, waited on with `flow_wait`, the run unflagged in `flow_list`.
- **The refusals:** profiles, rays and options of the wrong shape refused in
  place; a sheet given an index, and a solid a reflectance, sent back.
