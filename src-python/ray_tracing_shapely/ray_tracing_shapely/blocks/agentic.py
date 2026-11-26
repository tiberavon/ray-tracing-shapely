"""
Python-specific module: the construction tools an agent uses on blocks
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
PYTHON-SPECIFIC MODULE: agentic (blocks)
===============================================================================
Six tools, the same for every block, so a new recipe or a new block needs no
new tool (`KD12`: one tool per block would add a tool per recipe, forever):

    block_list(kind)              every block: its name, kind and one line
    block_describe(name)          one block's inputs and outputs: type, unit, default
    block_run(name, inputs)       run it; each output kept in the store as a handle
    block_value(ref, path)        a kept value's JSON form, or written to a file
    block_values()                the kept values: handle, type, what made it
    block_graph(path, refs)       the kept values written as a graph document

**Outputs are kept, and wired by handle.** `block_run` keeps each output in
this kernel's store under a handle (``"v3"``) and answers with a summary. An
input given as ``{"ref": "v3"}``, alone or inside a list, is that kept value,
checked by the wire rule (`wire_accepts`): a source entry of 600 rays never
travels through the agent, and a trace not saved to a folder can still feed
the next block. Every other input is JSON, parsed at the boundary (`KA9`).
The store is the blocks' own: the named contexts are not
switched.

**The store records each call** (the block, and its inputs as given, handles
included), so the agent's work reads back as a graph (`KA10`): a call is a
node, a ``{"ref": ...}`` a wire, every other input a literal. `block_graph`
writes it as a graph document, which the person opens on the graph canvas or
compiles to the notebook that runs the same calls (`C-GRAPH-02`). There is no
tool to add a node or a wire: `block_run` is how an agent builds.

Added to the core's tool lists by `register()`, called explicitly, never at
import (as the flows' tools are). Every tool answers ``{"status": "ok",
"data": ...}`` or ``{"status": "error", "message": ...}`` and never raises.
===============================================================================
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import Port, get_block, list_blocks
from .types import BlockTypeError, ListOf, Optional_, ValueType

#: The longest JSON form `block_run` and `block_value` put in a reply, in characters (`KA8`).
MAX_INLINE = 4000

_STORE: Dict[str, Dict[str, Any]] = {}
_COUNTER = [0]
#: Each successful block_run: its block, its inputs as given, and its outputs' handles, by call id.
_CALLS: Dict[str, Dict[str, Any]] = {}


def _ok(data: Any) -> Dict[str, Any]:
    return {"status": "ok", "data": data}


def _error(message: str) -> Dict[str, str]:
    return {"status": "error", "message": message}


def _is_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"ref"} and isinstance(value["ref"], str)


def _resolve(port: Port, value: Any, where: str) -> Any:
    """A port's live value: kept values by handle (wire-checked), the rest parsed."""

    def go(t: ValueType, v: Any, at: str) -> Any:
        if _is_ref(v):
            kept = _STORE.get(v["ref"])
            if kept is None:
                raise BlockTypeError(f"{at}: no kept value {v['ref']!r}; block_values lists them")
            if not t.accepts(kept["type"]):
                raise BlockTypeError(f"{at}: {v['ref']} is a {kept['type'].describe()}, which cannot feed "
                                     f"{t.describe()}")
            return kept["live"]
        if isinstance(t, Optional_) and v is not None:
            return go(t.inner, v, at)
        if isinstance(t, ListOf) and isinstance(v, list) and any(_has_ref(x) for x in v):
            return [go(t.inner, x, f"{at}[{i}]") for i, x in enumerate(v)]
        return t.parse(v, at)

    return go(port.type, value, where)


def _has_ref(value: Any) -> bool:
    if _is_ref(value):
        return True
    if isinstance(value, list):
        return any(_has_ref(v) for v in value)
    return False


def _json_form(t: ValueType, live: Any) -> Any:
    """The value's JSON form, or None when it has none (an unsaved trace)."""
    try:
        return t.format(live)
    except BlockTypeError:
        return None


