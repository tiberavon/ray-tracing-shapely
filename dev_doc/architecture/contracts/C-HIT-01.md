---
id: C-HIT-01
title: A hit record carries wavelength and incident angle; incident_angle there is not Ray.incident_angle
parties:
  provides: core_scene_objects (Detector.on_ray_incident)
  relies:   analysis_lineage, agentic_layer, optical_elements_physics
port: P-HIT-RECORD
viewpoint: radiometric
status: enforced
failure_mode: silent
checked_by: >-
  src-python/ray_tracing_shapely/developer_tests/test_detector_hit_records.py::test_wavelength_none_when_color_simulation_disabled,
  ::test_wavelength_recorded_when_color_simulation_enabled,
  ::test_incident_angle_at_normal_incidence,
  ::test_incident_angle_at_45_degrees,
  ::test_incident_angle_is_bounded
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KB4
since: 0.2
---

# C-HIT-01 — A detector's record of a hit includes the wavelength and the angle, and that angle is its own

**Assumptions.** A reader of a detector's hit records does not confuse the
`incident_angle` stored there with the field of the same name on a ray.
They are computed separately and mean different things.

**Guarantees.** Every counted hit records the ray's wavelength (or nothing,
if colour is not being simulated) and the angle at which it crossed the
detector line, measured from the line's perpendicular, always between 0
and 90 degrees.

**Invariants.** The ray's own `incident_angle` field describes the surface
that *stopped* the ray. A detector does not stop a ray, so a plain
detector crossing never writes to it. That field stays empty across a
detector.

**Units and frames.** Angle in radians, 0 to π/2, from the detector's
normal. Wavelength in nanometres, or none.

**If the assumption is violated.** Silent. A future change that reused the
ray's field for detector hits would leave a reader seeing either a stale
value from some earlier surface or nothing, and both look like ordinary
data.

**Checked by.** Five tests in `test_detector_hit_records.py`, against
geometries where the answer can be worked out by hand (0° and 45°).
