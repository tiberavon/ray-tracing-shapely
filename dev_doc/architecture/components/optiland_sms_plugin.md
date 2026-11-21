# `optiland_sms_plugin`

Registering this project's SMS lens surfaces with Optiland's sequential
engine as a native surface type, `sms_spline`, so that a designed lens can be
traced there exactly, and differentiated.

Shipped as its own distribution, `optiland-sms`. It depends on Optiland
only: it reads a `profile.json`, and does not import this project's core.

## What it is for, and what it is not

A refraction-only lens whose faces are surfaces of revolution, such as an RR
lens, in Optiland's **sequential** engine, where the torch backend makes a
trace differentiable.

It does not serve:
- **mirrors and total internal reflection** (the RX, XR, RXI): a sequential
  trace meets its surfaces in a fixed order, and loses a ray at total
  internal reflection;
- **the non-sequential engine:** Optiland's plugin interface registers
  geometries with the sequential engine's factory only. The non-sequential
  engine converts each geometry by its class and refuses one it does not
  know. Designs traced there go through the scene bridge, whose spline and
  asphere geometries are exact but forward-only (`C-3D-01`);
- **faces made of more than one span**, or faces that are not surfaces of
  revolution.

## Concepts this component realises

- **`KB7`** — the third of the three reasons Optiland was chosen: it has a
  geometry plugin interface. A designed curve is traced in 3D as itself, not
  as a stack of flat pieces, and through Optiland's own intersection solve,
  which gives the gradient.

- **`KC2`** — the surface keeps what it was built from: the profile and the
  span's label, in its dictionary form, and the spline's points as its
  parameters. The points are what a gradient is taken with respect to.

## Modules

- **`meridian`** — `read_meridian(profile, label, reverse=)` reads one spline
  span of a revolve profile into a surface's (r, z) frame: r from the axis,
  z along it from the span's vertex. It reports the vertex (where the curve
  meets the axis, between its points) and the rim radius, from which a
  system's thicknesses and apertures are set. It refuses what is not one
  spline span from the axis to the rim, with its radius strictly monotonic
  (`C-PLUGIN-01`).
- **`geometry`** — `SMSSplineGeometry`, an Optiland `NewtonRaphsonGeometry`.
  Its sag is the span's cubic Hermite curve: the piece holding the radius is
  found, the curve's parameter there by Newton's method, detached, then one
  attached step, so the derivative is the implicit one; the sag is the
  curve's z there. The normal comes from the curve's tangent. Beyond the rim
  the sag continues along the rim's tangent. Written with Optiland's backend
  operations only, so it runs on numpy and torch.
- **`register`** — `register()`, the target of the `optiland.surfaces` entry
  point: it adds `sms_spline` to Optiland's `GeometryFactory`, with the
  arguments `profile`, `span`, `reverse`, `tol` and `max_iter`.

## What it produces

- **`P-OPTILAND-PLUGIN`** — the surface type `sms_spline`.

## What it needs from elsewhere

- **`P-PROFILE`** from `nonimaging_design`: a revolve profile whose lens
  faces are spline spans (`C-PROFILE-01`).
- **Optiland 0.6.3 or later**, the first release whose Newton–Raphson
  geometries give exact first-order gradients through the intersection.
  The torch backend for gradients (the `torch` extra).

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-PLUGIN-01` | **Makes** it: the surface is the span's own curve, or the profile is refused. |
| `C-3D-01` | **Makes** it for the sequential engine: the trace is differentiable with respect to the spline's points. |
| `C-PROFILE-01` | **Relies** on it: exact samples, normals and spline spans. |

## How it is shipped

The `optiland-sms` distribution: the modules above, and its tests on the RR
lens of Chaves's Example 9.1 (a `profile.json` fixture, with the script that
writes it from this project's core).
