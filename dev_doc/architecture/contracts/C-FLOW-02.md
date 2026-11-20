---
id: C-FLOW-02
title: Every box that asks has one question as data and one trigger, so one verb answers any flow; a refused answer leaves the flow where it was, with its reason and an example; a send-back is stated; nine generic tools drive every flow with JSON only
parties:
  provides: flows (fields.FlowField, flow_base.ObservableFlow.answer, kinds, agentic); the flows with FIELDS (RayfileSlicingFlow, IEC62471IntakeFlow, IEC60825_1IntakeFlow)
  relies:   an agent, through flow_kinds, flow_start, flow_question, flow_answer, flow_reset, flow_result; a person or notebook through answer()
port: P-AGENTIC-ENVELOPE
viewpoint: agentic
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_tools.py::test_every_asking_box_has_a_field_and_one_trigger; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_tools.py::test_answer_refuses_shapes_and_checks_and_keeps_the_flow_in_place; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_tools.py::test_the_generic_tools_drive_the_slicing_flow; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_tools.py::test_the_mcp_server_publishes_the_nine_tools_and_drives_the_flow
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_tools.py::test_a_field_shapes_answers_and_reads_as_json; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_tools.py::test_a_hazard_value_asks_in_the_unit_alpha_implies
tracked_by: null
conflicts_with: null
refines: C-FLOW-01
rationale: KD10
since: 0.3
---

# C-FLOW-02 — One verb answers any flow

**Assumptions.** A flow lists its asking boxes in `FIELDS`, by state, in the
order the diagram asks them. Each such box has exactly one `provide_*`
trigger, whose `before` check raises `ValueError` or `TypeError` to refuse.

**Guarantees.**
- **Questions as data.** `pending_field()` is the current box's `FlowField`:
  - name, kind and what that kind accepts;
  - the unit, for a quantity;
  - the default, or none;
  - the question, why it is asked, and an example.

  A field may be refined per run (`flow_field`): an IEC 62471 hazard's value
  is asked in the unit `alpha_rad` implies, and the slicing flow's choice
  names its table's limits in its example.
- **What a question is answered from.** `question_context()` is the data a
  question needs, as JSON, or None: the slicing flow's choice carries its
  table there.
- **One verb.**
  - `answer(value)` shapes the value for its kind and fires the box's own
    trigger, found from the machine;
  - `answer_default()` answers with the default, and is refused for a
    question that has none.

  Each returns `accepted` and the run's `question_state`: state, question,
  context, explanation, last refusal, job, attempt.
- **A refusal moves nothing.** An answer of the wrong shape, or one the
  box's check refuses, leaves the flow in the same box. It is recorded as an
  event (`refused`, `reason`) and as `last_refusal`, and the box's
  explanation says why. Every refusal's reason ends with the field's
  example, so the reason alone says what would be accepted. An error raised
  after the flow has moved on is a failure of that step: the run ends
  `failed` (`C-FLOW-01`).
- **A send-back is stated.** A check that sends the flow back, to the same
  question or an earlier one, follows an accepted answer: the flow did move.
  The reply carries `sent_back`, `{from, to, reason}`, and the run records it
  as an event (`sent_back`, `to`, `reason`). The reason is the flow's own
  (`send_back_reason`), or else the box's explanation.
- **Kinds.** A flow class registered as a kind (`register_flow_kind`, by
  import path) is started by name with nothing but a folder. The core
  registers `rayfile_slicing`, `iec62471_intake` and `iec60825_1_intake`;
  the satellite's `agentic.register()` adds `compare_2d_3d` (`C-BRIDGE-15`)
  and `compare_slice_3d` (`C-BRIDGE-16`).
- **Nine generic tools.** Every tool answers `{"status": "ok", "data": ...}`
  or `{"status": "error", "message": ...}`, never raises, and needs no
  knowledge of a flow's methods:
  - `flow_kinds`, `flow_start`, `flow_question`, `flow_answer`, `flow_reset`,
    `flow_result`;
  - `flow_list`, `flow_wait`, `flow_cancel` (`C-FLOW-01`).

  `flow_result` lists at most 40 of the last attempt's events (`KA8`). The
  tools are added by an explicit `register()`, never at import.

**Invariants.** For a flow with `FIELDS`, the asking boxes of its diagram and
the keys of `FIELDS` are the same set, in the same order. A run driven by
`answer` reaches the same result as one driven by its `provide_*` methods
with the same answers.

**Units and frames.** As each flow's own: a quantity is a string with its
unit, a bare number is refused.

**If the assumption is violated.** Loud. A box with no trigger, or more than
one, raises when answered. An answer while nothing is asked, or while a job
runs, is refused with that reason.

**Checked by.**
- **Structure.** In each of the three kinds, every asking box has a field
  and exactly one trigger, in the diagram's order.
- **Refusals.** In the slicing flow:
  - a number for a path, a bare number for a length, a missing answer and
    no default are each refused in place, with the reason recorded and
    ending with the field's example;
  - a rayfile that cannot be read, and a footprint the rays do not fit, each
    send the flow back with `sent_back` and an event saying why;
  - driving it by `answer` gives the same table as its methods.
- **The tools.** The slicing flow is driven from start to table, with one
  refusal and one reset, with JSON only: once by calling the tools, and
  once through the MCP server's own `call_tool`, after `register()` added
  the nine tools to a freshly built server.
