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
  sweep is one run, saved here (the `parameter_study` flow saves one per
  point, in a job, not a notebook), and `compare_runs` between consecutive
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
| `analysis/run_registry.py` | `persist_run_artifacts` (from a scene and result, or copying an agentic context's database as it stands), `compare_runs` and `compare_run_dirs` (the same, given two folders), the manifest, the name-topology fingerprint and its check. |
| `analysis/saving.py` | Writing ray segments to CSV and XML, and the filters and statistics over a segment list. |
| `analysis/simulation_result.py` | `SimulationResult`: a run's segments, lineage and scene snapshot, bundled with the settings it ran under. |
| `analysis/targeted_resimulation.py` | Re-running one identified route at high density, by temporarily swapping in a narrow source, silencing the scene's other sources, and restoring the scene afterwards: its sources, its settings and its detectors' measurements. |
| `analysis/targeted_resimulation_flow.py` | The same as a flow an agent starts by name (`targeted_resimulation`): the context, the ranked path, the source, the rays and cone, where it runs, the estimate; the run in the kernel, or in chunks on `in_process`, `local_process` or `modal` (`C-AGENT-07`); its result a new named context and a saved bundle, and the rays at the detector grouped by their path's interactions (`C-AGENT-06`). |
| `analysis/portable_scene.py` | A live scene's optical objects as plain data a job rebuilds: a designed element as its profile, any other object as its class and its `serialize()`, each with its name; checked by rebuilding it here, and refused by name when it cannot be mapped back (`C-AGENT-07`). |
| `analysis/scene_file.py` | A whole scene as a file and back (`save_scene`, `load_scene`, `scene_to_dict`, `scene_from_dict`): the settings and every object in order, sources and detectors included. A primitive is written as its `serialize()` under the JavaScript simulator's type name; a designed element as a **recipe**, its constructor and the arguments it was built with, so opening the file builds it again from its requirement (`KC2`); a part of an element as a reference to the element. Every object is rebuilt from what will be written and compared before anything is written (`KD3`), and refused by name if it would not come back the same (`C-SCENE-01`). `list_recipes`, `recipe_parameters` (a constructor's parameters, as a form asks them) and `register_recipe` for a package outside the core. |
| `analysis/parameter_study.py` | One scene file, a parameter of it changed: a designed element's recipe argument (rebuilt from its requirement, `KC2`), a primitive's number in its `serialize()` (its type's defaults filled in), or any object's `rotate_deg`, `move_x`, `move_y` (an element's parts with it). `parameter_table` lists them all; `sweep_axes` checks a sweep (one axis, or two as a grid, at most 400 points); `build_point`, `trace_point` and `read_detector` give a point's power, share of the emitted power, power-weighted position along the detector and, when asked, its bins; `study_points_job` traces some points in a job, a point that fails recorded with its reason, each saved as a run bundle when asked. A finished study is read back, live or from its run's folder, as rows (`study_rows`), a markdown table (`study_table_markdown`) or numpy arrays, one a column, a failed point's readings NaN and a two-axis study shaped as its grid (`study_arrays`; the flow also saves them as `arrays.npz`). |
| `analysis/parameter_study_flow.py` | The same as a flow started by name (`parameter_study`): the scene file, built and checked (a source, a detector, every object named); the sweep, the scene built at its ends before anything is traced (`KA9`); the detector and what is read on it, with the ray settings; the executor; an estimate from a pilot of the first point's rays, asked over a minute. The points as one group step (`in_process`, `local_process` sharing them among one worker per two cores, or `modal`); a table, a plot, and each point a run, its swept values physical parameters and its ray settings numerical (`KC3`). |
| `analysis/ray_jobs.py` | 2D rays simulated as jobs: `simulate_rays_2d_job` (sums that merge: the flux by exit angle; its elements from profiles, plus optional absorbers, segments that stop a ray, so a mirror's back face can absorb) and `simulate_rays_2d_segments_job` (a chunk's segments and detector hits, as columns); `sample_source_rays`, `chunk_rays`, and `merge_segment_results`, the chunks as one `SimulationResult` mapped back to the live scene by name. |

## What it produces

- **`P-RUN-BUNDLE`** — the saved folder: `params.json`, `rays.sqlite`,
  `summary.json`, `manifest.jsonl`, and the graph and signature table when
  present. A schema version separate from the package version is required by
  `C-RUN-01` and not yet written; the contract records that gap.
- **`P-SCENE-FILE`** — a scene saved whole: its settings and its objects,
  designed elements as recipes, with a schema version of its own.

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
| `C-AGENT-06` | **Makes** it, with `agentic_layer`. The re-simulation leaves the scene as it was and its result beside the run. |
| `C-RUN-03` | **Owns** it, with `optiland_nsq_run_registry`. `persist_run_artifacts` refuses a folder that holds another engine's run, rather than overwrite its `params.json`. |
| `C-AGENT-07` | **Makes** it, with `flows`. A re-simulation sent out in chunks is the run in the kernel; the scene goes as plain data and comes back mapped by name. |
| `C-SCENE-01` | **Owns** it. A scene file opens as the scene that was saved: the same objects, names and rays; a designed element rebuilt from its recipe; an object that would not come back the same refused before anything is written. |
| `C-AGENT-05` | **Makes** it, with `agentic_layer`. What an agentic context was reading is what is saved, so a run loaded back answers as it did live. |

## How it is shipped

Core package.
