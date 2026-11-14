---
id: C-SOURCE-01
title: A source specification builds one source in both engines, the 2D source being the exact section of the 3D one by the scene plane, with the same emission law
parties:
  provides: nonimaging_design (optical_elements.sources: validate_source_spec, build_source_2d, RaySetSource); optiland_scene_bridge (sources: build_source_3d)
  relies:   whoever compares a 2D trace with a 3D trace of the same design, or reads a profile's sources
port: P-PROFILE
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_sources_3d.py::test_the_chip_spec_rebuilds_the_hand_placed_chip; src-python/ray_tracing_shapely_optiland/tests/test_sources_3d.py::test_the_2d_section_is_where_the_3d_rectangle_crosses_the_plane; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_source_spec.py::test_what_has_no_exact_source_is_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_source_spec.py::test_one_source_in_two_profiles_is_merged_or_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile_source_spec.py::test_a_rayfile_spec_through_a_profile_builds_the_slice; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile_source_spec.py::test_a_changed_file_or_a_stale_slice_is_refused; src-python/ray_tracing_shapely_optiland/tests/test_rayfile_source.py::test_a_rayfile_spec_adds_every_ray_of_its_file
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_source_spec.py::test_the_chip_section_is_longer_than_its_side
tracked_by: null
conflicts_with: null
refines: C-BRIDGE-10
rationale: KB7
since: 0.3
---

# C-SOURCE-01 — One source, described once, in both engines

**Assumptions.** A source specification (`P-SOURCE-SPEC`) is written in
the 2D scene's coordinates, plus one out of the plane. The optics it lights
are exported from the same scene and placed with `scene_placement`, so the
source and the optics share one mapping into the 3D world.

**Guarantees.**
- **Placement.** `build_source_3d` places the source at the scene point
  (a, b, c) mapped to the world point (a, c, b), its axis along the
  direction given in the plane. A patch's sides are the spec's, rolled as
  the spec says, and the rectangle sits where `anchor` puts it.
- **The law.** Each kind and emission law becomes the one Optiland source
  with that law exactly: a uniform point is a `PointSource`, a lambertian
  point or patch an `ExtendedSource` at 90°, a uniform patch an
  `ExtendedSource` below 90°, a pencil a `CollimatedSource` of radius 1e-9.
- **The 2D section.** `build_source_2d` emits the source's section by the
  scene plane. For a patch that is where its 3D rectangle crosses the
  plane, which need not be its side: a patch rolled about its axis, with a
  corner on the plane, cuts it in its side divided by the cosine of the
  roll. In the section each ray is weighted by the law's intensity in the
  plane: 1 for uniform, the cosine for lambertian. In any plane through
  its axis, a 3D source of that law has that intensity per unit angle.
- **Sampling.** The 2D rays are deterministic: midpoints of equal steps in
  position and angle, counts set by the caller, independent of the scene's
  ray density.
- **A measured LED** (`kind` `rayfile`, schema 1.4). The spec holds the
  file's path and the format its parser takes (`read_rayfile`'s `format`),
  the file's ray count, flux and SHA-256 digest when the spec was written,
  and the slice: the limit on h, and the share and number of rays it kept.
  - **The file or nothing:** both builders read the file through
    `spec_rayfile`, which refuses a file whose digest, count or flux is not
    the recorded one.
  - **In 2D:** the slice the spec records (`C-SOURCE-03`), recomputed and
    checked against the recorded share and count. A spec without a slice,
    or with its axis off the plane, has no 2D source and is refused.
  - **In 3D:** every record of the file, unturned (`add_source_3d`); the
    slice is the 2D section's, not the source's.
- **One name, one source.** One source written into several profiles is
  read once by `merged_sources`. Copies that differ are refused, naming the
  two profiles.

**Invariants.** The 3D source's frame is a proper rotation that Optiland's
Euler angles rebuild to 1e-12 (`cs_from_axes`), the gimbal-lock axis
included. The 2D section's ends lie on the 3D rectangle's edges, to 1e-12.

**Units and frames.** Scene units, which the 3D side reads as millimetres.
Wavelength in micrometres (the 2D rays get nanometres). Flux in watts, or
lumens converted by Optiland.

**If the assumption is violated.** Loud where it can be.
- **Refused at validation:** a law the 3D engine cannot represent exactly
  (a lambertian cone cut short of 90°, a uniform patch filling the
  hemisphere), an unknown field, two sources with one name.
- **Refused by `build_source_2d`:** a source with no section in the plane,
  and a rayfile with no slice.
- **Refused by both builders:** a rayfile that is not the file the spec was
  written for.

Silent in one case: optics placed without `scene_placement` sit elsewhere,
and the source does not follow them (`C-BRIDGE-10`).

**What it does not say.** A 2D section carries only the rays in the plane.
Its `flux_per_brightness` is per unit brightness of those rays, not a share
of the 3D source's flux. The share of a source's light that a 2D section
can represent is a separate question, answered for a measured source by
its slice.

**Checked by.**
- **The chip.** The LED collimator's chip, written as a spec, is placed
  with the hand-built frame's rotation and centre to 1e-12. Its traced
  birth points fill the 2 × 1 mm rectangle from the focus, and its flux
  is conserved. The share within 30° of the axis is 1/4, the lambertian
  value.
- **The section.** For that chip and for a tilted, rolled, offset patch,
  the 2D section's ends are where the 3D rectangle's edges cross the
  plane.
- **Refusals.** Each unrepresentable spec is refused, by name. Two
  profiles carrying different copies of one source are refused, naming
  both.
