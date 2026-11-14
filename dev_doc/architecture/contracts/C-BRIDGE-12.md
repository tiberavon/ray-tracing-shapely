---
id: C-BRIDGE-12
title: A revolved sheet becomes reflecting surfaces of revolution with no volume, and traces as its 2D mirrors do, meridional ray by ray
parties:
  provides: optiland_scene_bridge (RevolvedProfileSheet, build_revolved_faces)
  relies:   whoever builds a revolved reflector (searchlight, collimator, cone concentrator) from 2D mirrors
port: P-NSQ-SCENE
viewpoint: numerical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_revolve_sheet.py::test_every_meridional_ray_ends_in_3d_where_it_ends_in_2d; src-python/ray_tracing_shapely_optiland/tests/test_revolve_sheet.py::test_what_a_sheet_refuses; src-python/ray_tracing_shapely_optiland/tests/test_revolve_cut_sheet.py::test_every_meridional_ray_ends_in_3d_where_it_ends_in_2d_on_both_sides; src-python/ray_tracing_shapely_optiland/tests/test_revolve_cut_sheet.py::test_a_cut_conic_finds_the_first_root_in_the_kept_part
witness: src-python/ray_tracing_shapely_optiland/tests/test_revolve_sheet.py::test_a_sheet_traces_identically_to_a_hand_built_optiland_mirror
tracked_by: null
conflicts_with: null
refines: C-BRIDGE-02
rationale: KB7
since: 0.3
---

# C-BRIDGE-12 — A round mirror is the 2D mirror, turned about its axis

**Assumptions.** A `body: "sheet"` profile (from `export_sheet_profile`)
holds mirrors, not glass: every span reflects, and nothing is enclosed.
Its spans are the parts of mirrors left of the revolve axis; they need
not join. A conic span's descriptor gives its vertex, axis, vertex radius
and conic constant; a circle span its centre and radius. The profile may
declare `symmetry.azimuth_deg = [start, end]`: the sheet then covers only
that range about the axis, measured from the half-section's own side
towards the axis frame's +y, and the range keeps 0° (the half-section
itself). If it removes 180°, the 2D scene draws only the half-section's
side, and nothing on the other.

**Guarantees.** `RevolvedProfileSheet` builds one `ReflectiveComponent`
per span on the exact surface of revolution the span table gives it: a
conic or circle span with its vertex on the axis becomes Optiland's
`ConicGeometry` (paraboloid, ellipsoid, hyperboloid or sphere), a line a
disc, annulus or cone wall. A conic or circle span that does not reach
the axis becomes a zone, and a cut sheet's curved spans are cut to its
range: both are the bridge's `CutConicGeometry`, Optiland's conic with
its aperture test narrowed root by root. A reflector
running past its ellipsoid's equator is a cap and a zone of the far
vertex's sheet. Every sample and normal of a curved span is
checked against the surface built from it (`C-BRIDGE-08`). No `Volume`
is built: a sheet has no inside to check closed. Each span needs a
reflectance; there is no default. Placement and face naming are a
solid's (`C-BRIDGE-10`): `<name>.<short label>`, `cs`, `scene_placement`.
`import_from_optiland` reads a sheet back, its conic constant, a zone's
inner radius and the azimuth range included.

**Invariants.** A meridional ray ends in 3D where it ends in the 2D scene
of the same mirrors, after the same number of reflections, on either side
of the axis (on a cut side, it passes in both). An uncut sheet traces
event for event like Optiland's own `ReflectiveComponent` on the same
`ConicGeometry`; a cut one finds, on each surface, the first intersection
with Optiland's uncut conic that lies in the kept part.

**Units and frames.** The profile's length unit. A conic's radius is
signed along its own axis in the profile, along the solid's z in
Optiland; the bridge flips it when the two point opposite ways.

**If the assumption is violated.** Loud, at construction:
- a profile that is not a sheet given to `RevolvedProfileSheet` (or a sheet
  given to `RevolvedProfileSolid`);
- a span that does not reflect;
- a span with no reflectance;
- a conic whose axis is not the revolve axis (a CPC, out of scope);
- an azimuth range that is malformed, empty, over a full turn, or removes
  0°; and, in the export, a mirror on a side the range removes;
- an azimuth cut on a sheet with a line span (a cut disc or cone wall needs
  its own geometry), or on a solid (a cut solid is not closed).

**Checked by.**
- **2D against 3D:** a paraboloid, ellipsoid, hyperboloid, sphere and cone,
  on an axis tilted 10° in the 2D scene. Every meridional ray ends on the same
  detector plane at the same point to 1e-7 and in the same direction to 1e-9,
  after as many reflections as in 2D (the cone's rays bounce off both walls).
- **Optiland, hand-built:** an ellipsoid sheet against a `ReflectiveComponent`
  on a `ConicGeometry` built by hand gives identical events, flux included,
  over a random beam with reflectance 0.9.
- **Skew rays:** every ray of a full collimated beam, skew rays included,
  passes through the paraboloid's focus to 1e-9.
- **Mutations:** if the bridge ignores the conic constant or the sign flip,
  seven tests fail.
- **Cut sheets** (`test_revolve_cut_sheet.py`): `CutConicGeometry` against an
  oracle relaunching Optiland's uncut conic past every removed hit, for a
  hole, a half, a quarter, a 270° range and a hole with a half, on three
  conics; bit for bit Optiland's conic when nothing is cut. The patent
  reflector (cap and zone of one ellipse, upper half): rays from F1 in the
  profile plane end where they end in 2D on both sides, and every ray from
  F1, skew rays included, reflects through F2 to 1e-9 and only off the kept
  half.

**Placement caveat.** Near the world origin, or after a long path, Optiland's
engine lets a ray re-hit a surface at the point it just left
(`KW-OPTILAND-05`): a conic near the origin, or a cone wall lit
from 570 mm away. The tests place their mirrors 100 mm or more from the
origin, with sources close to them.
