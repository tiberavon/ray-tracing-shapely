# Alphabet — what each port is made of, field by field

`01_ports.md` says what each port is for. This page says what is *in* it:
every field, what it holds, and anything a reader needs to know to
interpret it. Where a field exists because of a promise, the promise is
named.

Types are given for the reader who wants them and can be skipped by the
reader who does not. *Optional* means the field may be empty. *Dimensionless*
means a plain number with no unit — the engine's brightness is like that,
and it only gains a unit in the physical layer.

## `P-SCENE-PROTOCOL` — the three questions

Every optical object answers these. The engine calls the first once before
any ray moves, and the other two for every ray that might touch the object.

| Question | What the object answers |
|---|---|
| `on_simulation_start()` | Nothing, usually. A source answers with the rays it is emitting. |
| `check_ray_intersects(ray)` | The point where this ray would hit me, or nothing if it would not. |
| `on_ray_incident(ray, ...)` | What happens: nothing (the ray continues), one new ray, or several. |

The answer to the third question is a small record, every part of it
optional:

| Field | Meaning |
|---|---|
| `isAbsorbed` | The ray stops here. |
| `newRays` | The rays that leave this surface — a refracted one, a reflected one, or both. |
| `truncation` | Brightness dropped because it fell below the cutoff. |
| `brightnessScale` | A correction when the ray density under-samples this object. |
| `isUndefinedBehavior` | Something the object could not handle properly. |

## `P-RAY-LINEAGE` — a ray segment, and the tree over all of them

One straight piece of a ray's path. It records its own identity, where it
came from, and what it is carrying.

| Field | Meaning | Type |
|---|---|---|
| `uuid` | This segment's own identifier, freshly made and never reused (`C-LINEAGE-01`). | text |
| `parent_uuid` | The identifier of the segment this one came from. Empty only for a ray straight from a source. | text, optional |
| `interaction_type` | The event that created this segment: `source`, `reflect`, `refract`, or `tir` (total internal reflection). Spelled exactly as the mechanism vocabulary spells it (`C-VOCAB-01`). | one of four words |
| `p1`, `p2` | The segment's two endpoints, in scene units. | two points |
| `brightness_s`, `brightness_p` | Brightness in the two polarisations. Dimensionless. | two numbers |
| `wavelength` | In nanometres. Empty unless colour is being simulated. | number, optional |
| `is_tir_result`, `caused_tir` | This segment was born of, or itself triggered, total internal reflection. | yes/no |
| `tir_count` | How many total internal reflections in this ray's history so far. | whole number |
| `is_grazing_result__…`, `caused_grazing__…` | Three separate tests for a ray skimming a surface — by angle, by polarisation, by transmission. | yes/no, each |
| `source_uuid`, `source_label` | Which source emitted the ray this segment belongs to. | text, optional |
| `medium_index` | The refractive index of whatever the segment is travelling through. Default 1 (air). Needed for optical path length. | number |
| `hit_surface_uuid`, `hit_point`, `hit_normal` | Where this segment ended: which surface (a blocker that absorbed it included), at what point, with what surface direction. Only recorded when the simulation was started with `record_surface_hits=True`. | optional |
| `incident_angle` | The angle at which this segment struck the surface that stopped it, from the surface's perpendicular. Between 0 and 90°. **Not** the same field as a detector hit's angle (`C-HIT-01`). | number, optional |
| `gap`, `is_new`, `body_merging_obj` | Internal bookkeeping for the engine. | — |

The tree itself (`RayLineage`) is stored as four lookups: each segment's
parent, each segment's children, each segment by identifier, and each
segment's interaction type. They are filled as the run proceeds and never
edited afterwards.

## `P-SCENE-NAMES` — an object's name

| Field | Meaning | Type |
|---|---|---|
| `name` | The name you gave the object. Empty by default, and nothing here checks it — the check happens when two runs are compared (`C-LABEL-01`). | text, optional |

## `P-ROLE-MECHANISM` — the two word lists

| Field | Meaning | Values |
|---|---|---|
| `Role` | What a surface is for. | `entrance`, `wall`, `absorber`, `exit`, `blocker`, `source`, `sample_medium` |
| `Mechanism` | What light does at it. Must be spelled exactly as a segment's `interaction_type` (`C-VOCAB-01`). | `refract`, `reflect`, `tir` |
| `.role` on any object | The object's role, if it has one. | a `Role`, optional |
| An element's edge-role entry | For each edge of a designed element: a short label, a long label, and optionally its role (`C-LABEL-02`). | 2 or 3 items |

