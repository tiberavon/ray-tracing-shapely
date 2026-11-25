# `web`

The flow form and the scene builder as web pages, for hosts where notebook
widgets do not run.

A solveit dialog supports Jupyter "except for ipywidgets", and so
`anywidget`, but it can serve a FastHTML app from the kernel. This component
serves the same two views as pages, from routes in such an app: each page is
the widget's own JavaScript module, unchanged. Where the widget's messages go
over the kernel's widget channel, the page posts them as JSON to its route,
and draws the traits that come back. Every rule stays in the model
(`FlowFormModel`, `SceneEditor`), so a fourth way of showing a flow (after the
widget, the transcript and the agent's tools) adds no logic of its own.

The routes are plain Starlette routes. FastHTML is built on Starlette, so they
mount on a solveit dialog's app, on any Starlette app, or alone with
`serve()`, for a browser with no notebook.

## Concepts this component realises

| Concept | How |
|---|---|
| `KC7` | `flows` and `builder` never import it; it imports them. |
| `KD7` | The pages talk to the kernel the person and the agent already share. |

## Modules

| File | What it holds |
|---|---|
| `web/views.py` | `Views`: the views a kernel serves, by id; `flow(flow)` and `builder(scene or path)` add one. `mount(app)` adds three routes per view, under a prefix (`/rts`): the page, its module, and `msg` (a message in, the traits out). The routes go ahead of the app's own, since a FastHTML app's catch-all for static files would otherwise take the module. `embed(id)` is an iframe for a cell's output, `url(id)` the page's address (from `base_url`), `serve()` a standalone server. `FlowView` and `BuilderView` adapt the two models. |

## What it needs from elsewhere

- `flows.widget`: `FlowFormModel`, the form's module and CSS.
- `builder`: `SceneEditor`, the builder's module and CSS.
- Starlette (and uvicorn for `serve`): the `web` extra.

## How it is shipped

In the core distribution, behind the `web` extra.
