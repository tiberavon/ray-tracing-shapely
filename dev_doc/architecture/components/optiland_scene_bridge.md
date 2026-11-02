# `optiland_scene_bridge`

Taking a 2D outline designed here and building it as a 3D solid in
Optiland, a separate ray-tracing library, so the design can be traced in
three dimensions — and bringing the result back.

## Concepts this component realises

- **`KB7`** — the bridge. `build_faces_from_profile` reads a `profile.json`
  — the outline of a designed element, span by span, with each span's role,
  mechanism and exact outward normal — and builds one Optiland surface per
  span, placed in 3D by `span_outward_ray`. `ExtrudedPolygonSolid` wraps the
  faces as one compound component. The direction is chosen from the span's
  stored normal, not recomputed from neighbouring points, because a sharp
  corner has two different normals and averaging them places the face
  wrong. An import entry point, recovering a 2D outline from a live solid,
  is planned so that a profile polished in 3D can come back.

- **`KA1`** — each span's role and mechanism decide what kind of Optiland
  surface it becomes. An *entrance* that *refracts* is a refracting face; an
  *absorber* is an absorbing one. A combination with no mapping is an error,
  not a guess.

- **`KD3`** — where the solid is incomplete, that is stated rather than
  smoothed over. The extrusion has no end caps: it is four walls with no
  floor or ceiling in the extrusion direction. Every source built by the
  helpers here aims across the walls and never toward the missing ends, so
  the gap is never reached — but a source tilted even slightly toward them
  loses light through the opening, and the tracer reports clean energy
  conservation because the escaped rays are simply gone. This was
  reproduced deliberately, with a tilted source, rather than reasoned about.
  The contract records it as a known limit with a known cause.

- **`KC7`** — the bridge never imports the viewer. Scene assembly runs
  headless, in batch, on machines with no display; a dependency on the
  interactive 3D view would break that at import time, before any work
  started. The renderers for the solid live in a separate file and are
  registered against it from outside.

## Modules

| File | What it holds |
|---|---|
| `ray_tracing_shapely_optiland/scene_bridge.py` | `build_faces_from_profile`, `face_from_span`, `span_outward_ray`, `ExtrudedPolygonSolid`. Only extrusion along one fixed axis and straight two-point spans are supported; anything else raises `NotImplementedError` rather than approximating. |
| `ray_tracing_shapely_optiland/visualization/renderers.py` | `ExtrudedPolygonRenderer2D` and `3D`, drawing the solid in Optiland's viewers. |

## What it produces

- **`P-NSQ-SCENE`** — the built Optiland components and their placements.
  Not a whole assembled scene: the caller adds sources and detectors and
  runs the trace.

## What it needs from elsewhere

- **`P-PROFILE`** from `nonimaging_design` — the `profile.json`.
- **`P-ROLE-MECHANISM`** from `core_labelling` — the vocabulary the mapping
  is keyed on.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-BRIDGE-01` | **Owns** it. Every (role, mechanism) pair maps to a component type, and an unmapped pair raises. |
| `C-BRIDGE-02` | **Owns** it. Only extrusion along the fixed axis, only straight spans; the rest raises. |
| `C-BRIDGE-03` | **Owns** it. The 2D renderer requires the `XZ` projection; the default `YZ` draws nothing useful. |
| `C-BRIDGE-04` | **Owns** it. The solid claims correctly placed faces only, never a validated closed volume. |
| `C-BRIDGE-05` | **Owns** it. This module must never import the viewer. |
| `C-PROFILE-01` | **Relies** on it. The profile carries exact normals, so this side never derives them. |

## How it is shipped

A separate package, `ray_tracing_shapely_optiland`, installed alongside the
core. Requires Optiland.
