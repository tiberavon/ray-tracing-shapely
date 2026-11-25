# `graph`

Blocks joined by wires, saved as a document, and compiled to the notebook
that runs them.

A graph is a saved file saying which blocks to run and which outputs feed
which inputs. This component reads and checks such a file, turns it into
a notebook (one cell per node, in the order the wires imply), and draws it
on a canvas where it is edited. Nothing runs a
graph by any other route (`KA10`), so a graph and its notebook are one run.

**The document.**

    {"graph_version": 1,
     "nodes": [{"id": "slice", "block": "slice_rayfile",
                "inputs": {"rayfile": "led.tm25", "position": [0, 0],
                           "direction_deg": "0 deg", "max_offset_mm": "0.5 mm"}},
               {"id": "led", "block": "source_from_slice",
                "inputs": {"slice": {"from": "slice.slice"}, "name": "led"}}]}

- A node names a block (`blocks`), gives some of its inputs as their JSON
  form, and may have a place on a canvas (`at`). An input not given takes the
  block's default.
- A wire is an input, `{"from": "<node>.<output>"}`, or the items of a list
  input, all wires. There is no separate list of wires.
- Checked when read, with the node, the input and the reason
  (`C-GRAPH-02`): known blocks and inputs, wires from existing outputs of a
  type the input accepts, literals their type accepts, unique ids that are
  Python names, no cycle. A literal naming a file is not opened until the
  notebook runs. The version is checked first (`C-GRAPH-01`).

**The compiled notebook.** A note, an import, then one cell per node:

    # led: source_from_slice (ray_tracing_shapely.blocks.chain:source_from_slice)
    led = call_block('source_from_slice', {
        'name': 'led',
    }, wired={
        'slice': slice['slice'],
    })

Literals go as their JSON, parsed by their types as `run_block` parses them.
A wire goes in `wired`, the source node's live output as it is, since a
quantity's live form is a bare float its type would refuse as JSON. The
compiler adds nothing else: no default, no conversion, no reordering.

**The runner.** `GraphRunner` runs a graph's compiled cells
(`node_source`) in a namespace of its own, the graph's store, and keeps each
node's result. A node runs again only when it is stale: its fingerprint, a
hash of its cell's text, the fingerprints of what feeds it and the stamps of
the files it reads, is not the one it ran under, or something feeding it is
stale. So a run after an edit is the compiled notebook less the cells whose
results it holds. A node with an estimate (a trace: its segment limit at the
measured rate) over a minute is sent to an executor (`flows`) as a JSON job
and comes back through its outputs' types; with no executor it is refused,
the estimate given, before anything runs.

**The editor.** `GraphEditor` is the canvas's model: the document, changed
by JSON messages (add, move, delete, rename a node; set an input; connect,
disconnect a wire; undo, redo; open, save, compile; run, poll). Every change is checked
by `check_graph(doc, complete=False)`, the compiler's rule less the required
inputs not given yet, so a graph is drawn, saved and reopened unfinished, and
compiled only when finished. A change refused leaves the document as it was,
the reason in the state's `error`. The state gives each output's targets, the
inputs that accept it less those that would close a cycle, so the page can
light them up while a wire is dragged without knowing the rule. Each node's
state is fresh, stale, running or failed, from the runner.
`graph_editor` (`widget.py`, the `widgets` extra) is its notebook view: plain
JavaScript drawing SVG, no build step, as the scene builder's.

**The agent's graph.** An agent builds by `block_run`, wiring outputs by
handle (`blocks`); the blocks' store records each call, so `block_graph`
writes the agent's work as a graph document: a call a node (named after its
object's `name`, or its block, by `free_id`), a handle a wire, every other
input as the agent gave it. It is checked as it is written, opens on the
canvas laid out by its wires, and compiles to a notebook giving the agent's
values. A list mixing handles and literals is refused with the reason, as a
graph cannot say it.

