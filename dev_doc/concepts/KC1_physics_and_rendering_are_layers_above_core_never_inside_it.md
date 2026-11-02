---
key: KC1
title: Why physics, units and rendering sit above the simulator instead of in it
one_line: The core is a geometry hot loop that owns no physical units and no rendering; every layer that adds meaning is built on top of it by composition, and none of them modifies it.
status: active
informs: [core_simulator, core_scene_objects, optical_elements_physics, optical_elements_units, svg_renderer, C-CORE-01, C-RUN-02]
since: 0.1
---

The engine at the centre of this program moves rays from surface to surface
and asks each surface what happens. It knows nothing about watts, or
nanometres, or what a detector reads. Everything that gives a ray a
physical meaning sits in a layer *above* the engine, built on top of it,
and none of those layers changes the engine.

## Where the line is

Positions in the scene, ray endpoints, the spacing of a sensor's pixels —
plain numbers. The quantities in the physical layer — irradiance, radiance,
a sensor's response — numbers with units, checked for the right kind. That
looks inconsistent and is deliberate. The engine's geometry runs once per
ray per surface, millions of times in a large run; the physical layer runs
once per result.

The line is drawn where the cost is paid. A check in the engine's loop is
paid on every intersection. A check in the layer above is paid once, and
it catches a kind of mistake the engine cannot make anyway, because the
engine never sees a unit.

## Built by composition, not by subclassing

The physical layer's objects are not new kinds of scene object. A detector
*holds* a conversion model; a source *holds* an emission model; each
consumes a description of the scene's units and a description of how a 2D
cross-section stands in for a 3D shape. A real sensor — a specific CCD
array, say — is assembled from an existing detector and an existing blocker
placed according to its pixel count and pitch, not modelled as a new type.

Making them subclasses would put physical behaviour inside the family of
types the engine walks, which is the same as putting it in the engine.
Composition keeps each addition on the outside, where it can change without
touching what traces rays.

## The test is whether it held

Every layer added this way has been added without touching the engine. The
physical layer landed without a change to the core. The rework that gave
every quantity a checked unit touched the layer above the simulator and
left the simulator alone. The drawing code works out what to draw by what
an object has, not by importing the list of object types.

That is a test applied after the fact, not a hope: a layer that *cannot* be
added without reaching into the engine is a sign the line was drawn in the
wrong place, not permission to move it.

## What this does not claim

That the engine is finished. It gains fields — a segment's identity, the
refractive index it travelled through, where it ended — whenever something
above it needs a quantity that only exists during the trace. The rule is
about *meaning*, not about additions: the engine records what it computed,
and nothing in it knows what a watt is.

## Read also

- **KC4** — [physical_quantities_are_unit_checked_not_docstring_documented](KC4_physical_quantities_are_unit_checked_not_docstring_documented.md) — what the layer above does with its freedom
- **KB4** — [quantities_computed_while_tracing_are_recorded_not_discarded](KB4_quantities_computed_while_tracing_are_recorded_not_discarded.md) — the one way the core does grow
- **KC2** — [elements_are_built_from_optical_requirements_not_vertices](KC2_elements_are_built_from_optical_requirements_not_vertices.md) — composition applied to device construction
