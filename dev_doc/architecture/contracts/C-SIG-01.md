---
id: C-SIG-01
title: A signature is (surface_name, edge_index, interaction_type)*; comparison requires a shared discretisation
parties:
  provides: analysis_signature
  relies:   analysis_run_registry, agentic_layer
port: P-SIGNATURE
viewpoint: structural
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

# C-SIG-01 — A route's description is a list of (surface, edge, event), and edges must be numbered the same way in both runs

**Assumptions.** Two designs being compared cut their corresponding
curved surfaces into straight pieces the same way — same number of pieces,
same starting point, same direction. The edge number in a signature is a
position along that cut-up curve, not a coordinate.

**Guarantees.** Given that, two designs' route tables can be compared
entry by entry.

**Invariants.** The surface name in the tuple has to satisfy `C-LABEL-01`
too; the two contracts compose.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. Two concentrators cut
differently produce route descriptions that never match, and the
comparison reports that as a structural difference between the designs.

**Checked by.** Nothing yet.
