# Port register

A **port** is something one component makes that another component uses.
Every place two parts of the program meet is a port, and every port is
listed here, with who makes it, who uses it, and which promises apply.

## The five kinds

Ports come in five kinds, and the kind tells you what it looks like:

| Kind | What it is | Example |
|---|---|---|
| **in-memory type** | A structure that exists while the program runs — a record, a list, an object. | A ray segment, with its endpoints and brightness. |
| **persisted artefact** | A file or folder written to disk, meant to be read back later, possibly by a different program. | A saved run's folder. |
| **extension point** | A set of questions a component asks, which anything that answers them can plug into. | The three questions the engine asks every optical object. |
| **convention** | An agreement with no code enforcing it — a promise about how things are named or spelled. | Object names stay the same across runs. |
| **live kernel state** | A place in the running notebook where live objects are kept for tools to find. | The context an AI assistant's tools read from. |

## Register

The **Concept** column names the reasoning behind the port's shape. The
**Promises** column names the contracts that state what must hold at it.

| Port | Kind | What it is | Made by | Used by | Concept | Promises |
|---|---|---|---|---|---|---|
| `P-SCENE-PROTOCOL` | extension point | The three questions the engine asks every optical object: get ready; does this ray hit you; it hit you, what happens. | `core_simulator` | every object in `core_scene_objects` | `KC1` | `C-CORE-01`, `C-CORE-02` |
| `P-RAY-LINEAGE` | in-memory type | Ray segments, the list of them, and the parent/child tree over them. | `core_simulator` | `analysis_lineage`, `analysis_signature`, `analysis_bidirectional`, `svg_renderer`, `agentic_layer` | `KB1`, `KB4` | `C-LINEAGE-01`, `C-HIT-01` |
| `P-SCENE-NAMES` | convention | Every object's `.name`, and the promise that it means the same thing in every run you compare. | `core_scene_objects` | `analysis_signature`, `analysis_run_registry`, `analysis_bidirectional`, `agentic_layer` | `KA1` | `C-LABEL-01` |
| `P-ROLE-MECHANISM` | in-memory type | The two word lists: what a surface is for, and what light does there. | `core_labelling` | `nonimaging_design`, `analysis_signature`, `optiland_scene_bridge` | `KA1` | `C-LABEL-02`, `C-VOCAB-01` |
| `P-HIT-RECORD` | in-memory type | A detector's record of each counted crossing: which ray, where, how bright, at what angle. | `core_scene_objects` | `analysis_lineage`, `analysis_bidirectional`, `agentic_layer`, `optical_elements_physics` | `KB4` | `C-DET-01`, `C-HIT-01`, `C-CORE-02` |
| `P-BEAM-CTOR` | in-memory type | The settings that build a beam — in particular its spread angle. | `core_scene_objects` | whoever builds a scene | — | `C-BEAM-01` |
| `P-SIGNATURE` | in-memory type | A route through the optic, reduced to a list of *(surface, edge, what happened)*. | `analysis_signature` | `analysis_run_registry`, `analysis_bidirectional`, `agentic_layer` | `KB3` | `C-SIG-01` |
| `P-SIGNATURE-SPECTRUM` | persisted artefact | The saved table of every route in a run and the energy each carried. | `analysis_signature` | `analysis_run_registry` | `KB3` | `C-SIG-02` |
| `P-RUN-BUNDLE` | persisted artefact | A saved run's folder: settings, every segment as a database, the headline numbers, and the manifest line. | `analysis_run_registry` | `analysis_run_registry`, `agentic_layer`, future models trained on many runs | `KB8`, `KC3` | `C-RUN-01`, `C-RUN-02`, `C-CONV-01`, `C-LABEL-01` |
| `P-PROFILE` | persisted artefact | A designed element's outline, span by span, with exact normals and roles, ready to become a 3D solid. | `nonimaging_design` | `optiland_scene_bridge`, `optiland_sms_plugin` (planned) | `KB7`, `KC2` | `C-PROFILE-01` |
| `P-PHYSICAL-SCENE` | in-memory type | A scene that knows its length unit and how brightness becomes power, plus the projection models that turn 2D into 3D quantities. | `optical_elements_physics` | `eye_safety`, `nonimaging_design` | `KC1`, `KC4` | `C-UNITS-01` |
| `P-QUANTITY-PARSING` | in-memory type | The one registry of units, and the two functions that turn text or a value into a checked number-with-unit. | `optical_elements_units` | `optical_elements_physics`, `eye_safety_classification_flow`, `agentic_layer` | `KC4`, `KA9` | `C-UNITS-02` |
| `P-HAZARD-ROUTINES` | in-memory type | The two standards' exposure limits and classification, each returning a limit that says where it came from. | `eye_safety` | `eye_safety_classification_flow`, `agentic_layer` (planned) | `KC5`, `KC6` | `C-EYE-01` to `C-EYE-06` |
| `P-CLASSIFICATION-RUN` | persisted artefact | One folder per classification run: the inputs, every step as an event, the result, and a live picture of the current state. | `eye_safety_classification_flow` | the dashboard, whoever reads the record | `KD10` | `C-EYE-05` |
| `P-INTAKE-RUN` | persisted artefact | The same, for a session that gathered the inputs field by field, with a link to the classification it launched. | `eye_safety_classification_flow` | the dashboard | `KD10` | — |
| `P-AGENTIC-ENVELOPE` | in-memory type | The answer shape every tool returns: a status, then data or a message. | `agentic_layer` | AI assistants and the programs acting for them | `KA4`, `KA3` | `C-AGENT-01`, `C-AGENT-02` |
| `P-KERNEL-CONTEXT` | live kernel state | The store of live objects — scene, segments, lineage, the per-run database — that tools read from. | `agentic_layer` | every tool that needs a simulation | `KA5`, `KD7` | `C-AGENT-01` |
| `P-TOOL-REGISTRY` | in-memory type | The list of tools with their names, descriptions and parameters, in a form any assistant framework can read. **New in this register.** | `agentic_layer` | `mcp_server`, any assistant framework | `KA2`, `KA7` | `C-AGENT-02` |
| `P-OPTILAND-PLUGIN` | extension point | This project's profiles registered with Optiland as a native geometry. **Planned, not built.** | `optiland_sms_plugin` | Optiland | `KB7` | `C-3D-01` |
| `P-NSQ-SCENE` | in-memory type | The 3D surfaces built from a profile, placed and ready for Optiland to trace. | `optiland_scene_bridge` | `optiland_nsq_viewer`, `optiland_nsq_run_registry` | `KB7`, `KC7` | `C-BRIDGE-01` to `C-BRIDGE-05`, `C-VIEWER-01` |
| `P-NSQ-RUN-BUNDLE` | persisted artefact | A saved 3D trace: every event as a database row, plus the settings. | `optiland_nsq_run_registry` | anything querying a 3D run | `KB8`, `KA6` | `C-NSQ-RUN-01` to `C-NSQ-RUN-03` |

## Reading the register

**A port with no concept** is one whose shape needs no explaining: a beam's
settings are a beam's settings.

**A port with no promises** is one nothing checks. `P-INTAKE-RUN` is the
only one, and it inherits `P-CLASSIFICATION-RUN`'s shape.

**Two ports are not yet real.** `P-OPTILAND-PLUGIN` is planned and has no
code. `P-RUN-BUNDLE`'s schema-version field, required by `C-RUN-01`, is not
yet written into the files.

**The field-by-field detail** of every port is in `03_alphabet.md`.
