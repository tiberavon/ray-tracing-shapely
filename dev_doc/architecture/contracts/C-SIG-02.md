---
id: C-SIG-02
title: Signature energies are ranking quantities, not calibrated throughput, unless separately calibrated
parties:
  provides: analysis_signature
  relies:   analysis_run_registry
port: P-SIGNATURE-SPECTRUM
viewpoint: numerical
status: documented
failure_mode: silent
checked_by: null
witness: dev_doc/architecture/04_worked_example.md
tracked_by: null
conflicts_with: null
refines: null
rationale: KB3
since: 0.1
---

# C-SIG-02 — Route energies rank routes; they are not amounts of light

**Assumptions.** Adaptive sampling is off when a route table is built for
comparison. No physical calibration has been applied unless it says so.

**Guarantees.** Within one table and between two, *this route carries more
than that one* is meaningful.

**Invariants.** The absolute numbers depend on the ray density and the
brightness cutoff, and do not carry over to a run with different settings
even when the ranking does. Converting to watts is a different component's
job, downstream.

**Units and frames.** The engine's dimensionless brightness units. Not
watts.

**If the assumption is violated.** Silent. Adaptive sampling left on
produces tables whose numbers reflect where the sampler chose to spend
rays, not where the light went.

**Checked by.** Nothing yet.
