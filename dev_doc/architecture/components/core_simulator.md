# `core_simulator`

The engine. It takes a scene full of optical objects and a list of light
sources, and works out where every ray goes.

## Why this component is different

It knows nothing about optics. It does not know what glass is, or what a
mirror does, or how light bends. What it knows is a queue: take the next ray
off the front, find the first object it hits, ask that object what happens,
put whatever comes back on the end of the queue. That is the whole loop. The
physics lives in the objects, and the engine only carries messages between
them.

This is deliberate, and it is why new kinds of optical element can be added
without touching the engine — the engine never asks what an object *is*,
only what it *returned*.

## Concepts this component realises

- **`KC1`** — the engine is a geometry loop and nothing else. The four files
  here hold rays, the scene, the lineage tree and the loop. None of them
  mentions a watt, a nanometre or a refractive index as a *physical* thing:
  a ray has a `wavelength` field because something downstream needs it, but
  the engine never uses it. Everything that turns a ray into a physical
  measurement sits in the layer above and reads from here.

- **`KB1`** — every ray segment carries a unique identifier, the identifier
  of its parent, and the kind of event that created it (*source*,
  *refract*, *reflect*, *tir* — total internal reflection). Those three
  fields make the output a **directed graph**: a network of segments joined
  by "this one came from that one". `RayLineage` indexes it so that
  questions like *which paths reached the sensor* are walks over the graph
  rather than searches over a flat list.

- **`KB4`** — quantities the engine computes on the way are kept on the
  segment rather than used and dropped. The index of the medium a segment
  is travelling through, how many total internal reflections it has
  undergone, and — when asked for — the point, surface and angle at which it
  hit something. Each of these was once computed and thrown away, and each
  was needed by something built later. The last set costs memory on every
  segment, so it is only recorded when the simulation is started with
  `record_surface_hits=True`.

## Modules

| File | What it holds |
|---|---|
| `core/scene.py` | `Scene`: the container holding every object and every source, plus run-wide settings like ray density and the brightness below which a ray is dropped. |
| `core/ray.py` | `Ray`: one straight segment of light, with its endpoints, brightness (split into two polarisations), wavelength, identifiers, and the fields above. |
| `core/ray_lineage.py` | `RayLineage`: the parent/child index over all segments, with queries for ancestors, children, leaves, and export to a standard graph library. |
| `core/simulator.py` | `Simulator`: the queue loop, and the four places in it where a new segment is created from an old one. |
| `core/geometry.py` | Shared geometric helpers used by the objects. |

## What it produces

A **port** is something this component makes available for other parts of
the program to use.

- **`P-SCENE-PROTOCOL`** — the three questions the engine asks every object.
  *Get ready* (`on_simulation_start`, once per object before any ray moves).
  *Does this ray hit you?* (`check_ray_intersects`). *It hit you — what
  happens?* (`on_ray_incident`). An object that answers those three is a
  scene object, whatever else it is. The engine dispatches only on the shape
  of the answers, with one exception noted in `C-CORE-01`: when two glasses
  share a surface, it checks the object's type to decide which one owns the
  boundary.
- **`P-RAY-LINEAGE`** — the segments, the list of them, and the parent/child
  tree, with every per-segment field filled in at each of the four places a
  segment is born.

## What it needs from elsewhere

Nothing from inside this codebase. This is the root: everything else depends
on it and it depends on the objects only through the three questions above.

## Promises this component makes and relies on

A **contract** is a written promise about what must be true at a boundary,
with a note on what happens if it is broken and, where possible, a test that
checks it.

| Contract | This component's part |
|---|---|
| `C-CORE-01` | **Owns** it. Objects own their physics; the engine only processes the queue. Every scene object is the other party. |
| `C-CORE-02` | **Relies** on it. A detector never ends a ray — light passes through and is counted — and the engine must not treat a detector crossing as a termination. |
| `C-LINEAGE-01` | **Owns** it. The lineage is a proper family tree: one parent per segment, no loops, and a parent is always registered before any child of it can exist. The queue's first-in-first-out order guarantees this without a separate check. |

## How it is shipped

Core package. It depends on a geometry library and a graph library, both
mandatory rather than optional, because every entry point into the analysis
would otherwise need a guard for their absence.
