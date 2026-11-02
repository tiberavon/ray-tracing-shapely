---
id: C-NSQ-RUN-01
title: An NSQ run is never persisted with an empty event table unless record_paths was genuinely off — silently persisting nothing when nothing was recorded is not permitted
parties:
  provides: optiland_nsq_run_registry
  relies:   execute_query/get_nsq_schema_description callers, future
port: P-NSQ-RUN-BUNDLE
viewpoint: agentic
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_nsq_db.py::test_create_nsq_database_raises_without_recorded_paths
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KD3
since: 0.1
---

# C-NSQ-RUN-01 — A saved 3D run with no events is an error, unless recording was off

**Assumptions.** A trace that was meant to record its ray paths did record
them.

**Guarantees.** `create_nsq_database` refuses to write a database with an
empty events table when path recording was on. A run that recorded nothing
is not silently saved as a run with nothing in it.

**Invariants.** The only way to persist an empty table is to have traced
with recording deliberately off, and `C-NSQ-RUN-02` writes that setting
into the run's parameters so a reader can tell the two apart.

**Units and frames.** Not applicable.

**If the assumption is violated.** Loud, which is the point: silently
persisting nothing looks identical to a run in which no ray reached any
surface.

**Checked by.** `test_nsq_db.py::test_create_nsq_database_raises_without_recorded_paths`.
