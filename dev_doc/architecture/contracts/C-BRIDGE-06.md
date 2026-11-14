---
id: C-BRIDGE-06
title: A solid read back from Optiland keeps every span's name, role and mechanism; the 2D rebuild refuses an outline that no longer closes rather than inventing an edge
parties:
  provides: optiland_scene_bridge (import_from_optiland), nonimaging_design (BasePrism.from_profile)
  relies:   analysis_signature, agentic_layer, anyone addressing a rebuilt element's edges by name
port: P-PROFILE
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_end_caps_and_import.py::test_round_trip_reads_live_geometry_and_keeps_labels
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_profile_export.py::test_from_profile_round_trips_export; test_from_profile_keeps_labels_addressable_unlike_from_vertices
tracked_by: null
conflicts_with: null
refines: C-LABEL-02
rationale: KA1
since: 0.2
---

# C-BRIDGE-06 — What comes back from 3D is the same labelled element, possibly with new numbers

A design goes out to Optiland as a `profile.json` and is built as a 3D
solid. It may be changed there. This is the promise about bringing it back
into the 2D environment, where edges are addressed by name.

**Assumptions.** The solid was built by this bridge, so it remembers the
profile it came from. Any change made in 3D moves or resizes faces within
the profile plane; it does not tilt a face out of it.

**Guarantees.** `import_from_optiland` returns a `profile.json` whose
points and normals are read from the live faces, and whose span names,
roles and mechanisms are the ones that went out. `BasePrism.from_profile`
builds a 2D element from it in which each edge carries its span's name,
role and mechanism — so the edge that was called `M` before the trip is
still called `M`, and is still a total-internal-reflection measuring
surface. Exporting the rebuilt element again reproduces the profile it was
rebuilt from. `interior_index` supplies the refractive index the rebuild
needs, read from the faces' material.

**Invariants.** The import never modifies the solid's own copy of the
profile. The rebuild is always a plain `BasePrism`: it carries the
outline, not the construction parameters of whatever class first built
it, and does not claim to be that class.

**Units and frames.** The profile's length unit. 3D world `(x, z)` maps
to the profile's 2D `(x, y)`; world `y` is the extrusion axis.

**If the assumption is violated.** Loud. A face out of the profile plane
makes the import raise. A single face moved on its own leaves a gap
between it and its neighbours; the import reports the geometry as it is,
and the rebuild raises, naming the span that no longer meets the next one.
A stored normal that disagrees with its span's points, a clockwise outline,
or a role or mechanism outside the shared vocabulary also raise in the
rebuild. The silent alternative — rebuilding from raw corners, which
always succeeds — is what this contract exists to rule out: it returns an
element with numbered edges, and every reference to an edge by name stops
resolving.

**Checked by.** `test_end_caps_and_import.py::test_round_trip_reads_live_geometry_and_keeps_labels`,
with the refusals in `test_import_refuses_a_face_moved_out_of_plane`,
`test_a_single_moved_face_cannot_be_rebuilt_silently`, and the
`test_from_profile_rejects_*` tests in `test_profile_export.py`.
