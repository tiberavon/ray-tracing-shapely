---
id: C-DET-01
title: Detector.power is signed flux, both directions by default as the JavaScript simulator's (twoSided), one side when twoSided is false; Photodetector.power is the light absorbed on its front face, never negative
parties:
  provides: core_scene_objects (Detector), optical_elements_physics (Photodetector)
  relies:   analysis_bidirectional, analysis_lineage, agentic_layer, analysis_run_registry
port: P-HIT-RECORD
viewpoint: radiometric
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_upstream_alignment.py::test_a_detector_is_two_sided_by_default_and_reads_the_signed_net_flux; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_upstream_alignment.py::test_a_one_sided_detector_is_not_met_by_rays_from_its_back; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_a_front_crossing_counts_by_default; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_non_absorbing_side_is_a_complete_no_op; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_absorbing_side_flip_recovers_the_hit; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_two_sided_restores_signed_net_flux; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_rxi_receiver_acceptance_curve_matches_15_bidirectional_3_4; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_photodetector.py::test_a_detector_reads_the_crossing_direction_as_the_sign_of_its_power; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_photodetector.py::test_a_photodetector_reads_absorbed_power_whichever_way_its_line_is_drawn; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_photodetector.py::test_a_photodetector_ignores_light_on_its_back_face; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_photodetector.py::test_a_photodetector_is_one_sided
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KB4
since: 0.2
---

# C-DET-01 — A detector counts light crossing it, with its direction; a photodetector reads what it absorbs

**Two objects, two questions.** A `Detector` is a flux probe: a line put
anywhere in a design to learn how much light crosses it, and which way. A
`Photodetector`, built on it, is a sensor: it reads the light its front face
absorbs. Both pass every ray on (`C-CORE-02`).

**Assumptions.** A detector's `twoSided` (default `true`, as the JavaScript
simulator's) says whether both crossing directions count. When it is false,
`absorbingSide` (default `+1`, a Python option) says which one does: `+1` for
light crossing from left to right of `p1 -> p2`, which is the JavaScript
simulator's only front, `-1` the other way, which is that simulator's
detector drawn the other way round. A detector used as a sensor says
`twoSided: false`, or is a `Photodetector`.

**Guarantees.**
- **`Detector`, two-sided (the default).** Every crossing enters `power`, the
  bin data and the hit records, with the crossing's sign: `power` is the net
  flux across the line, and light going both ways partly cancels. The sign is
  the information: a line in a design says how much more light goes one way
  than the other.
- **`Detector`, one-sided.** A ray arriving from the back does not meet the
  detector at all: its segment is not split there, and nothing on the
  detector changes, as in the JavaScript simulator. Crossings from the front
  count with their sign, so a front on the `-1` side reads negative. Two
  one-sided detectors on the same line, one each way, split the light by
  direction.
- **`Photodetector`.** Always one-sided (`twoSided` defaults to false and is
  refused if true). Every counted crossing adds its brightness with a plus
  sign, to `power` and to the bins, so `power` is the absorbed power: never
  negative, whichever way the line is drawn. Its hit records still carry each
  crossing's `sign`.

**Invariants.** The ray always continues through either. The side decides
only whether a crossing is counted, and, one-sided, whether the ray meets
the line at all.

**Units and frames.** `power` is a brightness-weighted sum in the engine's
dimensionless units: signed for `Detector`, non-negative for
`Photodetector`.

**If the assumption is violated.** Silent, and physically plausible. A
two-sided `Detector` read as a sensor sums light crossing in both directions
as a signed net: a receiver cavity's acceptance curve read `-5.216` at some
angles that way and sat in the record for months. The opposite mistake is as
quiet: a one-sided `Detector` drawn the other way round and given
`absorbingSide: -1` reads its light as negative power. A reading meant as
"how much light arrives" is a `Photodetector`'s.

This package's detector was one-sided by default for a while, with the keys
`two_sided` and `absorbing_side`. Those names still load, with a
`DeprecationWarning`; a scene file of version 1.0 whose detector left its side
out is read one-sided, as it meant then.

**Checked by.** `test_upstream_alignment.py`: two rays crossing a line in
opposite directions give the net flux by default, and one-sided the front's
ray only, the other ray's segment not split at the line. Tests in
`test_detector_hit_records.py` on the exact fixture that produced the
negative reading, swept across incidence angle: two-sided goes negative at
±30°, one-sided does not. Tests in `test_photodetector.py`: a `Detector` reads
light crossing its `-1` way as negative power, a `Photodetector` in the same
place as positive, one ignores its back face and refuses `twoSided`.
