---
id: C-BRIDGE-11
title: The revolved solid's and sheet's renderers draw the geometry Optiland traces, at its placement
parties:
  provides: optiland_scene_bridge (RevolvedProfileRenderer2D/3D, RevolvedProfileSheetRenderer2D/3D)
  relies:   a human or agent reading a 2D or 3D view of a revolved scene
port: P-NSQ-SCENE
viewpoint: agentic
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_revolve_placement.py::test_the_2d_renderer_draws_both_lenses_where_the_2d_scene_has_them; src-python/ray_tracing_shapely_optiland/tests/test_revolve_placement.py::test_the_3d_renderer_puts_every_point_on_the_placed_solid; src-python/ray_tracing_shapely_optiland/tests/test_revolve_sheet.py::test_the_2d_sheet_renderer_draws_the_2d_mirrors_unfilled; src-python/ray_tracing_shapely_optiland/tests/test_revolve_sheet.py::test_the_3d_sheet_renderer_puts_every_point_on_the_placed_mirror; src-python/ray_tracing_shapely_optiland/tests/test_revolve_cut_sheet.py::test_the_3d_renderer_sweeps_only_the_kept_half
witness: src-python/ray_tracing_shapely_optiland/tests/test_revolve_placement.py::test_the_3d_renderer_matches_optilands_lens_renderer_on_axis
tracked_by: null
conflicts_with: null
refines: C-BRIDGE-10
rationale: KD7
since: 0.3
---

# C-BRIDGE-11 — A view of a round element shows the element that is traced

**Assumptions.** Whoever looks at a view of a scene takes what is drawn to
be what is traced.

**Guarantees.** Both renderers read the half-section back from the live
faces, as `import_from_optiland` does, not from the profile the solid was
built from. A face reshaped after construction, for example by an
optimiser, is drawn reshaped. Both apply the solid's placement. The 2D
renderer draws the section through the axis that lies in the viewing
plane: the half-section, plus its mirror image across the axis. For a
solid placed with `scene_placement` and the `XZ` projection, that is
exactly the 2D scene's outline, transposed. Looking straight down the
axis, it draws the rim circle. The 3D renderer turns the contour about
the solid's own axis in numpy, in double precision, and places it with
the solid's transform. It does not use `vtkRotationalExtrusionFilter`,
which writes single-precision points (an error of about 1e-7 of the
size), so the drawn points match the traced surfaces to rounding.

A revolved sheet (`C-BRIDGE-12`) has its own pair,
`RevolvedProfileSheetRenderer2D`/`3D`, with the same read-back, placement
and double-precision sweep, but span by span and unfilled: a sheet's spans
are separate mirrors that enclose nothing. In 2D each span and its mirror
image is an open line; in 3D each span is its own actor. A cut sheet
(`symmetry.azimuth_deg`) is swept over its range only, and in 2D a side of
the section is drawn only where the cut keeps it.

**Invariants.** Every drawn point lies on the traced solid or mirror, to 1e-9.

**Units and frames.** World millimetres. Optiland's `XZ` projection puts
world z horizontal.

**If the assumption is violated.** Not applicable on this side. For
contrast, Optiland's own `LensRenderer3D` moves its contour to world
coordinates and then turns it about the world z axis. That is right
only for a lens on that axis: a `Lens` decentred to x = 5 is drawn as a
ring of radius 11.2 about the z axis (measured). If a face can no longer
be read back as a surface of revolution (rotated or moved off the axis),
the renderers draw the stored profile and warn that the view is of what
was built.

**Checked by.** Two lenses placed from one 2D scene: every vertex drawn
in 2D is on the scene's outline, and every outline point is drawn, to
1e-9. Every 3D mesh point of a lens tilted out of the plane, taken back
through a rotation computed independently in the test, lies on the
revolved half-section, to 1e-9. On axis, the 3D bounds equal those of
Optiland's `LensRenderer3D` for the same lens. If the renderers ignore
the placement, four tests fail. For sheets: a placed paraboloid and cone in
`XZ` draw exactly the 2D mirrors (every drawn point on them, every point of
them drawn, nothing filled); every 3D mesh point of a placed ellipsoid and
cone lies on its revolved spans; looking down the axis, the rim is a
circle. If the sheet renderers ignore the placement, all five fail.
