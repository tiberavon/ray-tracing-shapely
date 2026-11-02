---
id: C-LABEL-02
title: Every surface carries (Role, Mechanism); the class owns the role, the template owns the composition
parties:
  provides: core_labelling, nonimaging_design (SMS/prism templates)
  relies:   analysis_signature
port: P-ROLE-MECHANISM
viewpoint: structural
status: documented
failure_mode: silent
checked_by: null
witness: src-python/ray_tracing_shapely/developer_tests/test_roles.py::test_edge_roles_three_tuple_backward_compat
tracked_by: null
conflicts_with: null
refines: null
rationale: KA1
since: 0.1
---

# C-LABEL-02 — Every surface says what it is for and what light does there

**Assumptions.** Each optical element class states, for each of its
surfaces, a role (entrance, wall, absorber, exit, ...) and a mechanism
(refract, reflect, or total internal reflection). A template that
assembles several elements into a device states how their roles combine.

**Guarantees.** Any surface in a designed element can be asked what it is
for, and the answer is drawn from one shared list of words, so the same
question asked of a different design gets a comparable answer.

**Invariants.** The class owns the role. The template owns the
composition. Neither guesses the other's part.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. A surface with no role is
simply absent from any comparison keyed on roles, and a 3D bridge that
dispatches on roles would have nothing to dispatch on for it.

**Checked by.** Not yet. The curved element classes currently have empty
role lists, which is the known instance of the gap.
