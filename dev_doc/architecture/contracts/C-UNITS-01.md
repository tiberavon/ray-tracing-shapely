---
id: C-UNITS-01
title: Photometric projection is conditional on declared symmetry
parties:
  provides: whoever constructs a ProjectionModel and declares its symmetry (a design author)
  relies:   eye_safety, nonimaging_design (via C-PROFILE-01's symmetry field)
binds:      optical_elements_physics (PhysicalScene, ProjectionModel)
port: P-PHYSICAL-SCENE
viewpoint: radiometric
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/developer_tests/test_physical_scene.py::test_projection_base_has_no_symmetry,::test_cylindrical_projection_symmetry_is_extrude,::test_point_source_projection_symmetry_is_free,::test_lambertian_projection_symmetry_is_extrude,::test_revolved_projection_symmetry_is_revolve_but_unimplemented,::test_valid_symmetries_covers_every_concrete_projection,::test_projection_model_rejects_invalid_symmetry
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC4
since: 0.1
---

# C-UNITS-01 — Converting to a per-area quantity needs to know the source's shape

A 2D simulation traces a cross-section. Turning its result into watts per
square metre requires saying what the third dimension looks like: a strip
extending out of the page, a point, or a surface of revolution. Different
shapes, different conversion.

**Assumptions.** The projection model in use declares its symmetry —
`extrude`, `free`, or `revolve` — and any 3D result it is compared against
declares the same one. The declaration is fixed by which projection class
was chosen, not typed in freely.

**Guarantees.** For `extrude` and `free`, the conversion from the engine's
brightness through watts-per-metre to watts-per-square-metre is a stated
function of that symmetry. For `revolve`, the class exists and can be
named, but its conversion methods raise `NotImplementedError`: the factor
for a revolved receiver depends on where along the radius the light lands,
and the current interface has no way to be told.

**Invariants.** A 2D-versus-3D comparison is only meaningful under a
matching declaration, and there is no 3D engine to compare against yet.

**Units and frames.** Watts per metre, then watts per square metre.

**If the assumption is violated.** Silent. Two irradiances in the same
unit, computed under different symmetries, differ by a geometric factor
that nothing flags.

**Checked by.** Tests in `test_physical_scene.py` that each projection
class declares the symmetry it should, and that the revolved one raises.
