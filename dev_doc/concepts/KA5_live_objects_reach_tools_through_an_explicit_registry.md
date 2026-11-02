---
key: KA5
title: Why tools read live objects from an explicit registry, not from the caller's namespace
one_line: A library module's globals() are the library's, not the caller's, so the live scene and result are deposited into a registry the caller populates deliberately.
status: active
informs: [agentic_layer, analysis_run_registry]
since: 0.1
---

The tools an AI assistant calls need the live simulation: the scene, to
look up a name; the traced rays, to filter; the tree of ray ancestry, to
rank routes. None of that can be sent across as an argument. Instead, after
a simulation runs, the notebook puts those objects into a named store —
one call, `set_context_from_result` — and every tool reads them from there.

## Why the tools cannot just look for them

The obvious shortcut would be for a tool to reach into the notebook and
find the variables sitting there. It does not work, for a dull reason with
no way around it. A piece of code that asks *"what variables are around
me?"* gets the answer for the file it lives in — the tool's own file — not
for the notebook that called it. The variables are one step away and
unreachable from where the tool sits.

Handing the notebook's variables to the tool explicitly would work. That
is an explicit store with a worse interface.

## What the store buys

**One clear moment.** Before the store is filled, every tool reports that
no simulation is loaded. After, they work. There is no in-between state in
which a tool quietly answers about the wrong run because it found an old
variable with a familiar name.

**No copying.** The store is a plain part of the program, so anything that
loads that part holds the *same* objects, not copies. A tool host running in
the same process reads the live simulation directly; nothing is flattened
into a message and rebuilt.

**Explicit reset.** Re-running a simulation means re-filling the store. A
small chore, and the same chore prevents the worst mistake here — analysis
silently answering about the previous run.

## More than one at a time

A second run does not have to overwrite the first. Re-simulating one
particular route at high density, to study it closely, produces a different
context from the broad run it came from, and comparing the two needs both.
An overwrite would make the comparison impossible while looking like it had
worked. So the store holds named contexts, adding one is additive, and the
same applies to a run reloaded from disk beside the live one.

## What this does not claim

That a shared store is a good habit in general. It is a deliberate
exception for one boundary whose callers cannot hold onto objects, and it
is kept narrow: one store, filled by one call, read by tools that do
nothing else with it. Everything else in the program passes what it needs
by hand.

## Read also

- **KD7** — [human_agent_and_tools_share_one_live_kernel](KD7_human_agent_and_tools_share_one_live_kernel.md) — why the tool host shares the process holding these objects
- **KA8** — [tool_output_is_budgeted_against_the_context_window](KA8_tool_output_is_budgeted_against_the_context_window.md) — the serialisation cost the registry avoids
- **KB8** — [a_run_bundle_records_its_schema_version_and_parameter_split](KB8_a_run_bundle_records_its_schema_version_and_parameter_split.md) — the persisted form of the same objects
