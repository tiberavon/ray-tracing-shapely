---
id: C-BRIDGE-13
title: A plate standing on a 2D segment shows that segment as its section, and traces as the 2D segment does in the 2D plane and as its outline says out of it
parties:
  provides: optiland_scene_bridge (PlanarPlate, segment_placement)
  relies:   whoever builds a shade, a board or a baffle that lies in a plane containing the axis of a 2D section
port: P-NSQ-SCENE
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_plate.py::test_every_ray_in_the_2d_plane_ends_in_3d_where_it_ends_in_2d; src-python/ray_tracing_shapely_optiland/tests/test_plate.py::test_out_of_the_plane_a_ray_meets_the_plate_exactly_where_the_outline_is; src-python/ray_tracing_shapely_optiland/tests/test_plate.py::test_a_plate_whose_section_is_not_its_segment_is_refused
witness: src-python/ray_tracing_shapely_optiland/tests/test_plate.py::test_the_plate_stands_on_its_segment
tracked_by: null
conflicts_with: null
refines: null
rationale: KB7
since: 0.3
---

# C-BRIDGE-13 — A flat plate is the 2D segment, given an outline

**Assumptions.** A plate lies in a plane perpendicular to the 2D plane,
through a 2D segment (a `Mirror`, a `Blocker`, or two points): a
projector headlamp's shade or the board under its LED. The 2D scene shows
it edge on, so its outline in the third dimension is not in the 2D scene:
the caller gives it, as `(u, v)`, u along the segment from `p1`, v out of
the 2D plane.

**Guarantees.** `PlanarPlate.from_segment` builds one face on the bridge's
`PolygonPlaneGeometry`, named `<name>.plate`: a `ReflectiveComponent`
(`reflectance=`, required; both faces reflect and the rest is absorbed,
as Optiland's mirror does) or an `AbsorbingComponent` (`absorbing=True`).
It is placed by `segment_placement` under the scene bridge's plane mapping,
2D `(a, b)` to world `(a, 0, b)` (`C-BRIDGE-10`), so it lands with the
revolved and extruded elements of the same 2D scene. `PlanarPlate(name,
polygon, cs=...)` places one anywhere, with no 2D check.

**Invariants.** The outline's chord along `v = 0`, the plate's section in
the 2D plane, is the segment, `u` in `[0, length]`, to `1e-9`. A ray in the
2D plane ends in 3D where it ends in the 2D scene; out of the plane, a ray
meets the plate exactly where the outline contains its point, a concave
outline's notch included.

**Units and frames.** The 2D scene's length unit. The plate's local x is
along the segment, local y world y, local z the segment's normal in the
2D plane.

**If the assumption is violated.** Loud, at construction:
- an outline whose chord along `v = 0` is missing, shorter or longer than
  the segment, or in more than one piece;
- an outline that crosses itself, has fewer than three vertices or no area;
- both or neither of `reflectance` and `absorbing`;
- a zero-length segment.

**Checked by.**
- **2D against 3D:** six rays in the 2D plane, onto the segment from both
  sides at several angles and just past its ends, end on the same line in
  the same direction as in 2D, after as many reflections.
- **Outline:** rays along the plate's normal at 56 points of a grid around a
  stepped shade outline are reflected exactly when the outline contains
  the point.
- **Material:** an absorbing plate built from a 2D `Blocker` stops the
  light; a mirror of reflectance 0.8 passes on 0.8 of it.
- **Drawing:** in the 2D plane's projection the drawn plate is the segment
  to `1e-9`; the 3D actor is the outline at its place, and its triangles'
  area is the outline's, the notch unfilled.

**Not covered.** A plate in any other orientation to the 2D plane (use
`cs`); reading a plate back to 2D.