**Hosts.** Three views draw with the same page module and send the same
messages to a `GraphEditor`:

- a notebook cell: `graph_editor()`, an `anywidget` widget; the runner lives
  in the notebook's kernel;
- a VS Code editor for `*.graph.json`: the extension in `src-vscode/scene-editor`
  (with the scene builder's editor) starts `graph.server` with the interpreter
  the Python extension selected, and speaks JSON lines to it, as for a scene.
  No notebook kernel is involved: the runner lives in the server's process, a
  long node goes to a worker process (`LocalProcessExecutor`), and the page
  polls while it runs. The document is the file: an edit is written into it,
  a selection or a run is not, and an edit from elsewhere is loaded back. New,
  Open and Save are VS Code's; Compile offers to open the notebook it wrote;
- a solveit dialog: `web.Views.graph()`, the page served by HTTP routes in
  the kernel's app.

The VS Code editor does not drive a notebook's kernel. Another extension can
reach only a kernel the person has already started for an open notebook, and
run code in it (the Jupyter extension's `kernels.getKernel`); widgets' messages
are not part of that. A graph's results belong to its editor while it is
open; the compiled notebook is how they reach a notebook.

## Concepts this component realises

| Concept | How |
|---|---|
| `KA10` | A graph runs only as its compiled notebook. |
| `KA9` | A literal is parsed by its block's input type, at the boundary. |
| `KD7` | The compiled notebook runs in the kernel everything else uses. |

## Modules

| File | What it holds |
|---|---|
| `graph/document.py` | `check_graph` (the checks; the run order), `load_graph`, `save_graph`, `new_graph`, `GraphError`, the wire helpers, `free_id` (a node id from a name), `GRAPH_VERSION` and `SUPPORTED_VERSIONS`. |
| `graph/compile.py` | `compile_graph` (a document to nbformat 4 JSON), `compile_script` (the same as a script), `node_source`, `write_notebook`. |
| `graph/runner.py` | `GraphRunner` (start, advance, run; stale, estimate_s; outputs, values), `RunReport`, `NodeRun`, `RunnerError`, `ESTIMATES`, `run_node_job` (the executor's procedure). |
| `graph/editor.py` | `GraphEditor` (the canvas's model: messages, undo, open, save, compile; the state the view draws), `EditorError`. |
| `graph/widget.py` | `graph_editor`: the `anywidget` view (the `widgets` extra), its page module and style. |
| `graph/server.py` | `python -m ray_tracing_shapely.graph.server`: one editor and its runner served on standard input and output, in JSON lines (`builder.server.serve_lines`), for the VS Code editor. The editor's messages less new, open and save, plus `hello` (the page), `load_text` (a document's text as the graph) and `refresh`. A reply carries the document's text only when the graph changed, and never after a text it could not read; `compiled`, the notebook a compile wrote, once. |

## What it needs from elsewhere

- `blocks`: `get_block` and each block's ports, the value types' `parse` and
  `accepts`, and `call_block` with `wired`, which the compiled notebook calls.
- `flows`: `executors` (`Job`, an executor's five calls) and `budgets` (the
  trace's estimate) for long nodes, imported only when a node is long; the
  widget's `find_files`, the graph files the toolbar offers.
- `builder`: the scene builder `open_scene` opens (the widget only), and
  `serve_lines`, the JSON-lines loop both servers answer with.

## Promises this component makes and relies on

| Contract | Role |
|---|---|
| `C-GRAPH-01` | **Owns** it. A document carries its version; one outside the range is refused. |
| `C-GRAPH-02` | **Owns** it. A wire is checked by the blocks' rule; the compiled graph equals the blocks run directly. |
| `C-UNITS-02` | **Relies on** it. A quantity in a document is the unit-bearing text that contract fixes. |

## How it is shipped

In the core distribution, beside `blocks`, and needs what it needs (the
`radiometry` extra); the widget needs the `widgets` extra too, imported only
when one is made. The core never imports this package.
