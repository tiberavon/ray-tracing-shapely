# `agentic_layer`

The part of the program that an AI assistant talks to.

When you run a simulation in a notebook, the results — the scene, every ray
that was traced, the family tree of which ray produced which — sit in the
computer's memory as live objects. This component lets an AI assistant ask
questions about those objects: *which rays reached the sensor*, *what is the
critical angle between these two glasses*, *draw me the scene with the
grazing rays highlighted*. It does that by offering the assistant a fixed set
of **tools** — small named functions with a description of what they do and
what they need — and by connecting to it over a standard channel called MCP,
which is how assistants like Copilot or Claude reach functions inside a
running program.

## Why this component is different from every other one

Every other component in this codebase is called by *other code*. That code
was written by a programmer who read the instructions and passed the right
kind of thing. The rest of the program relies on that, and does not
double-check.

This component is called by a language model. It has read a *description* of
each tool, not the code, and it may have guessed at what to pass. It cannot
be held to any instruction, because it never agreed to one. So this is the
one place in the program that checks everything it is given, every time.
That single fact explains most of what is in here.

## Concepts this component realises

- **`KA9`** — every argument is checked before use. A quantity like
  *"30 mW/cm²"* arrives as text and goes through `parse_quantity`, which
  reads the number and the unit and confirms the unit is the right *kind*
  (an irradiance, not a radiance). A glass name goes through
  `get_object_by_name`, which confirms a glass with that name exists in the
  scene. A database query is scanned for words that would change the data
  rather than read it, and refused if any appear. Most of the code in this
  component that is not a thin wrapper is this checking.

- **`KA4`** — when something is wrong, the tool *says so* instead of
  crashing. Every tool returns either `{"status": "ok", "data": ...}` or
  `{"status": "error", "message": ...}`. The message is written to be
  useful: *"no object named 'entrance prism'; named objects are: ..."*.
  Checks run in a fixed order — is there a simulation loaded? does it have a
  lineage? does that glass exist? — so the assistant is told the first thing
  that is missing, not a later consequence of it.

- **`KA3`** — what crosses in and out is plain data: text, numbers, lists,
  and simple key-value records. Never a live object. `get_agentic_tools()`
  describes each tool as a record with a name, the function, a one-line
  description, and a formal list of its parameters, which is a format every
  assistant framework can read.

- **`KA5`** — the live objects are kept in a named place. After a simulation,
  the notebook calls `set_context_from_result` once, which puts the scene,
  the traced rays and the lineage into a store called `_CONTEXT`. Tools read
  from there. A second simulation can be added alongside the first rather
  than replacing it, so an assistant can compare two runs.

- **`KA2`** — for every tool that needs a name, there is a tool that lists
  the names. `list_detectors` exists so that `rank_detector_paths` has
  something to be given; `describe_schema` exists so that `query_rays` can be
  written against columns the assistant actually knows about. A column that
  exists in the database but is missing from `describe_schema`'s list is,
  for the assistant, not there.

- **`KA6`** — most questions are answered by one general tool rather than one
  tool per question. `query_rays` accepts a query in SQL, a standard language
  for asking questions of tables, over seven tables describing the run. An
  earlier design had a separate tool for each kind of question, and it turned
  out they could not be combined: *rays inside this glass* and *rays with
  high polarisation* each searched everything, and there was no way to ask
  for both at once. Those older tools still exist, marked as superseded,
  because an assistant's saved configuration might name them.

- **`KA7`** — a tool has to be registered in three separate places before
  the assistant can see it: the file that defines it, the registry that
  describes it, and the server that publishes it. Miss one and the tool is
  invisible — it has happened that a tool was mentioned in the assistant's
  instructions while missing from the server, and every call to it failed as
  if the tool had never been written. A test counts the registered tools so
  that mismatch is caught.

- **`KA8`** — answers are kept short enough to use. An assistant has a
  limited amount of text it can read before answering, so a result leads
  with the summary (*"230 rays, total brightness 0.83"*) and carries only
  the fields the question asked for. A drawing is never returned as the
  drawing itself: `render_scene_svg` returns where the file was saved, its
  size, and a written description of what is in it, because the assistant
  cannot look at pictures and a person can open the file.

- **`KD7`** — the server that the assistant connects to runs *inside* the
  notebook, as a background thread, rather than as a separate program. That
  way it reads the same live objects the notebook has, with nothing copied.
  A separate program would need the whole simulation sent to it on every
  question.

## Modules

| File | What it holds |
|---|---|
| `analysis/agentic_tools.py` | The tools themselves, the `_CONTEXT` store, and the two helpers that build an `ok` or an `error` answer. |
| `analysis/agentic_db.py` | Builds the seven-table database from a run, holds the column descriptions `describe_schema` returns, and refuses queries that would modify data. |
| `analysis/tool_registry.py` | The list of tools with their descriptions and parameters, and the generators that write the paragraph a person pastes into the assistant's chat to announce them. |
| `analysis/mcp_server.py` | The list of tools to publish, and the background server the assistant connects to. |

## What it produces

A **port** is something this component makes available for other parts of
the program to use.

- **`P-AGENTIC-ENVELOPE`** — the answer shape every tool uses: a status,
  then data or a message.
- **`P-KERNEL-CONTEXT`** — the store of live objects — scene, segments,
  lineage, the per-run database — that every tool reads from after
  `set_context_from_result` fills it.
- **`P-TOOL-REGISTRY`** — the tool list: for each tool, its name, the
  function, a description and its parameters. Read by the server and by
  any assistant framework.

## What it needs from elsewhere

- **`P-RAY-LINEAGE`** from `core_simulator` — the family tree of rays that
  the path-ranking tools walk.
- **`P-SCENE-NAMES`** from `core_scene_objects` — the names an assistant's
  *"measuring prism"* is looked up against.
- **`P-QUANTITY-PARSING`** from `optical_elements_units` — how a quantity
  written as text becomes a checked number-with-unit.
- **`P-RUN-BUNDLE`** from `analysis_run_registry` — a saved run, for tools
  that load rather than trace.

## Promises this component makes and relies on

A **contract** is a written promise about what must be true at a boundary,
with a note on what happens if it is broken and, where possible, a test that
checks it.

| Contract | This component's part |
|---|---|
| `C-AGENT-01` | **Makes** it. Every tool answers with the `ok`/`error` shape; nothing raises an exception toward the assistant. |
| `C-AGENT-02` | **Makes** it. A tool is reachable only if registered in all three places. |
| `C-NSQ-RUN-03` | **Relies** on it. The query machinery does not care what the tables are called, so the 2D and 3D databases share one implementation. |
| `C-UNITS-02` | **Relies** on it. The unit checking is done by `optical_elements_units`; this component only calls it. |

## How it is shipped

Part of the core package. The server needs the optional `mcp` dependency;
the tools themselves do not, and work from any assistant framework or from a
plain notebook cell.
