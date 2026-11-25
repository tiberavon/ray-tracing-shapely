"""
Python-specific module: scene builder server
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
The scene builder as a process: JSON lines on standard input and output
===============================================================================
``python -m ray_tracing_shapely.builder.server`` serves one `SceneEditor` to
a host that is not a notebook: the VS Code editor for ``*.scene.json`` files,
which starts it with the interpreter the Python extension has selected, as a
language server is started. It needs no kernel; its result is the scene file.

Each request is one line, ``{"id": n, "message": {...}}``; each reply one line,
``{"id": n, "state": {...}}``, or ``{"id": n, "error": "..."}`` when the
request itself cannot be read. The messages are the editor's own
(`SceneEditor.handle`), plus three of the host's:

- ``{"type": "hello"}``: the page's JavaScript module and CSS, which the host
  serves to its view, so the canvas always comes from the same version as the
  editor it talks to; and the package's version.
- ``{"type": "load_text", "text": "...", "path": "..."}``: the scene from a
  document's text (empty text: an empty scene). A text that is not a scene
  file leaves the editor empty and says why in ``state["error"]``, with
  ``state["text"]`` None, so the host never writes over the document.
- ``{"type": "refresh"}``: the state, unchanged.

Every state carries ``"text"``: the scene file as the editor holds it, which
the host writes into the document when it differs, and ``"host": "vscode"``
(or the ``--host`` given), which tells the page to leave saving to the host.
Nothing but replies is written to standard output; diagnostics go to
standard error.
===============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Callable, Dict, Optional, TextIO

from ..analysis import scene_file as sf
from .editor import SceneEditor


def scene_text(editor: SceneEditor) -> str:
    """The editor's scene as a scene file's text: what the host's document holds."""
    return json.dumps(sf.scene_to_dict(editor.scene), indent=2, sort_keys=False) + "\n"


class SceneServer:
    """One editor, answering the host's requests.

    Args:
        host: What the page is told it is hosted in (it hides its own Save and Open).
        width, height: The canvas's size in screen pixels.
    """

    def __init__(self, host: str = "vscode", width: int = 900, height: int = 560) -> None:
        self.host = host
        self.width, self.height = width, height
        self.editor = SceneEditor(width=width, height=height)
        self.loaded = True

    def _state(self) -> Dict[str, Any]:
        state = self.editor.state()
        state["host"] = self.host
        try:
            # mid-construction the scene holds a half-built object: the document waits for the release
            building = self.editor._constructing is not None
            state["text"] = scene_text(self.editor) if self.loaded and not building else None
        except sf.SceneFileError as exc:              # an object that cannot be saved: say so, write nothing
            state["text"] = None
            state["error"] = state.get("error") or f"the scene cannot be saved: {exc}"
        return state

    def _load_text(self, message: Dict[str, Any]) -> Dict[str, Any]:
        text = message.get("text") or ""
        error = None
        try:
            notice = None
            data = json.loads(text) if text.strip() else None
            if data is None:
                scene = None
            elif sf.is_web_scene(data):                   # the web simulator's file: converted on the first edit
                from .editor import _web_notice           # noqa: PLC0415
                scene, report = sf.scene_from_web_dict(data)
                notice = _web_notice("read from the web simulator's format; an edit writes it in this "
                                     "package's", report)
            else:
                scene = sf.scene_from_dict(data)
            self.editor = SceneEditor(scene, width=self.width, height=self.height)
            self.editor.notice = notice
            self.editor.path = message.get("path")
            self.loaded = True
        except (ValueError, sf.SceneFileError, KeyError, TypeError) as exc:
            self.editor = SceneEditor(width=self.width, height=self.height)
            self.loaded = False                       # never written back over the document
            error = f"this file is not a scene the builder can read: {type(exc).__name__}: {exc}"
        state = self._state()
        if error:
            state["error"] = error
        return state

    def request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """The reply to one host request's message (no ``id``)."""
        kind = (message or {}).get("type")
        if kind == "hello":
            from .. import __version__                # noqa: PLC0415
            from .widget import _CSS, _ESM            # noqa: PLC0415 -- the page, without anywidget
            return {"esm": _ESM, "css": _CSS, "version": __version__}
        if kind == "load_text":
            return self._load_text(message)
        if kind != "refresh":
            if not self.loaded and kind in ("press", "release", "set", "delete", "undo", "redo"):
                state = self._state()
                state["error"] = "the document could not be read as a scene; fix its text first"
                return state
            self.editor.handle(message)
        return self._state()

    def serve(self, stdin: TextIO, stdout: TextIO) -> None:
        """Answer requests line by line until standard input closes."""
        serve_lines(self.request, stdin, stdout)


def serve_lines(request: Callable[[Dict[str, Any]], Dict[str, Any]], stdin: TextIO, stdout: TextIO) -> None:
    """Answer ``{"id", "message"}`` lines with ``{"id", "state"}`` lines until standard input closes.

    A request that raises is answered ``{"id", "error"}``, its traceback on standard error, and the
    server goes on.
    """
    for line in stdin:
        if not line.strip():
            continue
        rid: Optional[Any] = None
        try:
            message = json.loads(line)
            rid = message.get("id")
            reply = {"id": rid, "state": request(message.get("message") or {})}
        except Exception as exc:                  # noqa: BLE001 -- the host gets the reason, the server lives
            traceback.print_exc(file=sys.stderr)
            reply = {"id": rid, "error": f"{type(exc).__name__}: {exc}"}
        stdout.write(json.dumps(reply, default=str) + "\n")
        stdout.flush()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="The scene builder, served on standard input and output.")
    parser.add_argument("--host", default="vscode")
    parser.add_argument("--width", type=int, default=900)
    parser.add_argument("--height", type=int, default=560)
    args = parser.parse_args(argv)
    SceneServer(args.host, args.width, args.height).serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["SceneServer", "main", "scene_text", "serve_lines"]
