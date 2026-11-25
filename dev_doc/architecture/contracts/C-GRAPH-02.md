---
id: C-GRAPH-02
title: A wire joins an output to an input that accepts it, and a compiled graph gives the result of the blocks run directly
parties:
  provides: whoever draws the graph (a person, an agent)
  relies:   graph (compile.py, editor.py, runner.py), and the person reading the result
binds: graph (document.py, compile.py, editor.py, runner.py)
port: null
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph.py::test_the_compiled_chain_equals_the_blocks_run_directly; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph.py::test_refusals_name_the_node_the_input_and_the_reason; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph.py::test_a_cycle_is_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph_editor.py::test_a_wrong_wire_is_refused_at_once_with_the_reason_and_changes_nothing; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph_editor.py::test_a_wire_that_closes_a_cycle_is_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph_runner.py::test_a_full_run_equals_the_compiled_script; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph_runner.py::test_after_an_edit_only_what_is_downstream_runs_and_equals_a_full_run; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph_runner.py::test_a_long_node_goes_to_an_executor_and_comes_back_equal; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_block_graph.py::test_the_agents_chain_as_a_graph_compiles_to_its_own_numbers
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph.py::test_the_wires_give_the_order; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph_editor.py::test_the_chain_drawn_by_messages_is_the_document_written_by_hand; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_graph_server.py::test_the_chain_runs_in_the_served_process_its_trace_in_a_worker
tracked_by: null
conflicts_with: null
refines: null
rationale: KA10
since: 0.4
---

# C-GRAPH-02 — A graph means exactly the calls it compiles to

**Assumptions.** Each wire names an output of another node, and the person or
agent drawing the graph chose which.

**Guarantees.**
- A wire is accepted only when the input's type accepts the output's
  (`ValueType.accepts`, the blocks' own rule). Otherwise the document is
  refused, naming the node, the input, the wire and both types.
- So is a document with an unknown block or input, a required input missing,
  a wire from no node or no output, a literal its type refuses, two nodes of
  one id, or a cycle.
- The compiled notebook, run, gives each node's outputs equal to the same
  blocks run directly from their inputs' JSON (`run_block`), exactly.
- On the canvas (`GraphEditor`), a wire, a literal or a rename is checked by
  the same rule as it is made, a required input not yet given excepted, and
  refused at once with the reason, the document left as it was. The targets
  the canvas lights up for an output are those the rule accepts, less the
  inputs that would close a cycle.
- The runner (`GraphRunner`) executes the compiled cells, and only the stale
  ones: after an edit, each node's outputs equal those of the edited graph's
  compiled script run whole. A node run by an executor gives outputs equal
  to the kernel's.
- An agent's kept values written as a graph (`block_graph`) compile to a
  notebook giving each of those values, exactly.

**Invariants.** The compiler adds no behaviour of its own: no default beyond
the block's, no conversion between types, no order beyond what the wires
imply (ties in document order). A literal is parsed by its type when the
notebook runs, as `run_block` parses it; a wired value is the source's live
output, passed as it is (`call_block`'s `wired`), its type having been checked
here.

**Units and frames.** A quantity is stored as text with its unit
(`C-UNITS-02`); a bare number is refused where a quantity goes.

**If the assumption is violated.** Loud: a wrong wire is refused when the
document is checked, before it compiles, not discovered when the run fails.

**Checked by.** `test_graph.py`: the example chain (rayfile to risk group)
as a document, compiled and executed, against the blocks run directly; each
refusal with its reason; a cycle through two nodes. `test_graph_editor.py`:
the chain drawn by the canvas's messages is the document written by hand;
wrong wires, a literal without its unit and a cycle refused at once, the
document unchanged. `test_graph_runner.py`: a full run, and runs after two
edits, against the compiled script; a long node in process and in a worker
process. `test_block_graph.py`: the chain built through `block_run`, written
by `block_graph` and compiled, against every value the agent kept.
`test_graph_server.py` (a witness): the chain run through the VS Code editor's
server, its trace in a worker process, every node fresh.

**Not covered.** A literal that names a file (a rayfile, a trace's folder) is
not opened when the document is checked, only when the notebook runs. An
input of the untyped `json` type accepts any wire, by the blocks' rule, so a
wrong wire into one is found only when the notebook runs (`KW-BLOCKS-03`).
The runner's staleness does not see a change in the library's own code; a
kept result then predates it until the store is dropped (`forget`).
