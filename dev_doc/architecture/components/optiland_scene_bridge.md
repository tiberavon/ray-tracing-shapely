# `optiland_scene_bridge`

Taking a 2D outline designed here and building it as a 3D solid in
Optiland, a separate ray-tracing library, so the design can be traced in
three dimensions — and reading the solid back out as a labelled 2D outline.

## Concepts this component realises

- **`KB7`** — the bridge. `build_faces_from_profile` reads a `profile.json`
  — the outline of a designed element, span by span, with each span's role,
  mechanism and exact outward normal — and builds one Optiland surface per
  span, placed in 3D by `span_outward_ray`. `ExtrudedPolygonSolid` wraps the
  faces as one compound component. The direction is chosen from the span's
  stored normal, not recomputed from neighbouring points, because a sharp
  corner has two different normals and averaging them places the face
  wrong. `import_from_optiland` is the same mapping run backwards: it reads
  each live face's width and placement and rebuilds the outline's points
  and normals, so a face that was moved or resized in 3D — by hand, or by
  an optimiser — comes back moved. What a face cannot carry (the span's
  name, role and mechanism) it takes from the profile the solid was built
  from. `interior_index` reads the glass's refractive index off the faces,
  because `profile.json` has no field for it.

- **`KB7`, for round elements.** A profile declared as a *revolution* — a
  lens, a cone — carries half of its cross-section, from the axis back to
  it. `RevolvedProfileSolid` turns each span of that half into one of
  Optiland's exact surfaces of revolution: a lens face becomes a
  sphere-shaped surface, a flat face a disc or a ring, a straight edge a
  cylinder or a cone wall. Which side of each surface is glass is read
  from the outward normal stored in the profile, compared with how
  Optiland orients that surface, and every stored point and normal of a
  curved face is checked against the surface built from it. A designed
  face (a spline edge in 2D) becomes a `SplineRevolutionGeometry`, an
  even asphere an `AsphereRevolutionGeometry`, and a face that does not
  reach the axis a zone. The result is then checked to
  be a closed solid by the bridge's versions of `Volume()`'s two checks,
  which the extruded solid cannot pass, cast from a point the profile
  proves is inside (`Volume()`'s own guess misses a steep meniscus:
  `KW-OPTILAND-04`), sampling every rim a face has and none at a cone's tip
  (`KW-OPTILAND-06`, `KW-OPTILAND-07`). Built from the same numbers, the solid traces
  identically to Optiland's own `Lens`, ray for ray — that is the test.
  `axis_frame` gives the map between the profile's 2D coordinates and the
  solid's own frame (the axis becomes z; the outline's plane, x–z), and the
  solid's `cs` places that frame in the world, as a `Lens` is placed.
  `scene_placement` is the placement that puts the solid where its 2D scene
  had it, under the same plane mapping as the extruded prism, so two lenses
  from one 2D scene — or a lens and a prism — keep their relative places in
  3D. Checked on a two-lens system with the second lens decentred and
  tilted: in the plane, every exit ray agrees with the 2D trace of the same
  scene; out of the plane, the pair traces like two placed Optiland lenses.
  `source_cs` places sources on or at an angle to the placed axis.
  `import_from_optiland` reads a revolved solid back the same way as an
  extruded one, from each face's live radius, aperture and position relative
  to its solid. Its renderers draw the same live faces at the solid's
  placement.

