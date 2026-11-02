---
id: C-CONV-01
title: A comparison claim is valid only with sampling noise, profile discretisation, and tessellation density kept separate
parties:
  provides: whoever writes the comparison and states its held-fixed axis (a person)
  relies:   analysis_run_registry (compare_runs), a future 3D component
binds:      analysis_run_registry, analysis_bidirectional
port: P-RUN-BUNDLE
viewpoint: numerical
status: documented
failure_mode: silent
checked_by: null
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC3
since: 0.1
---

# C-CONV-01 — A comparison says which kind of "not converged yet" it held fixed

There are three different reasons a simulation result can be imprecise:
too few rays (sampling noise), a curved surface approximated by too few
straight pieces (discretisation), and — in 3D — a surface tiled too
coarsely (tessellation). They are independent. More rays do not fix a
coarse curve.

**Assumptions.** Whoever compares two runs states which of the three was
varied and which were held fixed.

**Guarantees.** A convergence claim that names its axis can be checked
and repeated. One that does not has folded three separate errors into one
number.

**Invariants.** The three do not trade off against each other. A real
instance exists: the mesh-convergence sweep script holds the ray density
fixed at a high value so that sampling noise is saturated first, then
varies the mesh alone.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. A result refined along one axis
looks converged, and the residual error from the other two is invisible
in it.

**Checked by.** Nothing yet. What would check it is an explicit statistic
and confidence band per axis, not just a named one.
