---
id: C-EYE-05
title: A classification-flow FSM's terminal result matches calling classify_measurement directly
parties:
  provides: eye_safety_classification_flow (IEC62471ClassificationFlow, IEC60825_1ClassificationFlow)
  relies:   eye_safety (iec60825_1.classify_measurement, iec62471.classify_measurement — the ground truth this contract checks against)
binds:      eye_safety_classification_flow
port: P-CLASSIFICATION-RUN
viewpoint: process
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/developer_tests/test_eye_safety_classification_flow.py::test_iec62471_flow_parity_with_classify_measurement_directly,::test_iec62471_flow_parity_hazardous_case_is_rg3,::test_iec60825_1_flow_parity_with_classify_measurement_directly,::test_iec60825_1_flow_parity_non_visible_wavelength,::test_iec62471_comparison_verdicts_match_classify_measurement_decision
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KD10
since: 0.2
---

# C-EYE-05 — The step-by-step classification gives the same answer as the direct call

**Assumptions.** The state machines that run a classification as visible
steps call the same `classify_measurement` function, once, unchanged. The
extra work the steps do — computing each hazard's limit, building an
explanation of each comparison, recording a verdict — is only for the
record. None of it feeds back into which step comes next or what the
classification function is given.

**Guarantees.** A run's final result equals what calling
`classify_measurement` directly with the same inputs returns.

**Invariants.** The narration is not a second implementation. There is one
place the verdict is decided.

**Units and frames.** As the underlying functions.

**If the assumption is violated.** Loud, by test: a recorded verdict that
disagreed with the direct call would fail the parity test.

**Checked by.** Parity tests in `test_eye_safety_classification_flow.py`
for both standards, and a test that every recorded comparison verdict
agrees with what the direct call implies for that hazard.
