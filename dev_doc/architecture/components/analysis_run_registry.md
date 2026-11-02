# `analysis_run_registry`

Saving a simulation run to disk in a form that can be read back and compared
later — by a person, by a script sweeping a parameter, or by a model trained
on many runs, some time from now.

## Concepts this component realises

- **`KB8`** — a saved run describes itself. `persist_run_artifacts` writes
  a folder per run: `params.json` (what the run was set up with),
  `rays.sqlite` (every segment, queryable), `summary.json` (the headline
  numbers), and — when the run was bidirectional — the combined graph and
  the signature table. `manifest.jsonl` gets one line appended per run, so
  a design's whole history is one file. `params.json` also carries a
  fingerprint of the scene's object names, so a later comparison can tell
  whether two runs are even comparable before it starts.

- **`KC3`** — `params.json` keeps two kinds of setting apart. *Physical*:
  refractive index, geometry, wavelength — things about the device.
  *Numerical*: ray density, the brightness below which rays are dropped,
  mesh resolution — things about the simulation. They are in separate
  sections because a reader has to be able to tell them apart: a difference
  between two runs caused by the first kind is real, and one caused by the
  second kind should shrink as the simulation is made finer. A model trained
  on runs where the two were mixed would learn that ray density affects the
  optics.

- **`KD8`** — this is what a parameter sweep leaves behind. Each point in a
  sweep is one run, saved here, and `compare_runs` between consecutive
  points is how a sweep becomes a result. The same call compares two
  different designs, or the same design at two mesh resolutions; it does not
  care why the runs differ, which is what makes it useful for all three.

- **`KD3`** — `compare_runs` refuses before it misleads. It checks the name
  fingerprints first and raises if they differ, because a comparison across
  mismatched names would not be wrong, it would be meaningless, and it would
  look like a result. This has happened twice.

## Modules

| File | What it holds |
|---|---|
| `analysis/run_registry.py` | `persist_run_artifacts`, `compare_runs`, the manifest, the name-topology fingerprint and its check. |
| `analysis/saving.py` | Writing ray segments to CSV and XML, and the filters and statistics over a segment list. |
| `analysis/simulation_result.py` | `SimulationResult`: a run's segments, lineage and scene snapshot, bundled with the settings it ran under. |
| `analysis/targeted_resimulation.py` | Re-running one identified route at high density, by temporarily swapping in a narrow source and restoring the scene afterwards. |

## What it produces

- **`P-RUN-BUNDLE`** — the saved folder: `params.json`, `rays.sqlite`,
  `summary.json`, `manifest.jsonl`, and the graph and signature table when
  present. A schema version separate from the package version is required by
  `C-RUN-01` and not yet written; the contract records that gap.

## What it needs from elsewhere

- **`P-SIGNATURE-SPECTRUM`** from `analysis_signature` — the table it
  persists and diffs.
- **`P-SCENE-NAMES`** from `core_scene_objects` — what the fingerprint is
  built from.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-RUN-01` | **Owns** it. Every bundle carries a schema version independent of the package version. Documented; not yet present in the files. |
| `C-RUN-02` | **Owns** it. Physical and numerical parameters are strictly separated, and a numerical setting never enters a trained model as if it were physics. Checked by a test on what `persist_run_artifacts` writes. |
| `C-CONV-01` | **Owns** the comparison half. A comparison claim is valid only with sampling noise and discretisation kept separate. |
| `C-LABEL-01` | **Enforces** it. The fingerprint is written here and checked here, before any comparison. |

## How it is shipped

Core package.
