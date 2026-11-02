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
| `core/scene_objs/base_scene_obj.py` | `BaseSceneObj`: what every object has in common, including its `.name`. |
| `core/scene_objs/base_glass.py`, `glass/` | Glass, ideal lens, spherical lens. `refract()` is here. |
| `core/scene_objs/base_grin_glass.py` | Glass whose refractive index varies with position. |
| `core/scene_objs/base_custom_surface.py`, `base_filter.py` | Surfaces defined by an equation; wavelength filters. |
| `core/scene_objs/mirror/` | Mirror and ideal mirror. |
| `core/scene_objs/other/detector.py` | `Detector`: a line that counts light crossing it, one-sided by default. |
| `core/scene_objs/blocker/blocker.py` | Absorbs any ray that reaches it. |
| `core/scene_objs/ground_glass.py` | A diffusing surface. |
| `core/scene_objs/light_source/` | Beam, single ray, point source, angle source, and the backward source used to trace from a detector outward. |

## What it produces

- **`P-SCENE-NAMES`** — every object has a `.name`, and every comparison
  between runs relies on those names meaning the same thing in both. This
  component provides the field; it does not check it. A name left empty, or
  a name that changes between runs, breaks comparisons downstream.
- **`P-HIT-RECORD`** — a detector's record of each absorbed crossing, with
  the fields listed under `KB4` above.
- **`P-BEAM-CTOR`** — a beam's construction parameters, in particular
  `emis_angle`: the *full* angle the beam spreads across, in degrees, from
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
| `C-DET-01` | **Makes** it. `Detector.power` counts light arriving from one side only, by default. `two_sided=True` restores the older behaviour of counting both directions as a signed net — which produced a physically impossible negative reading in one real case, and is why one-sided is now the default. |
| `C-HIT-01` | **Makes** it. A hit record carries wavelength and incidence angle. The angle recorded there is the angle at the detector, and is a different field from the one recorded on a ray when it hits a surface and stops. |
| `C-BEAM-01` | **Makes** it. `emis_angle` is a full divergence angle. A negative value used to be accepted silently and flipped the sign of every ray's brightness; it now raises. |
| `C-LABEL-01` | **Provides** the names. Enforcement — refusing to compare runs whose names differ — happens in `analysis_run_registry`. |

## How it is shipped

Core package.
