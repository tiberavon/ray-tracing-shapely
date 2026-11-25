"""
Python-specific package: web
Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

===============================================================================
The flow form, the scene builder and the graph editor as web pages
===============================================================================
Where notebook widgets do not run (a solveit dialog, whose manual says it
supports Jupyter "except for ipywidgets", and so `anywidget`), the same
views are served as pages by HTTP routes in the kernel's own web app:

    from fasthtml.common import FastHTML
    from fasthtml.jupyter import JupyUvi
    from ray_tracing_shapely.web import Views

    app = FastHTML()
    views = Views(base_url="https://<this instance's public URL>")
    views.mount(app)                       # the routes, under /rts
    server = JupyUvi(app)
    views.embed(views.builder(path="my.scene.json"))      # an iframe, in the output
    views.embed(views.graph(path="design.graph.json"))

A page is the widget's own JavaScript module, unchanged; where the widget's
messages go over the kernel's widget channel, the page posts them as JSON to
its route, and draws what comes back. Every rule stays in Python
(`FlowFormModel`, `SceneEditor`, `GraphEditor`; a graph's runner in this
kernel, the page polling while a long node runs). The routes are plain Starlette routes, so
they mount on a FastHTML app (FastHTML is built on Starlette) and on any
Starlette app; `serve()` runs them alone, for a browser with no notebook.

Needs the ``web`` extra (Starlette; uvicorn for `serve`). `flows`,
`builder` and `graph` never import this package (`KC7`).
===============================================================================
"""

from .views import BuilderView, FlowView, GraphView, View, Views

__all__ = ["BuilderView", "FlowView", "GraphView", "View", "Views"]
