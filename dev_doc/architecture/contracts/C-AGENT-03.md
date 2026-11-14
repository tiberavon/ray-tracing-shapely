---
id: C-AGENT-03
title: The 3D tools reach an assistant only when registered explicitly, read one 3D context kept in the core's registry, name every face as the event log does, and only read
parties:
  provides: optiland_nsq_run_registry (ray_tracing_shapely_optiland.agentic); agentic_layer (set_extension_context, register_tool)
  relies:   MCP clients / LLM agents asking about a 3D trace
port: P-AGENTIC-ENVELOPE
viewpoint: agentic
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_agentic_3d.py::test_describe_scene_names_faces_as_the_log_does; src-python/ray_tracing_shapely_optiland/tests/test_agentic_3d.py::test_path_spectrum_matches_a_direct_count; src-python/ray_tracing_shapely_optiland/tests/test_agentic_3d.py::test_query_is_read_only_and_capped; src-python/ray_tracing_shapely_optiland/tests/test_agentic_3d.py::test_a_persisted_log_is_read_only; src-python/ray_tracing_shapely_optiland/tests/test_agentic_3d.py::test_register_adds_the_five_tools_once
witness: src-python/ray_tracing_shapely_optiland/tests/test_agentic_3d.py::test_without_a_context_every_tool_says_what_to_call; src-python/ray_tracing_shapely_optiland/tests/test_compare_2d_3d.py::test_the_summary_tool
tracked_by: null
conflicts_with: null
refines: C-AGENT-02
rationale: KA5
since: 0.3
---

# C-AGENT-03 — An assistant can read a 3D trace, and only read it

**Assumptions.** The 3D package depends on the core, never the reverse. A
trace that the tools are to read was run with `record_paths`. Its solids
were built by the bridge, so each keeps its `profile`.

**Guarantees.**
- **Registered on request.** `ray_tracing_shapely_optiland.agentic.register()`
  adds five tools through `register_tool`, so they are in all three lists
  at once (`C-AGENT-02`). It is never called at import, and a second call
  adds nothing. One server publishes the 2D and 3D tools together.
- **One registry.** `set_nsq_context(scene, result)` keeps the scene, the
  result, the solids' profiles and the event-log database under one key,
  `optiland.nsq`, in the core's own context (`set_extension_context`).
  `set_comparison_context(comparison)` keeps a 2D-against-3D comparison
  (`C-BRIDGE-14`) under `optiland.compare`. The core's `clear_context`
  clears both and closes the database.
- **Names as the log has them.** `describe_nsq_scene` names each face
  `<solid>.<span label>`, as the event log does, with the span's role and
  mechanism from the profile and the kind of surface it became. A source
  added with `add_source_3d` is logged under its spec's name. A detector's
  hits are logged as `''`, which the tools report as the detector, by name
  when there is one.
- **Read only.**
  - `query_nsq` refuses anything but a SELECT, and caps rows at 200
    (`execute_query`, `C-NSQ-RUN-03`).
  - A persisted `nsq_events.sqlite` is opened read-only.
- **The path spectrum.** `nsq_path_spectrum` groups every ray by its
  source, the faces it met in order, and its end: the detector, escaped,
  or absorbed at its last face. Counts and shares are over all rays.
- **The comparison.** `compare_2d_3d_summary` returns the comparison's
  summary, never its per-ray table (`KA8`).
- **The answer shape.** Every tool answers `{"status": "ok", "data": ...}`
  or `{"status": "error", "message": ...}`; none raises (`C-AGENT-01`).
  Without a context, the message names the setter to call.

**Invariants.** The path spectrum's ray counts sum to the number of traced
rays and its shares to 1. Every face name that appears in a hit event is a
face `describe_nsq_scene` lists.

**Units and frames.** World millimetres, flux in watts, wavelength in
micrometres: the event log's own.

**If the assumption is violated.** Loud.
- **Not registered:** the tools are absent from the lists. That is the
  intent until the caller registers them.
- **Registered while the MCP server runs:** refused (`C-AGENT-02`).
- **A trace without a path log:** refused by `set_nsq_context`.
- **No context set:** every tool answers with an error that says what to
  call.

**Checked by.**
- **The trace.** A revolved singlet lit by a 35° cone that overfills it:
  - the faces are named with their roles and surface kinds;
  - every face in the log is one the scene description lists;
  - the main path's count equals a count made directly from the trace's
    event array, the spectrum's counts sum to the traced rays, and light
    that missed the lens is reported as escaped.
- **Read only.** `DELETE` is refused, row output is capped, and a
  persisted log is opened read-only.
- **Registration.** `register()` adds five tools once, and the three
  lists still agree.
- **The comparison's summary.** Without a comparison it names
  `set_comparison_context`; with one it lists at most `max_listed`
  differing rays, without the per-ray fields.
