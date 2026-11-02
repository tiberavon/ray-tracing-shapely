---
key: KC7
title: Why the batch path never depends on the interactive one
one_line: Scene assembly, tracing and persistence must run with no display, no browser and no interactive toolkit installed, so dependencies point one way and a viewer may import a builder but never the reverse.
status: active
informs: [optiland_scene_bridge, optiland_nsq_viewer, svg_renderer, C-BRIDGE-05, C-VIEWER-01]
since: 0.1
---

The parts of the program divide into those that *build and trace* and those
that *display*. Dependencies run in one direction: a viewer may use a
builder, but a builder never uses a viewer. The code that assembles a 3D
scene does not load the code that draws it, and a drawing routine reads its
settings from the caller rather than from something a viewer filled in
earlier.

## What breaks otherwise

Large parameter sweeps run without a screen — many copies in parallel, on
machines with no display and no browser. A building component that loads a
display library drags in everything that library needs — rendering
toolkits, browser plumbing, native windows — for code that will never draw
anything. It fails at load time, before any work starts, on the machine
least able to say why.

The other direction is harmless. A viewer needs the thing it is viewing.

## The usual way it goes wrong

A viewer that writes its drawing settings into a shared global spot makes
anything touching that spot depend on the viewer having been loaded first.
The consequences depend on load order and appear only in the configuration
nobody tests: the interactive session loads the viewer early and works; the
batch job does not and fails somewhere apparently unrelated.

Reading the settings from the caller's own configuration removes the
ordering question. A component uses what it was handed.

## The split shows in the parts themselves

Building a solid and drawing it are separate components, not one class with
a `draw()` method, because that separation is what lets the first exist
without the second. Saving a trace and looking at it are separate for the
same reason: one writes the events to a file, and looking at them is a
different component reading that file.

## What this does not claim

That display is second-class. It is where most of the understanding
happens. The rule is about direction, not importance: the display layer is
free to depend on everything below it, and that freedom is exactly why the
layers below must not depend back.

## Read also

- **KC1** — [physics_and_rendering_are_layers_above_core_never_inside_it](KC1_physics_and_rendering_are_layers_above_core_never_inside_it.md) — the layering this sits inside
- **KD8** — [parameter_sweeps_run_as_disposable_headless_notebooks](KD8_parameter_sweeps_run_as_disposable_headless_notebooks.md) — the headless case this protects
- **KB7** — [optiland_verifies_2d_designs_in_3d_and_hands_them_back](KB7_optiland_verifies_2d_designs_in_3d_and_hands_them_back.md) — the bridge that has to obey it