def _summary(t: ValueType, live: Any) -> Dict[str, Any]:
    """What a value is, in a few lines: enough to choose the next block."""
    from .types import Trace  # noqa: PLC0415
    name = t.describe().get("type")
    if isinstance(live, Trace):
        return {"detectors": {d: {k: r.get(k) for k in ("power", "share", "hits")} for d, r in live.readings.items()},
                "folder": None if live.folder is None else str(live.folder)}
    if name == "scene":
        return {"objects": [{"name": getattr(o, "name", None), "type": type(o).__name__} for o in live.objs]}
    if name == "scene_entry":
        obj = live.get("object") or {}
        out = {"name": live.get("name"), "type": obj.get("type") or live.get("recipe")}
        if "rays" in obj:
            out["rays"] = len(obj["rays"])
        return out
    if name == "rayfile_slice":
        return {"rays_kept": int(len(live.flux)), "kept_share_of_flux": 1.0 - live.skew_share,
                "max_offset_mm": live.max_offset_mm, "flux_unit": live.flux_unit}
    return {}


def _keep(t: ValueType, live: Any, made_by: str, call: str, port: str) -> Dict[str, Any]:
    _COUNTER[0] += 1
    ref = f"v{_COUNTER[0]}"
    _STORE[ref] = {"type": t, "live": live, "made_by": made_by, "call": call, "port": port}
    _CALLS[call]["outputs"][port] = ref
    out: Dict[str, Any] = {"ref": ref, "type": t.describe()}
    form = _json_form(t, live)
    text = None if form is None else json.dumps(form)
    summary = _summary(t, live)
    if text is not None and len(text) <= MAX_INLINE:
        out["value"] = form
        if summary:
            out["summary"] = summary
    else:
        out["summary"] = summary
        out["note"] = ("no JSON form (a trace not saved: give the trace block runs_dir)" if form is None
                       else f"its JSON form is {len(text)} characters: block_value({ref!r}) gives it")
    return out


def block_list(kind: Optional[str] = None) -> Dict[str, Any]:
    """Every block (or those of one kind: function, recipe, primitive), each with its kind and one line."""
    try:
        names = list_blocks(kind)
    except Exception as e:  # noqa: BLE001 -- the answer shape, not an exception
        return _error(f"could not list blocks: {type(e).__name__}: {e}")
    if kind is not None and not names:
        return _error(f"no block of kind {kind!r}; kinds: function, recipe, primitive")
    return _ok({"blocks": [{"name": n, "kind": get_block(n).kind, "doc": get_block(n).doc} for n in names]})


def block_describe(name: str) -> Dict[str, Any]:
    """One block's inputs and outputs: each one's type (a quantity's unit), whether required, its default."""
    try:
        return _ok(get_block(name).describe())
    except Exception as e:  # noqa: BLE001
        return _error(str(e))


