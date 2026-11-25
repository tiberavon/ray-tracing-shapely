"""
Python-specific module: graph compiler
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
The compiler: a graph document to the notebook that runs it (KA10)
===============================================================================
Nothing runs a graph but its compiled notebook. Each node is one code cell,
in the order the wires imply, and each cell is one `call_block` naming its
result after the node:

    # led: source_from_slice (ray_tracing_shapely.blocks.chain:source_from_slice)
    led = call_block('source_from_slice', {
        'name': 'led',
    }, wired={
        'slice': slice['slice'],
    })

A literal is written as the Python value of its JSON and parsed by its type,
as `run_block` parses it. A wire becomes the source node's live output,
``slice['slice']``, passed in ``wired`` as it is, since its type was checked
when the graph was. The compiler adds nothing of its
own (C-GRAPH-02): no default (an input not given takes the block's), no
conversion, no order beyond the wires'. A path in the document resolves
where the notebook runs.
===============================================================================
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..blocks import get_block
from .document import GRAPH_VERSION, check_graph, is_wire, wire_source, wires_of


def _source(value: Any) -> str:
    """A JSON input value as Python source; a wire as its node's output."""
    if is_wire(value):
        node, output = wire_source(value)
        return f"{node}[{output!r}]"
    if isinstance(value, list) and any(is_wire(v) for v in value):
        return "[" + ", ".join(_source(v) for v in value) + "]"
    return repr(value)


def node_source(node: Dict[str, Any]) -> str:
    """One node's cell: a comment naming the block and the call it makes, and the call.

    Literal inputs go as their JSON; wired ones as the source node's live
    output, in ``wired`` (`call_block`).
    """
    block = get_block(node["block"])
    where = f" ({block.origin})" if block.origin else ""
    inputs = node.get("inputs") or {}
    literal = {k: v for k, v in inputs.items() if not any(True for _ in wires_of(v))}
    wired = {k: v for k, v in inputs.items() if k not in literal}

    def _dict(items: Dict[str, Any]) -> List[str]:
        return [f"    {name!r}: {_source(value)}," for name, value in items.items()]
    lines = [f"# {node['id']}: {block.name}{where}"]
    head = f"{node['id']} = call_block({block.name!r}, "
    if not wired:
        lines += [head + "{}" + ")"] if not literal else [head + "{", *_dict(literal), "})"]
    else:
        lines += [head + "{", *_dict(literal), "}, wired={", *_dict(wired), "})"]
    return "\n".join(lines)


def compile_script(doc: Dict[str, Any]) -> str:
    """The graph as a Python script: the import, then each node's call in run order."""
    order = check_graph(doc)
    nodes = {n["id"]: n for n in doc["nodes"]}
    parts = ["from ray_tracing_shapely.blocks import call_block"] + [node_source(nodes[n]) for n in order]
    return "\n\n".join(parts) + "\n"


def _cell(kind: str, cell_id: str, text: str) -> Dict[str, Any]:
    cell: Dict[str, Any] = {"cell_type": kind, "id": cell_id, "metadata": {}, "source": text.splitlines(True)}
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
    return cell


def compile_graph(doc: Dict[str, Any], title: Optional[str] = None) -> Dict[str, Any]:
    """The graph as a notebook (nbformat 4 JSON): a note, the import, one cell per node in run order.

    Raises:
        GraphError: If the document is refused (`check_graph`).
    """
    order = check_graph(doc)
    nodes = {n["id"]: n for n in doc["nodes"]}
    head = f"# {title or 'A compiled graph'}\n\n"
    if doc.get("notes"):
        head += f"{doc['notes']}\n\n"
    head += ("Compiled from a graph document: one cell per block, in the order its wires imply. "
             "Each cell's result is named after its node; an input not given takes the block's default.")
    cells: List[Dict[str, Any]] = [_cell("markdown", "graph-note", head),
                                   _cell("code", "graph-import", "from ray_tracing_shapely.blocks import call_block")]
    cells += [_cell("code", f"node-{n}", node_source(nodes[n])) for n in order]
    return {"cells": cells,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python"},
                         "ray_tracing_shapely": {"graph_version": GRAPH_VERSION}},
            "nbformat": 4, "nbformat_minor": 5}


def write_notebook(doc: Dict[str, Any], path: Any, title: Optional[str] = None) -> Path:
    """Compile a graph and write the notebook; the path written."""
    target = Path(path)
    target.write_text(json.dumps(compile_graph(doc, title), indent=1) + "\n", encoding="utf-8")
    return target


__all__ = ["compile_graph", "compile_script", "node_source", "write_notebook"]
