"""
Python-specific module: web views
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
Views, their pages, and the routes that serve them
===============================================================================
A `View` is a model the page talks to: ``traits()`` is what the page reads
with ``model.get(name)``, ``handle(message)`` applies what it sends. `Views`
keeps them by id and answers three routes per view, under a prefix
(default ``/rts``):

- ``GET  {prefix}/{id}/``          the page;
- ``GET  {prefix}/{id}/module.js`` its JavaScript module (the widget's own);
- ``POST {prefix}/{id}/msg``       ``{"message": {...}}`` in, the traits out.

The page reaches the other two by relative URL, so it works under any mount
path and behind a proxy. A message the view refuses comes back in its traits
(the editor's ``error``, the form's ``last``), as in the widget.
===============================================================================
"""

from __future__ import annotations

import html
import itertools
import json
import threading
from typing import Any, Dict, List, Optional

#: The page: the module, a stand-in for the widget's model, and nothing else.
PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>body {{ margin: 8px; font: 13px system-ui, sans-serif; }} {css}</style></head>
<body><div id="root">Loading…</div>
<script type="module">
import page from "./module.js";
// The widget's model, over HTTP: get() reads the last traits, send() posts a message and
// fires every change handler with what comes back. One request at a time, in order.
let traits = {traits};
const handlers = {{}};
let queue = Promise.resolve();
const model = {{
  get: (name) => traits[name],
  on: (event, f) => {{ (handlers[event] = handlers[event] || []).push(f); }},
  send: (message) => {{
    queue = queue.then(async () => {{
      const r = await fetch("./msg", {{ method: "POST", headers: {{ "Content-Type": "application/json" }},
                                        body: JSON.stringify({{ message }}) }});
      traits = r.ok ? await r.json() : {{ ...traits, state: {{ ...(traits.state || {{}}), error: `HTTP ${{r.status}}` }} }};
      for (const name of Object.keys(traits)) (handlers["change:" + name] || []).forEach((f) => f());
    }}).catch((e) => console.error(e));
  }},
}};
page.render({{ model, el: document.getElementById("root") }});
</script></body></html>
"""


class View:
    """A model behind one page."""

    title = "ray-tracing-shapely"
    esm = ""
    css = ""

    def traits(self) -> Dict[str, Any]:
        raise NotImplementedError

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def page(self) -> str:
        """The page's HTML, with the current traits inlined so it draws at once."""
        traits = json.dumps(self.traits(), default=str).replace("</", "<\\/")
        return PAGE.format(title=html.escape(self.title), css=self.css, traits=traits)


class FlowView(View):
    """A flow's form (`flows.widget.FlowFormModel`), the widget's page and messages."""

    def __init__(self, flow: Any) -> None:
        from ..flows.widget import _CSS, _ESM, FlowFormModel  # noqa: PLC0415
        self.model = FlowFormModel(flow)
        self.esm, self.css = _ESM, _CSS
        self.title = f"{type(flow).__name__}"

    @property
    def flow(self) -> Any:
        return self.model.flow

    def traits(self) -> Dict[str, Any]:
        return self.model.traits()

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        self.model.handle(message or {})
        return self.traits()


class BuilderView(View):
    """The scene builder (`builder.SceneEditor`), the widget's page and messages."""

    def __init__(self, editor: Any) -> None:
        from ..builder.widget import _CSS, _ESM  # noqa: PLC0415
        self.editor = editor
        self.esm, self.css = _ESM, _CSS
        self.title = "Scene builder"

    @property
    def scene(self) -> Any:
        return self.editor.scene

    def traits(self) -> Dict[str, Any]:
        from ..flows.widget import find_files  # noqa: PLC0415
        state = self.editor.state()
        state["files"] = find_files("*.scene.json")
        return {"state": state}

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if (message or {}).get("type") != "refresh":
            self.editor.handle(message or {})
        return self.traits()


class GraphView(View):
    """The graph editor (`graph.GraphEditor`), the widget's page and messages.

    Its runner lives in this kernel, as the widget's does; a page polls while a long node runs.
    """

    def __init__(self, editor: Any) -> None:
        from ..graph.widget import _CSS, _ESM  # noqa: PLC0415
        self.editor = editor
        self.esm, self.css = _ESM, _CSS
        self.title = "Graph editor"

    def document(self) -> Dict[str, Any]:
        """A copy of the graph document as it stands."""
        return self.editor.document()

    def traits(self) -> Dict[str, Any]:
        from ..flows.widget import find_files  # noqa: PLC0415
        state = self.editor.state()
        state["files"] = find_files("*.graph.json")
        return {"state": state}

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if (message or {}).get("type") != "refresh":
            self.editor.handle(message or {})
        return self.traits()


