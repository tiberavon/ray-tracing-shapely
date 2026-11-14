---
id: C-BRIDGE-14
title: The same meridional rays are traced in 2D and as 3D pencils, their faces named alike on both sides, and every ray whose 3D rays never follow its 2D main path is reported, with both paths
parties:
  provides: optiland_scene_bridge (compare.compare_2d_3d, events.split_rays)
  relies:   pilots and tests that check a 2D design exported to 3D; agentic_layer (compare_2d_3d_summary)
port: P-NSQ-SCENE
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_compare_2d_3d.py::test_a_revolved_lens_traces_the_same_ray_by_ray; src-python/ray_tracing_shapely_optiland/tests/test_compare_2d_3d.py::test_a_different_3d_lens_is_reported; src-python/ray_tracing_shapely_optiland/tests/test_compare_2d_3d.py::test_a_revolved_mirror_sheet_traces_the_same; src-python/ray_tracing_shapely_optiland/tests/test_compare_2d_3d.py::test_plates_without_a_profile_trace_the_same
witness: src-python/ray_tracing_shapely_optiland/tests/test_compare_2d_3d.py::test_span_at_and_bad_names
tracked_by: null
conflicts_with: null
refines: null
rationale: KB7
since: 0.3
---

# C-BRIDGE-14 — A 2D design and its 3D export trace the same rays alike, ray by ray, or the comparison says which rays do not

**Assumptions.**
- The rays are meridional: each is given in the 2D scene as a start point
  and an angle.
- The caller says which 3D component each 2D object became.
- A bridge-built component keeps its `profile`. A component without one
  (a `PlanarPlate`) has exactly one face.

**Guarantees.**
- **Both sides traced alike.**
  - **2D:** each ray is traced alone, with surface hits recorded; at every
    split the brighter child is followed (its main path).
  - **3D:** the same ray is a pencil source at the mapped place
    (x = a, y = c, z = b), traced by Monte Carlo; the rays are split out of
    the event log by `events.split_rays`, which needs no VTK (`KC7`).
- **Faces named alike.** Both sides name a face `<component>.<label>`, as
  the event log does. A 2D hit takes the label of the profile span whose
  outline lies nearest the hit point, mirrored onto the stored half for a
  revolved profile. A plate's face is its one face. A 2D blocker records
  where it absorbs a ray, so a ray ends on it in both engines.
- **Agreement.** A ray agrees when more than `min_share` of its pencil's 3D
  rays met the 2D main path's faces in order and ended as it did (escaped,
  or absorbed at the same face). The default is any. For those rays the
  exit direction and exit point are compared, at the last event or on a
  given plane.
- **The summary.**
  - **Always:** the worst direction and point differences, and the least
    share on the 2D path.
  - **Rays that differ:** listed with both paths, the 2D main path and the
    commonest 3D one.

  `compare_2d_3d_summary` returns this summary and never the per-ray table
  (`KA8`).

**Invariants.** Each ray is in exactly one of agree and differ. Every face
name on either side is a face the 3D components log, or is marked
`2d:<uuid>` for a 2D object the caller did not name.

**Units and frames.**
- **2D values:** in the 2D scene.
- **3D values:** in the world, in millimetres.
- **Directions:** compared as unit vectors in the world, component by
  component, so a difference out of the plane counts.

**If the assumption is violated.** Loud.
- **A 2D name that is not a 3D component:** refused.
- **A component without a profile and with several faces:** refused, since
  its hits cannot be named.
- **A 3D component that is not the 2D object's export:** 2D hits are named
  after its nearest faces, and the rays that differ are reported. That is
  the point of the comparison.

**Checked by.**
- **Three exports, each against its own 2D source:** a revolved singlet
  (rays below the axis too), a revolved V of two mirrors, the same V as two
  plates. Every ray agrees to below 1e-9 in direction.
- **Two wrong 3D lenses:**
  - a different back radius gives the same faces and directions off by more
    than 1e-3;
  - a smaller semi-diameter makes the rays that miss it differ, listed with
    an empty 3D path.
- **In the pilots:**
  - the cone concentrator, the Shafer triplet and the projector headlamp
    agree on every ray;
  - in the LED collimator, the only rays that differ meet the mount, which
    2D refracts through and 3D absorbs.
