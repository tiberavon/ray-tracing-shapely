---
id: C-LABEL-01
title: Scene-object names are stable across runs of one design
parties:
  provides: scene builders (notebooks, papermill templates, optical_elements constructors)
  relies:   analysis_signature, analysis_run_registry, analysis_bidirectional
port: P-SCENE-NAMES
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: >-
  src-python/ray_tracing_shapely/developer_tests/test_run_registry.py::test_persist_run_artifacts_writes_name_topology_fingerprint,
  ::test_persist_run_artifacts_duplicate_name_raises,
  ::test_compare_runs_raises_on_swept_parameter_absorbed_into_name,
  ::test_compare_runs_raises_on_unnamed_objects,
  ::test_compare_runs_check_name_topology_false_bypasses_the_check
witness: dev_doc/architecture/04_worked_example.md
tracked_by: null
conflicts_with: null
refines: null
rationale: KA1
since: 0.1
---

# C-LABEL-01 — Object names mean the same thing in every run you compare

**Assumptions.** Whoever builds a scene gives each object a name, typed in
as a plain word — not built from the parameter being swept, so that a
prism called `prism_n1.5` in one run is not `prism_n1.6` in the next. Two
designs being compared give matching surfaces matching names.

**Guarantees.** Given that, every comparison between runs — route
signatures, spectra, the database queries keyed on a surface name — lines
up, even though every object's internal identifier is different each time.

**Invariants.** A name belongs to the design. An internal identifier
belongs to one run and must never be used to match across runs.

**Units and frames.** Not applicable.

**If the assumption is violated.** Loud, at the one place it can be
caught. Nothing about a single scene says whether its names will match a
*different* run, so the check happens where two runs meet: `compare_runs`.
It computes a fingerprint of each run's names and raises before comparing
anything if the fingerprints differ, if two objects share a name but not a
type, or if any object is unnamed. Before that check existed, a mismatch
produced a comparison that reported spurious differences, and an unnamed
object silently merged with every other unnamed object into one bucket.
Both happened.

**Checked by.** Five tests in `test_run_registry.py`: the fingerprint is
written, an unnamed object raises, a mismatched key set raises, a
same-name-different-type collision raises, and the check can be switched
off deliberately.
