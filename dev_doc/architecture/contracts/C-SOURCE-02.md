---
id: C-SOURCE-02
title: A rayfile is read only in a layout checked against a file, every other refused by the field that differs, and traced in 3D as its own rays, in order, placed as the 2D scene says, with their flux
parties:
  provides: 'nonimaging_design (optical_elements.sources.rayfile: read_rayfile, write_tm25, intensity_vs_angle); optiland_scene_bridge (sources: RayfileSource, rayfile_frame, add_rayfile_source_3d)'
  relies:   whoever lights a design with a measured LED
port: P-RAYFILE
viewpoint: physical
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile.py::test_a_written_file_reads_back_ray_for_ray; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile.py::test_a_different_layout_is_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile.py::test_a_wrong_ray_count_or_a_non_unit_direction_is_refused; src-python/ray_tracing_shapely_optiland/tests/test_rayfile_source.py::test_a_run_emits_the_files_rays_in_order_where_the_scene_puts_them; src-python/ray_tracing_shapely_optiland/tests/test_rayfile_source.py::test_per_ray_flux_survives_and_sums_to_the_file; src-python/ray_tracing_shapely_optiland/tests/test_rayfile_source.py::test_a_lambertian_file_traces_like_optilands_lambertian_source
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rayfile.py::test_a_lambertian_file_has_a_cosine_far_field
tracked_by: null
conflicts_with: null
refines: C-SOURCE-01
rationale: KD5
since: 0.3
---

# C-SOURCE-02 — A measured LED's rays, read exactly or not at all, traced as they are

**Assumptions.** The file is IES TM-25, binary. The standard is sold and the
reader was written from a supplier's file, so only the layout checked
against that file is read:
- version 2013;
- ray-data flags (1, 1, 1, 0, …): position, direction and flux per ray;
- seven float32 per ray, filling the file after the header exactly.

**Guarantees.**
- **Read exactly, or refused.**
  - **Refused, by the field that differs:** another magic, version, flag
    set or ray count, a direction more than 1e-4 from unit length, a
    negative flux.
  - **Kept raw:** header fields not decoded are returned as read, and
    nothing uses them.
- **What a read returns.**
  - The rays, in the LED's frame: positions in mm, unit directions, flux
    per ray in W.
  - The spectrum, as (nm, relative value).
  - The product's name and the header's radiant flux.
- **Traced as read.** `RayfileSource` emits the file's records in order:
  - ray *k* of a run is record *k* mod *n*;
  - it is placed by `rayfile_frame`: the file's z along the emission axis,
    x along `e_out`, y along `e_in`, the axes of `C-SOURCE-01`;
  - each ray carries its own share of the flux, scaled to the source's
    total, the file's by default;
  - wavelengths are drawn from the file's spectrum, unless one is given.
- **Written alike.** `write_tm25` writes the same layout, so the tests use
  synthetic files only. A supplier's file is used under its terms and is
  never needed by a shipped test.

**Invariants.** The rays' flux at birth sums to the source's total. A file
read, written and read again gives the same rays and spectrum.

**Units and frames.**
- **Positions:** mm, in the LED's frame.
- **Flux:** W.
- **Spectrum:** nm in the file, µm in Optiland.

**If the assumption is violated.** Loud.
- **Any other layout:** refused, naming the field.
- **A source with no spectrum and no wavelength:** refused.
- **The emitter IR (`KW-OPTILAND-08`):** Optiland traces only its own source
  classes, so `RayfileSource` is an `ExtendedSource` whose `generate` is
  replaced. The lowered emitter describes an extended source that is not
  the one traced. The NumPy backend never reads it; a compiled backend
  would.

**Checked by.**
- **Synthetic files:** a Lambertian square written and read back ray for
  ray, with a cos θ far field; each layout change refused.
- **In 3D:**
  - a run's rays are the file's records, placed, to 1e-12;
  - 1 : 3 per-ray fluxes survive and sum to the file's total;
  - a Lambertian file traces like Optiland's own Lambertian
    `ExtendedSource`: a quarter of the flux within 30°, within 4σ.
