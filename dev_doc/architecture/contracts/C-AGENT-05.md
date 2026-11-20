---
id: C-AGENT-05
title: A saved run is loaded by reference, read-only, into a new context; the tools it cannot serve say so; a save never overwrites
parties:
  provides: 'whoever saves or loads a run: save_context_tool, load_run_context, a package registering a run-file loader (register_run_file_loader)'
  relies:   'the assistant reading a run after the kernel that made it is gone; compare_persisted_runs_tool'
binds: agentic_layer (agentic_tools.py), analysis_run_registry (run_registry.py)
port: P-KERNEL-CONTEXT
viewpoint: agentic
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_saved_runs_in_context.py::test_a_saved_run_loads_by_reference_and_answers_as_the_live_one_did; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_saved_runs_in_context.py::test_the_tools_that_need_the_scene_say_the_run_was_loaded; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_saved_runs_in_context.py::test_a_loaded_database_is_read_only; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_saved_runs_in_context.py::test_saving_never_overwrites_and_needs_a_result; src-python/ray_tracing_shapely_optiland/tests/test_agentic_3d.py::test_a_run_folder_loads_its_2d_run_and_its_3d_log_into_one_context
witness: null
tracked_by: null
conflicts_with: null
refines: C-AGENT-04
rationale: KA5, KB8
since: 0.2
---

# C-AGENT-05 — A saved run, back in view without its kernel

A run saved to a folder (`P-RUN-BUNDLE`) can be loaded into a context of its
own and questioned as the live run was: the same database, the same path
graph. Nothing live is rebuilt, so what needs the live scene is refused, by
name.

**Assumptions.** The folder was written by `save_context_tool` or
`persist_run_artifacts` (or holds a file a registered package loads, such as
the 3D bridge's `nsq_events.sqlite`), and has not been edited since.

**Guarantees.**
- **Loading makes a new context and never switches to it** (`C-AGENT-04`).
  A name already in use is refused; so is a folder holding none of the files
  a run is loaded from, and the refusal lists what the folder does hold.
- **The database is opened read-only.** The saved run cannot be changed by
  questioning it.
- **What the tools were reading is what is saved.** `save_context_tool`
  writes the context's own database, with the backward rays and connections
  a bidirectional result added, and the path graph with the detector it was
  traced from. Loaded back, `query_rays` and the bidirectional path ranking
  give the live run's answers.
- **The tools that need what was not saved say so.** A tool that needs the
  live scene or the lineages, run on a loaded context, answers with an error
  naming the folder it was loaded from and the tools that do work on it; it
  never answers from another context.
- **A save never overwrites.** An existing run folder is refused, and so is a
  `design_id` or `run_id` that is not a plain folder name.
- **A package's file loads into the same context.** With the 3D bridge
  registered, a folder holding a 2D run and its 3D event log loads both into
  one context; clearing it closes both databases.

**Invariants.** A loaded context's `run_dir` names the folder its databases
were opened from.

**Units and frames.** Not applicable.

**If the assumption is violated.** Loud where it can be seen: a folder with
no run in it, or a run named twice, is an error. A bundle edited by hand
after it was saved is not detected: it loads, and its answers are the edited
file's.

**Checked by.** `test_saved_runs_in_context.py`: a bidirectional run saved
and loaded back gives the same counts and path energies; the scene and
lineage tools refuse with the folder's name; the loaded database refuses a
write; a save onto an existing run is refused. `test_agentic_3d.py`: a 2D run
and its 3D event log in one folder load into one context.
