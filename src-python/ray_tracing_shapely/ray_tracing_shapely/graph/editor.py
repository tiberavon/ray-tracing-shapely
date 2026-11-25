"""
Python-specific module: graph editor
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
GraphEditor -- the graph canvas's model: every rule in Python, no view
===============================================================================
A view (the notebook widget, later a VS Code editor) draws what `state()`
returns and sends back what the person did, as messages (`handle`). The
document it edits is the graph document of `graph.document`; every change is
checked by `check_graph(..., complete=False)`, the compiler's own rule less
the inputs not given yet, and a change it refuses leaves the document as it
was, the reason in ``state()["error"]``.

Messages (JSON):

- ``{"type": "add", "block", "at"?: [x, y], "id"?}``: a node of a block; its
  id made from the block's name unless given, its place moved aside from a
  node already there. The new node is selected.
- ``{"type": "move", "id", "at": [x, y]}``; ``{"type": "delete", "id"}``,
  which takes the wires from it away too; ``{"type": "rename", "id", "to"}``,
  which renames the wires from it too.
- ``{"type": "set", "id", "input", "value"}``: an input's JSON value; ``null``
  takes it away, so the block's default applies. A wired input set so loses
  its wire.
- ``{"type": "connect", "from": "<node>.<output>", "to": "<node>.<input>"}``:
  a wire. Into a list input it is added to the list's wires; into another, it
  takes the place of what was there. Refused when the input's type does not
  accept the output's, or when it would close a cycle.
- ``{"type": "disconnect", "to": "<node>.<input>", "index"?}``: a wire taken
  away, or one item of a list of wires.
- ``{"type": "select", "id": <id | null>}``; ``{"type": "notes", "text"}``.
- ``{"type": "undo"}``, ``{"type": "redo"}``.
- ``{"type": "new"}``, ``{"type": "open", "path"}``, ``{"type": "save",
  "path"}``: the graph file. A graph is saved as drawn, unfinished or not; a
  node without a place is laid out by its wires when opened.
- ``{"type": "compile", "path"}``: the notebook (`compile.write_notebook`),
  only of a graph with every required input given.
- ``{"type": "run"}``: the stale nodes run (`runner.GraphRunner`), as far as
  they go without waiting; a long node goes to the runner's executor, and
  ``{"type": "poll"}`` takes the run on once its job has ended. Each node's
  ``status`` says whether it is fresh, stale, running or failed; the
  selected node's computed ``values`` are its outputs' JSON, shortened.

What a node shows: each output, and each input that is given, required, or of
a type some block's output can feed. The rest are its form's fields only.
===============================================================================
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..blocks import catalogue, get_block
from ..blocks.types import BlockTypeError, ListOf, Optional_, ValueType
from .compile import write_notebook
from .runner import GraphRunner, RunnerError
from .document import GraphError, check_graph, free_id, is_wire, new_graph, wire_source, wires_of

#: The palette's groups, in its order.
PALETTE_KINDS = ("function", "recipe", "primitive")
#: Where a node is placed when the view gives no place, and how far apart laid-out nodes are.
_ORIGIN, _COLUMN, _ROW = (40.0, 40.0), 240.0, 140.0


class EditorError(ValueError):
    """A message the editor cannot apply, with the reason."""


def _split(end: Any, what: str) -> tuple:
    if not isinstance(end, str) or "." not in end:
        raise EditorError(f"{what} is '<node>.<port>', got {end!r}")
    node, _, port = end.partition(".")
    return node, port


def _accepts(target: ValueType, source: ValueType) -> bool:
    """Whether an output of type ``source`` can be wired into an input of type ``target``."""
    if target.accepts(source):
        return True
    return isinstance(target, ListOf) and target.inner.accepts(source)


class GraphEditor:
    """A graph document, edited by messages, with undo.

    Args:
        doc: The document to edit; a new one if not given.
        path: A graph file to open instead.
        runner: What runs the graph; one with no executor if not given, so a long node is refused
            with its estimate.
    """

    def __init__(self, doc: Optional[Dict[str, Any]] = None, path: Optional[str] = None,
                 runner: Optional[GraphRunner] = None) -> None:
        self.runner = runner if runner is not None else GraphRunner()
        self.doc: Dict[str, Any] = new_graph()
        self.path: Optional[str] = None
        self.selected: Optional[str] = None
        self.error: Optional[str] = None
        self.notice: Optional[str] = None
        #: The notebook the last message compiled to, for a host that opens it; None otherwise.
        self.compiled: Optional[str] = None
        self._undo: List[Dict[str, Any]] = []
        self._redo: List[Dict[str, Any]] = []
        self._output_types = [get_block(b["name"]).outputs for b in catalogue()]
        if path is not None:
            self._open(path)
        elif doc is not None:
            self._load(copy.deepcopy(doc))

    # --- the document --------------------------------------------------------------

    def document(self) -> Dict[str, Any]:
        """A copy of the document as it stands."""
        return copy.deepcopy(self.doc)

    def _node(self, nid: Any, doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        for node in (doc or self.doc)["nodes"]:
            if node["id"] == nid:
                return node
        raise EditorError(f"no node {nid!r}; nodes: {', '.join(n['id'] for n in (doc or self.doc)['nodes']) or 'none'}")

    def _new_id(self, block: str) -> str:
        return free_id(block, (n["id"] for n in self.doc["nodes"]))

    def _commit(self, doc: Dict[str, Any]) -> None:
        """Check ``doc`` as a draft and make it the document; refused, the document stays."""
        check_graph(doc, complete=False)
        self._undo.append(self.doc)
        self._redo.clear()
        self.doc = doc

    def _load(self, doc: Dict[str, Any]) -> None:
        check_graph(doc, complete=False)
        doc.setdefault("notes", "")
        self._lay_out(doc)
        self.doc, self.selected = doc, None
        self._undo.clear()
        self._redo.clear()

    @staticmethod
    def _upstream(doc: Dict[str, Any]) -> Dict[str, Set[str]]:
        return {n["id"]: {wire_source(w)[0] for v in n.get("inputs", {}).values() for w in wires_of(v)}
                for n in doc["nodes"]}

    def _lay_out(self, doc: Dict[str, Any]) -> None:
        """Give a place to each node without one: its column by the wires feeding it."""
        ups = self._upstream(doc)
        depth: Dict[str, int] = {}

        def depth_of(nid: str) -> int:
            if nid not in depth:
                depth[nid] = 0
                depth[nid] = 1 + max((depth_of(u) for u in ups[nid] if u in ups), default=-1)
            return depth[nid]

        rows: Dict[int, int] = {}
        for node in doc["nodes"]:
            if node.get("at") is None:
                col = depth_of(node["id"])
                row = rows.get(col, 0)
                rows[col] = row + 1
                node["at"] = [_ORIGIN[0] + col * _COLUMN, _ORIGIN[1] + row * _ROW]

    # --- messages ------------------------------------------------------------------

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Apply one message; the new state. A refusal is kept in ``state()["error"]``."""
        self.error, self.notice, self.compiled = None, None, None
        kind = (message or {}).get("type")
        apply = getattr(self, f"_on_{kind}", None) if isinstance(kind, str) else None
        try:
            if apply is None:
                raise EditorError(f"no message type {kind!r}")
            apply(message)
        except (EditorError, GraphError, BlockTypeError, RunnerError) as e:
            self.error = str(e)
        except (OSError, json.JSONDecodeError) as e:
            self.error = f"{type(e).__name__}: {e}"
        return self.state()

    def _on_add(self, m: Dict[str, Any]) -> None:
        block = get_block(m.get("block")) if isinstance(m.get("block"), str) else None
        if block is None:
            raise EditorError(f"add needs a block name, got {m.get('block')!r}")
        nid = m.get("id") or self._new_id(block.name)
        at = m.get("at") or [_ORIGIN[0], _ORIGIN[1] + _ROW * len(self.doc["nodes"])]
        x, y = float(at[0]), float(at[1])
        while any(abs(n["at"][0] - x) < 20 and abs(n["at"][1] - y) < 20 for n in self.doc["nodes"] if n.get("at")):
            x, y = x + 30, y + 30                       # not on top of a node already there
        doc = self.document()
        doc["nodes"].append({"id": nid, "block": block.name, "inputs": {}, "at": [x, y]})
        self._commit(doc)
        self.selected = nid

    def _on_move(self, m: Dict[str, Any]) -> None:
        at = m.get("at")
        if not (isinstance(at, (list, tuple)) and len(at) == 2):
            raise EditorError(f"move needs at: [x, y], got {at!r}")
        doc = self.document()
        self._node(m.get("id"), doc)["at"] = [float(at[0]), float(at[1])]
        self._commit(doc)

    def _on_delete(self, m: Dict[str, Any]) -> None:
        doc = self.document()
        gone = self._node(m.get("id"), doc)["id"]
        doc["nodes"] = [n for n in doc["nodes"] if n["id"] != gone]
        for node in doc["nodes"]:
            inputs = node.get("inputs", {})
            for name, value in list(inputs.items()):
                if is_wire(value) and wire_source(value)[0] == gone:
                    del inputs[name]
                elif isinstance(value, list) and any(is_wire(v) for v in value):
                    kept = [v for v in value if wire_source(v)[0] != gone]
                    if kept:
                        inputs[name] = kept
                    else:
                        del inputs[name]
        self._commit(doc)
        if self.selected == gone:
            self.selected = None

    def _on_rename(self, m: Dict[str, Any]) -> None:
        doc = self.document()
        old, new = self._node(m.get("id"), doc)["id"], m.get("to")
        if new == old:
            return
        self._node(old, doc)["id"] = new
        for node in doc["nodes"]:
            for name, value in node.get("inputs", {}).items():
                for w in wires_of(value):
                    src, out = wire_source(w)
                    if src == old:
                        w["from"] = f"{new}.{out}"
        self._commit(doc)
        if self.selected == old:
            self.selected = new

    def _input(self, node: Dict[str, Any], name: Any) -> Any:
        block = get_block(node["block"])
        port = next((p for p in block.inputs if p.name == name), None)
        if port is None:
            raise EditorError(f"{node['id']}: {block.name} has no input {name!r}; "
                              f"inputs: {', '.join(p.name for p in block.inputs)}")
        return port

    def _on_set(self, m: Dict[str, Any]) -> None:
        doc = self.document()
        node = self._node(m.get("id"), doc)
        port = self._input(node, m.get("input"))
        inputs = node.setdefault("inputs", {})
        if m.get("value") is None or m.get("value") == "":
            inputs.pop(port.name, None)
        else:
            inputs[port.name] = m["value"]
        self._commit(doc)

    def _on_connect(self, m: Dict[str, Any]) -> None:
        src, out = _split(m.get("from"), "a wire's from")
        dst, name = _split(m.get("to"), "a wire's to")
        doc = self.document()
        node = self._node(dst, doc)
        port = self._input(node, name)
        if src == dst:
            raise EditorError(f"{dst}.{name}: a node's output cannot feed its own input")
        wire = {"from": f"{src}.{out}"}
        inputs = node.setdefault("inputs", {})
        current = inputs.get(name)
        if isinstance(port.type, ListOf):
            wires = [w for w in current if is_wire(w)] if isinstance(current, list) else []
            if wire in wires:
                raise EditorError(f"{dst}.{name}: already wired from {wire['from']!r}")
            inputs[name] = wires + [wire]
        else:
            inputs[name] = wire
        self._commit(doc)

    def _on_disconnect(self, m: Dict[str, Any]) -> None:
        dst, name = _split(m.get("to"), "a wire's to")
        doc = self.document()
        node = self._node(dst, doc)
        self._input(node, name)
        inputs = node.get("inputs", {})
        current = inputs.get(name)
        index = m.get("index")
        if isinstance(current, list) and index is not None:
            if not (isinstance(index, int) and 0 <= index < len(current)):
                raise EditorError(f"{dst}.{name}: no wire {index!r}; it has {len(current)}")
            del current[index]
            if not current:
                del inputs[name]
        elif current is not None and next(wires_of(current), None) is not None:
            del inputs[name]
        else:
            raise EditorError(f"{dst}.{name} has no wire")
        self._commit(doc)

    def _on_select(self, m: Dict[str, Any]) -> None:
        nid = m.get("id")
        self.selected = None if nid is None else self._node(nid)["id"]

    def _on_notes(self, m: Dict[str, Any]) -> None:
        doc = self.document()
        doc["notes"] = str(m.get("text") or "")
        self._commit(doc)

    def _on_undo(self, _m: Dict[str, Any]) -> None:
        if not self._undo:
            raise EditorError("nothing to undo")
        self._redo.append(self.doc)
        self.doc = self._undo.pop()
        self._keep_selection()

    def _on_redo(self, _m: Dict[str, Any]) -> None:
        if not self._redo:
            raise EditorError("nothing to redo")
        self._undo.append(self.doc)
        self.doc = self._redo.pop()
        self._keep_selection()

    def _keep_selection(self) -> None:
        if self.selected not in {n["id"] for n in self.doc["nodes"]}:
            self.selected = None

    def _path(self, m: Dict[str, Any]) -> str:
        path = m.get("path") or self.path
        if not isinstance(path, str) or not path:
            raise EditorError("a path is needed")
        return path

    def _on_new(self, _m: Dict[str, Any]) -> None:
        self._load(new_graph())
        self.path = None

    def _open(self, path: str) -> None:
        self._load(json.loads(Path(path).read_text(encoding="utf-8")))
        self.path = str(path)

    def _on_open(self, m: Dict[str, Any]) -> None:
        self._open(self._path(m))
        self.notice = f"opened {self.path}"

    def _on_save(self, m: Dict[str, Any]) -> None:
        path = self._path(m)
        check_graph(self.doc, complete=False)
        Path(path).write_text(json.dumps(self.doc, indent=2) + "\n", encoding="utf-8")
        self.path = path
        missing = self.missing()
        self.notice = f"saved {path}" + (f"; not finished: {'; '.join(missing)}" if missing else "")

    def _on_compile(self, m: Dict[str, Any]) -> None:
        path = m.get("path")
        if not path:
            if not self.path:
                raise EditorError("compile needs a path for the notebook, or save the graph first")
            path = re.sub(r"(\.graph)?\.json$", "", self.path) + ".ipynb"
        title = Path(self.path).name if self.path else None
        written = write_notebook(self.doc, path, title)
        self.compiled = str(written)
        self.notice = f"compiled to {written} ({len(self.doc['nodes'])} nodes)"

    def _on_run(self, _m: Dict[str, Any]) -> None:
        missing = self.missing()
        if missing:
            raise EditorError(f"the graph is not finished: {'; '.join(missing)}")
        self._after_run(self.runner.start(self.document()))

    def _on_poll(self, _m: Dict[str, Any]) -> None:
        if self.runner.report is None:
            return
        self._after_run(self.runner.advance())

    def _after_run(self, report: Any) -> None:
        failed = report.failed()
        if failed is not None:
            self.error = f"{failed.node}: {failed.error}"
        elif report.done:
            ran = report.ran()
            self.notice = f"ran {', '.join(ran)}" if ran else "nothing to run: every node is fresh"
        else:
            self.notice = f"waiting on {', '.join(self.runner.waiting)}"

    # --- what the view draws -------------------------------------------------------

    def _statuses(self, finished: bool) -> Dict[str, Dict[str, Any]]:
        """Each node's run status: fresh, stale, running or failed (with the reason)."""
        report = self.runner.report
        stale = set(self.runner.stale(self.doc)) if finished else {n["id"] for n in self.doc["nodes"]}
        out = {}
        for node in self.doc["nodes"]:
            nid = node["id"]
            run = report.nodes.get(nid) if report is not None else None
            if nid in self.runner.waiting:
                out[nid] = {"status": "running", "where": run.where if run else None}
            elif run is not None and run.state == "failed" and nid in stale:
                out[nid] = {"status": "failed", "error": run.error}
            else:
                out[nid] = {"status": "stale" if nid in stale else "fresh"}
        return out

    def _values(self, nid: str) -> Optional[Dict[str, str]]:
        """The selected node's outputs as JSON text, shortened, when it is fresh."""
        try:
            values = self.runner.values(self.doc, nid)
        except (RunnerError, BlockTypeError):
            return None
        out = {}
        for name, value in values.items():
            text = json.dumps(value)
            out[name] = text if len(text) <= 120 else text[:117] + "..."
        return out


    def missing(self) -> List[str]:
        """The required inputs not given yet, one line per node."""
        out = []
        for node in self.doc["nodes"]:
            block = get_block(node["block"])
            given = node.get("inputs", {})
            need = [p.name for p in block.inputs if p.required and given.get(p.name) is None]
            if need:
                out.append(f"{node['id']} needs {', '.join(need)}")
        return out

    def _feedable(self, t: ValueType) -> bool:
        """Whether some block's output can feed ``t``; a JSON input, which takes anything, counts only when given."""
        if (t.inner if isinstance(t, Optional_) else t).name == "json":
            return False
        return any(_accepts(t, p.type) for outputs in self._output_types for p in outputs)

    def palette(self) -> List[Dict[str, Any]]:
        """The blocks, grouped by kind."""
        blocks = catalogue()
        return [{"kind": kind, "blocks": [{"name": b["name"], "doc": b["doc"]} for b in blocks if b["kind"] == kind]}
                for kind in PALETTE_KINDS]

    def _targets(self, src: str, t: ValueType, ups: Dict[str, Set[str]]) -> List[str]:
        """The inputs an output of node ``src`` and type ``t`` can be wired into: a type that accepts it, no cycle.

        A wire into a node that already feeds ``src`` would close a cycle, so ``src`` and what feeds it are left out.
        """
        feeding, todo = {src}, [src]
        while todo:
            for u in ups.get(todo.pop(), ()):
                if u not in feeding:
                    feeding.add(u)
                    todo.append(u)
        out = []
        for node in self.doc["nodes"]:
            if node["id"] in feeding:
                continue
            for p in get_block(node["block"]).inputs:
                if _accepts(p.type, t):
                    out.append(f"{node['id']}.{p.name}")
        return out

    def state(self) -> Dict[str, Any]:
        """What the view draws, as JSON."""
        ups = self._upstream(self.doc)
        kinds = {b["name"]: b for b in catalogue()}
        nodes, wires = [], []
        for node in self.doc["nodes"]:
            block = get_block(node["block"])
            given = node.get("inputs", {})
            inputs = []
            for p in block.inputs:
                value = given.get(p.name)
                wired = [w["from"] for w in wires_of(value)] if value is not None else []
                for k, w in enumerate(wired):
                    wires.append({"from": w, "to": f"{node['id']}.{p.name}",
                                  "index": k if isinstance(value, list) else None})
                described = p.describe()
                inputs.append({**described, "value": None if wired else value, "wired": wired,
                               "list": isinstance(p.type, ListOf),
                               "shown": bool(wired) or value is not None or p.required or self._feedable(p.type)})
            outputs = [{**p.describe(), "targets": self._targets(node["id"], p.type, ups)} for p in block.outputs]
            nodes.append({"id": node["id"], "block": block.name, "kind": block.kind, "doc": kinds[block.name]["doc"],
                          "origin": kinds[block.name].get("origin"), "at": node.get("at") or list(_ORIGIN),
                          "inputs": inputs, "outputs": outputs})
        missing = self.missing()
        order = None
        if not missing:
            try:
                order = check_graph(self.doc)
            except GraphError as e:                     # cannot happen after a draft check; said if it does
                missing = [str(e)]
        statuses = self._statuses(order is not None)
        for n in nodes:
            n.update(statuses[n["id"]])
        return {"nodes": nodes, "wires": wires, "palette": self.palette(), "notes": self.doc.get("notes", ""),
                "selected": self.selected, "missing": missing, "order": order, "error": self.error,
                "values": (self._values(self.selected) if self.selected and statuses.get(self.selected, {}).get(
                    "status") == "fresh" else None),
                "waiting": self.runner.waiting,
                "notice": self.notice, "path": self.path, "can_undo": bool(self._undo),
                "can_redo": bool(self._redo)}


__all__ = ["EditorError", "GraphEditor", "PALETTE_KINDS"]
