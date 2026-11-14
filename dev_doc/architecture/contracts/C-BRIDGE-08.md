---
id: C-BRIDGE-08
title: A curved span's samples and its exact descriptor agree, in position and in slope, with the surface built from them; disagreement raises
parties:
  provides: nonimaging_design (export_profile)
  relies:   optiland_scene_bridge (surface_from_span), nonimaging_design (BasePrism.from_profile)
port: P-PROFILE
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_a_sample_off_the_conic_raises; src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_a_normal_off_the_conics_raises; src-python/ray_tracing_shapely_optiland/tests/test_revolve_led_collimators.py::test_a_spline_sample_off_its_surface_or_a_tilted_normal_is_refused; src-python/ray_tracing_shapely_optiland/tests/test_revolve_asphere.py::test_the_asphere_reads_back_and_what_the_bridge_refuses
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_singlet_lens_profile.py::test_from_profile_rejects_a_sample_off_its_circle; test_from_profile_rejects_a_wrong_normal_on_an_arc
tracked_by: null
conflicts_with: null
refines: C-PROFILE-01
rationale: null
since: 0.3
---

# C-BRIDGE-08 — A curved surface's points and its formula say the same thing

**Assumptions.** A curved span carries two descriptions of the same
surface: an exact one (for a circle, its centre and radius) and a list of
points along it with the outward direction at each. The receiving side
builds its surface from the exact description.

**Guarantees.** Before building, every stored point is checked against the
built surface: it must lie on it within a tolerance (`sag_tol`, 1e-9 in
the profile's length unit, by default), measured along the surface's
normal (to first order, the sag difference times the normal's axial
part: near an ellipsoid's equator the surface runs along the axis, and a
point a rounding error from it is far from it in sag), and its stored normal must point
the way the built surface's normal points there, within a tolerance on the
angle (`slope_tol`). The angle check matters more than the position check.
A ray is bent by the direction of the surface it meets, so a small tilt
error moves rays where an equally small position error would not.

**Invariants.** A surface that passes is the surface the points describe.
Today the points and the formula come from the same calculation, so they
agree to rounding error, and fixed tolerances are enough. A surface whose
points come from somewhere else — a fit, or a measurement — would need
tolerances derived from how much angular error the design can afford.

**Units and frames.** The profile's own length unit; normals are unit
vectors.

**If the assumption is violated.** Loud. A point moved by a millionth of a
unit, or a normal turned by a thousandth of a radian, raises in both the
3D bridge and the 2D rebuild.

**Checked by.** `test_revolve.py::test_a_sample_off_the_conic_raises` and
`test_a_normal_off_the_conics_raises`; for a spline span,
`test_revolve_led_collimators.py::test_a_spline_sample_off_its_surface_or_a_tilted_normal_is_refused`;
for an asphere span (an `AsphereRevolutionGeometry`, the same checks),
`test_revolve_asphere.py::test_the_asphere_reads_back_and_what_the_bridge_refuses`.