class Views:
    """The views a kernel serves, by id, and the routes that serve them.

    Args:
        prefix: Where the routes live (default ``/rts``; solveit keeps ``/``).
        base_url: The URL the browser reaches the app at, for `url` and
            `embed` (a solveit instance's public URL for port 8000). Empty:
            URLs relative to the page that shows them.
    """

    def __init__(self, prefix: str = "/rts", base_url: str = "") -> None:
        self.prefix = "/" + prefix.strip("/")
        self.base_url = base_url.rstrip("/")
        self._views: Dict[str, View] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()                 # one message at a time per kernel

    # --- the views -------------------------------------------------------------

    def add(self, view: View) -> str:
        """Register a view; its id."""
        vid = f"v{next(self._ids)}"
        self._views[vid] = view
        return vid

    def flow(self, flow: Any) -> str:
        """A flow's form; its id."""
        return self.add(FlowView(flow))

    def builder(self, scene: Any = None, path: Optional[str] = None, **kwargs: Any) -> str:
        """A scene builder over `scene` or the scene file at `path`; its id (kwargs: `SceneEditor`'s)."""
        from ..builder.editor import SceneEditor  # noqa: PLC0415
        return self.add(BuilderView(SceneEditor(scene, path=path, **kwargs)))

    def graph(self, doc: Any = None, path: Optional[str] = None, runner: Any = None) -> str:
        """A graph editor over the document `doc` or the graph file at `path`; its id."""
        from ..graph.editor import GraphEditor  # noqa: PLC0415
        return self.add(GraphView(GraphEditor(doc, path=path, runner=runner)))

    def __getitem__(self, vid: str) -> View:
        return self._views[vid]

    def url(self, vid: str) -> str:
        """The page's URL."""
        return f"{self.base_url}{self.prefix}/{vid}/"

    def embed(self, vid: str, height: int = 760) -> Any:
        """The page in an iframe, for a cell's output (an IPython ``HTML`` object)."""
        from IPython.display import HTML  # noqa: PLC0415
        return HTML(self.iframe(vid, height))

    def iframe(self, vid: str, height: int = 760) -> str:
        """The iframe's HTML."""
        return (f'<iframe src="{html.escape(self.url(vid))}" style="width: 100%; height: {int(height)}px; '
                f'border: 1px solid #ccc;" loading="lazy"></iframe>')

    def message(self, vid: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """Apply one message to a view; its traits."""
        with self._lock:
            return self._views[vid].handle(message)

    # --- the routes ------------------------------------------------------------

    def routes(self) -> List[Any]:
        """The Starlette routes serving every view."""
        from starlette.responses import HTMLResponse, JSONResponse, Response  # noqa: PLC0415
        from starlette.routing import Route  # noqa: PLC0415

        def view_of(request):
            view = self._views.get(request.path_params["vid"])
            if view is None:
                return None, Response(f"no view {request.path_params['vid']!r}", status_code=404)
            return view, None

        async def page(request):
            view, missing = view_of(request)
            return missing or HTMLResponse(view.page())

        async def module(request):
            view, missing = view_of(request)
            return missing or Response(view.esm, media_type="text/javascript")

        async def msg(request):
            view, missing = view_of(request)
            if missing:
                return missing
            try:
                body = await request.json()
            except ValueError:
                return Response("the body is not JSON", status_code=400)
            traits = self.message(request.path_params["vid"], (body or {}).get("message") or {})
            return JSONResponse(json.loads(json.dumps(traits, default=str)))

        p = self.prefix
        return [Route(f"{p}/{{vid}}/", page, methods=["GET"]),
                Route(f"{p}/{{vid}}/module.js", module, methods=["GET"]),
                Route(f"{p}/{{vid}}/msg", msg, methods=["POST"])]

    def mount(self, app: Any) -> Any:
        """Add the routes to a FastHTML or Starlette app, ahead of its own.

        Ahead, because a FastHTML app's catch-all for static files would
        otherwise take ``module.js``.
        """
        app.router.routes[0:0] = self.routes()
        return app

    def app(self) -> Any:
        """A Starlette app serving only these views."""
        from starlette.applications import Starlette  # noqa: PLC0415
        return Starlette(routes=self.routes())

    def serve(self, host: str = "127.0.0.1", port: int = 8765) -> str:
        """Serve the views alone, in a background thread (no notebook needed); the base URL."""
        import uvicorn  # noqa: PLC0415
        server = uvicorn.Server(uvicorn.Config(self.app(), host=host, port=port, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        self._server = server
        if not self.base_url:
            self.base_url = f"http://{host}:{port}"
        return self.base_url

    def stop(self) -> None:
        """Stop the server `serve` started."""
        server = getattr(self, "_server", None)
        if server is not None:
            server.should_exit = True


__all__ = ["BuilderView", "FlowView", "GraphView", "PAGE", "View", "Views"]
