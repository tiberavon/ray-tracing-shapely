"""
Python-specific module: graph editor server
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
The graph editor as a process: JSON lines on standard input and output
===============================================================================
``python -m ray_tracing_shapely.graph.server`` serves one `GraphEditor` to a
host that is not a notebook: the VS Code editor for ``*.graph.json`` files,
started with the interpreter the Python extension has selected, as the scene
builder's server is (same protocol, `builder.server.serve_lines`). It needs no
notebook kernel: the graph's runner lives in this process, its results kept
here for as long as the editor is open, and a long node goes to a worker
process (`LocalProcessExecutor`, its records under ``--jobs``).

Each request is ``{"id": n, "message": {...}}``; each reply ``{"id": n,
"state": {...}}``, or ``{"id": n, "error": "..."}``. The messages are the
editor's own (`GraphEditor.handle`), less ``new``, ``open`` and ``save``,
which are the host's, plus four of the host's:

- ``{"type": "hello"}``: the page's JavaScript module and CSS, and the
  package's version;
- ``{"type": "load_text", "text": "...", "path": "..."}``: the graph from a
  document's text (empty: a new graph). A text that is not a graph document
  leaves the editor empty and says why in ``state["error"]``; the host's
  document is then never written;
- ``{"type": "refresh"}``: the state, unchanged;
- ``{"type": "open_scene", "id": node, "output": "scene"}``: a copy of a fresh
  node's computed scene written to ``<graph>.<node>.scene.json`` beside the
  graph, and named in ``state["scene"]`` for the host to open in the scene
  editor. A copy, as the notebook widget's ``open_scene`` gives: an edit there
  does not change the value the runner keeps. A file of that name with other
  content (a copy edited since) is kept, and the next free name taken.

A state carries ``"text"``, the graph document as the editor holds it, only
when it changed since the document was loaded or last sent, so the host
writes the document on an edit and not on a selection, a run or an opening
(where nodes without a place are laid out, written with the next edit). It
also carries ``"host"``, which tells the page to leave the file to the host,
and ``"compiled"``, the notebook a ``compile`` wrote, which the host offers
to open. A relative notebook path is taken from the graph's folder.
===============================================================================
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ..builder.server import serve_lines
from .document import GraphError, new_graph
from .editor import GraphEditor
from .runner import GraphRunner

#: Where the worker processes' job records go when ``--jobs`` is not given.
DEFAULT_JOBS = Path(tempfile.gettempdir()) / "ray_tracing_shapely" / "graph_jobs"
#: The messages the host answers itself: the document is its file.
HOST_MESSAGES = frozenset({"new", "open", "save"})


def graph_text(doc: Dict[str, Any]) -> str:
    """A graph document's text, as `save_graph` writes it."""
    return json.dumps(doc, indent=2) + "\n"


