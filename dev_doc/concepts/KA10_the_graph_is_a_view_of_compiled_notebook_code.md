---
key: KA10
title: Why a graph of blocks is a view of notebook code, not a program of its own
one_line: A graph a person draws compiles to the notebook that runs it, so the graph adds no second way of running anything, and an agent, a reader and a headless run all meet the same code.
status: active
informs: [graph, blocks, agentic_layer, flows, C-GRAPH-01, C-GRAPH-02]
since: 0.4
---

A design can be drawn as blocks joined by wires: a rayfile slice feeds a
source, the source, a collimator and a detector feed a scene, the scene a
trace, the trace a reading, and so on to a risk group. Each block is one
call into the library, each wire one value passed from one call to the next.
The drawing is saved as a small file, and that file is turned into a
notebook: one cell per block, in the order the wires imply.

## Why the drawing is not the program

A graphical tool that runs its own graphs is a second engine. It needs its
own way of ordering steps, of passing values, of reporting failure, and each
of those can drift from what the library does when called directly. Two
engines answering the same question differently is the failure a comparison
tool exists to prevent.

Compiling to a notebook removes the second engine. What runs is ordinary
code, in the kernel everything else already uses (`KD7`). A run from the
graph and a run of its notebook are the same run.

## What this buys

**Reading without the tool.** The compiled notebook can be read, diffed and
reviewed by someone who never opens the editor.

**Running without the tool.** The notebook runs headless, as sweeps already
do (`KD8`).

**One surface for the agent.** An agent builds with the same blocks, by
handle (`blocks`); what it builds can be handed over as a graph and compiled,
so nothing it does is a kind of run the person cannot read.

## Running it without compiling a file

Drawing a graph and seeing its numbers should not need a notebook written
and run each time. So the graph's runner executes the same compiled cells,
one per node, in a namespace of the graph's own, and keeps each result. After
an edit, only the cells whose code, files or upstream changed run again. It
is still the compiled code that runs, cell by cell; what is skipped is a
cell whose result is already held. A long cell goes to an executor as a job
and comes back in its JSON form, as any long step does (`KD8`).

## Why a graph is not a flow

A flow is a fixed diagram of one procedure, the same for every input
(`KD10`). A graph is composed by its user and differs every time. The two are
kept apart: a flow may appear in a graph as one block, whose questions,
already data, are shown as a form.

## What this does not claim

That every notebook can be drawn as a graph. The direction is one way: graph
to code. A notebook edited by hand after compiling is a notebook, and the
editor does not read it back.

Nor that the graph is the easiest way to work. For a person fluent in the
library, writing the notebook directly stays the shorter path.

## Read also

- **KD7**: [human_agent_and_tools_share_one_live_kernel](KD7_human_agent_and_tools_share_one_live_kernel.md), the kernel the compiled code runs in.
- **KD8**: [parameter_sweeps_run_as_disposable_headless_notebooks](KD8_parameter_sweeps_run_as_disposable_headless_notebooks.md), why a compiled notebook runs headless for free.
- **KD10**: [classification_runs_as_a_state_machine_with_one_fixed_diagram](KD10_classification_runs_as_a_state_machine_with_one_fixed_diagram.md), what a flow is, and why it is not a graph.
- **KA9**: [every_argument_is_parsed_and_checked_at_the_agent_boundary](KA9_every_argument_is_parsed_and_checked_at_the_agent_boundary.md), a graph's literals are parsed as a block's inputs are.