## `P-HIT-RECORD` — one counted crossing of a detector

| Field | Meaning | Type |
|---|---|---|
| `ray_uuid` | Which segment crossed. | text |
| `bin_index` | Which bin along the detector it landed in. Empty if the detector has no bins. | whole number, optional |
| `position` | How far along the detector line from its first end. | number |
| `incident_point` | Where exactly. | a point |
| `brightness_s`, `brightness_p`, `brightness_total` | Brightness at the crossing, by polarisation and combined. | numbers |
| `sign` | Which direction it crossed: `+1` or `-1`. Only the absorbing side is counted by default (`C-DET-01`). | +1 or −1 |
| `wavelength` | In nanometres, or empty. | number, optional |
| `incident_angle` | The angle to the detector line's perpendicular, 0 to 90°. The detector's own measurement, separate from the ray's field of the same name (`C-HIT-01`). | number |

## `P-BEAM-CTOR` — what builds a beam

| Field | Meaning | Type |
|---|---|---|
| `p1`, `p2` | The line the beam is emitted from. | two points |
| `brightness` | Starting brightness. Default 0.5. | number |
| `wavelength` | Default green. | number |
| `emis_angle` | The **full** angle the beam spreads across, 0 to 180°. Not a half-angle. Negative values raise (`C-BEAM-01`). | number |
| `lambert` | Emit more straight ahead and less to the sides, as a diffuse surface does. | yes/no |
| `random` | Place rays randomly across the spread rather than evenly. | yes/no |

## `P-SIGNATURE` — a route, reduced

One entry per interaction along the route, in order.

| Field | Meaning | Type |
|---|---|---|
| `surface_name` | The object's name. Empty if it was unnamed. | text, optional |
| `edge_index` | Which edge of that object: one number per physical surface, in outline order. A circular arc is one edge, however it is stored; a curve that a design cut into straight pieces is one edge per piece, so the number is a position along the cut-up curve, not a coordinate (`C-SIG-01`). | whole number, optional |
| `interaction_type` | What happened there. | one of four words |

## `P-SIGNATURE-SPECTRUM` — every route in a run, with its energy

The saved form of the table above, one row per distinct route.

| Field | Meaning | Type |
|---|---|---|
| `signature` | The route, as a list of the triples above. | list |
| `energy` | The summed energy of every path that reduced to this route. Ranks routes against each other; not a physical amount (`C-SIG-02`). | number |
| `count` | How many paths reduced to this route. | whole number |

## `P-RUN-BUNDLE` — a saved run

One folder per run, containing:

**`params.json`** — the settings, in two sections (`C-RUN-02`):

| Field | Meaning |
|---|---|
| `physical_params` | Settings that describe the device: geometry, index, wavelength. |
| `numerical_params` | Settings that describe the simulation: ray density, brightness cutoff, mesh resolution. |
| `name_topology` | A fingerprint of every object's name and type, checked before any comparison (`C-LABEL-01`). |

**`summary.json`** — the headline numbers: how many rays and segments,
counts of total internal reflection and grazing events, the wavelengths
present, the sources present, and whether the run succeeded.

**`rays.sqlite`** — every segment and its relationships, as seven tables an
assistant can query:

| Table | One row per | Holds |
|---|---|---|
| `rays` | segment | Everything in `P-RAY-LINEAGE` above, flattened into columns. |
| `glass_objects` | glass | Name, type, refractive index, edge count, centroid, area. |
| `edges` | edge of a glass | Its labels, type (`line`, `circular`, `conic` or `spline`), endpoints, midpoint, length. For a curved edge the midpoint is on the curve and the length is the arc length. |
| `ray_glass_membership` | (segment, glass) | Which segments lie inside which glass. |
| `ray_edge_crossing` | (segment, edge) | Which segments cross or end on which edge, and at what angle to the edge's perpendicular. A circular edge's perpendicular is taken where the segment meets it. |
| `detectors` | detector | Name, endpoints, bin size. |
| `detector_hits` | counted crossing | `P-HIT-RECORD`, as rows. |
| `connections` | joined forward/backward pair | Only present after a bidirectional run: which two segments were matched, on which surface, how close, how nearly opposite. |

