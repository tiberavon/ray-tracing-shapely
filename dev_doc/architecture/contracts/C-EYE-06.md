---
id: C-EYE-06
title: iec62471.classify_measurement's retinal-thermal risk-group comparison uses IEC 62471's own Table 6.1 classification limits, not a duration lookup into the general-purpose MPE formula
parties:
  provides: eye_safety (iec62471.py's classify_measurement / _retinal_thermal_classification_limit_w_m2_sr)
  relies:   any caller of classify_measurement (a human or an agent evaluating a real lamp/LED product), eye_safety_classification_flow, wraps classify_measurement unchanged)
port: P-HAZARD-ROUTINES
viewpoint: physical
status: enforced
failure_mode: silent
checked_by: >-
  src-python/ray_tracing_shapely/developer_tests/test_eye_safety.py::test_retinal_thermal_classification_limit_exempt_equals_rg1,
  ::test_retinal_thermal_classification_limits_match_table_6_1,
  ::test_retinal_thermal_classification_limit_unknown_group_raises,
  ::test_risk_group_durations_no_longer_has_retinal_thermal_key,
  ::test_classify_measurement_retinal_thermal_only_uses_corrected_limits,
  ::test_classify_measurement_retinal_thermal_rg1_boundary
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KD5
since: 0.4
---

# C-EYE-06 — The lamp standard's retinal-thermal risk groups use the standard's own table

**Assumptions.** None on the caller.

**Guarantees.** `classify_measurement`'s retinal-thermal comparison uses
the emission limits from the standard's Table 6.1 for each risk group:
the same limit for the exempt group and risk group 1, and a distinct,
larger one for risk group 2. Both are obtained from the existing
`mpe_retinal_thermal` function at the durations where its formula gives
those values, so this comparison cannot drift out of step with it.

**Invariants.** A single measured radiance is compared against three
limits of the *same* physical kind.

**Units and frames.** Watts per square metre per steradian throughout.

**If the assumption is violated.** Silent, and it was. The earlier code
looked up a "reference duration" per risk group and called the general
limit function with it — including a duration for risk group 1 that had no
basis in either source — so one measured number was compared against three
different kinds of quantity with no conversion between them. Found while
adding a dimensional check to the inputs; corrected against the table.

**Checked by.** Tests in `test_eye_safety.py` that each group's limit
matches the table's value.
