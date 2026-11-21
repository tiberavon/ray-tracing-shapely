---
id: C-PLUGIN-01
title: An sms_spline surface is its profile span's own curve, from the axis to the rim, or the profile is refused
parties:
  provides: optiland_sms_plugin (meridian.read_meridian, geometry.SMSSplineGeometry)
  relies:   a sequential Optiland system built from a profile.json; whoever compares its trace with the 2D design's
port: P-OPTILAND-PLUGIN
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/optiland_sms/tests/test_geometry.py::test_the_sag_and_normal_are_the_profiles_at_its_samples; src-python/optiland_sms/tests/test_geometry.py::test_the_sag_is_the_profiles_curve_between_its_samples; src-python/optiland_sms/tests/test_meridian.py::test_what_the_reader_refuses; src-python/optiland_sms/tests/test_meridian.py::test_a_meridian_whose_radius_turns_back_is_refused; src-python/optiland_sms/tests/test_geometry.py::test_optiland_finds_the_surface_type_by_entry_point
witness: src-python/optiland_sms/tests/test_geometry.py::test_a_trace_takes_e1s_rays_to_r2; src-python/optiland_sms/tests/test_meridian.py::test_both_faces_run_from_the_axis_to_the_rim_with_the_curves_own_vertex
tracked_by: null
conflicts_with: null
refines: C-PROFILE-01
rationale: KB7
since: 0.4
---

# C-PLUGIN-01 — An `sms_spline` surface is the profile's own curve

**Assumptions.** The profile is a revolve profile (a full turn) whose schema
the reader knows. The named span is a spline (`C-PROFILE-01`, schema 1.2 and
later) that runs from the axis to its rim, with its radius strictly monotonic
along it: one surface, one span.

**Guarantees.**
- **The shape is the profile's.** The surface's meridian is the span's cubic
  Hermite curve itself, not a second curve fitted through its points. At the
  profile's samples, the sag agrees to 1e-15 and the normal's direction to
  1e-13 rad; densely along the curve, the sag agrees with the curve to
  1e-15. Measured: 3e-16, 2.5e-14 rad and 2e-16.
- **The vertex is the curve's.** It is where the curve meets the axis, which
  lies between its points: the reader reports it (`Meridian.vertex`,
  `vertex_along_axis`), and a system's thicknesses are taken from it. Taken
  from the nearest points instead, the RR's exit face would be misplaced by
  8e-4.
- **Found by entry point.** Optiland creates `surface_type="sms_spline"`
  without the package being imported.
- **Beyond the rim** the sag continues along the rim's tangent, so a Newton
  iterate there sees a smooth surface; the surface's aperture, set to its rim
  radius by whoever builds the system, limits the rays.

**Units and frames.** The profile's units. The surface's local z runs along
the profile's axis direction, or against it with `reverse`; r is the
distance from the axis on the half-section's side.

**If the assumption is violated.** Loud: `read_meridian` raises a ValueError
naming the reason:
- a schema it does not know;
- a profile that is not a revolve, or covers only part of a turn;
- a label that names no span, or more than one;
- a span that is not a spline;
- a span with neither end on the axis (a surface made of more than one span);
- a radius that turns back along the span.

**Checked by.** The shape at the samples and along the curve, the refusals,
and the entry point, on the RR lens of Chaves's Example 9.1. A trace of that
lens takes the rays from one edge of the emitter to the far edge of the
receiver within 5e-3 (witness).
