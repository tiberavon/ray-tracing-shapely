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
| `hit_surface_uuid`, `hit_point`, `hit_normal` | Where this segment ended: which surface, at what point, with what surface direction. Only recorded when the simulation was started with `record_surface_hits=True`. | optional |
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
| `edge_index` | Which edge of that object — a position along a curve that was cut into straight pieces, not a coordinate (`C-SIG-01`). | whole number, optional |
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
| `edges` | edge of a glass | Its labels, endpoints, midpoint, length. |
| `ray_glass_membership` | (segment, glass) | Which segments lie inside which glass. |
| `ray_edge_crossing` | (segment, edge) | Which segments cross which edge, and at what angle to the edge's perpendicular. |
| `detectors` | detector | Name, endpoints, bin size. |
| `detector_hits` | counted crossing | `P-HIT-RECORD`, as rows. |
| `connections` | joined forward/backward pair | Only present after a bidirectional run: which two segments were matched, on which surface, how close, how nearly opposite. |

**`manifest.jsonl`** — one line appended per run, so a design's history is
one file. **`graph.json`** and **`signature_spectrum.json`** — present
when the run was bidirectional.

A schema version and a confidence field are required by `C-RUN-01` and not
yet written.

## `P-PROFILE` — a designed outline, ready to become 3D

| Field | Meaning | Type |
|---|---|---|
| `schema_version` | Currently `"1.0"`. | text |
| `points` | Every span endpoint, two per straight span. | list of points |
| `normals` | The outward direction at each endpoint — stored **per span**, so a sharp corner's two edges each keep their own (`C-PROFILE-01`). | list of unit vectors |
| `spans[i].index_start`, `.index_end` | Which entries in `points` and `normals` belong to this span. | two whole numbers |
| `spans[i].short_label`, `.long_label` | The span's functional labels. | text, optional |
| `spans[i].role`, `.mechanism` | What it is for and what light does there. Empty if the element's class did not tag it. | one word each, optional |
| `symmetry.kind` | How the outline becomes a solid: `extrude`, `revolve`, or `free`. | one word |
| `symmetry.plane_axes`, `.extrude_axis`, `.length` | For `extrude`: which two axes the outline lies in, which axis it extends along, and how far. | required for `extrude` |
| `symmetry.axis` | For `revolve`. Not yet read by anything. | required for `revolve` |
| `construction_params` | The physical and numerical settings that built the element, split as in `P-RUN-BUNDLE`. | two sections |
| `fit` | Always empty from this side. Reserved for a 3D tool that fits the profile. | — |

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
| `build_faces_from_profile(...)` returns | One Optiland surface per span, keyed by the span's short label — refracting, reflecting or absorbing according to its mechanism (`C-BRIDGE-01`). |
| `ExtrudedPolygonSolid.surfaces` | The same surfaces, wrapped as one compound object so a viewer can draw it. |
| `ExtrudedPolygonSolid.profile` | The original profile, kept so the 2D and 3D renderers can draw the cross-section. |
| `span_outward_ray(...)` returns | Where and how to place a face, read from the span's own stored normal. |

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
