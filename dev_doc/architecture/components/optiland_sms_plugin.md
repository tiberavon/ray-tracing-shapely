# `optiland_sms_plugin`

Registering this project's designed profiles with Optiland as a native
geometry type, so that a curved surface built here can be traced there
without being approximated by flat facets.

**Planned, not built.** The scene bridge handles straight-edged profiles by
building one flat face per span. A curved profile — an RR lens or an RXI —
would need many facets to approximate, and the approximation is itself a
source of error. Optiland has a plugin interface for geometry types; this
component would use it to hand over the exact curve.

## Concepts this component realises

- **`KB7`** — the third of the three reasons Optiland was chosen: it has a
  geometry plugin interface at all. Without one, a designed curve could only
  be traced in 3D as a stack of flat pieces, and the question *does the 2D
  design survive in 3D* would be muddied by the question *how fine was the
  faceting*.

- **`KC2`** — a profile handed over as a plugin keeps its construction
  parameters. The receiving side gets the shape and what it was built from,
  which is what a differentiable tracer needs to polish the design rather
  than only trace it.

## Modules

None yet.

## What it produces

- **`P-OPTILAND-PLUGIN`** (planned) — the registered geometry type.

## What it needs from elsewhere

- **`P-PROFILE`** from `nonimaging_design` — which cannot yet export a
  curved profile, because the curved classes do not carry role and
  mechanism tags. That is the actual blocker.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-3D-01` | **Will rely** on it. A geometry supplied to Optiland must provide a differentiable backward pass; a mesh built by revolving points is forward-only and does not qualify. |
| `C-PROFILE-01` | **Will rely** on it. |

## How it is shipped

Would live in `ray_tracing_shapely_optiland`. Not shipped.
