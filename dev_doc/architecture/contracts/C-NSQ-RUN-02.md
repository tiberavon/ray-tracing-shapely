---
id: C-NSQ-RUN-02
title: The exact record_paths value used for a trace is written into that run's params.json, never silently omitted
parties:
  provides: optiland_nsq_run_registry
  relies:   anyone reading an NSQ run's params.json to judge whether its lineage is complete or a sampled subset
port: P-NSQ-RUN-BUNDLE
viewpoint: numerical
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_nsq_db.py::test_persist_nsq_run_writes_db_and_params
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC3
since: 0.1
---

# C-NSQ-RUN-02 — The run's parameters say whether paths were recorded

**Assumptions.** None on the caller.

**Guarantees.** The exact `record_paths` setting used for a trace is
written into that run's `params.json`.

**Invariants.** It is never omitted, and never defaulted on read.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. A reader could not tell whether
a run's lineage is complete, a sampled subset, or absent.

**Checked by.** `test_nsq_db.py::test_persist_nsq_run_writes_db_and_params`.
