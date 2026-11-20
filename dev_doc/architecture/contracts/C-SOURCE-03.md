---
id: C-SOURCE-03
title: A rayfile slice turns each ray about the axis into the 2D plane with its direction kept exactly, keeps the rays whose line passes within a stated distance of the axis, and reports the share of the flux it could not keep
parties:
  provides: 'nonimaging_design (optical_elements.sources.rayfile_slice: slice_rayfile, RayfileSlice); optiland_scene_bridge (compare.compare_slice_3d; as a flow, C-BRIDGE-16)'
  relies:   whoever lights a 2D section of a rotationally symmetric optic with a measured LED
port: P-RAYFILE
viewpoint: physical
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile_slice.py::test_meridional_rays_are_all_kept_unchanged_but_for_the_turn; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile_slice.py::test_a_skew_ray_reports_its_distance_from_the_axis_and_keeps_its_direction; src-python/ray_tracing_shapely_optiland/tests/test_rayfile_slice_3d.py::test_meridional_records_trace_the_same_in_2d_and_3d; src-python/ray_tracing_shapely_optiland/tests/test_rayfile_slice_3d.py::test_the_difference_grows_with_the_skew_offset; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_radiation_plot.py::test_a_lambertian_point_and_its_slice; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_radiation_plot.py::test_the_cross_sections_follow_the_roll; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile_slicing_flow.py::test_the_table_of_a_four_die_emitter; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile_slicing_flow.py::test_the_source_is_written_into_the_profile
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile_slice.py::test_the_skew_share_quantiles_and_the_2d_source; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_radiation_plot.py::test_a_slice_of_an_extended_emitter_is_scaled_to_the_whole_flux
tracked_by: null
conflicts_with: null
refines: C-SOURCE-02
rationale: KB7
since: 0.3
---

# C-SOURCE-03 — A measured LED in a 2D section: the rays it can carry, and the share it cannot

**Assumptions.** The optic is rotationally symmetric about the LED's axis,
so turning a ray about that axis does not change what the optic does to it.
The rayfile is placed as `rayfile_frame` places it: its z along the axis.

**Guarantees.**
- **The skew offset.** Every record gets h: the distance at which its line
  passes the axis, signed (its skew invariant over its transverse length).
  No turn about the axis changes h; a meridional ray has h = 0.
- **The turn.**
  - **The common case:** each ray is turned until its transverse direction
    lies in the 2D plane, the smaller of the two turns, and its offset h out
    of the plane is dropped. The 2D ray has the 3D ray's direction exactly
    and is displaced by h.
  - **A ray along the axis:** its start is turned into the plane instead.
- **What is kept.** The rays with |h| ≤ `max_offset_mm`, plus 1e-9 mm of
  rounding, each with its flux. The caller states the limit.
- **What is reported.**
  - `skew_share`: the share of the flux not kept, with the limit that
    decided it.
  - `offset_quantiles`: flux-weighted quantiles of |h|.
  - **The radiation pattern** (`radiation_pattern`, drawn by
    `radiation_plot_svg` as a datasheet draws one): intensity against the
    signed angle from the axis, in the rayfile's flux unit per steradian.
    - **3D, half averages:** over each half of the azimuths, the half whose
      direction points to the plane's positive side on the right. The slice
      turns every ray onto that side, so this is the curve it reproduces
      when its kept rays are a fair sample of the LED's directions.
    - **3D cross sections**, in the plane and across it: a wedge of azimuths
      each, as a datasheet's cross sections.
    - **The slice:** its flux per steradian of half ring, over the kept
      share.
    - **The share of the flux within stated angles**, for the LED and for
      the slice.
  - **The table for choosing the limit** (`RayfileSlicingFlow`): the flux
    kept at the package's half diagonal in equal steps, and the limits that
    keep the ends of a stated range of the flux, exactly: the flux-weighted
    quantiles of |h|. The flow refuses a footprint the rays do not start
    inside. The choice is asked of the caller, as a kept share (its limit
    is then the exact quantile) or as a limit, and written, if asked, into
    a `profile.json` as a `rayfile` source with its slice, the rayfile's
    path relative to the profile's folder.
- **In 2D.** `source_2d` emits the kept rays as a `RaySetSource`, the
  brightest at 1, with `flux_per_brightness` the flux of brightness 1.

**Invariants.** Kept flux plus skew share times the total is the total. A
file of meridional rays has skew share 0 at any limit, and its slice's
pattern is its half averages, bin for bin.

**Units and frames.**
- **h:** mm.
- **Flux:** the rayfile's unit.
- **The slice's rays:** in the 2D scene.

**If the assumption is violated.** Silent.
- **An optic that is not symmetric about the LED's axis:** the turn is not a
  symmetry, and the slice is not the light that optic sees.
- **A large `max_offset_mm`:** the slice keeps rays whose 2D path differs
  from their 3D path. The difference grows with h.
- **The 2D brightness:** it is the file's flux per ray, not an in-plane
  intensity law (unlike `C-SOURCE-01`'s sections). A 2D result lit by a
  slice is what the near-meridional rays of the 3D source do.

**Checked by.**
- **The turn, on synthetic files:**
  - meridional rays are kept unchanged but for the turn, h below 1e-12;
  - a ray passing the axis at 1 mm reports h = 1 and keeps its direction;
  - a ray along the axis has its start turned.
- **Against 3D, through a revolved singlet** (`compare_slice_3d`):
  - meridional records agree with their own 3D rays in exit angle to
    1e-7°;
  - for skew records the median difference is under 0.01° below
    h = 0.1 mm and over 0.1° above 0.6 mm.
- **The pattern, against known emitters:**
  - a Lambertian point: half averages (flux / π) cos θ to 3%, a full width
    at half maximum of 120°, a share sin² θ within θ; its slice equal to the
    half averages;
  - a Lambertian square: a slice at 0.2 mm within 5% of the half averages
    inside 60°, its direction independent of its start;
  - rays in one plane through the axis show only in that plane's cross
    section, on the side the roll puts them.
- **The table, on a synthetic four-die emitter:** limits in equal steps to
  the half diagonal, kept shares rising to 1, the limits at 50% and 75%
  equal to the quantiles of |h|.
- **The choice and the profile:** a share of 75% gives the 75% quantile; a
  profile written by the flow holds the source with that slice, a path
  that resolves from the profile's folder, and replaces a source of the
  same name; a profile below schema 1.4 is refused.
