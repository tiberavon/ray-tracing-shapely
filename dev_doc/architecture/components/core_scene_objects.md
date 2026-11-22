# `core_scene_objects`

The things light interacts with: glasses, lenses, mirrors, detectors,
blockers, and the sources that emit the light in the first place.

Each one is a class that answers the engine's three questions — *get ready*,
*does this ray hit you*, *it hit you, what happens* — and owns the physics of
its own answer. A glass computes refraction and reflection at its surface. A
mirror reflects. A detector records the crossing and lets the ray continue.
A blocker absorbs it. The engine never knows which of these it is talking to.

## Concepts this component realises

- **`KC1`** — every object owns its own physics. `refract()` in
  `base_glass.py` is where Snell's law and the Fresnel equations live; the
  engine calls it and uses what comes back. This is the other half of
  `core_simulator`'s promise: the engine has no optics because the optics
  are all here, each object responsible for exactly one kind of surface.

- **`KC2`** — objects are described by what they are for, not by their
  corners. A `Beam` is given a position, a direction and a divergence angle.
  A `Detector` is given the two ends of a line and a bin size. The objects
  compute their own geometry from that. Coordinates appear, but as the way to
  say *where*, never as a substitute for saying *what*.

- **`KB4`** — a detector keeps which ray hit it. `Detector.hit_records`
  holds, for every crossing that was absorbed, the ray's identifier, which
  bin it landed in, where along the detector, its brightness, its
  wavelength and its incidence angle. Before this was recorded, a detector
  could report *how much* light arrived but not *which paths* brought it,
  and the question a refractometer exists to answer — which routes reached
  the sensor — could not be asked.

## Modules

| File | What it holds |
|---|---|
| `core/scene_objs/base_scene_obj.py` | `BaseSceneObj`: what every object has in common, including its `.name`. Every object also records how it was built: for a constructor that takes requirements rather than a serialized dict, its arguments (`_construction_args`), and the object whose constructor was running when it was made, if any (`_built_inside`: an XR concentrator's primary mirrors). The scene file saves a designed element from that record (`C-SCENE-01`). A class's `legacy_keys` maps a key an earlier version of this package saved under another name to the current one, which is the JavaScript simulator's: the old name still loads, with a `DeprecationWarning`, and is never saved (`Glass`: `cauchy_b` to `cauchyB`). Each class also lists its editable properties, `property_schema()`: the JavaScript simulator's `getPropertySchema`, in its order, each entry a key path, a type (`PROPERTY_TYPES`), upstream's English label and, split out of it, a display unit; Python-only entries come last, marked `python_only`. |
| `core/key_path.py` | `get_by_key_path` and `set_by_key_path`: a schema entry's key path (`"p1"`, `"path.3.arc"`, `""` for the object itself) read or written on a scene object or its serialized dict, by upstream's rules. |
| `core/scene_objs/base_glass.py`, `glass/` | Glass, ideal lens, spherical lens. `refract()` is here. A `Glass`'s outline is straight edges and circular arcs, as the JavaScript simulator's; one with a `curve` edge is refused. A glass with exact curved edges is a `CurvedGlass` (`optical_elements/curved_glass.py`), saved under its own type. |
| `core/glass_spans.py` | A glass outline read as its physical surfaces: one span per straight edge, whole arc, or curve edge, numbered in outline order. Everything downstream that counts edges — the analysis layer, signatures, the profile export — counts these. |
| `core/glass_curves.py` | The exact curve edges: `ConicCurve`, `AsphereCurve` (the even asphere: a conic plus a polynomial in s², coefficients in Zemax's and Optiland's order; a line's meeting points bracketed within the edge's sag bounds and refined, a grazing double crossing documented) and `SplineCurve` (a curve through given points with given directions). Where a ray meets one, its normal there, its length, and points along it. Plain geometry, no Shapely, so the glass can depend on it. |
| `core/scene_objs/base_grin_glass.py` | Glass whose refractive index varies with position. |
| `core/scene_objs/base_custom_surface.py`, `base_filter.py` | Surfaces defined by an equation; wavelength filters. |
| `core/scene_objs/mirror/` | Mirror and ideal mirror. |
| `core/scene_objs/other/detector.py` | `Detector`: a line that counts light crossing it, two-sided by default as the JavaScript simulator's; its `power` keeps the crossing's sign, so it tells which way the light goes (`C-DET-01`). The sensor built on it, `Photodetector`, is in `optical_elements/sensors/`. |
| `core/scene_objs/blocker/blocker.py` | Absorbs any ray that reaches it. |
| `core/scene_objs/light_source/` | Beam, single ray, point source, angle source. (The backward source used to trace from a detector outward is in `analysis/`.) |

## What it produces

- **`P-SCENE-NAMES`** — every object has a `.name`, and every comparison
  between runs relies on those names meaning the same thing in both. This
  component provides the field; it does not check it. A name left empty, or
  a name that changes between runs, breaks comparisons downstream.
- **`P-HIT-RECORD`** — a detector's record of each absorbed crossing, with
  the fields listed under `KB4` above.
- **`P-BEAM-CTOR`** — a beam's construction parameters, in particular
  `emisAngle`: the *full* angle the beam spreads across, in degrees, from
  0 to 180. It is halved internally; it is not a half-angle and not an angle
  of incidence.

## What it needs from elsewhere

`P-SCENE-PROTOCOL` from `core_simulator` — the three questions. This
component implements them rather than consuming them.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-CORE-01` | **Implements** it. Each object owns its physics. |
| `C-CORE-02` | **Makes** it. A detector never ends a ray. A crossing that is not absorbed changes nothing on the detector and nothing on the ray. |
| `C-DET-01` | **Makes** it. `Detector.power` is the signed flux across the line: both directions by default (`twoSided`, as the JavaScript simulator's), so light going both ways partly cancels; with `twoSided: false` only rays from the front (`absorbingSide`) meet it at all. A sensor's reading is `Photodetector.power`, the absorbed power, never negative. |
| `C-HIT-01` | **Makes** it. A hit record carries wavelength and incidence angle. The angle recorded there is the angle at the detector, and is a different field from the one recorded on a ray when it hits a surface and stops. |
| `C-BEAM-01` | **Makes** it. `emisAngle` is a full divergence angle. A negative value used to be accepted silently and flipped the sign of every ray's brightness; it now raises. |
| `C-LABEL-01` | **Provides** the names. Enforcement — refusing to compare runs whose names differ — happens in `analysis_run_registry`. |

## How it is shipped

Core package.