A glass's edge may be an exact curve rather than a straight line or an arc:
a point of its outline (`path[i]`) may carry a `curve` descriptor, a conic or
a spline with the same fields as `spans[i].curve` in `P-PROFILE` below, or an
even asphere, `{"type": "asphere", "vertex", "axis", "radius", "conic",
"coefficients"}`: the conic's sag plus A1 s² + A2 s⁴ + …, the coefficients in
Zemax's and Optiland's order, `radius` null for a flat base. The edge from
that point to the next is then that curve, traced exactly
(`core.glass_curves`: `ConicCurve`, `AsphereCurve`, `SplineCurve`), and
moving, rotating or scaling the glass carries it along. In `edges` it is one
row, of type `conic`, `asphere` or `spline`. In `profile.json` an asphere
span is schema 1.5's.

**`manifest.jsonl`** — one line appended per run, so a design's history is
one file. **`graph.json`** and **`signature_spectrum.json`** — present
when the run was bidirectional.

A schema version and a confidence field are required by `C-RUN-01` and not
yet written.

## `P-PROFILE` — a designed outline, ready to become 3D

The same shape travels both ways: written by `export_profile` from a 2D
element, and by `import_from_optiland` from a 3D solid; read by the 3D
bridge, and by `BasePrism.from_profile` to rebuild the element in 2D.

| Field | Meaning | Type |
|---|---|---|
| `schema_version` | Currently `"1.5"` (1.2 added conic and spline glass edges; 1.3 adds `sources`; 1.4 the `rayfile` source; 1.5 the asphere glass edge). A `"1.0"` profile — no `curve`, no `body` — still reads, as all straight spans and a solid. | text |
| `points` | Points along each span: its two ends for a straight span; for an arc, conic, asphere or spline, `curve_samples` points evenly spaced along it (33 by default), both ends included. | list of points |
| `normals` | The exact outward direction at each point — stored **per span**, so a sharp corner's two edges each keep their own (`C-PROFILE-01`). | list of unit vectors |
| `spans[i].index_start`, `.index_end` | Which entries in `points` and `normals` belong to this span. | two whole numbers |
| `spans[i].short_label`, `.long_label` | The span's functional labels. | text, optional |
| `spans[i].role`, `.mechanism` | What it is for and what light does there. Empty if the element's class did not tag it. | one word each, optional |
| `spans[i].curve` | The span's exact shape: `{"type": "line"}`, `{"type": "circle", "center": [a, b], "radius": R}`, `{"type": "conic", "vertex": [a, b], "axis": [ux, uy], "radius": R, "conic": K}` (R signed along the axis, as in Optiland), for a mirror or (schema 1.2) a glass edge, or `{"type": "spline", "points": [...], "tangents": [...]}`, a cubic Hermite curve through the points with those unit tangents, with an optional `"domain": [p0, p1]` for a piece of one. The points are checked against it. Absent means a line. | a small record |
| `spans[i].curve` (asphere) | Schema 1.5: `{"type": "asphere", "vertex", "axis", "radius", "conic", "coefficients"}`, the conic's sag plus A1 s² + A2 s⁴ + …; `radius` null for a flat base. | descriptor |
| `body` | `solid` — glass with an inside; or `sheet` — mirrors with no inside, every span reflecting, spans not necessarily joined (written by `export_sheet_profile`). | one word |
| `symmetry.kind` | How the outline becomes a solid: `extrude`, `revolve`, or `free`. | one word |
| `symmetry.plane_axes`, `.extrude_axis`, `.length` | For `extrude`: which two axes the outline lies in, which axis it extends along, and how far. | required for `extrude` |
| `symmetry.axis` | For `revolve`: the axis of revolution, as a point on it and a direction, `{"point": [a, b], "direction": [ux, uy]}`, in the outline's own coordinates. The spans are then only the half of the outline to the left of that direction, one chain from the axis back to it; a surface the axis crosses, such as a lens face, is cut there. | required for `revolve` |
| `construction_params` | The physical and numerical settings that built the element, split as in `P-RUN-BUNDLE`. When any span is curved, the numerical half records `curve_samples`. | two sections |
| `sources` | The light the element is designed for: source specifications, `P-SOURCE-SPEC` below, each with a distinct `name`. Empty when none was given; absent from a 1.2 profile, which reads as none. | list of records |
| `fit` | `null`, or for spans built from a measurement `{"spans": {label: record}}`: the scan file and its digest, the model the span holds (`fitted` or `as_measured`), the fitted surface and alignment, the residual (RMS, PV, slope and its noise floor), the correlation warnings, the smoothing, and the rotational symmetry assumed (one meridian) or measured (several). The span's normals are its model's. | record |

