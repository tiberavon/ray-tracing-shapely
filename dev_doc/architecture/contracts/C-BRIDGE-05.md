---
id: C-BRIDGE-05
title: optiland_scene_bridge must never import optiland_nsq_viewer — headless/batch scene assembly never needs the notebook/trame stack
parties:
  provides: optiland_scene_bridge
  relies:   any batch/headless caller of optiland_scene_bridge (papermill sweeps, an agentic tool call)
port: P-NSQ-SCENE
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely_optiland/tests/test_scene_bridge.py::test_scene_bridge_does_not_import_jupyter_viewer
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KC7
since: 0.1
---

# C-BRIDGE-05 — The bridge never imports the viewer

**Assumptions.** None on any caller.

**Guarantees.** `scene_bridge.py` can be imported and used on a machine
with no display, no browser and none of the interactive 3D libraries
installed.

**Invariants.** The dependency runs one way. The viewer imports the
bridge; the bridge does not import the viewer.

**Units and frames.** Not applicable.

**If the assumption is violated.** Loud, at import time, on the machine
least able to diagnose it — a headless sweep would fail before doing any
work because a library it never needed was not installed.

**Checked by.** `test_scene_bridge.py::test_scene_bridge_does_not_import_jupyter_viewer`.
