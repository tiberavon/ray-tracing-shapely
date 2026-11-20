---
id: C-AGENT-04
title: The tools read the active context only; making a context never switches to it, and clearing one closes only its own databases
parties:
  provides: 'whoever fills a context: a notebook, a load, a re-simulation, a package outside the core (set_context, set_extension_context)'
  relies:   every agentic tool that reads the store; the assistant comparing two runs
binds: agentic_layer (agentic_tools.py)
port: P-KERNEL-CONTEXT
viewpoint: agentic
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_context_registry.py::test_a_named_context_is_made_without_switching_to_it; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_context_registry.py::test_switching_changes_what_the_tools_read; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_context_registry.py::test_clearing_one_context_closes_its_database_and_leaves_the_others; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_context_registry.py::test_an_extension_keeps_its_objects_in_each_context; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_targeted_resimulation_flow.py::test_two_runs_of_one_scene_keep_their_own_detector_hits; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_saved_runs_in_context.py::test_only_a_saved_inactive_context_is_dropped_and_it_reloads
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KA5
since: 0.2
---

# C-AGENT-04 — Several runs held at once, and the tools always say which

The store of live objects holds named contexts, each with its own scene,
rays, lineage, database and the objects packages outside the core keep
there (the 3D bridge's trace). One of them is active, and every tool reads
that one.

**Assumptions.** Whoever fills a context names it when it is not meant to
replace what the tools are reading: `set_context_from_result(...,
context_name=...)`, `set_extension_context(..., context_name=...)`. A setter
given no name writes into the active context.

**Guarantees.**
- **Making a context never switches to it.** A new named context leaves the
  active one, and every answer about it, as they were.
- **Only `set_active_context` changes what the tools read.** An unknown
  name is an error that lists the names that exist, and the active context
  stays as it was.
- **`list_contexts` says what is loaded**: each context's name, origin,
  segment count, whether it holds a bidirectional result, the packages
  with objects in it, and which one is active.
- **Clearing one context closes its own databases**, the core's and every
  package's, and leaves the others open. If it was active, the default
  context becomes active. `clear_context()` with no name clears them all.
- **An agent drops only what can come back.** `drop_context`, the tool,
  drops one context, and only one that is saved as a run bundle (its
  `run_dir`, on disk) and is not the active one; `load_run_context` reloads
  it from the folder it returns. An unsaved live run is refused. Clearing
  every context stays in Python (`clear_context`).
- **Each context keeps its own detector hits.** A scene's detectors hold
  only the last run's; a context keeps the hits of the run it was filled
  from (`SimulationResult.detector_hits`), so two runs of one scene each
  answer `list_detectors` and `rank_detector_paths` with their own.
- **Re-filling a context replaces it whole:** its old database is closed,
  and a bidirectional result that belonged to the old rays is dropped.

**Invariants.** One context is active at any time; the default one exists
whenever no other is active.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. A run filled into the active
context by mistake replaces what the tools were reading: every later answer
is about the new run, correct for it and wrong for the question. The
re-simulation of one path at high density is the case this exists for: its
rays answering a question about the broad run would look like a finding.
No guarantee holds then; `list_contexts` shows which run is active, which is
the only way to notice.

**Checked by.** `test_context_registry.py`: a named context made without
switching, switching both ways, clearing one (its database closed, the
default active again), and a package's objects kept per context and closed
with it; `test_targeted_resimulation_flow.py`: two runs of one scene, each
context reading its own detector hits; `test_saved_runs_in_context.py`:
`drop_context` refusing an unsaved, an active and an unknown context,
dropping a saved one, which reloads with the same rays.
