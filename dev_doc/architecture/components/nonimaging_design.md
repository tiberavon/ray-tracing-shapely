# `nonimaging_design`

Building the shapes of concentrators and lenses from the rules that define
them, rather than drawing them.

A nonimaging optic — a concentrator that gathers light from a range of
angles onto a small receiver — has a shape that follows from what it must
do: the acceptance angle, the receiver size, the refractive indices. Those
shapes have published construction methods. This component implements the
methods, so that a caller states the requirement and gets the geometry.

## Concepts this component realises

- **`KC2`** — every class here is constructed from its optical requirement.
  A `DTIRCPrism` takes an edge angle and a wall count. A `RefractometerPrism`
  takes two refractive indices and the internal path length, and derives
  every vertex so that a ray entering square-on strikes the measuring
  surface at exactly the critical angle. Below a certain critical angle the
  shape degenerates, and the constructor raises rather than producing a
  trapezoid with a negative base.

- **`KD5`** — the construction primitives are tested against the textbook.
  `nonimaging_geometry.py` holds the book's own building blocks — line
  intersection, vector refraction, constant-optical-path point construction
  — and the tests compare their output to the intermediate values the book
  publishes for its worked examples. The reference material is the test
  oracle, which is rare and worth having.

- **`KD9`** — the chapters those methods come from are transcribed in the
  private repository and never published. The code, the citations by
  chapter and section, and the tests against published values all ship. The
  text does not.

- **`KA1`** — each element's surfaces carry a role and a mechanism. A
  `RefractometerPrism` knows which edge is its entrance face and that light
  refracts there. This is what a downstream 3D bridge dispatches on, and
  what a signature is written in. The curved SMS-family classes do not carry
  these tags yet, which is why a curved profile cannot be exported.

## Modules

| File | What it holds |
|---|---|
| `base_prism.py`, `equilateral.py`, `right_angle.py`, `refractometer.py` | The prism family. `BasePrism` owns the two-label scheme and the profile walk. |
| `dtirc.py`, `angle_transformer.py` | A dielectric total-internal-reflection concentrator, and a four-mirror angle transformer — the book's worked examples. |
| `rxi.py`, `rxi_direct.py` | A closed-form RXI dome, and the direct-method construction of the true RXI profile. |
| `sms_chain.py`, `rr_lens.py`, `rx_concentrator.py` | The simultaneous-multiple-surface chain and the two lens families built with it. |
| `nonimaging_geometry.py` | The book's construction primitives. |
| `prism_utils.py`, `tir_utils.py` | Dispersion formulas, critical-angle helpers, and the derivation behind the refractometer's constructor. |
| `profile_export.py` | Writing a `profile.json` for the 3D bridge. |

## What it produces

- **`P-PROFILE`** — a `profile.json`: for each span of the outline, its two
  endpoints and the exact outward normal at each, its role and mechanism,
  a symmetry declaration saying how the 2D outline becomes a 3D solid, and
  the physical/numerical parameter split. Built for straight-edged
  profiles; curved profiles have the internal data but not the tags.

## What it needs from elsewhere

- **`P-ROLE-MECHANISM`** from `core_labelling` — the words each surface is
  tagged with.
- `core_scene_objects`'s glass classes — every element here *is* a glass,
  with a computed outline.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-PROFILE-01` | **Owns** it. A profile handoff carries position and exact normal per span, plus the construction parameters, so the receiving side never has to re-derive a normal from neighbouring points. |
| `C-LABEL-02` | **Implements** it. The class owns each surface's role; the template that assembles a compound device owns how they compose. |

## How it is shipped

Core package, under `optical_elements/prisms/`.
