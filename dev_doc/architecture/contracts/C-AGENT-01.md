---
id: C-AGENT-01
title: The agentic envelope
parties:
  provides: agentic_layer (agentic_tools.py)
  relies:   MCP clients / LLM agents
port: [P-AGENTIC-ENVELOPE, P-KERNEL-CONTEXT]
viewpoint: agentic
status: documented
failure_mode: loud
checked_by: >-
  src-python/ray_tracing_shapely/developer_tests/test_phase2_schemas_and_lineage.py::test_fresnel_ill_typed_args,
  ::test_rank_paths_ill_typed_top_n
witness: src-python/ray_tracing_shapely/developer_tests/test_bidirectional.py::test_bidirectional_tool_no_detector
tracked_by: null
conflicts_with: null
refines: null
rationale: KA4
since: 0.1
---

# C-AGENT-01 — Every tool answers; none of them crashes

A promise about what an AI assistant sees when it calls a tool and
something goes wrong. It sees a message. It never sees the program fall
over.

**Assumptions.** The caller is an AI assistant or a program acting for one.
It cannot read the source code, may pass the wrong kind of value, and
treats a crash as the end of the conversation rather than as information.

**Guarantees.** Every tool returns a small record: either
`{"status": "ok", "data": ...}` or `{"status": "error", "message": ...}`.
An error is an answer, written so the assistant can act on it — *"no
object named 'entrance prism'; named objects are: ..."*.

Two tools once broke this: given a value of the wrong type, each crashed
with an error the tool's own safety net did not catch, because the net had
been written for a different kind of mistake. Both were found by calling
them with bad values on purpose, both are fixed, and both have a test that
repeats the bad call. The same net has not been checked tool by tool across
the other twenty or so; several have the same narrow shape. A test that
throws random bad values at every tool and confirms each still answers with
a `status` is the known gap.

**Invariants.** The `_ok` and `_error` helpers are the only way a tool
builds its answer. Records built by hand drift from the shape over time.

**Units and frames.** Not applicable.

**If the assumption is violated.** Loud, on our side: a crash inside a
tool is a bug in the tool. The unusual thing about this promise is who is
doing the checking. Everywhere else, the caller is trusted to pass what was
asked for. Here the caller cannot be, so all of the checking sits with the
tool. That is a deliberate exception, and this contract is where it is
written down.

**Checked by.** Regression tests for the two tools that were fixed. No
general test yet.
