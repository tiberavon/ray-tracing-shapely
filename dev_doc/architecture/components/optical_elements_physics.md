# `optical_elements_physics`

Turning the engine's numbers into physical ones.

The engine reports a ray's brightness as a plain number between zero and
one. That is enough to say *this path carries more than that one*, and not
enough to say *how many watts landed on the sensor*. This component adds
what is missing: what the scene's units are, how a 2D cross-section stands
in for a 3D source or detector, and how arriving light becomes an electrical
signal.

## Why this component is different

It is the one place in the stack where a unit label can silently become
wrong while every number stays plausible. A brightness of 0.83 has no unit
and cannot be wrong in that way; an irradiance of 0.83 is either W/m² or
mW/cm² and the difference is a factor of ten. That is why this layer, and
not the engine, is where quantities carry their units and are checked.

## Concepts this component realises

- **`KC1`** — this whole component sits *above* the engine and never reaches
  into it. `PhysicalScene` is a `Scene` with two extra facts attached (the
  unit of a scene coordinate, and a factor linking brightness to W/m). The
  projection models and the conversion classes are separate objects that a
  detector or a source *holds*, not new kinds of detector or source. Nothing
  in `core/` was changed to add any of this.

- **`KC4`** — every quantity here is a number with a unit that is checked
  for the right *kind*. `PhysicalScene`'s calibration factor, a projection
  model's inputs, a photoconversion's responsivity: each goes through
  `ensure_quantity` and is rejected if it is a radiance where an irradiance
  was expected. One class here once carried two different unit conventions
  in two of its own methods, distinguishable only by a suffix in the name,
  with nothing checking either. That is the failure this replaces.

- **`KD3`** — where something is not yet supported, it raises rather than
  approximating. A projection with rotational symmetry (`revolve`) can be
  named but its conversion methods throw `NotImplementedError`, because the
  right factor depends on where along the radius the light lands and the
  current method has no way to be told. A plausible average would have been
  easy to write and wrong to trust.

## Modules

| File | What it holds |
|---|---|
| `optical_elements/physical_scene.py` | `PhysicalScene`: a scene that knows its length unit and its brightness-to-power calibration. |
| `optical_elements/physics/projection.py` | `ProjectionModel` and its concrete forms — how a 2D line stands in for a 3D strip, point or revolved surface. Each declares its `symmetry`. |
| `optical_elements/physics/photoconversion.py` | Light arriving on a detector becomes current, then voltage. |
| `optical_elements/physics/photoemission.py`, `liv_curve.py` | A source's emitted power as a function of drive current. |
| `optical_elements/sensors/linear_sensor.py` | `LinearSensor`: a real linear CCD or CMOS array, built from a `Detector` and a `Blocker`, described by pixel count and pitch. |

## What it produces

- **`P-PHYSICAL-SCENE`** — `PhysicalScene` and `ProjectionModel`. Choosing
  a concrete projection is how brightness becomes W/m and then W/m², and the
  projection's declared symmetry (`extrude`, `free`, or the unimplemented
  `revolve`) is what a 3D comparison would check against.

## What it needs from elsewhere

- **`P-HIT-RECORD`** from `core_scene_objects` — a `LinearSensor` is a
  `Detector` underneath, and reads its hits.
- **`P-QUANTITY-PARSING`** from `optical_elements_units` — every quantity
  entering a class here is validated there.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-UNITS-01` | **Owns** it. Converting to a per-area quantity is only valid for a projection whose symmetry has been declared, and the declaration is checked. |
| `C-UNITS-02` | **Relies** on it. Radiometric quantities are typed and dimension-checked; the checking is done by `optical_elements_units`. |

## How it is shipped

Core package. `PhysicalScene` is optional — a plain `Scene` traces
identically and just has no units.
