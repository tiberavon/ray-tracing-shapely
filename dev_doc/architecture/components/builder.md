# `builder`

A drag-and-drop scene builder, like the JavaScript simulator's, in a notebook
cell.

A person draws a scene: picks a primitive from a palette and places it with
the pointer, drags an endpoint, a vertex or a whole object, places a designed
element from a form of its constructor's arguments, edits any property, and
sees a quick trace after every change. The result is a scene file, which the
parameter-study flow and an agent read.

**Every rule is in Python.** `SceneEditor` is the model. It holds the scene
and answers JSON messages: the pointer goes down, the pointer comes up, a tool
is chosen, a property is set, undo, save. Its answer is the whole state a view
draws. The view draws the SVG the editor renders, hovers and previews a drag
in the browser, and sends what the person did. A drag is applied once, on
release, by the scene objects' own editing hooks (`check_mouse_over`,
`on_drag`, `on_construct_mouse_*`), with the pointer as a `Mouse`: snapping to
the grid, to directions with shift, mirroring about the middle with ctrl, as
the JavaScript simulator does. So the geometry rules exist in one place, and
the same messages can serve another view: a VS Code editor for scene files,
or a page in an environment without notebook widgets.

**A designed element is moved by its placement only.** A drag anywhere on it
moves its `position`, or every point argument when it has no position. A
vertex drag would make it something its constructor did not build (`KC2`).
Its outline changes only through a recorded edit: a `SculptedGlass` holds its
base recipe and the edits made to its spline edges, and is moved by its base's
placement, the edits unchanged (`C-SCULPT-03`, `C-SCULPT-04`).
Its other parameters are its form, and a change rebuilds it through the scene
file, so a value its constructor refuses comes back as that refusal, with the
scene as it was.

## The sculpt mode

**Sculpt**, with a designed glass selected, edits it by its handles with its
light in view (`builder.sculpt`). The glass becomes a `SculptedGlass` (its
recipe kept as the base; undoable), its source's light is cut into flux tubes
at the receiver, and an RR lens's edge bundles are aimed. The canvas shows the
sculpt layer instead of the rays: Map A, Map B or both, and a handle at every
designed point.

- **A drag** moves a handle's point along its outward normal (shift: turns its
  tangent), the pointer's travel scaled down by the fine-drag factor, since at
  full scale one screen pixel is already past the first-order range. Each move
  is sent as `sculpt_preview`: the first-order estimate, nothing traced, the
  edited outline dashed, the panel's numbers updated. Past the edge's limit the
  preview is faded.
