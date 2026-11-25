"""
Python-specific module: graph document
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
The graph document: blocks joined by wires, saved as JSON, checked when read
===============================================================================
A graph is a list of nodes. A node names a block, gives some of its inputs
as JSON, and has a place on the canvas:

    {"graph_version": 1,
     "nodes": [{"id": "slice", "block": "slice_rayfile",
                "inputs": {"rayfile": "led.tm25", "max_offset_mm": "0.5 mm", ...}},
               {"id": "led", "block": "source_from_slice",
                "inputs": {"slice": {"from": "slice.slice"}, "name": "led"}}]}

**A wire is an input**, ``{"from": "<node>.<output>"}``, also as an item of a
list (``assemble``'s ``entries``), whose items are then all wires. There is no list of wires apart from the
inputs, so the two cannot disagree.

`check_graph` reads a document as the compiler will, and refuses it with the
node, the input and the reason (C-GRAPH-02): an unknown block or input, a
wire from a node or output that does not exist, a wire whose type the input
does not accept (`ValueType.accepts`, the blocks' own rule), a literal its
type refuses, two nodes of one id, a cycle. A document without
``graph_version``, or of a version this library does not read, is refused,
not read as the current one (C-GRAPH-01). A literal that names a file is
not opened here: it is checked when the compiled notebook runs.
===============================================================================
"""

from __future__ import annotations

import copy
import json
import keyword
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Tuple, Union

from ..blocks import BlockTypeError, get_block
from ..blocks.types import ListOf, Optional_, ValueType, _FilePath

#: The version this library writes.
GRAPH_VERSION = 1
#: The versions this library reads.
SUPPORTED_VERSIONS = (1, 1)
#: Names a node may not take: the compiled notebook uses them.
RESERVED_IDS = frozenset({"call_block"})
#: Value types whose JSON form names a file or folder, opened only when the notebook runs.
_READS_FILES = frozenset({"rayfile_slice", "trace"})


class GraphError(ValueError):
    """A graph document refused, with the node, the input and the reason."""


def is_wire(value: Any) -> bool:
    """Whether an input value is a wire, ``{"from": "<node>.<output>"}``."""
    return isinstance(value, dict) and set(value) == {"from"} and isinstance(value["from"], str)


def wire_source(value: Dict[str, str]) -> Tuple[str, str]:
    """A wire's node and output."""
    node, _, output = value["from"].partition(".")
    return node, output


def wires_of(value: Any) -> Iterator[Dict[str, str]]:
    """The wires an input value holds: itself, or the items of a list."""
    if is_wire(value):
        yield value
    elif isinstance(value, list):
        for item in value:
            if is_wire(item):
                yield item


def free_id(name: str, taken: Iterable[str]) -> str:
    """A node id made from ``name`` (a block's name, or an object's), free among ``taken``.

    ``TIRCollimator`` gives ``tir_collimator``, ``"LED 1"`` gives ``led_1``; a second ``trace``
    gives ``trace_2``. Always a Python name, not a keyword or a reserved id.
    """
    base = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", str(name))      # TIRCollimator -> TIR_Collimator
    base = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", base).lower()
    base = re.sub(r"\W+", "_", base).strip("_") or "node"
    if base[0].isdigit():
        base = f"n_{base}"
    if keyword.iskeyword(base) or base in RESERVED_IDS:
        base = f"{base}_node"
    taken = set(taken)
    if base not in taken:
        return base
    k = 2
    while f"{base}_{k}" in taken:
        k += 1
    return f"{base}_{k}"


def _reads_files(t: ValueType) -> bool:
    while isinstance(t, (Optional_, ListOf)):
        t = t.inner
    return isinstance(t, _FilePath) or t.name in _READS_FILES


def _check_version(doc: Any) -> None:
    if not isinstance(doc, dict):
        raise GraphError(f"a graph document is a JSON object, got {type(doc).__name__}")
    version = doc.get("graph_version")
    low, high = SUPPORTED_VERSIONS
    if not isinstance(version, int) or isinstance(version, bool):
        raise GraphError(f"the document has no graph_version; this library reads versions {low} to {high}")
    if not low <= version <= high:
        raise GraphError(f"the document is graph_version {version}; this library reads versions {low} to {high}")


def _check_wire(nodes: Dict[str, Dict[str, Any]], where: str, wire: Dict[str, str], target: ValueType) -> str:
    """The wire's source node, after checking that it exists and that ``target`` accepts it."""
    node, output = wire_source(wire)
    if node not in nodes:
        raise GraphError(f"{where}: wire from {wire['from']!r}: no node {node!r}; "
                         f"nodes: {', '.join(nodes) or 'none'}")
    block = get_block(nodes[node]["block"])
    port = next((p for p in block.outputs if p.name == output), None)
    if port is None:
        raise GraphError(f"{where}: wire from {wire['from']!r}: {block.name} has no output {output!r}; "
                         f"outputs: {', '.join(p.name for p in block.outputs)}")
    if not target.accepts(port.type):
        raise GraphError(f"{where}: wire from {wire['from']!r}: {port.type!r} cannot feed {target!r}")
    return node


