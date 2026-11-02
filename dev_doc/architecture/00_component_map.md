# Component map

Eighteen components in five groups, and what each one is an instance of.

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
| `analysis_lineage` | `KB1` `KB4` | Energy ranking, branching statistics, trap detection, path length. |
| `analysis_bidirectional` | `KB2` `KB1` | Forward and backward passes joined at shared surfaces, and path auditing. |
| `analysis_signature` | `KB3` `KA1` | Path signatures and the spectra two runs are compared by. |
| `analysis_run_registry` | `KB8` `KC3` `KD8` | Persisting a run, and comparing runs across a sweep. |

## The agentic layer

The one boundary whose caller cannot be trusted to satisfy a precondition.

| Component | Realises | What it is |
|---|---|---|
| `agentic_layer` | `KA9` `KA4` `KA3` `KA2` `KA5` `KA6` `KA7` `KA8` | Tools, the SQL surface, the context registry, MCP exposure. |

## The physical layer

Above the simulator. Turns dimensionless brightness into physical quantity.

| Component | Realises | What it is |
|---|---|---|
| `optical_elements_physics` | `KC1` `KC4` `KD3` | `PhysicalScene`, projection models, photoconversion. |
| `optical_elements_units` | `KC4` `KA9` `KA3` | One registry, one parser, one validator, named dimensionalities. |
| `eye_safety` | `KC5` `KC6` `KD5` | Hazard evaluation against two standards. |
| `eye_safety_classification_flow` | `KD10` `KD4` `KA9` | The observable state machine over classification, and intake. |
| `nonimaging_design` | `KC2` `KD5` `KD9` | CPC, DTIRC, RXI, RR, RX construction from design methods. |

## Rendering and 3D

| Component | Realises | What it is |
|---|---|---|
| `svg_renderer` | `KB6` `KA1` `KC7` | The scene as an addressable SVG, including the annotation layer. |
| `optiland_scene_bridge` | `KB7` `KC7` `KD3` | A 2D profile into placed 3D solids, and back. |
| `optiland_sms_plugin` | `KB7` `KC2` | This project's profiles as an Optiland geometry plugin. |
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
- `Beam.emis_angle` is a full divergence angle, not a half-angle and not an
  incidence angle (`C-BEAM-01`).
- Which parameters are physical and which are numerical is your declaration,
  not something the code can infer (`C-RUN-02`).
- An apparent source's symmetry is declared correctly, or the photometric
  projection is wrong (`C-UNITS-01`, `C-EYE-03`).
- Geometric optics is valid at your feature sizes (`C-MODEL-01`).
