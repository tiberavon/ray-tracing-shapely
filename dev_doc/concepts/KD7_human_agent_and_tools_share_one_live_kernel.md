---
key: KD7
title: Why the working environment is one live kernel
one_line: A person, an agent and the analysis tools operate on the same live objects in one process, which is why tools are hosted inside that process and why every landed phase ships an executed notebook.
status: active
informs: [agentic_layer, analysis_run_registry, optiland_nsq_viewer]
since: 0.1
---

A design session here is one running notebook. The scene, the traced
result and the tree of ray ancestry sit in its memory as live objects. A
person looks at them, an AI assistant asks about them through tools, and
the drawing routine draws them — all from the same objects, with nothing
copied for anyone.

## Why the tools run inside the notebook

The alternative is a tool server in its own process. That process then
needs the simulation. Sending it means turning the whole scene into a
message: lossy if done compactly, enormous if done faithfully — and the
enormous version lands in the reading budget of whatever asked the
question.

Running the tools inside the notebook removes the transfer entirely. The
notebook and the tool code share the same objects in memory, not copies.
What crosses to the assistant is the answer.

The cost is a tied lifetime: the tool server dies when the notebook does,
and an assistant connected to it has to reconnect. That is a real nuisance,
worked around rather than designed away, because the alternative brings
back the copying.

## Why every finished piece of work ships as a notebook

A notebook is that same environment, saved. Running it reproduces what a
person had in front of them; reading it shows what they saw, with the
outputs kept, so the numbers can be read without re-running anything.

One file therefore does three jobs: the demonstration a piece of work ships
as its proof, the reference a later reader runs to get a working setup, and
the raw material a published write-up is edited from. Work without one has
shipped code whose use is undocumented in the only form that can be
checked by running it.

## What follows from this

Tools take names, not objects, because the objects are already on this
side. Heavy state stays put and only answers move. Analysis functions are
plain functions over live objects rather than a pipeline needing its own
machinery. All of that follows from the environment being one process
rather than several.

## What this does not claim

That everything must run in a notebook. Parameter sweeps run without one,
and results are saved to disk precisely so they outlive the notebook that
made them. The claim is about where *interactive* work happens, and why
the tooling is built to sit there.

## Read also

- **KA5** — [live_objects_reach_tools_through_an_explicit_registry](KA5_live_objects_reach_tools_through_an_explicit_registry.md) — how tools reach those objects
- **KA8** — [tool_output_is_budgeted_against_the_context_window](KA8_tool_output_is_budgeted_against_the_context_window.md) — what the sharing avoids paying
- **KD8** — [parameter_sweeps_run_as_disposable_headless_notebooks](KD8_parameter_sweeps_run_as_disposable_headless_notebooks.md) — the same notebook, run without a person
