---
id: C-BRIDGE-07
title: A revolve profile is a half-section on one side of a declared axis, taken from an outline symmetric about it, and each revolved face's glass side is read from the stored normal
parties:
  provides: nonimaging_design (export_profile), optiland_scene_bridge (RevolvedProfileSolid)
  relies:   optiland_scene_bridge, nonimaging_design (BasePrism.from_profile)
port: P-PROFILE
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_singlet_lens_profile.py::test_revolve_rejects_an_outline_not_symmetric_about_the_axis; src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_sidedness_follows_the_stored_normals
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_singlet_lens_profile.py::test_revolve_export_is_the_half_section_from_axis_to_axis; src-python/ray_tracing_shapely_optiland/tests/test_revolve.py::test_the_solid_traces_identically_to_optilands_lens
tracked_by: null
conflicts_with: null
refines: C-PROFILE-01
rationale: KB7
since: 0.3
---

# C-BRIDGE-07 — A round element travels as half its cross-section

**Assumptions.** A solid of revolution — a round lens, a cone — is the
shape swept out when a cross-section turns about an axis. Its 2D section
through the axis is a mirror image of itself across that axis. The
profile carries only the half on one side (the left of the axis
direction), as one chain of spans from the axis back to it. A span that
crossed the axis in the full section (a lens face) is cut there.

**Guarantees.** The exporter checks the mirror symmetry before writing
anything: a section that is not symmetric cannot be the slice of a round
element, and it raises instead of exporting one side of it. The 2D
rebuild mirrors the half back and rejoins a face that was cut at the axis
into one surface. When the bridge builds each face, it decides which side
of the face is glass by comparing Optiland's own orientation of that
surface with the outward normal stored in the profile. The bridge does
not assume the orientation.

**Invariants.** The two ends of the half-section lie exactly on the axis.
Every revolved face's glass side agrees with the stored normal.

**Units and frames.** The axis is given in the profile's own coordinates,
as a point on it and a direction.

**If the assumption is violated.** Loud: an asymmetric section, a
malformed axis, or a half-section whose ends are not on the axis raises.
Getting the glass side wrong would be silent — the solid would still
trace, with glass and air swapped at a face — which is why it is read
from the profile and tested against Optiland's own lens, not assumed.

**Checked by.** `test_singlet_lens_profile.py::test_revolve_rejects_an_outline_not_symmetric_about_the_axis`
and `test_revolve.py::test_sidedness_follows_the_stored_normals`. Forcing
every face's glass onto the same side fails five tests, including the
comparison with Optiland's lens for three lens shapes.
