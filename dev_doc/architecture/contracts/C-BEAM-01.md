---
id: C-BEAM-01
title: Beam.emis_angle is a full (total) divergence angle in [0, 180] degrees; it is not an incidence angle and is not signed
parties:
  provides: scene builders (notebooks, papermill templates) setting Beam attributes directly
  relies:   core_scene_objects (Beam.on_simulation_start)
port: P-BEAM-CTOR
viewpoint: physical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_beam_negative_emis_angle_raises
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: null
since: 0.2
---

# C-BEAM-01 — A beam's spread angle is the whole spread, from zero to 180 degrees

**Assumptions.** Whoever sets `emis_angle` on a `Beam` gives the full angle
the beam fans out across, in degrees, between 0 and 180. Not half of it.
Not an angle of incidence. Not negative.

**Guarantees.** The beam emits rays across that full angle, centred on its
direction. Internally the value is halved to a per-side angle before rays
are generated.

**Invariants.** The field is a total divergence. Nothing in the code
reinterprets it.

**Units and frames.** Degrees.

**If the assumption is violated.** Loud. A negative value used to be
accepted and silently flipped the sign of every emitted ray's brightness;
it now raises a `ValueError`.

**Checked by.** `test_detector_hit_records.py::test_beam_negative_emis_angle_raises`.
