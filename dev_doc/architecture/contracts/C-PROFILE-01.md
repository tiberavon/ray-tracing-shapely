---
id: C-PROFILE-01
title: A profile handoff is Hermite (position and exact surface normal) plus construction parameters, role-tagged arc spans, and a symmetry declaration
parties:
  provides: nonimaging_design (SMS chain, prism constructors)
  relies:   optiland_scene_bridge
port: P-PROFILE
viewpoint: structural
status: documented
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_profile_export.py::test_from_profile_rejects_a_wrong_normal; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_singlet_lens_profile.py::test_from_profile_rejects_a_wrong_normal_on_an_arc; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_conic_mirror.py::test_the_sheet_export_refuses_what_a_revolve_cannot_make; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_conic_mirror.py::test_the_sheet_rebuild_refuses_what_is_not_a_exported_sheet; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_asphere_curve.py::test_export_and_rebuild_keep_the_exact_asphere; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_asphere_curve.py::test_a_revolve_half_section_rebuilds_the_whole_asphere; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_asphere_curve.py::test_from_profile_refuses_a_sample_off_the_asphere_and_a_wrong_normal; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_profile_scan.py::test_a_scanned_face_goes_through_profile_json_with_its_record; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_profile_scan.py::test_symmetry_is_assumed_for_one_meridian_and_measured_for_two
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_profile_export.py; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_conic_mirror.py; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_singlet_lens_profile.py; src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py
tracked_by: null
conflicts_with: null
refines: null
rationale: KB7
since: 0.2
---

# C-PROFILE-01 — A profile handoff carries exact normals, roles, and how it becomes 3D

**Assumptions.** Whatever writes a `profile.json` includes, for every span
(one physical surface — a straight edge, a whole circular arc, or an exact
conic or spline edge): its exact shape, points along it (the two ends of a
straight span; evenly spaced points on a curve), the exact outward normal
at each point, its role and
mechanism, and — once per profile — a declaration of how the 2D outline
becomes a 3D solid, plus the construction parameters and the physical/
numerical parameter split.

A **sheet** (`body: "sheet"`, from `export_sheet_profile`) is mirrors with
no inside: every span reflects, spans need not join, and since a sheet has
no outside, a curve's normals point towards its vertex's centre of
curvature and a line's are its direction turned 90° counter-clockwise. A
conic span (a `ConicMirror`) declares `{"type": "conic", "vertex", "axis",
"radius", "conic"}`, sampled evenly in the coordinate across its axis. A
sheet's revolve symmetry may declare `azimuth_deg: [start, end]`, the range
about the axis the sheet covers (from the half-section's side, keeping 0°);
a full turn is written as no `azimuth_deg`. A solid's may not.
`mirrors_from_sheet_profile` rebuilds a sheet's 2D mirrors, checking every
sample against its curve, as `BasePrism.from_profile` does for a solid.

Schema 1.2: a glass edge, too, may be a `conic` (the same
descriptor) or a `spline`, `{"type": "spline", "points", "tangents"}` with
an optional `"domain": [p0, p1]`. It is a cubic Hermite curve through the
points with the given unit tangents, so its normals are exact at the
points. A piece of a spline is the same spline over a narrower `domain`, so
cutting a span at a revolve axis stays exact. `BasePrism.from_profile`
rebuilds both kinds exactly. It checks every sample against the curve and
every normal against the curve's own, and joins a surface the axis cut in
two back into one edge.

Schema 1.5: a glass edge may also be an even `asphere`, `{"type":
"asphere", "vertex", "axis", "radius", "conic", "coefficients"}`: the
conic's sag plus A1 s² + A2 s⁴ + …, the coefficients in Zemax's and
Optiland's order, `radius` null for a flat base. Exported and rebuilt as a
conic is, with the same checks, its two halves joined when the axis cut it.
The 3D bridge builds it as an asphere of revolution.

**A measured span.** A span built from a scan carries a record in the
top-level `fit`, `{"spans": {label: record}}`. The record holds:
- **the source:** the scan file and its digest, its unit, and the meridian;
- **the model:** `fitted`, the asphere, or `as_measured`, the asphere plus
  the residual's smoothed even part, as a spline;
- **the fitted surface, alignment and residual;**
- **the correlation warnings;**
- **the symmetry:** assumed for one meridian, measured for more.

The guarantees above hold for such a span **as a statement about its
model**. Its samples and normals are exactly the model's, and the checks
apply unchanged. They are not the lens's: a scan has no normals, and the
residual says how far the model is from the measurement. Nothing reads the
record to build a surface. It travels with the profile so that a result
traced through the model can be traced back to the data, and to the
assumptions, such as rotational symmetry from one meridian.

Schema 1.3: a profile also carries `sources`, the light the element is
designed for: a list of source specifications (`P-SOURCE-SPEC`), in the
same coordinates as the points, validated on export, empty when none was
given. A 1.2 profile has no `sources` and reads as having none. What a
source specification guarantees is `C-SOURCE-01`.

Schema 1.4: a source may be a measured LED's rayfile (`kind` `rayfile`):
its path (relative to the profile's folder), the format its parser takes,
the file's count, flux and digest, and how its 2D section is sliced. The
file is not in the profile.

**Guarantees.** The receiving side never has to derive a normal from
neighbouring points. At a sharp corner the two spans meeting there carry
two different normals, and neither is averaged with the other.

**Invariants.** Normals are stored per span, not per shared vertex. A
curved span's points lie on the curve it declares, because both come from
the same formula. A fitted-curve field is always empty from this side.

**Units and frames.** The profile's declared length unit.

**If the assumption is violated.** Loud where the receiving side checks a
required field. A normal that is present but wrong is loud when the
profile is rebuilt in 2D — `BasePrism.from_profile` compares every stored
normal with the one the span's geometry implies at that point (on an arc,
at every sample) and raises on disagreement, and raises as well for a
point off the circle its span declares —
and silent when it is built in 3D: the bridge orients each face from the
span's two points and does not read the stored normal there.

**Checked by.** `test_profile_export.py::test_from_profile_rejects_a_wrong_normal`
and `test_singlet_lens_profile.py::test_from_profile_rejects_a_wrong_normal_on_an_arc`
for the 2D rebuild. `profile_export.py` itself is exercised on every flat
prism by `test_profile_export.py` and by the bridge's tests.
