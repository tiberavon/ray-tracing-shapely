---
id: C-BRIDGE-01
title: A profile span's (Role, Mechanism) maps totally to an NSQ component type, loud on anything unrecognised
parties:
  provides: optiland_scene_bridge
  relies:   optiland_nsq_viewer, optiland_nsq_run_registry
port: P-NSQ-SCENE
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py::test_unrecognised_mechanism_raises_value_error
witness: src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py::test_only_base_span_is_unreached
tracked_by: null
conflicts_with: null
refines: null
rationale: KA1
since: 0.1
---

# C-BRIDGE-01 — Every kind of surface maps to a 3D component, and an unknown kind is an error

**Assumptions.** Each span in a profile carries a role and a mechanism
from the shared vocabulary.

**Guarantees.** The bridge turns each (role, mechanism) pair into the
matching kind of Optiland surface — refracting, reflecting, absorbing —
and places it. Every pair in the vocabulary has a mapping.

**Invariants.** The mapping is a fixed table. A pair not in the table
raises a `ValueError` naming the pair.

**Units and frames.** Not applicable.

**If the assumption is violated.** Loud. The alternative — a default
surface type for anything unrecognised — would build a solid that traces
plausibly and is not the one that was designed.

**Checked by.** `test_scene_bridge.py::test_unrecognised_mechanism_raises_value_error`.
