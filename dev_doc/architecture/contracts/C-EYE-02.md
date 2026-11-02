---
id: C-EYE-02
title: A Class 1/1M and Class 3R AEL/classification call resolves the correct IEC 60825-1 Table 4.3 time base for its own wavelength band by default; a caller is never required to know the UV/visible split to get a correct answer
parties:
  provides: eye_safety (iec60825_1.py's ael_class_1/ael_class_3r/classify_measurement)
  relies:   any caller of ael_class_1/ael_class_3r/classify_measurement (a human or an agent evaluating a real laser/lamp product)
port: P-HAZARD-ROUTINES
viewpoint: physical
status: enforced
failure_mode: loud
checked_by: >-
  src-python/ray_tracing_shapely/developer_tests/test_eye_safety.py::test_ael_class_1_uv_default_duration_matches_correct_time_base,
  ::test_ael_class_1_visible_default_duration_unaffected,
  ::test_ael_class_3r_uv_default_duration_matches_correct_time_base,
  ::test_classify_measurement_uv_default_no_longer_silently_wrong
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC5
since: 0.4
---

# C-EYE-02 — A laser classification picks the right exposure duration by itself

The laser standard's exposure limits depend on how long the eye is
exposed, and the duration to assume depends on the wavelength: 100 seconds
for visible and near-infrared, 30 000 seconds for ultraviolet. A caller
should not have to know that.

**Assumptions.** None on the caller — that is the point.

**Guarantees.** `ael_class_1`, `ael_class_3r` and `classify_measurement`
take an optional duration. Left unset, each resolves it internally to the
standard's own time base for the wavelength it was given. Set explicitly,
the caller's value is used in full. The default fills a gap; it never
overrides a choice.

**Invariants.** One function, `_resolve_class1_duration`, holds the rule.
Every caller goes through it rather than repeating it.

**Units and frames.** Nanometres and seconds.

**If the assumption is violated.** Silent, and it was. Before this
contract the default was 100 seconds regardless of wavelength, so an
ultraviolet evaluation that did not override it got a limit computed
against the wrong duration — with passing tests, because the tests shared
the assumption.

**Checked by.** Tests in `test_eye_safety.py` that an ultraviolet call
with no duration resolves to 30 000 seconds, a visible one to 100, and an
explicit duration is honoured.
