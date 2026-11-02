# `analysis_signature`

Reducing a route to a short description that means the same thing in a
different run, so that two designs can be compared.

Two runs share no identifiers — every ray and every surface gets a new one
each time. What they can share is a *description*: this route entered
through the entrance face, reflected off the third wall segment, and left
through the exit. This component turns every route into that description
and turns a whole run into a table of descriptions with the energy each one
carried.

## Concepts this component realises

- **`KB3`** — the reduction. `path_signature` takes a route and returns a
  tuple of *(surface name, edge index, what happened)* for each interaction
  along it. `signature_spectrum` takes every route in a run and adds up the
  energy per signature. `diff_signature_spectra` subtracts one run's table
  from another's. A design change shows up as routes appearing, vanishing,
  or shifting energy — readable in a way a shift in thousands of individual
  brightnesses is not.

- **`KA1`** — the words in a signature are the functional labels. *Entrance*
  and *wall* and *absorber* come from the role vocabulary, and the *what
  happened* comes from the mechanism vocabulary. If two designs named their
  collecting surface differently, their signatures could never match, and
  the comparison would report "no shared routes" — which looks identical to
  "no difference". This is why stable naming is a checked promise rather than
  advice.

- **`KD2`** — a known imperfection is documented rather than hidden.
  `path_signature` pairs each node with the event that *created* that
  segment, which happened at the previous node's surface — one hop off.
  `path_surfaces` in `analysis_bidirectional` is the corrected version. Both
  exist because the uncorrected tuple is what everything downstream already
  consumes, and its docstring says so.

## Modules

| File | What it holds |
|---|---|
| `analysis/signature_analysis.py` | `path_signature`, `signature_spectrum`, `diff_signature_spectra`. |

## What it produces

- **`P-SIGNATURE`** — the *(surface name, edge index, interaction)* tuple.
  The edge index is a position along a curved surface that was approximated
  by straight segments, so two designs can only be compared if they were
  discretised the same way.
- **`P-SIGNATURE-SPECTRUM`** — the saved table, `signature_spectrum.json`.
  Its energies rank routes against each other; they are not calibrated
  amounts of light unless something else calibrates them.

## What it needs from elsewhere

- **`P-RAY-LINEAGE`** from `core_simulator`.
- **`P-SCENE-NAMES`** from `core_scene_objects` — this component is the
  reason that port's stability matters.
- **`P-ROLE-MECHANISM`** from `core_labelling` — the spelling of the
  interaction names, which must match what the engine wrote.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-SIG-01` | **Owns** it. A signature is the tuple above; comparing two requires the same discretisation. |
| `C-SIG-02` | **Owns** it. Signature energies rank; they are not throughput. |
| `C-LABEL-01` | **Relies** on it, and is the sharpest case of what breaks silently without it. Enforcement happens in `analysis_run_registry`, which refuses to compare runs whose names differ before this component's functions are reached. |
| `C-VOCAB-01` | **Relies** on it. The interaction spellings. |

## How it is shipped

Core package.
