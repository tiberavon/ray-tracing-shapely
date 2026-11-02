---
id: C-BRIDGE-03
title: ExtrudedPolygonRenderer2D requires projection="XZ"; the default projection="YZ" draws this device as a degenerate flat line
parties:
  provides: optiland_scene_bridge
  relies:   a human or agent calling NSQViewer2D.view() against this device
port: P-NSQ-SCENE
viewpoint: agentic
status: documented
failure_mode: silent
checked_by: null
witness: notebooks/optiland_scene_bridge_refractometer_demo.ipynb section 10
tracked_by: null
conflicts_with: null
refines: null
rationale: null
since: 0.1
---

# C-BRIDGE-03 — The 2D viewer must be told which plane to draw

**Assumptions.** Whoever draws an extruded solid in Optiland's 2D viewer
passes `projection="XZ"`.

**Guarantees.** With that projection the solid appears as its cross-
section.

**Invariants.** The viewer's default projection is `YZ`, which looks along
the extrusion axis and draws the whole solid as a single flat line.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. The viewer draws a line, the
line is not an error, and the reader concludes the solid is degenerate.

**Checked by.** Not by a test; the renderer documents it.
