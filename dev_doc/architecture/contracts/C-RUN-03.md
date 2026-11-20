---
id: C-RUN-03
title: A run folder holds one engine's run; a second engine's writer refuses it rather than overwrite its params.json
parties:
  provides: 'analysis_run_registry (persist_run_artifacts), optiland_nsq_run_registry (persist_nsq_run)'
  relies:   'whoever reads a run folder''s params.json: compare_run_dirs (the name-topology check), load_run_context, a reader judging an NSQ run by its record_paths'
binds: analysis_run_registry (run_registry.py), optiland_nsq_run_registry (nsq_db.py)
port: P-RUN-BUNDLE
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_nsq_db.py::test_a_run_folder_holds_one_engines_run
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC3
since: 0.2
---

# C-RUN-03 — One engine's run per folder

The 2D writer (`persist_run_artifacts`) and the 3D bridge's writer
(`persist_nsq_run`) lay runs out the same way, `<out_dir>/<design_id>/<run_id>/`,
and each writes `params.json` whole. Into one folder, the second would
replace the first's settings: a 2D run would lose its `name_topology`
fingerprint (and `compare_run_dirs` skips its name check when a fingerprint
is missing), a 3D trace its `record_paths` (`C-NSQ-RUN-02`).

**Assumptions.** None on the caller.

**Guarantees.**
- **`persist_run_artifacts` refuses a folder that holds another engine's
  run** (`OTHER_ENGINE_RUN_FILES`: `nsq_events.sqlite`), with
  `FileExistsError`, before writing anything.
- **`persist_nsq_run` refuses a folder that holds a 2D run**
  (`rays.sqlite`), the same way.
- A 2D run and the 3D trace of the same device sit side by side as sibling
  `run_id`s under one `design_id`.

**Invariants.** A run folder's `params.json` is the settings of the one run
whose database it holds.

**Units and frames.** Not applicable.

**If the assumption is violated.** Not applicable: there is no assumption.
The refusal is loud, and nothing in the folder changes.

**Checked by.** `test_nsq_db.py::test_a_run_folder_holds_one_engines_run`:
each order refused, the first run's `params.json` unchanged and no second
database written; the trace saved beside the 2D run under its own `run_id`.
