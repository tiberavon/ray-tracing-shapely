---
id: C-EYE-04
title: IEC 60825-1 (laser) and IEC 62471 (lamp/LED) hazard functions are separate formula families and must not be conflated
parties:
  provides: eye_safety (iec60825_1.py, iec62471.py — both accessed via submodule, neither flattened)
  relies:   agentic_layer (planned,, any caller choosing which module to call
port: P-HAZARD-ROUTINES
viewpoint: physical
status: enforced
failure_mode: silent
checked_by: >-
  src-python/ray_tracing_shapely/developer_tests/test_eye_safety.py::test_iec62471_no_namespace_collision_with_iec60825_1,
  ::test_worked_example_d1_21_uva_blacklight_limits_match_guide,
  ::test_worked_example_d1_22_streetlight_limits_match_guide
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC6
since: 0.6
---

# C-EYE-04 — The laser standard and the lamp standard are never mixed

**Assumptions.** A caller knows whether the source is a laser (IEC
60825-1) or a lamp or LED (IEC 62471), and calls the matching module.

**Guarantees.** Each module uses its own standard's wavelength bands,
formulas and angular conventions throughout. No constant from one appears
in a calculation from the other.

**Invariants.** The two disagree on things that look identical. The
smallest angular size considered is 1.5 milliradians in one and 1.7 in the
other. The blue-light band is 400–600 nm in one and 300–700 nm in the
other. The lamp standard has a measurement field-of-view the laser
standard lacks entirely. None of these is a typo to reconcile. Neither
module is reachable at the package top level; each is called by name.

**Units and frames.** Both use W/m², W/(m²·sr), J/m² and milliradians —
the unit labels match exactly, which is what makes mixing them dangerous.

**If the assumption is violated.** Silent. A limit computed with one
standard's constant in the other's formula has the right unit and a
plausible size.

**Checked by.** Tests in `test_eye_safety.py` that each module's constants
are its own, and that neither function is exported at the top level.
