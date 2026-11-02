---
id: C-EYE-01
title: Hazard weighting functions are interpolated linearly on the log of tabulated values, then anti-logged, per IEC 62471 §5.3.1
parties:
  provides: eye_safety (spectral_data.py's interp_log)
  relies:   eye_safety (mpe_*/ael_* functions built on it)
port: P-HAZARD-ROUTINES
viewpoint: numerical
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/developer_tests/test_eye_safety.py (108 tests, incl. HeNe/therapy-laser/KrF-XeCl worked-example regressions)
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KD5
since: 0.3
---

# C-EYE-01 — Hazard weighting curves are interpolated on a log scale

The lamp standard gives its spectral weighting curves as tables at fixed
wavelengths. Between those points, the standard specifies how to
interpolate: on the logarithm of the values, then back.

**Assumptions.** None on the caller.

**Guarantees.** A query between tabulated wavelengths reproduces the
standard's own interpolation and matches its published worked examples to
the precision they are reported at.

**Invariants.** `interp_log` raises on a non-positive value or a
wavelength outside the table's range rather than extrapolating. A hazard
function does not guess outside its validated span. A separate, plain
linear interpolation exists for spectral *power* distributions, which are
a different quantity and may contain zeros.

**Units and frames.** Nanometres in; dimensionless weighting out.

**If the assumption is violated.** Silent — linear interpolation of a
curve that spans orders of magnitude gives a plausible wrong weight.

**Checked by.** `test_eye_safety.py`, 108 tests, including regressions
against the standard's worked examples for several laser types.
