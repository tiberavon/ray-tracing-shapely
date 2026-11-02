# `eye_safety`

Is this light source safe to look at, for how long, and in which class?

Two international standards answer that question, for different kinds of
source: IEC 60825-1 for lasers, IEC 62471 for lamps and LEDs. This component
implements both — the exposure limits, the correction factors, the
spectral weighting tables, and the final classification — as functions that
take a measured irradiance or radiance and return a limit, a comparison,
and where the limit came from.

## Why this component is different

It is the one place in the project where a wrong number has a safety
consequence rather than a scientific one. Everywhere else, an error produces
a bad design. Here it produces a source that is labelled safe and is not.
Several decisions below that look like excess caution follow from that.

## Concepts this component realises

- **`KC5`** — every limit the standard defines is implemented, not only the
  ones the examples happen to use. The retinal *photochemical* limit was
  once left out because neither worked example reached it; in the blue
  region it is ten times stricter than the thermal limit that was being
  reported, and nothing in the output said a hazard had been skipped. A
  reader would have seen a pass. It was added, along with the ultraviolet
  and skin limits that neighbour it, on the principle that in this module
  a missing limit is a defect, not a scoping choice.

- **`KC6`** — the two standards are reached through their own names,
  `eye_safety.iec60825_1` and `eye_safety.iec62471`, and neither is
  available at the package top level. For a while the laser standard's
  functions *were* at the top level and the lamp standard's were not, which
  meant the shortest name — the one that autocompletes first — silently
  gave you the laser limits. In a project whose stated audience is LEDs into
  concentrators, that is the wrong default, and a default nobody chose is
  still a default.

- **`KD5`** — limits are checked against the standards' own tables and
  worked cases, not against tests written from the same understanding as the
  code. One risk-group comparison passed its tests and was still wrong,
  because the test and the code agreed on a time base the standard did not
  use. The correction cites the table it came from.

## Modules

| File | What it holds |
|---|---|
| `angular_subtense.py`, `pupil_aperture.py`, `exposure_duration.py` | How large the source appears to the eye, the pupil area to average over, and the durations and time constants the limits depend on. Shared by both standards. |
| `spectral_data.py`, `hazard_functions.py` | Spectral power distributions, and the lamp standard's weighting curves for ultraviolet, blue light and retinal thermal hazard. |
| `correction_factors.py` | The laser standard's wavelength- and duration-dependent factors. |
| `iec60825_1.py` | Laser: maximum permissible exposure, accessible emission limits for each class, and classification. |
| `iec62471.py` | Lamp: exposure limits per hazard and risk-group classification. |
| `radiometry_conversions.py` | Irradiance to radiance and back, given the source's solid angle. |
| `result.py` | `LimitResult`: a limit *with* where it came from — equation, region, time regime, unit. |

## What it produces

- **`P-HAZARD-ROUTINES`** — the limit and classification functions of both
  standards, each returning a `LimitResult` that carries its own provenance,
  so a caller can say not just *the limit is X* but *the limit is X because
  of this equation in this regime*.

## What it needs from elsewhere

- **`P-QUANTITY-PARSING`** from `optical_elements_units` — inputs are
  checked quantities. Internally the formulas work in documented SI base
  units, because they are dense numerical code transcribed against tables
  and the checking is done at the edge.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-EYE-01` | **Owns** it. Spectral weighting tables are interpolated linearly on the logarithm of the tabulated values, as the standard prescribes. Checked by a large test suite. |
| `C-EYE-02` | **Owns** it. A laser classification call resolves the correct time base for its class. The defect that motivated it was in tested code. |
| `C-EYE-03` | **Owns** it. Whether a source is revolved or extruded changes how its apparent size is computed, and the caller declares which. |
| `C-EYE-04` | **Owns** it. The two standards are separate formula families, and neither is reachable without naming it. |
| `C-EYE-05` | **Relies** on it. The state-machine flow's final result must equal what calling `classify_measurement` directly would give; the flow owns that promise. |
| `C-EYE-06` | **Owns** it. The lamp standard's retinal-thermal risk-group comparison uses the standard's own table, after a transcription error was found and corrected against it. |

## How it is shipped

Core package, under `optical_elements/eye_safety/`.