- **`KB7`, for round mirrors.** A revolve profile with `body: "sheet"` —
  a paraboloid, ellipsoid, hyperboloid, sphere or cone exported from 2D
  mirrors — becomes a `RevolvedProfileSheet`: one Optiland mirror
  (`ReflectiveComponent`) per span, on the same exact surfaces of
  revolution, placed and named as a solid's faces are, with no volume
  (`C-BRIDGE-12`). Each span needs a reflectance. Every meridional ray
  ends where the 2D trace of the same mirrors says it does. A span that
  does not reach the axis becomes a zone, and `symmetry.azimuth_deg` cuts
  the sheet to a range about its axis (the upper half of a projector
  headlamp's reflector), both on `CutConicGeometry`.

- **`KB7`, for plates.** A flat mirror or absorber in a plane containing the
  2D section's axis, perpendicular to the 2D plane (a headlamp's shade, an
  LED's board), is a `PlanarPlate`: one face on `PolygonPlaneGeometry`,
  standing on its 2D segment, with an outline the caller gives
  (`C-BRIDGE-13`).

- **`KD5`, a third tracer.** A collimator designed here is traced three
  ways: in 2D, revolved in Optiland's non-sequential engine, and in
  Optiland's *sequential* engine — the one used for imaging lenses, which
  follows a fixed order of surfaces and computes focal lengths. The last is
  built not from a profile but from the element's designed faces
  (`P-DESIGNED-FACES`), so it shares no geometry code with the other two.
  `fit_even_asphere` fits a face that reaches the axis as a conic plus
  polynomial terms, on its points and its slopes together;
  `fit_meridional_polynomial` fits a curved ring face as a polynomial in a
  frame tilted to its chord. Each fit reports its worst sag and slope error.
  The sequential engine cannot describe a cone wall, so the ring channel is
  built for meridional rays only — rays in a plane through the axis — with
  each cone a plane tilted to its line. A ray from the source leaves
  parallel in all three tracers, and the sequential engine's focal length
  agrees with the size of the source's image in 2D.

- **`KA1`** — each span's role and mechanism decide what kind of Optiland
  surface it becomes. An *entrance* that *refracts* is a refracting face; an
  *absorber* is an absorbing one. A combination with no mapping is an error,
  not a guess. A *reflecting* span also needs a reflectance — the fraction
  of light the mirror returns — which `profile.json` does not record; it is
  passed as `reflectances={"H": 0.95}`, and a reflecting span without one
  raises rather than becoming a perfect mirror nobody asked for. On the way
  back the same vocabulary is kept: the import produces a `profile.json`,
  not a bare list of corners, and `BasePrism.from_profile` (in
  `nonimaging_design`) turns it into a 2D element whose edges keep their
  names. Rebuilt from corners alone, every edge would come back called `0`,
  `1`, `2`, and *"the measuring surface"* would no longer resolve to
  anything; rebuilt from the profile, `find_edge_by_functional_label("M")`
  still finds it, with its role and mechanism attached.

- **`KD3`** — where the solid is incomplete, that is stated rather than
  smoothed over, and checked rather than trusted. By default the extrusion
  has no end caps: it is a set of walls with no floor or ceiling in the
  extrusion direction. Every source built by the helpers here aims across
  the walls and never toward the missing ends, so the gap is never reached
  — but a source tilted even slightly toward them loses light through the
  opening, and the tracer reports clean energy conservation because the
  escaped rays are simply gone. This was reproduced deliberately, with a
  tilted source, rather than reasoned about. Two things now answer it.
  `end_caps="refract"` or `"absorb"` closes both ends with a flat face cut
  to the exact outline (a polished glass end, or a blackened one), built
  from the same points as the walls so the edges meet exactly. And
  `check_containment(result)` reads the finished trace's event log — the
  record of where each ray went — and reports every ray whose path passed
  through where a cap would be. On the tilted-source reproduction the rays
  the check flags on the open solid are exactly the rays an absorbing cap
  stops on the closed one, so each confirms the other.

- **`KD13`** — where Optiland itself is wrong, the bridge says so by id.
  Its closed-solid check is not Optiland's `Volume()` but the bridge's own
  version of its two checks, because `Volume()` rejects three kinds of
  closed solid the bridge builds: a steep meniscus (`KW-OPTILAND-04`), a
  cone tip on the axis (`KW-OPTILAND-06`), and a conic zone
  (`KW-OPTILAND-07`). Each entry carries the Optiland change that would
  make the bridge's version unnecessary. Where a workaround would hide a
  defect instead, there is none: a ray can re-hit a mirror it just left
  near the world origin (`KW-OPTILAND-05`), and the tests and
  `C-BRIDGE-12` keep mirrors away from it rather than nudging rays.

- **`KC7`** — the bridge never imports the viewer. Scene assembly runs
  headless, in batch, on machines with no display; a dependency on the
  interactive 3D view would break that at import time, before any work
  started. The renderers for the solid live in a separate file and are
  registered against it from outside.

## Modules

| File | What it holds |
|---|---|
| `ray_tracing_shapely_optiland/scene_bridge.py` | Out to 3D: `build_faces_from_profile`, `face_from_span`, `span_outward_ray`, `build_end_caps`, `ExtrudedPolygonSolid`. Checking a trace: `check_end_cap_crossings`, and `ExtrudedPolygonSolid.check_containment`. Back to 2D: `import_from_optiland`, `interior_index`. Extrusion is built along one fixed axis from straight two-point spans; a revolve profile is passed on to `revolve.py`. Anything else raises `NotImplementedError` rather than approximating. |
| `ray_tracing_shapely_optiland/revolve.py` | The revolved half: `axis_frame`, `scene_placement`, `cs_from_axes` (a frame as Optiland's Euler angles, checked), `surface_from_span` (one span to one exact surface, placed and oriented), `build_revolved_faces`, `interior_point` (where the closed-solid check starts), `RevolvedProfileSolid`, `RevolvedProfileSheet` (revolved mirrors, no volume), and `import_revolved_from_optiland`, which `import_from_optiland` calls for a revolved solid. |
| `ray_tracing_shapely_optiland/sources.py` | A source specification (`P-SOURCE-SPEC`) as an Optiland source: `build_source_3d` (its coordinate system and config, the one Optiland source with the spec's emission law), `add_source_3d` (which also takes a `rayfile` spec: the file it names, checked, every record traced), and `scene_to_world`, the scene frame (a, b, c) to the world (a, c, b). The frame goes through `revolve.cs_from_axes`, which `scene_placement` uses too. A measured LED: `RayfileSource` (an `ExtendedSource` emitting a rayfile's records in order, with their flux; `KW-OPTILAND-08`), placed by `rayfile_frame`, added by `add_rayfile_source_3d`. |
| `ray_tracing_shapely_optiland/events.py` | `split_rays`: an Optiland event log cut into one `RayRecord` per ray (its source, the faces it hit, how it ended, its points, directions and flux). A record's direction at an event is the one it arrives with, so a ray's last free segment starts at its second-to-last point. numpy only: the snapshot, the agent tools and the comparison read the log through it. |
| `ray_tracing_shapely_optiland/compare.py` | `compare_2d_3d`: the same meridional rays traced in 2D (each alone, its brightest branch) and as 3D pencils (the source spec's `pencil`), faces named `<component>.<label>` on both sides (`span_at`: the profile span nearest a 2D hit), compared ray by ray; `Comparison.summary()` keeps the worst differences and the rays that differ. `compare_slice_3d`: each kept ray of a rayfile slice in 2D against its own record traced unturned in 3D, by exit angle from the axis (`C-SOURCE-03`). Headless. |
| `ray_tracing_shapely_optiland/plate.py` | `PlanarPlate` and `segment_placement`: a flat polygonal mirror or absorber standing on a 2D segment. |
| `ray_tracing_shapely_optiland/geometry.py` | `PolygonPlaneGeometry`, a flat surface bounded by any polygon — the end cap's shape, which Optiland's own flat surfaces (a rectangle or a disc) cannot take. `CutConicGeometry`, Optiland's conic with a central hole and an azimuth cut. `SplineRevolutionGeometry`, a surface of revolution whose meridian is a 2D spline edge, exact, NumPy only. `AsphereRevolutionGeometry`, the even asphere of revolution (the 2D asphere edge revolved): a ray's meeting points found in its own parameter, where the sag is a smooth function of the squared radius, bracketed within the surface's radius and sag bounds and split where the ray turns, so two close crossings are found; exact normals; NumPy only. |
| `ray_tracing_shapely_optiland/sequential_collimator.py` | A point-source collimator in Optiland's *sequential* engine, a third reference beside the 2D and non-sequential traces: `fit_even_asphere` (a designed face reaching the axis as a conic plus asphere terms, fitted on sag and slope), `central_channel_optic`, `fit_meridional_polynomial` (a designed curve as a polynomial in a tilted frame), `ring_channel_optic` (cavity wall and exit face as tilted planes, the TIR face a polynomial mirror: meridional rays only), `trace_from_focus`. Not part of the profile path: it is built from the element's designed faces, not from a profile (`P-DESIGNED-FACES`). |
| `ray_tracing_shapely_optiland/visualization/renderers.py` | `ExtrudedPolygonRenderer2D` and `3D`, drawing the extruded solid in Optiland's viewers, caps included; `RevolvedProfileRenderer2D` and `3D`, drawing a revolved solid from its live faces at its placement; `RevolvedProfileSheetRenderer2D` and `3D`, the same for a revolved sheet; `PlanarPlateRenderer2D` and `3D`, a plate's outline. |
| `ray_tracing_shapely_optiland/irradiance.py` | A 3D trace's light on a plane: `exit_rays_3d` (the last free segment of every ray that escaped or reached a detector, back in the scene frame) and `irradiance_map_3d` (those binned by the core's `irradiance_map`). numpy only. |
| `ray_tracing_shapely_optiland/visualization/snapshot.py` | Static 3D pictures that survive a saved notebook: `snapshot_png` renders a populated `vtkRenderer` off-screen to PNG bytes at a camera given in world terms; `ray_polylines` makes one polyline per ray with the faces it met (from `events.split_rays`), `group_polylines` sorts them by path, and `polyline_actor` draws a group in one colour (Optiland's own ray overlay colours only by source, bounce or segment). vtk only, no trame; the bridge never imports it (`KC7`). |
| `ray_tracing_shapely_optiland/visualization/irradiance_plot.py` | `plot_irradiance_map`: the map, its two sections through the axis, and, given a 2D `LineProfile`, the 3D flux per mm of radius against the 2D profile folded about the axis (each over its own peak: what a 2D section carries). `save_irradiance_plot` writes SVG and PNG and returns `render_result`'s descriptor with the map's summary. matplotlib, imported only when drawing. |

## What it produces

- **`P-NSQ-SCENE`** — the built Optiland components and their placements.
  Not a whole assembled scene: the caller adds sources and detectors and
  runs the trace.
- **`P-PROFILE`**, on the way back — `import_from_optiland`'s result is a
  `profile.json` like the one that went out, with the live geometry's
  numbers in it.

## What it needs from elsewhere

- **`P-PROFILE`** from `nonimaging_design` — the `profile.json`.
- **`P-ROLE-MECHANISM`** from `core_labelling` — the vocabulary the mapping
  is keyed on.
- **`P-DESIGNED-FACES`** from `nonimaging_design` — a collimator's designed
  faces, for the sequential reference.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-BRIDGE-01` | **Owns** it. Every (role, mechanism) pair maps to a component type, and an unmapped pair raises. A reflecting span without a reflectance raises too. |
| `C-BRIDGE-02` | **Owns** it. Extrusion along the fixed axis from straight spans, and revolution from exact surfaces of revolution; the rest raises. |
| `C-BRIDGE-03` | **Owns** it. The 2D renderer requires the `XZ` projection; the default `YZ` draws nothing useful. |
| `C-BRIDGE-04` | **Owns** it. An uncapped solid leaks silently under off-plane light; caps close it, and the containment check detects it. |
| `C-BRIDGE-05` | **Owns** it. This module must never import the viewer. |
| `C-BRIDGE-06` | **Owns** it, with `nonimaging_design`. A solid read back keeps every span's name, role and mechanism. |
| `C-BRIDGE-07` | **Owns** it, with `nonimaging_design`. A revolve profile is a half-section; each face's glass side comes from the stored normal. |
| `C-BRIDGE-08` | **Relies** on it. Every point and normal of a curved span is checked against the surface built from it. |
| `C-BRIDGE-09` | **Owns** it. A revolved solid passes the bridge's versions of `Volume()`'s two checks when it is built, from a point proved inside; zones and cone tips are allowed. |
| `C-BRIDGE-10` | **Owns** it. A revolved solid is placed by its `cs`; `scene_placement` puts it where its 2D scene had it. |
| `C-BRIDGE-11` | **Owns** it. The revolved solid's and sheet's renderers draw the live, placed geometry. |
| `C-BRIDGE-12` | **Owns** it. A revolved sheet becomes reflecting surfaces of revolution with no volume, and traces as its 2D mirrors do. |
| `C-BRIDGE-13` | **Owns** it. A plate standing on a 2D segment shows that segment as its section, and traces as the 2D segment does. |
| `C-BRIDGE-14` | **Owns** it. The same meridional rays traced in 2D and as 3D pencils, faces named alike; every ray whose 3D rays never follow its 2D main path is reported with both paths. |
| `C-PROFILE-01` | **Relies** on it. The profile carries exact normals, so this side never derives them. |
| `C-SOURCE-01` | **Owns** it, with `nonimaging_design`. A source specification becomes the Optiland source with its law, placed under the same mapping as the optics. |
| `C-SOURCE-02` | **Owns** it, with `nonimaging_design`. A rayfile is traced as its own records, in order, placed by the scene's axes, each with its flux. |
| `C-SOURCE-03` | **Owns** it, with `nonimaging_design`. A slice's rays are checked against their own records in 3D, by exit angle. |

## How it is shipped

A separate package, `ray_tracing_shapely_optiland`, installed alongside the
core. Requires Optiland.
