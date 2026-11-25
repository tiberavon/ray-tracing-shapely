"""
Python-specific package: graph
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
Graphs of blocks: a document, checked, and compiled to a notebook (KA10)
===============================================================================
`document` holds the graph document: nodes that name blocks, inputs given as
JSON or as wires from another node's output, checked by the blocks' own wire
rule. `compile` turns a document into the notebook that runs it, one cell
per node; nothing runs a graph by any other route. `runner` runs the compiled
cells, only the stale ones, keeping each node's result. `editor` is the
canvas's model, driven by JSON messages; `graph_editor` (``widget``, the ``widgets``
extra) its notebook view.

Built on `blocks`, and needs what it needs (the ``radiometry`` extra). The
core never imports this package.
===============================================================================
"""

from .compile import compile_graph, compile_script, node_source, write_notebook
from .document import (GRAPH_VERSION, SUPPORTED_VERSIONS, GraphError, check_graph, is_wire, load_graph, new_graph,
                       save_graph, wire_source, wires_of)
from .editor import EditorError, GraphEditor
from .runner import GraphRunner, RunnerError, RunReport

__all__ = ["EditorError", "GRAPH_VERSION", "GraphEditor", "GraphError", "GraphRunner", "RunReport", "RunnerError",
           "SUPPORTED_VERSIONS", "check_graph", "compile_graph", "compile_script", "graph_editor", "is_wire",
           "load_graph", "new_graph", "node_source", "save_graph", "wire_source", "wires_of", "write_notebook"]


def __getattr__(name):
    if name == "graph_editor":            # the view needs anywidget; the editor does not
        from .widget import graph_editor
        return graph_editor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
