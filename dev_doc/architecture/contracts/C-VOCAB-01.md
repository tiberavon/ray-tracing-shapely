---
id: C-VOCAB-01
title: Mechanism's values are string-identical to Ray.interaction_type's literals
parties:
  provides: core_labelling (Mechanism enum)
  relies:   core_simulator (Ray.interaction_type), analysis_signature
port: P-ROLE-MECHANISM
viewpoint: structural
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/developer_tests/test_roles.py::test_role_mechanism_enum_values
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: null
since: 0.1
---

# C-VOCAB-01 — The word for what a ray did is spelled the same everywhere

**Assumptions.** None on any caller.

**Guarantees.** The list of mechanisms a surface can have — `refract`,
`reflect`, `tir` — uses exactly the strings the engine writes into a ray's
`interaction_type` field when that event happens.

**Invariants.** The two are not linked by code; one does not import the
other. They agree because a test says they must.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. If the two spellings drifted —
even by one capital letter — comparing two runs by their routes would find
no matching routes, and report that as "no difference between these
designs".

**Checked by.** `test_roles.py::test_role_mechanism_enum_values`.