def block_run(name: str, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run a block; keep each output under a handle and answer with it."""
    try:
        b = get_block(name)
    except Exception as e:  # noqa: BLE001
        return _error(str(e))
    if inputs is not None and not isinstance(inputs, dict):
        return _error(f"{name}: inputs must be an object of input name -> value, got {type(inputs).__name__}")
    try:
        live = b._inputs(dict(inputs or {}), _resolve)
        outputs = b.call(live)
    except BlockTypeError as e:
        return _error(str(e))
    except Exception as e:  # noqa: BLE001 -- a block's own failure, reported
        return _error(f"{name} failed: {type(e).__name__}: {e}")
    made_by = f"{name}({', '.join(sorted(inputs or {}))})"
    call = f"c{len(_CALLS) + 1}"
    _CALLS[call] = {"block": name, "inputs": copy.deepcopy(dict(inputs or {})), "outputs": {}}
    return _ok({"outputs": {p.name: (None if outputs.get(p.name) is None
                                     else _keep(p.type, outputs[p.name], made_by, call, p.name))
                            for p in b.outputs}})


def block_value(ref: str, path: Optional[str] = None) -> Dict[str, Any]:
    """A kept value's JSON form; with ``path``, written there as JSON instead (a scene: a scene file)."""
    kept = _STORE.get(ref)
    if kept is None:
        return _error(f"no kept value {ref!r}; block_values lists them")
    form = _json_form(kept["type"], kept["live"])
    if form is None:
        return _error(f"{ref} has no JSON form (a trace not saved to a folder: run trace again with runs_dir)")
    if path is not None:
        try:
            target = Path(path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(form, indent=2), encoding="utf-8")
        except OSError as e:
            return _error(f"could not write {path}: {e}")
        return _ok({"ref": ref, "written": str(target.resolve())})
    text = json.dumps(form)
    if len(text) > MAX_INLINE:
        return _ok({"ref": ref, "truncated": True, "characters": len(text), "summary": _summary(kept["type"], kept["live"]),
                    "note": "too long for a reply: give path to write it to a file"})
    return _ok({"ref": ref, "type": kept["type"].describe(), "value": form})


def block_values() -> Dict[str, Any]:
    """The values kept in this kernel: handle, type, and the block that made each."""
    return _ok({"values": [{"ref": r, "type": v["type"].describe(), "made_by": v["made_by"]}
                           for r, v in _STORE.items()]})


def _refs_in(value: Any) -> List[str]:
    if _is_ref(value):
        return [value["ref"]]
    if isinstance(value, list):
        return [r for v in value for r in _refs_in(v)]
    return []


def _calls_for(refs: List[str]) -> List[str]:
    """The calls that made ``refs`` and everything they were made from, in the order they ran."""
    wanted, todo = set(), [_STORE[r]["call"] for r in refs]
    while todo:
        call = todo.pop()
        if call in wanted:
            continue
        wanted.add(call)
        for value in _CALLS[call]["inputs"].values():
            todo.extend(_STORE[r]["call"] for r in _refs_in(value) if r in _STORE)
    return [c for c in _CALLS if c in wanted]


def graph_of_values(refs: Optional[List[str]] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """The kept values as a graph document: each call a node, each handle a wire, the rest literals.

    Args:
        refs: Only these values and the calls they were made from; every call if not given.
        notes: The document's notes; a line saying where it came from if not given.

    Returns:
        ``{"doc": <graph document>, "values": {handle: "<node>.<output>"}}``. The document is not
        checked here; `block_graph` checks it.

    Raises:
        BlockTypeError: If nothing is kept, or a handle is unknown.
    """
    from ..graph.document import GRAPH_VERSION, free_id  # noqa: PLC0415 -- graph builds on blocks

    if not _CALLS:
        raise BlockTypeError("nothing is kept yet: block_run keeps the values a graph is written from")
    for r in refs or []:
        if r not in _STORE:
            raise BlockTypeError(f"no kept value {r!r}; block_values lists them")
    calls = _calls_for(list(refs)) if refs else list(_CALLS)
    node_of: Dict[str, str] = {}
    for call in calls:
        given = _CALLS[call]["inputs"].get("name")
        node_of[call] = free_id(given if isinstance(given, str) and given else _CALLS[call]["block"],
                                node_of.values())

    def wire(value: Any) -> Any:
        if _is_ref(value):
            kept = _STORE[value["ref"]]
            return {"from": f"{node_of[kept['call']]}.{kept['port']}"}
        if isinstance(value, list) and _has_ref(value):
            return [wire(v) for v in value]
        return copy.deepcopy(value)

    nodes = [{"id": node_of[c], "block": _CALLS[c]["block"],
              "inputs": {k: wire(v) for k, v in _CALLS[c]["inputs"].items()}} for c in calls]
    values = {ref: f"{node_of[c]}.{port}" for c in calls for port, ref in _CALLS[c]["outputs"].items()}
    if notes is None:
        notes = f"Written by block_graph from {len(calls)} block_run call(s) kept in the kernel."
    return {"doc": {"graph_version": GRAPH_VERSION, "nodes": nodes, "notes": notes}, "values": values}


def block_graph(path: str, refs: Optional[List[str]] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """Write the kept values as a graph document (a ``.graph.json`` file), checked; answer with its nodes."""
    from ..graph.document import GraphError, save_graph  # noqa: PLC0415 -- graph builds on blocks

    if refs is not None and (not isinstance(refs, list) or not all(isinstance(r, str) for r in refs)):
        return _error(f"refs must be a list of handles such as [\"v9\"], got {refs!r}")
    try:
        made = graph_of_values(refs, notes)
    except BlockTypeError as e:
        return _error(str(e))
    try:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        save_graph(made["doc"], target)
    except GraphError as e:
        return _error(f"the kept calls do not make a graph: {e}")
    except OSError as e:
        return _error(f"could not write {path}: {e}")
    return _ok({"written": str(target.resolve()),
                "nodes": [{"id": n["id"], "block": n["block"]} for n in made["doc"]["nodes"]],
                "values": made["values"]})


def clear_values() -> None:
    """Forget every kept value and call (for a new session or a test); not a tool."""
    _STORE.clear()
    _CALLS.clear()
    _COUNTER[0] = 0


_NAME = {"type": "string", "description": "The block's name, as block_list gives it."}
_REF = {"type": "string", "description": "A kept value's handle, as block_run gives it (e.g. \"v3\")."}

TOOLS: List[Any] = [
    (block_list, "List the blocks: typed calls that build a design and analyse it. Kinds: 'recipe' (a designed "
                 "element: collimator, concentrator, lens, from its requirements), 'primitive' (a scene object: "
                 "a detector, a mirror, a source), 'function' (the steps between: slice a rayfile, make a source, "
                 "assemble a scene, trace, read a detector, irradiance, IEC 62471 classification). Start here to "
                 "build a scene; block_describe gives a block's inputs.",
     {"type": "object", "properties": {"kind": {"type": "string", "enum": ["function", "recipe", "primitive"],
                                                "description": "Only blocks of this kind."}}, "required": []}),
    (block_describe, "One block's inputs and outputs: each one's type ({'type': 'quantity', 'unit': 'mm'} is a "
                     "quantity given as text with its unit, e.g. \"7 mm\"; a position is [x, y] in mm; a direction "
                     "[dx, dy]), whether it is required, its default and what it means.",
     {"type": "object", "properties": {"name": _NAME}, "required": ["name"]}),
    (block_run, "Run a block. inputs maps input names to JSON values: a quantity as text with its unit "
                "(\"25 mm\", \"0.5 W/m\"; a bare number is refused); or {\"ref\": \"v3\"} for a value an earlier "
                "block_run kept, also inside a list ([{\"ref\": \"v1\"}, {\"ref\": \"v2\"}]). Each output is kept "
                "under a new handle; the reply gives the handle and the value, or a summary when it is long. "
                "Wire outputs to inputs by handle: a ref of the wrong type is refused with the reason. A refused "
                "input names the input and what it expects.",
     {"type": "object", "properties": {"name": _NAME,
                                       "inputs": {"type": "object", "description": "Input name -> JSON value or "
                                                                                   "{\"ref\": handle}."}},
      "required": ["name"]}),
    (block_value, "A kept value's full JSON form (a scene as a scene file's content, a reading, a classification "
                  "with its limits). With path, write it there as JSON instead: a scene written so is a scene "
                  "file the scene builder and a parameter study open.",
     {"type": "object", "properties": {"ref": _REF,
                                       "path": {"type": "string", "description": "A file to write it to."}},
      "required": ["ref"]}),
    (block_values, "List the values block_run has kept in this kernel: handle, type and the block that made each.",
     {"type": "object", "properties": {}, "required": []}),
    (block_graph, "Write your work as a graph document (a .graph.json file) to hand to the person: each "
                  "block_run that kept a value is a node, each {\"ref\": ...} input a wire, every other input "
                  "as you gave it. They open it on the graph canvas to see and edit it, or compile it to the "
                  "notebook that reruns the same calls. With refs, only those values and the calls they were "
                  "made from (leave out runs you tried and dropped); without, every call. A node is named "
                  "after the object's name input, or its block. Give file paths in inputs as absolute paths "
                  "if the graph is opened elsewhere. Answers with the nodes and which node.output each handle "
                  "became.",
     {"type": "object", "properties": {
         "path": {"type": "string", "description": "The file to write, e.g. \"design.graph.json\"."},
         "refs": {"type": "array", "items": _REF,
                  "description": "Only these values and what they were made from."},
         "notes": {"type": "string", "description": "What the graph is, shown with it."}},
      "required": ["path"]}),
]


def register() -> bool:
    """Add the six block tools to the core's tool lists, once. Call before the MCP server starts.

    Returns:
        True if they were added now, False if they already were.

    Raises:
        RuntimeError: If the MCP server is already running (`register_tool`).
    """
    from ..analysis.tool_registry import get_agentic_tools, register_tool  # noqa: PLC0415

    present = {t["name"] for t in get_agentic_tools()}
    if all(fn.__name__ in present for fn, _, _ in TOOLS):
        return False
    for fn, description, schema in TOOLS:
        if fn.__name__ not in present:
            register_tool(fn, description, schema, module="ray_tracing_shapely.blocks.agentic")
    return True


__all__ = ["MAX_INLINE", "TOOLS", "block_describe", "block_graph", "block_list", "block_run", "block_value",
           "block_values", "clear_values", "graph_of_values", "register"]
