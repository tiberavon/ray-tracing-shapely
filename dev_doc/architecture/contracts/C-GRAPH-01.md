---
id: C-GRAPH-01
title: A graph document carries its version, and one this library does not read is refused, not read as the current one
parties:
  provides: whoever writes a graph document (the canvas, an agent, a person by hand)
  relies:   graph (document.py, compile.py), and the person whose graph would otherwise be misread
binds: graph (document.py)
port: null
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph.py::test_refusals_name_the_node_the_input_and_the_reason
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph.py::test_the_notebook_is_the_script_in_cells
tracked_by: null
conflicts_with: null
refines: null
rationale: KA10
since: 0.4
---

# C-GRAPH-01 — A graph says which version it is, or it is not read

The canvas, the library and a saved graph change at different times. This
promise is what stops a graph written for one meaning of its fields from
being read under another.

**Assumptions.** Whoever writes a document puts the version it was written
in, `graph_version`, at its top.

**Guarantees.** `check_graph` reads a document only when its
`graph_version` is in `SUPPORTED_VERSIONS`. Outside the range, or without
one, it is refused with both: *"the document is graph_version 2; this
library reads versions 1 to 1"*. The compiled notebook records the version
it was compiled from in its metadata.

**Invariants.** A document without a version is refused, never read as the
current version.

**Units and frames.** Not applicable.

**If the assumption is violated.** Loud. A refusal is an answer the person
can act on. The silent alternative, reading a node whose inputs have changed
meaning, would compile to the wrong calls.

**Checked by.** `test_graph.py`: a document with no version and one of
version 2 are refused with the message; a compiled notebook carries version 1.
