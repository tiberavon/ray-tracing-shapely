---
key: KB4
title: Why quantities computed during tracing are kept
one_line: The simulator computes wavelength, incidence angle, surface normals, medium index and ray identity while tracing, then historically threw them away; they are recorded instead, attributed to the path that produced them.
status: active
informs: [core_simulator, core_scene_objects, analysis_lineage, optical_elements_physics, C-HIT-01, C-DET-01]
since: 0.1
---

A simulation works out more than it reports. It needs the angle at which a
ray strikes a surface to refract it, the surface's direction to reflect it,
the ray's identity to build the family tree. Each of those used to be
computed, used once, and forgotten. Now each is recorded on the segment or
the detector hit that produced it.

## A measurement that cannot say where it came from

A detector once counted how much light arrived, and in which bin, and threw
away *which ray* had arrived. The family tree of rays existed alongside it,
unconnected. So the question a refractometer exists to answer — *which
routes reached the sensor?* — could not be asked, while both halves of the
answer sat in memory.

Recording the arriving ray's identity on each hit connects the two. Ranking
routes by energy can then start from the detector's own list of hits, and
each pixel of a sensor can list the routes that reached it.

## Later physics needs what was thrown away

How a photodiode responds depends on the wavelength and the angle of the
light. A time-of-flight measurement depends on how far the light travelled
and through what — which needs the refractive index of the material each
segment passed through. None of that can be reconstructed afterwards from a
brightness total. The information existed exactly once, at the moment of
the interaction, and nothing else in the run can recover it.

That is the general shape of the rule: the trace is the only moment these
values exist, so the choice is to record them then or never have them.

## Cost is handled by a switch, not by forgetting

Recording where every segment ended — the surface, the point, the angle —
costs memory on every segment of every run, including the large runs that
will never look at it. So it is behind a switch, off by default, and the
saved files leave those columns empty for runs that did not use it.

Detector hits are not behind a switch, because only the few rays that
actually reach a detector are recorded and the cost is negligible. The rule
is decided quantity by quantity, by how many segments carry it.

## What this does not claim

That everything should be kept. Intermediate values with no consumer are
noise, and the switch exists because even useful provenance can cost more
than it returns. The claim is narrower: a physically meaningful quantity
with a known downstream use is recorded at the moment it exists, because
there is no later moment.

## Read also

- **KB1** — [ray_lineage_is_a_graph_not_a_hand_rolled_tree](KB1_ray_lineage_is_a_graph_not_a_hand_rolled_tree.md) — the structure the identity attaches to
- **KB8** — [a_run_bundle_records_its_schema_version_and_parameter_split](KB8_a_run_bundle_records_its_schema_version_and_parameter_split.md) — why the recorded fields are written down carefully
- **KC1** — [physics_and_rendering_are_layers_above_core_never_inside_it](KC1_physics_and_rendering_are_layers_above_core_never_inside_it.md) — who consumes these quantities
