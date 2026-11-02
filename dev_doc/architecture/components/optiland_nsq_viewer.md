# `optiland_nsq_viewer`

Showing an Optiland 3D scene inside a notebook cell, in the browser, instead
of in a separate window that blocks everything else.

Optiland's own 3D viewer opens a native window and waits. In a notebook
that means the session stops until the window is closed. This component
renders the same scene through the browser instead, so it appears in the
cell and the session continues.

## Concepts this component realises

- **`KC7`** — this is the interactive end of the one-way dependency rule.
  The viewer imports the scene bridge; the scene bridge never imports the
  viewer. `build_vtk_renderer` reads the renderer registry from the
  caller's own configuration rather than from a global that some other
  import may or may not have filled in — so what gets drawn does not depend
  on the order in which modules happened to load.

- **`KD7`** — a view in the cell is a view of the live objects. The scene
  being drawn is the one in the kernel; nothing is exported, saved and
  reloaded to show it.

## Modules

| File | What it holds |
|---|---|
| `ray_tracing_shapely_optiland/visualization/jupyter_viewer.py` | `build_vtk_renderer`, `view_in_notebook`. |

## What it produces

Nothing another component reads. A view is for a person, in the moment.

## What it needs from elsewhere

- **`P-NSQ-SCENE`** from `optiland_scene_bridge` — the built components and
  their renderers.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-VIEWER-01` | **Owns** it. `build_vtk_renderer` reads the caller's configured renderer registry, never a global. |
| `C-BRIDGE-05` | **The other party.** The bridge promises never to import this; this component is free to import the bridge. |

## How it is shipped

In `ray_tracing_shapely_optiland`. Requires the `trame` browser-rendering
stack, which is optional and not needed for anything headless.
