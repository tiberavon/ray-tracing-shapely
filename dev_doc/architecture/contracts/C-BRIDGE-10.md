---
id: C-BRIDGE-10
title: A revolved solid is placed by its coordinate system, and scene_placement puts it where its 2D scene had it, under the same plane mapping as the extruded prism
parties:
  provides: optiland_scene_bridge (RevolvedProfileSolid, scene_placement)
  relies:   whoever assembles a 3D scene from several elements of one 2D scene
port: P-NSQ-SCENE
viewpoint: structural
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_revolve_placement.py::test_scene_placement_puts_every_point_where_the_2d_scene_has_it; src-python/ray_tracing_shapely_optiland/tests/test_revolve_placement.py::test_2d_and_3d_agree_through_a_decentred_tilted_second_lens
witness: src-python/ray_tracing_shapely_optiland/tests/test_revolve_placement.py::test_a_placed_pair_traces_identically_to_two_placed_optiland_lenses
tracked_by: null
conflicts_with: null
refines: C-BRIDGE-07
rationale: KB7
since: 0.3
---

# C-BRIDGE-10 — A round element goes where its 2D scene put it

**Assumptions.** A revolve profile is written in its 2D scene's
coordinates: the axis point is where the element sits, and the axis
direction is where it points. Several elements exported from one scene —
two lenses, a lens and a prism — are meant to keep their relative places
in 3D.

**Guarantees.** `RevolvedProfileSolid(..., cs=...)` places the solid's
own axis frame in the world, the way Optiland's `Lens` places its front
vertex. In that frame the axis runs along z through the axis point, and
the half-section lies on the +x side. Every face refers to that
coordinate system, so the faces move together. `scene_placement(profile)`
is the coordinate system that puts the solid back where its 2D scene had
it. It uses the plane mapping the extruded prism already uses: a scene
point (a, b) becomes the world point (a, 0, b). Each face is named after
its solid (`L2.S1`), so the faces of two lenses stay apart in the trace's
event log. Reading the solid back with `import_from_optiland` returns the
profile in its own coordinates, wherever the solid was placed.

**Invariants.** Under `scene_placement`, every profile point lands at
(a, 0, b), to 1e-12. A solid placed with a coordinate system traces
exactly like Optiland's `Lens` placed with the same one.

**Units and frames.** World millimetres, as in the profile. The rotation
is stored as Optiland's Euler angles (R = Rz·Ry·Rx). An axis along world
x is gimbal lock for those angles, so `scene_placement` checks that its
angles rebuild the frame and raises if they do not.

**If the assumption is violated.** Silent. A solid built without `cs`
sits in its own axis frame, with its axis on world z through the origin.
It traces correctly there, but not where its 2D scene put it relative to
the other elements. Nothing can detect this from the solid alone; the
caller has to pass the placement.

**Checked by.** Every point of a lens at six orientations, including the
gimbal-lock axis and axes along −x and +y. A two-lens system whose
second lens is decentred 0.5 and tilted 2° in the plane: each exit ray
of the 3D trace matches the 2D trace of the same scene to 1e-7. The same
pair with the second lens also tilted out of the plane traces ray by ray
like two placed Optiland `Lens` objects. If the faces ignore `cs`, three
tests fail: the comparison with Optiland, the 2D-against-3D comparison,
and the import.