The glass's refractive index is not a field; a 2D rebuild is given it
separately — from `interior_index` when the profile was read off a solid.

### `P-SOURCE-SPEC` — one light source, for both engines

The format of one entry of a profile's `sources`, and the argument of
`build_source_2d` and `build_source_3d`. Written in the 2D scene's
coordinates, with one more out of the plane: a point is (a, b, c), and in
the 3D world it is (a, c, b). The (a, b) to (a, 0, b) half is the bridge's
plane mapping (`C-BRIDGE-10`).

| Field | Meaning | Type |
|---|---|---|
| `name` | Unique within the profile; the 2D source's name and the 3D source's. | text |
| `kind` | `pencil` (one ray), `point`, `patch` (a flat rectangle square to its axis), or `rayfile` (a measured LED's rays; schema 1.4, fields below). | one word |
| `position` | `[a, b]` or `[a, b, c]`; `c` is 0 when left out. For a patch, the point `anchor` names. | two or three numbers |
| `direction_deg` | The emission axis: an angle in the 2D plane, from +a towards +b. An axis out of the plane cannot be written. | degrees |
| `emission` | `uniform` (equal intensity in every direction of the cone) or `lambertian` (intensity proportional to the cosine from the axis). Not for a pencil. | one word |
| `half_angle_deg` | The cone's half-angle, up to 90. A `lambertian` source fills the hemisphere, so it is 90; a `uniform` patch must be below 90. Both limits are the 3D engine's: it has no other counterpart. | degrees |
| `size` | A patch's sides: `[in_plane, out_of_plane]`, the first lying in the 2D plane when `roll_deg` is 0. | two numbers |
| `roll_deg` | A patch's turn about its axis; positive turns its first side from the plane towards +c. Default 0. | degrees |
| `anchor` | Where `position` is on a patch, as fractions of `size`: `[0.5, 0.5]` its centre (default), `[0, 0]` a corner. | two numbers |
| `flux`, `flux_unit` | Total flux; `W` (default) or `lm`. Default 1. | a number, one word |
| `wavelength_um` | One wavelength, in micrometres. Default 0.55; for a rayfile, none (its spectrum, the peak in 2D). | a number |

A `rayfile` source has `position`, `direction_deg` and `roll_deg`, placed
as `rayfile_frame` places a file (its z along the axis), and no emission
law, size or flux of its own. Instead:

| Field | Meaning | Type |
|---|---|---|
| `rayfile.path` | The file, relative to the profile's folder or absolute. The file is not in the profile. | text |
| `rayfile.format` | The format argument its parser takes (`read_rayfile`'s, one of `FORMATS`: `tm25`). | one word |
| `rayfile.n_rays`, `rayfile.flux`, `rayfile.flux_unit`, `rayfile.sha256` | The file when the spec was written. A file that no longer matches is refused. `flux` and `flux_unit` are copied to the top level. | numbers, text |
| `slice.max_offset_mm` | The 2D section's limit on h (`slice_rayfile`), chosen from the slicing flow's table. | mm |
| `slice.kept_share`, `slice.rays_kept` | What that limit kept; checked against the file when the 2D source is built. | a share, a count |

**In 2D** a source is its section by the scene plane (c = 0), as a
`RaySetSource`: a list of rays, each with its start, direction and
brightness. Positions sit at the midpoints of equal steps along the section, and
angles at the midpoints of equal steps across the cone. Each ray is
weighted by its law's intensity in the plane, the largest weight 1.
`flux_per_brightness` is the flux over the summed brightness of those rays.
A pencil or point off the plane, or a patch that does not cross it, has no
section and is refused.

## `P-RAYFILE` — a measured LED's rays

A supplier's rayfile (IES TM-25, binary), and what `read_rayfile` returns
from it: a `Rayfile`. Only the layout checked against a file is read; any
other is refused (`C-SOURCE-02`).

| Field | Meaning | Type |
|---|---|---|
| `positions` | Where each ray starts, in the LED's own frame: z along its axis, origin where the supplier puts it (for ams OSRAM, the centre of the package on top of the mould's base). Rays start in air. | n × 3, mm |
| `directions` | Each ray's direction. | n × 3, unit |
| `flux` | Each ray's share of the flux. | n numbers, W |
| `spectrum_nm` | One spectrum for every ray: wavelength and relative value. | k × 2, nm |
| `name` | The product, from the header. | text |
| `header` | Every header field read: radiant flux, ray count, date, text fields; fields not decoded kept raw. | record |

**In 3D** a rayfile is placed like a source specification's axes: its z along
the emission axis, its x along `e_out`, its y along `e_in`, at a point of the
2D scene (`rayfile_frame`). Ray *k* of a run is record *k* mod *n*.

**In 2D** a rayfile is sliced (`slice_rayfile`, `C-SOURCE-03`) for a
rotationally symmetric optic:
- **Skew:** each record's skew offset h is the distance at which its line
  passes the axis, 0 for a meridional ray.
- **The turn:** each ray is turned about the axis into the plane with its
  direction kept, and its offset dropped.
- **What is kept:** rays with |h| at most the caller's limit.
- **What is reported:** the flux in the rest, as `skew_share`: the light a
  2D section cannot carry.
- **The radiation pattern** (`radiation_pattern`, `radiation_plot_svg`):
  the kept rays' intensity against the angle from the axis, laid over the
  LED's own, so a slice that is not a fair sample of the LED's directions
  shows.
- **Choosing the limit** (`RayfileSlicingFlow`): a machine that asks for
  the rayfile and the package's footprint, checks one against the other,
  and tabulates the flux kept at a series of limits, with the limits at the
  ends of the range the choice is made in.

## `P-DESIGNED-FACES` — a designed element's faces, for another tracer

Returned by `TIRCollimator.section_faces(points=None)`: one entry per
optical face of the upper half-section, keyed by the face's short label.

| Field | Meaning | Type |
|---|---|---|
| key | The face's short label, as in the element's outline: `12b`, `22b`, `12a`, `22c`, `22a`. | text |
| points | The face's points in the element's own frame: the source point F at the origin, the axis along the first coordinate, the distance from the axis (never negative) the second. A straight face is its two ends; a designed face is its designed points, `12a` from the vertex outwards, `22c` from its rear end to its front end. | list of points |
| normals | The exact unit normal at each point — the design's own, not estimated from neighbours. | list of unit vectors |
| `points=` | How many points per designed face, recomputed from the design; by default the spline edge's own count. | whole number, optional |

The receiving side (`sequential_collimator`) reads the first coordinate as
Optiland's z and the second as its y.

## `P-PHYSICAL-SCENE` — the scene with units

| Field | Meaning | Type |
|---|---|---|
| `PhysicalScene.scene_unit` | What one scene unit is: `nm`, `µm`, `mm`, `cm`, or `m`. Default `mm`. | text |
| `PhysicalScene.calibration_factor` | How much power one unit of brightness represents, per metre of scene. Empty until `set_calibration` is called. | quantity (W/m), optional |
| `ProjectionModel.symmetry` | Fixed by which projection class was chosen: `extrude`, `free`, or `revolve` (`C-UNITS-01`). | one word |
| `ProjectionModel.to_irradiance(...)`, `.to_power_per_m(...)` | The two conversions: power per metre to power per square metre, and total power to power per metre. The revolved projection's raise `NotImplementedError`. | quantity in, quantity out |
| `CylindricalPerpendicularProjection.height_m`, `PointSourceProjection.effective_depth_m`, `RevolvedProjection.receiver_radius_m` | The one physical dimension each projection needs. | quantity (m) |
| `Photoconversion.photosensitivity`, `.integration_time`, `.dark_output_voltage`, `.saturation_output_voltage`, `.output_offset_voltage`, `.readout_noise` | A sensor's response: how much voltage per unit of light per second, and its floor, ceiling, offset and noise. | quantities, unit-checked (`C-UNITS-02`) |
| `Photoconversion.compute_irradiance(...)`, `LinearSensor.compute_irradiance()` | Pixel readings back to irradiance. | quantity (W/m²) per pixel |

## `P-QUANTITY-PARSING` — reading and checking a number-with-unit

| Field | Meaning |
|---|---|
| `ureg`, `Quantity` | The one unit registry the whole physical layer shares, and the quantity type bound to it. |
| `parse_quantity(text, expected_kind)` | Turn `"30 mW/cm^2"` into a checked quantity of the expected kind, or raise a `ValueError`. For text arriving from outside. |
| `ensure_quantity(value, expected_kind, name=…)` | Check a quantity someone already has. For code receiving a value it must validate. |
| `parse_radiometric_quantity`, `ensure_radiometric_quantity` | Stricter versions that also tell an irradiance from a radiance — which the registry, treating angles as dimensionless, otherwise cannot. |
| `POWER`, `IRRADIANCE`, `RADIANCE`, `RADIANT_EXPOSURE`, `LENGTH`, `TIME`, `VOLTAGE`, `PHOTOSENSITIVITY`, `SOLID_ANGLE`, `ANGLE`, … | Named reference units for each kind of quantity the layer uses, so a caller writes `IRRADIANCE` rather than `"W/m^2"`. |

## `P-HAZARD-ROUTINES` — a limit that says where it came from

Every limit function returns a `LimitResult`:

| Field | Meaning | Type |
|---|---|---|
| `value`, `unit` | The limit and its unit. | number, text |
| `wavelength_nm`, `duration_s`, `alpha_rad` | What it was computed for: wavelength, exposure duration, and the source's apparent angular size (0 if not relevant). | numbers |
| `region` | Which hazard: `retinal_thermal`, `blue_light`, `actinic_uv`, … | text |
| `time_regime` | Which branch of the formula applied, e.g. `t <= 10 s`. | text |
| `equation` | A readable citation of the formula and its source. | text |
| `factors` | The correction factors that went in. | named numbers |
| `notes` | Anything else the reader should know. | text |

## `P-CLASSIFICATION-RUN` — a classification, step by step

One folder per run:

| File | Meaning |
|---|---|
| `inputs.json` | The inputs, exactly as submitted. |
| `events.jsonl` | One line per step entered: a sequence number, a timestamp, the step's name, the attempt number, and the step's explanation. Append-only. |
| `result.json` | The result, the attempt number, and how long it took. Rewritten on each attempt; holds the latest. |
| `state.svg` | A picture of the diagram with the current step marked. Rewritten on every move. Absent if drawing was switched off or the drawing tool was not installed. |

And two files at the top level: `manifest.jsonl`, one line per run; and
`heartbeats.json`, the current state of every run in progress, for the
dashboard.

## `P-INTAKE-RUN` — gathering the inputs, step by step

The same folder shape as above. `result.json` additionally records the
identifier and result of the classification run this intake launched.

## `P-SLICING-RUN` — choosing a rayfile slice's limit, step by step

The same folder shape, from `RayfileSlicingFlow`. The events are its
questions, the answers' checks, and the slicing. `result.json` holds the
table:

| Field | Meaning |
|---|---|
| `rows` | Per limit on h (mm): rays kept, flux kept, kept and skew share, the kept flux's share within 30° of the axis, and whether the kept share is inside the kept range. |
| `limit_for_kept_share_mm` | The limits that keep exactly the two ends of the kept range. |
| `package_mm`, `half_diagonal_mm` | The footprint given, and the largest limit it allows. |
| `led_within_30deg` | The whole LED's share within 30°, for the rows' column. |
| `warnings` | Start points covering little of the footprint, or centred off the axis. |

## `P-AGENTIC-ENVELOPE` — a tool's answer

| Field | Meaning |
|---|---|
| `status` | `"ok"` or `"error"`. |
| `data` | Present only on `ok`. The answer, as plain data. |
| `message` | Present only on `error`. What went wrong, written to be acted on. |

## `P-KERNEL-CONTEXT` — where the live objects are kept

A store filled once after a simulation, read by every tool.

| Key | Holds | Filled by |
|---|---|---|
| `scene` | The scene. | `set_context` |
| `segments` | Every traced segment. | `set_context` |
| `lineage` | The parent/child tree, if there is one. | `set_context` |
| `db` | The per-run database, built from the segments. | `set_context` |
| `render_dir` | Where rendered drawings are saved. | `set_context` |
| `bidirectional` | A bidirectional result, if one was added. | `set_bidirectional_context` |

## `P-TOOL-REGISTRY` — the list of tools

One record per tool:

| Field | Meaning |
|---|---|
| `name` | What the assistant calls it. |
| `function` | The code that runs. |
| `description` | One line saying what it does — the text the assistant reads. |
| `parameters` | The tool's inputs, each with a type and a description, in the JSON Schema form assistant frameworks expect. |

## `P-OPTILAND-PLUGIN`

Planned. No fields specified yet.

## `P-NSQ-SCENE` — the 3D surfaces built from a profile

| Field | Meaning |
|---|---|
| `build_faces_from_profile(...)` returns | One Optiland surface per span, keyed by the span's short label — refracting, reflecting or absorbing according to its mechanism (`C-BRIDGE-01`). A reflecting span takes its reflectance from the `reflectances` argument. |
| `ExtrudedPolygonSolid.surfaces` | The same surfaces, wrapped as one compound object so a viewer can draw it — plus the two end caps, `end_cap_neg` and `end_cap_pos`, when the solid was built with `end_caps` (`C-BRIDGE-04`). |
| `ExtrudedPolygonSolid.end_caps` | `None` (open ends, the default), `"refract"` (polished glass ends) or `"absorb"` (blackened ends). |
| `ExtrudedPolygonSolid.profile` | The original profile, kept so the 2D and 3D renderers can draw the cross-section, and so a read-back can recover the labels. |
| `span_outward_ray(...)` returns | Where and how to place a face, read from the span's own stored normal. |
| `PolygonPlaneGeometry.vertices` | An end cap's outline, in the cap's own flat frame. Optiland's own checks see only its bounding rectangle (`C-BRIDGE-04`). |
| `CutConicGeometry(radius, conic, aperture_radius, inner_radius=, azimuth_deg=)` | Optiland's conic of revolution with a central hole and/or cut to an azimuth range (degrees, from local +x towards +y). Each root of the surface is tested against the cut separately, so a ray through a removed part still meets the kept part behind it (`C-BRIDGE-12`). |
| `SplineRevolutionGeometry(points, tangents, domain=)` | A surface of revolution whose meridian is a spline (`(r, z)` points with unit tangents, the 2D spline edge's own curve), monotonic in r: a designed lens face or TIR wall, or a zone of one. Exact normals; roots bracketed per segment and refined by bisection, so only a ray grazing the surface within 1/16 of a segment can pass it. NumPy only, no gradients (`C-3D-01`). |
| `AsphereRevolutionGeometry(radius, conic, coefficients, outer_radius, inner_radius=)` | The even asphere of revolution about the local z axis, its vertex at the origin: the 2D asphere edge's surface, coefficients from r², `radius` None for a flat base; a zone when `inner_radius > 0`. Exact, NumPy only, forward only. |
| `symmetry.azimuth_deg` | In a sheet profile: the range about the axis the revolved mirror covers, from the half-section's side; `[-90, 90]` is the half on the side drawn in 2D (`C-PROFILE-01`, `C-BRIDGE-12`). |
| `check_containment(result)` returns | `crossings` — how many recorded ray paths passed through an end-cap position; `ray_ids` — which rays; `flux` — the light they carried. Warns when `crossings` is not zero. |
| `import_from_optiland(solid)` returns | A `P-PROFILE` with the live faces' points and normals and the original labels (`C-BRIDGE-06`). |
| `interior_index(solid, wavelength_um)` returns | The glass's refractive index at that wavelength, read from the faces. Wavelength in micrometres, Optiland's unit. |
| `RevolvedProfileSolid.surfaces` | One exact surface of revolution per span of the half-section, each named `<solid>.<short label>` (`L2.S1`); `face(label)` finds one by its short label (`C-BRIDGE-02`, `C-BRIDGE-10`). |
| `RevolvedProfileSolid.surface_kinds` | What each span became: `conic` (a lens face, or a zone of one), `spline` (a designed face: a spline meridian revolved), `disc`, `annulus` (a flat ring), or `frustum` (a cylinder or cone wall). |
| `RevolvedProfileSolid.volume` | Optiland's `Volume`; the faces were checked to form a closed solid by the bridge's versions of Optiland's two checks (every rim meets another face's; every ray from `interior_point(profile)` crosses the boundary an odd number of times), which accept zones and cone tips on the axis (`C-BRIDGE-09`, `KW-OPTILAND-06`, `KW-OPTILAND-07`). |
| `interior_point(profile)` | A point inside a revolve profile's half-section, as far from its edges as possible (its pole of inaccessibility); where the closed-solid check starts its rays, since `Volume()`'s own guess misses a steep meniscus (`KW-OPTILAND-04`). |
| `RevolvedProfileSolid.interior_on_back(label)` | Whether that face's glass is on the side Optiland calls its back, as read from the stored normal (`C-BRIDGE-07`). |
| `axis_frame(profile)` returns | The map between a revolve profile's 2D coordinates and the solid's own frame: the axis is z through the origin, the half-section's side +x. Without a placement, that frame is the world. |
| `RevolvedProfileSolid(..., cs=)` | Where the solid's own frame sits in the world, as a `Lens`'s `cs` places its front vertex (`C-BRIDGE-10`). `to_world(point)` maps a profile point to the world; `source_cs(z, field_angle_deg, x)` places a source on the placed axis, optionally tilted within the outline's plane. |
| `scene_placement(profile)` returns | The `cs` that puts the solid where its 2D scene had it: scene point (a, b) to world (a, 0, b), the extruded prism's mapping, so the elements of one 2D scene keep their places in 3D (`C-BRIDGE-10`). |
| `RevolvedProfileSheet(name, profile, reflectances, medium=, cs=)` | Revolved mirrors from a `sheet` profile: one Optiland mirror per span, named, placed and looked up as a solid's faces are; no volume. `reflectances` is one value for every span or one per label. A span not reaching the axis becomes a zone; `azimuth_deg` holds the profile's cut, None for a full turn (`C-BRIDGE-12`). |
| `RevolvedProfileSheetRenderer2D`, `RevolvedProfileSheetRenderer3D` | The same for a revolved sheet, span by span and unfilled: each mirror and its mirror image as open lines in 2D (a side only where a cut keeps it), one swept actor per span in 3D, over the cut's range (`C-BRIDGE-11`). |
| `PlanarPlate.from_segment(name, segment, polygon, reflectance= \| absorbing=True)` | A flat plate standing on a 2D segment, perpendicular to the 2D plane: one mirror or absorber face named `<name>.plate`. `polygon` is (u along the segment, v out of the 2D plane); its chord along v = 0 must be the segment (`C-BRIDGE-13`). `PlanarPlate(name, polygon, cs=...)` places one anywhere. |
| `PlanarPlateRenderer2D`, `PlanarPlateRenderer3D` | Draw a plate's outline from its live face, at its place (`C-BRIDGE-13`). |
| `RevolvedProfileRenderer2D`, `RevolvedProfileRenderer3D` | Draw a revolved solid in Optiland's viewers, from its live faces and at its placement: in 2D the section through the axis in the viewing plane; in 3D the contour turned about the solid's own axis, in double precision (`C-BRIDGE-11`). |

## `P-NSQ-RUN-BUNDLE` — a saved 3D trace

**`nsq_events.sqlite`**, one table, one row per event:

| Column | Meaning |
|---|---|
| `row_id` | A stable key for the row. Not for ordering a path — use `bounce`. |
| `ray_id` | Which ray. |
| `event_type` | `birth`, `hit`, or `death`. Not the 2D vocabulary of refract/reflect/tir — a known gap. |
| `x`, `y`, `z` | Where the event happened. |
| `L`, `M`, `N` | The ray's direction at that moment, as direction cosines. |
| `flux` | How much light the ray carried. |
| `wavelength` | In micrometres — Optiland's convention, not nanometres. |
| `bounce` | The event's position in this ray's sequence. |
| `component_name` | Which surface. **Empty for every detector hit** — Optiland's detector has no name field to fill it from. |

**`params.json`** — the same physical/numerical split as a 2D bundle, and
`numerical_params.record_paths`, always present, holding the exact setting
the trace ran with (`C-NSQ-RUN-02`).
