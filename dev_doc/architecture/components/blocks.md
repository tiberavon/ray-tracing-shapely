# `blocks`

Calls with typed inputs and outputs, and the vocabulary of what passes between
them.

A design can be built as a chain of calls: a rayfile, a collimator, a trace, a
reading, a classification. A graph editor draws such a chain as blocks joined
by wires; an agent builds it with tools. Both need the same thing: each call's
inputs and outputs, with a type that says whether one may feed another. An
annotation does not say enough. It says `float` where a wire needs a length
in millimetres, and `Point` where it needs a position or a direction. So
blocks are **declared**: a function is registered with its ports' types, and
stays the same function, to call from a notebook as before.

**A value type has two forms.**
- **JSON**, which a graph document, an agent's call or a flow's answer holds. A
  quantity is text with its unit (`"7 mm"`), a scene is a scene file or its
  path.
- **Live**, which the function receives in the kernel. A quantity is a float in
  the type's unit, a scene a `Scene`.

A block is run from the JSON form, every input parsed and checked at the
boundary (`KA9`). A bare number where a quantity is expected is refused,
since it says nothing of its unit (`KC4`). A quantity is checked as the
eye-safety layer checks one (`parse_radiometric_quantity`): its
dimensionality, then its kind, its base units with radian and steradian
kept. pint counts those two dimensionless, so dimensionality alone would let
a radiance pass where an irradiance is wanted, or a bare number pass as an
angle. Wires are matched by kind too. Scene coordinates stay plain
numbers in the scene unit, the millimetre, as everywhere in the core.

**The constructors are blocks too.** A constructor needs a live scene, so its
block gives the element's scene entry instead (`C-SCENE-01`): a designed
element's recipe and arguments, a primitive's `serialize()` dict. The element
is built once in a scratch scene, so a value its constructor refuses is
refused by the block, with the constructor's reason.
- A designed element's arguments are typed by rules written out in
  `blocks/library.py`, overridable per class.
- A primitive's are its `property_schema`.

**The example chain is blocks too** (`blocks/chain.py`), each an ordinary
function as well:

    slice_rayfile -> source_from_slice --+
    (a constructor block) ---------------+-> assemble -> trace -> detector_reading
                                                                     |
              classify_iec62471 <- hazard_weighted <- physical_reading

- **`trace`** reads every named detector when it traces. Saved, its JSON form
  is the run's folder, which holds a run bundle (`P-RUN-BUNDLE`) with
  `scene.json` and `readings.json`, and reads back to the same readings.
  Unsaved, it is live only, and a JSON boundary refuses it with the reason.
- **`physical_reading`** makes the 2D reading an irradiance for an
  **extruded** scene: power per metre of extrusion over the detector's
  length, so the height cancels. A **revolved** reading needs
  `RevolvedProjection`, a stub (`C-EYE-03`), so the block refuses it.
- **`hazard_weighted`** weighs an irradiance by a hazard's function over the
  rayfile's spectrum (`weighted_fraction`).
- **`classify_iec62471`** checks each value's kind as the intake flow does
  (`checked_hazard_value`). Blue light is two ports, a radiance and an
  irradiance, one for each side of α = 0.011 rad.

**An agent builds with six tools** (`blocks/agentic.py`), the same for every
block, as the flows' nine are for every flow. One tool per block would add a
tool with every recipe, which `KD12` argues against.
- `block_list`, `block_describe`, `block_run`, `block_value`, `block_values`
  and `block_graph`.
- `block_run` keeps each output in the kernel under a handle (`"v3"`) and
  answers with the value, or a summary when it is long. An input given as
  `{"ref": "v3"}`, alone or in a list, is that value, checked by the wire rule.
  So a 600-ray source never travels through the agent, and an unsaved trace
  still feeds the next block.
- The store is the blocks' own. The named contexts are never switched.
- The store records each call: the block, its inputs as given (handles
  included) and the handles of its outputs. So the agent's work reads back
  as a graph (`KA10`): `block_graph` writes it as a graph document (`graph`),
  a call a node, a handle a wire, the rest literals; with handles given, only
  those values and the calls they were made from. The person opens it on the
  graph canvas, or compiles it to the notebook that reruns the same calls.
  There is no tool to add a node or a wire: `block_run` is how an agent builds.
- `register()` adds the six tools to the three lists (`C-AGENT-02`), called
  explicitly, never at import.

A quantity's JSON form is the shortest text that reads back as the same
float, so a chain run through JSON gives the numbers a chain run live does.

## Concepts this component realises

| Concept | How |
|---|---|
| `KA9` | Every input is parsed and checked where it enters, as JSON. |
| `KC2` | A designed element's block takes its requirements, never its outline. |
| `KC4` | A physical magnitude crosses the boundary as a quantity with its unit. |
| `KA3` | A block's inputs and outputs, at the boundary, are plain JSON. |

## Modules

| File | What it holds |
|---|---|
| `blocks/types.py` | The vocabulary. Scalars; `Quantity(unit)`; `Choice`; `Position` and `Direction`; `Optional_` and `ListOf`; `SceneEntry`, `Scene`, `Rayfile`, `RayfileSlice`, `Profile`, `Trace`, `DetectorReading`, `Classification`, `GlassVertex`; `JSON` for what is not typed yet, shown as such. Each type has `parse`, `format`, `accepts` (the wire rule), and `describe` / `from_description`. Closed in the core; a satellite adds a type with `register_type`. |
| `blocks/registry.py` | `@block` (declare a function), `Block` and `Port`, `run_block` (JSON in and out), `call_block` (live; `wired` for other blocks' live outputs, taken as they are, which a compiled graph uses), `catalogue()` (every block as JSON), `wire_accepts`. |
| `blocks/chain.py` | The example chain's blocks: `slice_rayfile`, `source_from_slice`, `assemble`, `trace`, `detector_reading`, `physical_reading`, `hazard_weighted`, `classify_iec62471`. |
| `blocks/agentic.py` | The six construction tools, the store of kept values and of the calls that made them; `graph_of_values`; `register()`. |
| `blocks/library.py` | The constructor blocks, generated from the recipe registry and the primitives' schemas, with the argument rules as a table. A recipe registered later by a satellite becomes a block too. |

## What it needs from elsewhere

- `analysis.scene_file`: the recipe and primitive registries, `recipe_parameters`, building an entry.
- Each scene object's `property_schema`.
- `optical_elements.units`: quantity parsing (`P-QUANTITY-PARSING`), so the `radiometry` extra.
- The chain: `RayfileSlice.scene_entry`, `scene_file.assemble`, `parameter_study.read_detector`
  (its `DetectorReading`), `run_registry.persist_run_artifacts`, `PhysicalScene`,
  `eye_safety.weighted_fraction`, `iec62471.classify_measurement` and the intake flow's
  `checked_hazard_value`.

## Promises this component makes and relies on

| Contract | Role |
|---|---|
| `C-SCENE-01` | **Relies on** it. A constructor block's output is a scene entry, which builds back to the same element. |
| `C-AGENT-02` | **Relies on** it. The six tools join the three lists through `register_tool`. |
| `C-UNITS-01` | **Relies on** it. `physical_reading` takes the symmetry, and makes only `extrude` physical. |
| `C-EYE-03` | **Relies on** it. A revolved reading is refused until `RevolvedProjection` exists. |
| `C-UNITS-02` | **Relies on** it. A quantity's JSON form is the unit-bearing text that contract fixes. |

## How it is shipped

In the core distribution. Quantities need the `radiometry` extra. The core
never imports this package.
