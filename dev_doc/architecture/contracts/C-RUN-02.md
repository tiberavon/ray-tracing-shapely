---
id: C-RUN-02
title: Physical and numerical parameters are strictly separated; a numerical setting never enters a learned model as if it were physics
parties:
  provides: a run author (whoever decides which parameter is physical vs. numerical)
  relies:   Era 5 surrogate (planned)
binds:      analysis_run_registry (params.json)
port: P-RUN-BUNDLE
viewpoint: numerical
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/developer_tests/test_run_registry.py::test_persist_run_artifacts_writes_expected_files
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC3
since: 0.1
---

# C-RUN-02 — Device settings and simulation settings live in separate sections

**Assumptions.** Whoever writes a run decides, for each setting, whether it
describes the device (refractive index, geometry, wavelength) or the
simulation (ray density, the brightness below which rays are dropped, mesh
resolution), and puts it in the matching section of `params.json`.

**Guarantees.** A reader — in particular a model trained on many runs —
can be told which settings are physics and should generalise, and which
are simulation knobs that should not appear in the model at all.

**Invariants.** A simulation setting that changes across a sweep must never
be mistaken for a swept design variable.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. A model trained on a set of runs
where ray density varied alongside the intended sweep would learn that
ray density affects the optics, and report it as physics.

**Checked by.** `test_run_registry.py::test_persist_run_artifacts_writes_expected_files`
— checks that the two sections are written and survive a round trip.
Which section a setting belongs in remains a human judgement.
