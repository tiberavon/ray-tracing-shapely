---
key: KB5
title: Why the 2D geometry comes from Shapely
one_line: Containment, intersection, interpolation and centroid come from a geometry library rather than from hand-written vector code, and the library's polygon model is the scene's model.
status: active
informs: [core_simulator, core_scene_objects, nonimaging_design, analysis_lineage]
since: 0.1
---

The shapes in a scene — the outline of a prism, the line of a mirror — are
represented using Shapely, a library for two-dimensional geometry. When
the program needs to know whether a point is inside a glass, where a ray
meets an edge, or what lies three-quarters of the way along a surface, it
asks the library.

**This is one of the less well-argued choices here, and it is worth saying
so plainly.** It was made against the program this one replaced — a
JavaScript ray tracer with its own hand-written geometry — and not by
comparing Shapely with other geometry libraries. No such comparison was
recorded, and none is claimed now.

## What hand-written geometry costs

Working out where two line segments cross, or whether a point lies inside a
polygon, sounds simple and is full of awkward special cases: segments that
overlap, a point exactly on a boundary, an edge of zero length. Each one
written from scratch is a chance to get a rare case wrong in a way that
produces a plausible-looking number. A library has already met those cases.

A library also gives vocabulary. `contains`, `intersects` and `interpolate`
say what they mean, and code that needs them is short enough to read.

## Where it stops

Shapely is two-dimensional. Every question about the third dimension —
whether a design survives being extruded into a solid, whether that solid
is closed, whether the trace can be differentiated — leaves this library
entirely, and is the reason a separate 3D tool exists at all.

It is also not the physics. Bending light at a surface, splitting it into
reflected and transmitted parts, total internal reflection: those are this
project's own code. The library answers where the surfaces are and where a
ray meets them, and nothing more.

## The fast path stays plain

Positions in the scene are plain numbers, not numbers-with-units. The
simulator checks geometry once per ray per surface, millions of times in a
large run, and that path is deliberately free of unit checking and
validation. Physical units begin in the layer above.

## What this does not claim

That Shapely was compared with anything and won. It replaced hand-written
code, which is a low bar it clears easily, and it has not been re-examined
since. If a reason to reconsider ever appears — a 3D requirement reaching
back into the 2D model, a speed limit — there is no recorded argument here
that would have to be overturned first.

## Read also

- **KC1** — [physics_and_rendering_are_layers_above_core_never_inside_it](KC1_physics_and_rendering_are_layers_above_core_never_inside_it.md) — why the geometry layer carries no units
- **KB7** — [optiland_verifies_2d_designs_in_3d_and_hands_them_back](KB7_optiland_verifies_2d_designs_in_3d_and_hands_them_back.md) — what happens where 2D stops
- **KC2** — [elements_are_built_from_optical_requirements_not_vertices](KC2_elements_are_built_from_optical_requirements_not_vertices.md) — what produces the polygons
