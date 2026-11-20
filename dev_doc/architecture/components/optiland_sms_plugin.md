# `optiland_sms_plugin`

Registering this project's designed profiles with Optiland as a native
geometry type, so that a curved surface built here can be traced there
without being approximated by flat facets.

**Planned, not built.** The scene bridge already builds exact surfaces
for much of what is designed here: an extruded prism's flat faces, and,
for an element of revolution, conic faces and designed spline faces
(`SplineRevolutionGeometry`) revolved about the axis. What it cannot hand
over is a curved surface that is not a surface of revolution — a freeform
face, an SMS lens extruded or cut into segments. And its spline geometry
is computed in NumPy only and cannot be differentiated, so a designed face
built through it can be traced and checked in 3D but not polished there
(`C-3D-01`). Optiland has a plugin interface for geometry types; this
component would use it for both.

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

- **`P-PROFILE`** from `nonimaging_design` — which exports curved profiles
  for the lenses, collimators, mirrors and the SMS elements, each surface
  with its role and mechanism. For an SMS design the profile is no longer
  the blocker; the differentiable geometry `C-3D-01` asks for is.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-3D-01` | **Will rely** on it. A geometry supplied to Optiland must provide a differentiable backward pass; a mesh built by revolving points is forward-only and does not qualify. |
| `C-PROFILE-01` | **Will rely** on it. |

## How it is shipped

Would live in `ray_tracing_shapely_optiland`. Not shipped.
