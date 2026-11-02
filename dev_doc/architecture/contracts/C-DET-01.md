---
id: C-DET-01
title: Detector.power is one-sided absorbed flux by default; two_sided=True restores signed net flux as an explicit opt-in
parties:
  provides: core_scene_objects (Detector)
  relies:   analysis_bidirectional, analysis_lineage, agentic_layer
port: P-HIT-RECORD
viewpoint: radiometric
status: enforced
failure_mode: silent
checked_by: >-
  src-python/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_one_sided_absorption_is_default,
  ::test_non_absorbing_side_is_a_complete_no_op,
  ::test_absorbing_side_flip_recovers_the_hit,
  ::test_two_sided_restores_signed_net_flux,
  ::test_rxi_receiver_acceptance_curve_matches_15_bidirectional_3_4
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KB4
since: 0.2
---

# C-DET-01 — A detector counts light from one side, unless told otherwise

**Assumptions.** A detector's `absorbing_side` (default `+1`) says which
crossing direction it physically absorbs. `two_sided=True` is an explicit
choice for a genuinely two-sided sensor, not the default.

**Guarantees.** By default only crossings from the absorbing side are
counted into `power`, the bin data and the hit records. A crossing from
the other side changes nothing on the detector. `power` therefore cannot
go negative under one-sided illumination, however the geometry lets rays
cross the line.

**Invariants.** The ray always continues through the detector, whichever
side it came from. The side only decides whether the detector *counts* it.

**Units and frames.** `power` is a brightness-weighted sum in the engine's
dimensionless units. Non-negative by default; signed under `two_sided`.

**If the assumption is violated.** Silent, and physically plausible. Before
one-sided became the default, a receiver cavity's acceptance curve read
`-5.216` at some angles and sat in the record for months, because the
detector was summing light crossing in both directions as a signed net.
That fixture is the regression test.

**Checked by.** Tests in `test_detector_hit_records.py` on the exact
fixture that produced the negative reading, swept across incidence angle:
the old behaviour goes negative at ±30°, the default does not.