class GraphServer:
    """One graph editor, answering the host's requests.

    Args:
        host: What the page is told it is hosted in (it hides its own New, Open and Save).
        jobs: Where a long node's job records go; `DEFAULT_JOBS` if not given.
        runner: What runs the graph; one with a `LocalProcessExecutor` over ``jobs`` if not given.
    """

    def __init__(self, host: str = "vscode", jobs: Optional[str] = None,
                 runner: Optional[GraphRunner] = None) -> None:
        self.host = host
        if runner is None:
            from ..flows.executors import LocalProcessExecutor  # noqa: PLC0415
            root = Path(jobs) if jobs else DEFAULT_JOBS
            root.mkdir(parents=True, exist_ok=True)
            runner = GraphRunner(executor=LocalProcessExecutor(root))
        self.runner = runner
        self.editor = GraphEditor(runner=runner)
        self.loaded = True
        self.scene: Optional[str] = None
        self._sent = graph_text(self.editor.document())

    def _state(self) -> Dict[str, Any]:
        state = self.editor.state()
        state["host"] = self.host
        state["compiled"], self.editor.compiled = self.editor.compiled, None     # offered once
        state["scene"], self.scene = self.scene, None                             # opened once
        state["can_open_scene"] = True
        text = graph_text(self.editor.document())
        state["text"] = text if self.loaded and text != self._sent else None
        if state["text"] is not None:
            self._sent = text
        return state

    def _load_text(self, message: Dict[str, Any]) -> Dict[str, Any]:
        text = message.get("text") or ""
        error = None
        try:
            doc = json.loads(text) if text.strip() else new_graph()
            self.editor = GraphEditor(doc, runner=self.runner)
            self.editor.path = message.get("path")
            self.loaded = True
        except (ValueError, GraphError, KeyError, TypeError) as exc:
            self.editor = GraphEditor(runner=self.runner)
            self.loaded = False                       # never written back over the document
            error = f"this file is not a graph the editor can read: {type(exc).__name__}: {exc}"
        self._sent = graph_text(self.editor.document())
        state = self._state()
        if error:
            state["error"] = error
        return state

    def _scene_path(self, node: str, text: str) -> Path:
        """Where a node's scene is written: beside the graph (or in the jobs' temporary folder).

        ``<graph>.<node>.scene.json``; a file there with other content (a copy edited since) is
        kept, and the next free name taken.
        """
        if self.editor.path:
            graph = Path(self.editor.path)
            folder, stem = graph.parent, re.sub(r"(\.graph)?\.json$", "", graph.name)
        else:
            folder, stem = DEFAULT_JOBS.parent / "scenes", "graph"
        k = 1
        while True:
            path = folder / f"{stem}.{node}{'' if k == 1 else f'_{k}'}.scene.json"
            if not path.exists() or path.read_text(encoding="utf-8") == text:
                return path
            k += 1

    def _open_scene(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Write a copy of a fresh node's computed scene to a file, for the host to open in the scene editor."""
        from ..analysis import scene_file as sf  # noqa: PLC0415
        node, output = message.get("id"), message.get("output") or "scene"
        status = {n["id"]: n for n in self.editor.state()["nodes"]}.get(node)
        error = None
        if not self.loaded:
            error = "the document could not be read as a graph; fix its text first"
        elif status is None:
            error = f"no node {node!r}"
        elif not any(p["name"] == output and p["type"]["type"] == "scene" for p in status["outputs"]):
            error = f"{node} has no scene output {output!r}"
        elif status["status"] != "fresh":
            error = f"{node} is {status['status']}: run the graph first"
        if error is None:
            try:
                text = json.dumps(sf.scene_to_dict(self.runner.outputs(node)[output]), indent=2) + "\n"
                path = self._scene_path(node, text)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                self.scene = str(path)
            except (KeyError, OSError, sf.SceneFileError) as exc:
                error = f"{node}.{output} could not be written as a scene file: {exc}"
        self.editor.error, self.editor.notice = error, (None if error else f"a copy of {node}.{output} in {path.name}")
        return self._state()

    def request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """The reply to one host request's message (no ``id``)."""
        message = dict(message or {})
        kind = message.get("type")
        if kind == "hello":
            from .. import __version__                # noqa: PLC0415
            from .widget import _CSS, _ESM            # noqa: PLC0415 -- the page, without anywidget
            return {"esm": _ESM, "css": _CSS, "version": __version__}
        if kind == "load_text":
            return self._load_text(message)
        if kind == "refresh":
            return self._state()
        if kind == "open_scene":
            return self._open_scene(message)
        if kind in HOST_MESSAGES:
            state = self._state()
            state["error"] = f"{kind} is the editor's own here: use VS Code's File menu"
            return state
        if not self.loaded and kind not in ("select", "poll"):
            state = self._state()
            state["error"] = "the document could not be read as a graph; fix its text first"
            return state
        path = message.get("path")
        if kind == "compile" and isinstance(path, str) and path and self.editor.path \
                and not Path(path).is_absolute():
            message["path"] = str(Path(self.editor.path).parent / path)
        self.editor.handle(message)
        return self._state()

    def serve(self, stdin: Any, stdout: Any) -> None:
        """Answer requests line by line until standard input closes."""
        serve_lines(self.request, stdin, stdout)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="The graph editor, served on standard input and output.")
    parser.add_argument("--host", default="vscode")
    parser.add_argument("--jobs", default=None, help="where long nodes' job records go")
    args = parser.parse_args(argv)
    GraphServer(args.host, args.jobs).serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["DEFAULT_JOBS", "GraphServer", "graph_text", "main"]
