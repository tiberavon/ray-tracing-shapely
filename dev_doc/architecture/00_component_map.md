# Component map

Nineteen components in five groups, and what each one is an instance of.

## Reading this map

The right-hand column is the point. A component is largely predictable from
the concepts it realises, and the concepts are where its reasoning lives. A
reader who wants to know *why* a boundary sits where it does should follow
the key, not look for an explanation on the component page.

## The core

The ray-tracing engine. Owns geometry and lineage, knows no optics and no
units.

| Component | Realises | What it is |
|---|---|---|
| `core_simulator` | `KC1` `KB1` `KB4` | The ray-queue loop, `Ray`, `Scene`, `RayLineage`. |
| `core_scene_objects` | `KC1` `KC2` `KB4` | The optical elements. Each owns its own physics. |
| `core_labelling` | `KA1` `KB3` | The `Role`/`Mechanism` vocabulary structural comparison is written in. |

## Analysis

Post-hoc, over a completed run. Reads the core; never modifies it.

| Component | Realises | What it is |
|---|---|---|
| `analysis_lineage` | `KB1` `KB4` | Energy ranking, branching statistics, trap detection, path length; the light that left, on a plane past the optic (irradiance map, line profile). |
| `analysis_bidirectional` | `KB2` `KB1` | Forward and backward passes joined at shared surfaces, and path auditing. |
| `analysis_signature` | `KB3` `KA1` | Path signatures and the spectra two runs are compared by. |
| `analysis_run_registry` | `KB8` `KC3` `KD8` | Persisting a run, and comparing runs across a sweep. |
| `analysis_flux_tubes` | `KB3` `KC3` `KD5` | A source's light cut into tubes of equal delivered power, each kept as replayable seeds with its routes and arrivals, and traced again on an edited scene; the first-order change of a small edit of a designed surface, untraced; an SMS design's edge bundles and Map A, the spread of their optical path lengths to the target; a sculpted glass, a designed recipe and the edits made to it, kept as one recipe; all of it drawn as a sculpt layer. |

## The agentic layer

The one boundary whose caller cannot be trusted to satisfy a precondition,
and the procedures a caller drives step by step.

| Component | Realises | What it is |
|---|---|---|
| `agentic_layer` | `KA9` `KA4` `KA3` `KA2` `KA5` `KA6` `KA7` `KA8` | Tools, the SQL surface, the context registry, MCP exposure. |
| `flows` | `KD10` `KA4` `KA9` `KC7` | The observable state machine any multi-step procedure is built on: questions as data, long steps through executors, fixed ends; a run's record, the run list, the dashboard; nine generic agent tools. |
| `blocks` | `KA9` `KC2` `KC4` `KA3` | Calls with typed inputs and outputs: a vocabulary of value types (JSON and live forms, a wire rule), declared function blocks, and every constructor as a block giving its scene entry. |
| `graph` | `KA10` `KA9` `KD7` | Blocks joined by wires: a versioned graph document, checked by the blocks' wire rule, compiled to the notebook that runs it, one cell per node; edited on a canvas whose every rule is in Python; run cell by cell, only what an edit made stale. |

## The physical layer

Above the simulator. Turns dimensionless brightness into physical quantity.

| Component | Realises | What it is |
|---|---|---|
| `optical_elements_physics` | `KC1` `KC4` `KD3` | `PhysicalScene`, projection models, photoconversion. |
| `optical_elements_units` | `KC4` `KA9` `KA3` | One registry, one parser, one validator, named dimensionalities. |
| `eye_safety` | `KC5` `KC6` `KD5` `KD13` | Hazard evaluation against two standards. |
| `eye_safety_classification_flow` | `KD10` `KD4` `KA9` | The classification and intake flows over both standards. |
| `nonimaging_design` | `KC2` `KD5` `KD9` | CPC, DTIRC, RXI, RR, RX, XR construction from design methods; labelled lenses, LED collimators, aspheres and exact curved mirrors, exportable as profiles; light sources described once for both engines; measured LEDs (rayfiles: reading, slicing, radiation plot); scanned lens faces, fitted. |

## Rendering and 3D

| Component | Realises | What it is |
|---|---|---|
| `svg_renderer` | `KB6` `KA1` `KC7` | The scene as an addressable SVG, including the annotation layer. |
| `builder` | `KB6` `KC2` `KC7` | The scene builder: a scene drawn and edited with the pointer in a notebook cell, every rule in Python, saved as a scene file; a designed glass sculpted by its handles, its light in view, by a person or by an agent's tools. |
| `web` | `KC7` `KD7` | The flow form and the scene builder as pages served by routes in the kernel's web app, for hosts without notebook widgets (a solveit dialog). |
| `optiland_scene_bridge` | `KB7` `KC7` `KD3` `KD5` `KD13` | A 2D profile into placed 3D solids, mirrors and plates, and back, aspheres of revolution included; sources and measured LEDs in 3D; the same rays compared in 2D and 3D; irradiance maps; a collimator in Optiland's sequential engine; static 3D pictures. |
| `optiland_sms_plugin` | `KB7` `KC2` | A profile's spline span as an Optiland sequential surface, differentiable: the `optiland-sms` distribution. |
| `optiland_nsq_viewer` | `KC7` `KD7` | An NSQ scene into a notebook cell over WebGL. |
| `optiland_nsq_run_registry` | `KB8` `KA6` `KD4` | One 3D trace's lineage persisted and queryable. |

## Which concepts have no component

Some concepts are about how the project works rather than what it contains,
and appear on no row above: `KD1` `KD2` `KD5` `KD6` `KD9` `KD11` `KD12`.
They inform the documentation, the tests and the process. Their absence here
is expected — see `dev_doc/concepts/00_index.md`, group D.

## Undischarged assumptions

What this codebase assumes of whoever uses it, and does not check. Each is a
contract whose `provides` names a person rather than a module.

- Scene-object names are stable across the runs you intend to compare
  (`C-LABEL-01`).
- `Beam.emisAngle` is a full divergence angle, not a half-angle and not an
  incidence angle (`C-BEAM-01`).
- Which parameters are physical and which are numerical is your declaration,
  not something the code can infer (`C-RUN-02`).
- An apparent source's symmetry is declared correctly, or the photometric
  projection is wrong (`C-UNITS-01`, `C-EYE-03`).
- Geometric optics is valid at your feature sizes (`C-MODEL-01`).
