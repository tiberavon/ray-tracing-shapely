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
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_mirror_coated_edge.py::test_the_coated_face_reflects_from_inside_exactly_and_losslessly; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_mirror_coated_edge.py::test_the_coated_face_reflects_from_outside_and_the_other_face_refracts; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rx_concentrator.py::test_r_refracts_and_x_is_mirror_coated; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_rxi_direct.py::test_the_labels_and_the_coatings
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_roles.py::test_edge_roles_three_tuple_backward_compat
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

A glass edge whose mechanism is `reflect` is mirror-coated, by the glass
itself: in 2D it reflects a ray from either side at its exact normal with no
loss (`BasePrism.edge_reflects`, `Glass.on_ray_incident`); in 3D it is a
reflecting face of the solid (`reflectances`). No mirror object lies on the
edge. One would meet a ray at the same distance as the edge, and the 2D
simulator could take either (the SMS RX and RXI lost about half their
mirror rays that way).

**Invariants.** The class owns the role. The template owns the
composition. Neither guesses the other's part.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. A surface with no role is
simply absent from any comparison keyed on roles, and a 3D bridge that
dispatches on roles would have nothing to dispatch on for it.

**Checked by.**
- **The mirror-coated edge:** a singlet's back face coated through its
  profile reflects from inside and from outside, exactly and without loss,
  and its front face still refracts. The RX's X and the RXI's mirrors (`MT`
  on the top's centre, `MB` on the bottom) are `reflect` edges of the glass,
  and no other edge is, with no mirror objects.
- **Roles and mechanisms:** the SMS elements (`RRLens`, `RXConcentrator`,
  `XRConcentrator`, `RXIOpticDirect`) label every surface (`sms_chain.label_sms_edges`). Other
  curved element classes still have empty role lists: that is the gap left.
