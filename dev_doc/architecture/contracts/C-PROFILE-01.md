---
id: C-PROFILE-01
title: A profile handoff is Hermite (position and exact surface normal) plus construction parameters, role-tagged arc spans, and a symmetry declaration
parties:
  provides: nonimaging_design (SMS chain, prism constructors)
  relies:   optiland_scene_bridge
port: P-PROFILE
viewpoint: structural
status: documented
failure_mode: loud
checked_by: null
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_profile_export.py; src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py
tracked_by: null
conflicts_with: null
refines: null
rationale: KB7
since: 0.2
---

# C-PROFILE-01 — A profile handoff carries exact normals, roles, and how it becomes 3D

**Assumptions.** Whatever writes a `profile.json` includes, for every span:
its two endpoints, the exact outward normal at each end, its role and
mechanism, and — once per profile — a declaration of how the 2D outline
becomes a 3D solid, plus the construction parameters and the physical/
numerical parameter split.

**Guarantees.** The receiving side never has to derive a normal from
neighbouring points. At a sharp corner the two spans meeting there carry
two different normals, and neither is averaged with the other.

**Invariants.** Normals are stored per span, not per shared vertex. A
fitted-curve field is always empty from this side.

**Units and frames.** The profile's declared length unit.

**If the assumption is violated.** Loud where the receiving side checks a
required field; silent for a normal that is present but wrong.

**Checked by.** Not by a dedicated test. `profile_export.py` is exercised
by the bridge's tests on the refractometer profile.
