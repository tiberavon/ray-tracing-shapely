---
key: KC2
title: Why constructors take optical requirements rather than coordinates
one_line: An element is built from what it has to do optically — a critical angle, a path length, a pixel pitch — and computes its own geometry, so no caller writes vertex coordinates.
status: active
informs: [nonimaging_design, core_scene_objects, optical_elements_physics, C-PROFILE-01]
since: 0.1
---

To build a prism in this program you do not give it corner coordinates. You
give it the two refractive indices and the internal path length you want,
and it works out every vertex. To build a line sensor you give it the pixel
count and the pixel pitch, and it places the detector and the blocker
accordingly.

**The grounding for this is by demonstration rather than argument.** Three
families of element were built this way and the pattern held each time. No
alternative — an API that takes corners, with helper functions beside it —
was written down and rejected. What follows is the case as it stands.

## What the caller would otherwise have to do

Take a refractometer prism, sized so that a ray entering square-on strikes
the measuring surface at exactly the critical angle and leaves square-on
through the exit face. Every corner follows from the two indices and the
desired internal path length, through a chain of trigonometry with a
validity condition attached: below a certain critical angle the shape
degenerates into a triangle, and below that it stops making sense.

A caller given corners has to do that derivation, get the degenerate case
right, and redo both every time the sample index changes. A caller given the
indices and the path length states what is wanted and gets a valid shape
or a clear error.

## The inputs are what you would sweep

A design is studied by varying what it was specified with — an index, an
acceptance angle, a mesh resolution. Those are the natural axes of a sweep
precisely because they are the constructor's inputs. An API that takes
corners makes the swept quantity something the caller has to derive, and
puts that derivation in every notebook instead of once in the class.

It also makes the split between "settings about the device" and "settings
about the simulation" fall out for free: the optical requirement is
physical, the mesh resolution is numerical, and they arrive through
different inputs rather than one flat list.

## Real devices are assembled from parts

A real sensor is a detector and a blocker arranged by pitch and count. The
constructor's job is to place existing pieces according to the datasheet,
and the caller never needs to know how they are arranged inside.

## What this does not claim

That corners are never right. A profile produced by an iterative
construction *is* a list of points, and what gets handed to the 3D tracer
is positions and directions. The claim is about how a person or an
assistant describes a device: by what it must do, not by where its corners
are.

## Read also

- **KC1** — [physics_and_rendering_are_layers_above_core_never_inside_it](KC1_physics_and_rendering_are_layers_above_core_never_inside_it.md) — composition as the general habit
- **KC3** — [physical_and_numerical_parameters_are_stored_separately](KC3_physical_and_numerical_parameters_are_stored_separately.md) — why the parameter split matters downstream
- **KA1** — [edges_carry_a_functional_and_a_cardinal_label](KA1_edges_carry_a_functional_and_a_cardinal_label.md) — what the constructor labels as it builds
