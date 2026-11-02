---
id: C-RUN-01
title: Every persisted run bundle carries a schema version independent of package version, and a converged/uncertainty field
parties:
  provides: analysis_run_registry
  relies:   analysis_run_registry (compare_runs), Era 5 surrogate (planned)
port: P-RUN-BUNDLE
viewpoint: structural
status: aspirational
failure_mode: deferred
checked_by: null
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KB8
since: 0.1
---

# C-RUN-01 — A saved run says which version of the file format it is

**Assumptions.** Every saved run bundle — `params.json`, `rays.sqlite`,
`summary.json`, the manifest line, and the graph and signature files when
present — carries a version number for its *format*, separate from the
version of the software that wrote it, and a field saying how much the run
trusts its own result.

**Guarantees.** A reader opening an old bundle, possibly years later and
with a different version of the software, can tell whether the fields mean
what it expects before reading them, and can decide whether to trust the
result at all.

**Invariants.** None of this exists in the code yet. The status is
*aspirational*: this contract states the target, and `persist_run_artifacts`
does not yet write either field.

**Units and frames.** Not applicable.

**If the assumption is violated.** Deferred — the failure appears only
when a future reader misreads an old field.

**Checked by.** Nothing. Not yet built.
