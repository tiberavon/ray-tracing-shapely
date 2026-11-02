# `optical_elements_units`

One place where a number-with-a-unit is read, checked and handed on.

Everything physical in this codebase is a *quantity* — a number and a unit
together, using the Pint library, which knows that 30 mW/cm² and 300 W/m²
are the same irradiance and that neither is a radiance. This component owns
the single unit registry, the function that turns text into a quantity, the
function that checks a quantity someone already has, and the named list of
what kinds of quantity the physical layer uses.

## Concepts this component realises

- **`KC4`** — the check is on the *kind* of quantity, not the unit spelling.
  `ensure_quantity(value, IRRADIANCE)` accepts W/m² or mW/cm² and rejects
  W/(m²·sr). Unit conversion is arithmetic and the library does it; mixing
  up an irradiance with a radiance is a physics mistake, and that is what
  the check catches. A subtlety found while building this: the library
  treats angles and solid angles as dimensionless by default, so irradiance
  and radiance looked *identical* to it. A stricter pair,
  `ensure_radiometric_quantity` and `parse_radiometric_quantity`, exists to
  tell them apart.

- **`KA9`** — `parse_quantity` is the checkpoint for text coming from an AI
  assistant. It takes a single string such as `"30 mW/cm^2"`, not a number
  and a separate unit, because a caller that fills in one and forgets the
  other produces something that looks complete. One string cannot be half
  supplied. It either becomes a checked quantity or fails.

- **`KA3`** — all failures become the same ordinary error. The library
  raises its own unusual exception type for a malformed unit string; this
  component converts that to a plain `ValueError`, so the standard
  error-catching every tool already does needs no special case for units.

## Modules

| File | What it holds |
|---|---|
| `optical_elements/units.py` | `ureg` (the registry), `Quantity`, `parse_quantity`, `ensure_quantity`, the stricter radiometric pair, and the named dimensionality constants: `POWER`, `IRRADIANCE`, `RADIANCE`, `RADIANT_EXPOSURE`, `LENGTH`, `TIME`, `VOLTAGE`, `PHOTOSENSITIVITY`, `SOLID_ANGLE`, `ANGLE`, and others. |

## What it produces

- **`P-QUANTITY-PARSING`** — two entry points for two callers.
  `parse_quantity(text, expected_kind)` for text arriving from outside;
  `ensure_quantity(value, expected_kind, name=...)` for code that already
  holds a quantity and only needs it validated. Both fail with a
  `ValueError` and a message naming what was expected.

## What it needs from elsewhere

Nothing from this codebase. The Pint library.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-UNITS-02` | **Owns** it. Every radiometric-layer quantity is Pint-typed and dimension-checked on entry; scene geometry (coordinates, pixel pitch) is explicitly excluded and stays a plain number. |

## How it is shipped

Core package.