def _check_literal(where: str, value: Any, t: ValueType) -> None:
    if _reads_files(t):
        return
    try:
        t.parse(copy.deepcopy(value), where)
    except BlockTypeError as e:
        raise GraphError(str(e)) from None


def check_graph(doc: Dict[str, Any], complete: bool = True) -> List[str]:
    """Check a graph document; the order its nodes run in (the wires', ties in document order).

    With ``complete=False`` a required input not yet given is let pass: a graph
    being drawn is checked so, every other refusal the same (the editor's rule).

    Raises:
        GraphError: If anything in the document is refused, with the node, the
            input and the reason.
    """
    _check_version(doc)
    raw = doc.get("nodes")
    if not isinstance(raw, list):
        raise GraphError("the document's nodes must be a list")
    nodes: Dict[str, Dict[str, Any]] = {}
    for k, node in enumerate(raw):
        if not isinstance(node, dict):
            raise GraphError(f"nodes[{k}]: a node is an object, got {type(node).__name__}")
        nid = node.get("id")
        if not isinstance(nid, str) or not nid.isidentifier() or keyword.iskeyword(nid) or nid in RESERVED_IDS:
            raise GraphError(f"nodes[{k}]: id {nid!r} must be a Python name (it names the node's result "
                             f"in the compiled notebook), not a keyword or {', '.join(sorted(RESERVED_IDS))}")
        if nid in nodes:
            raise GraphError(f"nodes[{k}]: two nodes have the id {nid!r}")
        try:
            get_block(node.get("block"))
        except BlockTypeError as e:
            raise GraphError(f"{nid}: {e}") from None
        if not isinstance(node.get("inputs", {}), dict):
            raise GraphError(f"{nid}: inputs must be an object of input name -> value")
        nodes[nid] = node

    needs: Dict[str, List[str]] = {}
    for nid, node in nodes.items():
        block = get_block(node["block"])
        ports = {p.name: p for p in block.inputs}
        inputs = node.get("inputs", {})
        unknown = sorted(set(inputs) - set(ports))
        if unknown:
            raise GraphError(f"{nid}: {block.name} has no input {', '.join(map(repr, unknown))}; "
                             f"inputs: {', '.join(ports)}")
        upstream: List[str] = []
        for name, value in inputs.items():
            where, t = f"{nid}.{name}", ports[name].type
            if is_wire(value):
                upstream.append(_check_wire(nodes, where, value, t))
            elif isinstance(value, list) and any(is_wire(v) for v in value):
                inner = t.inner if isinstance(t, ListOf) else None
                if inner is None:
                    raise GraphError(f"{where}: a list of wires goes into a list input; this one is {t!r}")
                if not all(is_wire(v) for v in value):
                    raise GraphError(f"{where}: a list is all wires or all literals; this one mixes them")
                for i, item in enumerate(value):
                    upstream.append(_check_wire(nodes, f"{where}[{i}]", item, inner))
            elif value is not None:
                _check_literal(where, value, t)
        missing = [p.name for p in block.inputs if p.required and inputs.get(p.name) is None]
        if missing and complete:
            raise GraphError(f"{nid}: {block.name} needs {', '.join(map(repr, missing))}")
        needs[nid] = upstream

    order: List[str] = []
    done: set = set()
    while len(order) < len(nodes):
        ready = [n for n in nodes if n not in done and all(u in done for u in needs[n])]
        if not ready:
            stuck = [n for n in nodes if n not in done]
            raise GraphError(f"the wires make a cycle through {', '.join(stuck)}")
        order.append(ready[0])
        done.add(ready[0])
    return order


def new_graph(notes: str = "") -> Dict[str, Any]:
    """An empty graph document of the current version."""
    return {"graph_version": GRAPH_VERSION, "nodes": [], "notes": notes}


def load_graph(path: Union[str, Path]) -> Dict[str, Any]:
    """A graph document read from a file, and checked."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    check_graph(doc)
    return doc


def save_graph(doc: Dict[str, Any], path: Union[str, Path]) -> Path:
    """Write a graph document, after checking it; the path written."""
    check_graph(doc)
    target = Path(path)
    target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return target


__all__ = ["GRAPH_VERSION", "GraphError", "SUPPORTED_VERSIONS", "check_graph", "free_id", "is_wire", "load_graph",
           "new_graph", "save_graph", "wire_source", "wires_of"]