- **A release** sends `sculpt_apply`: the edit is recorded in the glass's edit
  list, the tubes and bundles are traced again (1.35 s on the Example 9.1
  lens), and what changed in kind is listed as events (a tube split, total
  internal reflection switched, light leaving the receiver, rays leaving a
  bundle's route, an outline refused).
- **Each edge's preview limit is measured**: at every apply the estimate made
  before the edit is compared with the re-trace after it, and the limit set so
  that the estimate's error stays within 10% of the change.
- Undo is the builder's; an undo past the start leaves the mode, the glass as
  it was.
- **An agent sculpts through the same messages** (`builder.agentic`): it
  previews several handles, applies the best within its limit, reads the
  events, and repeats. Attached to a builder widget, the page shows each step.

## Hosts

- **A notebook cell:** `scene_builder()`, an `anywidget` widget. Its messages travel over the
  kernel's widget channel.
- **A VS Code editor for `*.scene.json`:** the extension in `src-vscode/scene-editor` (which also
  holds the graph editor's, `graph`). It starts
  `builder.server` with the interpreter the Python extension selected, so it needs no kernel.
  - It serves the page the server sends, from local storage, under a strict content-security
    policy.
  - It writes each change into the document, so the editor's dirty marker, save, undo and
    version control work as for any text file.
  - A change made to the document from elsewhere is loaded back.

Both draw with the same module, and send the same messages to the same `SceneEditor`.

**The web simulator's files.** Open reads them too, converted, and *Export for the web* writes
the scene back in their format. What either leaves out is shown as a notice.

**The pointer, between messages.** While an object is built, the pointer's moves go to Python one
at a time, so the object follows the pointer by its own rule. That includes a polygon's next
vertex between clicks. A drag on empty canvas pans the view. A designed element with no editing
hooks (a curved mirror) is grabbed where the page drew it. It moves by the arguments its class
names as `placement_points`, its directions left as they are.

## Concepts this component realises

| Concept | How |
|---|---|
| `KB6` | The page finds each object in the drawing by the identity the renderer gives it, so hovering and selecting need no round trip. |
| `KC2` | A designed element is placed from its requirements and moved by its placement; its outline changes only through a recorded edit (a `SculptedGlass`'s edit list), itself an argument of the recipe. |
| `KC7` | The model imports no widget library; the view is the only part that does. |

## Modules

| File | What it holds |
|---|---|
| `builder/agentic.py` | The eight sculpt tools an agent uses, added to the tool lists by an explicit `register()` (`KA7`): `sculpt_start`, `list_flux_tubes`, `describe_flux_tube`, `list_sculpt_handles`, `preview_handle_move`, `apply_handle_move`, `undo_handle_move`, `sculpt_report`. They send the editor's own `sculpt_*` messages, to the scene the notebook attaches (`attach`: a scene, an editor, or a builder widget, whose page is refreshed after each change so a person watches the agent work). Plain dicts, errors as values, names listed, arguments checked, lists capped (`KA2`–`KA9`). |
| `builder/editor.py` | `SceneEditor`: the scene, the selection, the palette, construction and drags through the objects' hooks, properties through `property_schema` and key paths, designed elements through `recipe_parameters`, undo and redo as scene-file snapshots, save and open, the view (zoom about a point, pan, fit) and a quick trace after each change. `state()` is everything a view draws, as JSON, with each object's designed element and recipe, and a point object's place (`at`). |
| `builder/sculpt.py` | `SculptSession`: the sculpt mode's state and rules. The tubes as cut and the bundles as aimed (their seeds replayed on every trace), the estimate of a move (`estimate`), the events between two traces (`events_between`), the preview limit of each edge measured at each apply (`learn`), and the handles a view draws. |
| `builder/server.py` | `python -m ray_tracing_shapely.builder.server`: one editor served on standard input and output, in JSON lines (`serve_lines`, which `graph.server` uses too), for a host that is not a notebook. It takes the editor's messages, plus `hello` (the page's module and CSS, so the host serves the very page this version draws with) and `load_text` (a document's text as the scene). Every reply carries the scene file's text for the host's document. That text is withheld while an object is half-built, and when the document could not be read, so a document is never overwritten with something it did not say. |
| `builder/widget.py` | `scene_builder(scene=None, path=None)`: the editor as an `anywidget` widget. The page's JavaScript is one module with no build step: the canvas, the handles, the drag preview, the palette with a form for a designed element's arguments, the scene as a tree (each designed element with its parts; a row selects, a hover highlights), and a property form built from the selected object's schema. Each object has a grip: an invisible copy of its drawing whose stroke is the click extent wide, above the rays and labels, so a press within 10 screen pixels of an object takes it rather than panning; a press that still hits none picks the nearest point object (a point source) within the same extent. Rays, labels' layer aside, and the handles take no clicks: a handle shows where to grab, and the object's own hit test finds the part. A press on empty canvas pans; the **Pan** button makes every drag pan, objects included, until pressed again or Esc. |

## What it needs from elsewhere

- `core`: the scene objects' editing hooks, `core.mouse.Mouse`, `core.key_path`, and each object's `property_schema`.
- `analysis.scene_file`: the scene file, the primitive and recipe registries, `recipe_parameters`.
- `svg_renderer`: the drawing, with each object's identity on its elements.
- `flows.widget.find_files`: the scene files offered by Open.

## Promises this component makes and relies on

| Contract | Role |
|---|---|
| `C-SCENE-01` | **Relies on** it. A scene saved by the builder is a scene file; a designed element is saved as its recipe. |
| `C-LABEL-01` | **Keeps** it. An object is named when it is placed and never renamed by an edit, so names are unique and stable across a study. |

## How it is shipped

In the core distribution. The model needs nothing beyond the core; the widget
needs the `widgets` extra (`anywidget`).
