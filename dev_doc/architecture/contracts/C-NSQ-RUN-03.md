---
id: C-NSQ-RUN-03
title: analysis_run_registry's execute_query/_validate_sql stay table-name-agnostic; get_schema_description does not, and optiland_nsq_run_registry ships its own equivalent instead of relying on it
parties:
  provides: analysis_run_registry (analysis/agentic_db.py)
  relies:   optiland_nsq_run_registry
binds: optiland_nsq_run_registry
port: P-NSQ-RUN-BUNDLE
viewpoint: structural
status: documented
failure_mode: silent
checked_by: null
witness: src-python/ray_tracing_shapely_optiland/tests/test_nsq_db.py (all tests reuse execute_query against nsq_events unmodified); test_get_nsq_schema_description
tracked_by: null
conflicts_with: null
refines: null
rationale: KA6
since: 0.1
---

# C-NSQ-RUN-03 — The query machinery does not care what the tables are called

**Assumptions.** None on the caller.

**Guarantees.** `execute_query` and the read-only guard in the 2D registry
work unchanged against the 3D database, so there is one implementation of
"run a query safely" for both.

**Invariants.** The function that *describes* a schema is not
table-agnostic — it knows the 2D columns — so the 3D registry ships its
own equivalent rather than pretending the 2D one applies.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent: a query helper that assumed 2D
table names would fail on the 3D database with an error about a missing
table, which reads as a data problem rather than a code one.

**Checked by.** Not by a dedicated test. The 3D tests exercise the shared
`execute_query` directly.
