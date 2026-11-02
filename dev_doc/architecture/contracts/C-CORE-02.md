---
id: C-CORE-02
title: A Detector never terminates a ray
parties:
  provides: core_scene_objects (Detector.on_ray_incident)
  relies:   core_simulator, analysis_bidirectional, analysis_lineage
port: P-HIT-RECORD
viewpoint: radiometric
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_detector_never_terminates_ray
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: null
since: 0.2
---

# C-CORE-02 — A detector never stops a ray

**Assumptions.** A detector is a line that counts light crossing it. It is
not a wall.

**Guarantees.** A ray that crosses a detector continues past it,
unchanged. The detector records the crossing — or not, depending on which
side it came from — and the ray goes on to whatever is next.

**Invariants.** The ray's position is updated across the detector line on
every crossing, whether or not the crossing was counted. Counting and
continuing are independent.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. If a detector absorbed rays,
anything behind it would receive less light than it should, and no number
anywhere would say why.

**Checked by.** `test_detector_hit_records.py::test_detector_never_terminates_ray`.
