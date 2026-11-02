# `analysis_lineage`

Questions you can ask a finished simulation about *paths* — the routes light
took, rather than individual rays.

After a run, every segment knows its parent. Following parents back from any
segment gives the whole route from a source to that point. This component
holds the functions that walk those routes: which ones carry the most
energy, where light splits, where it gets trapped bouncing, how far it
travelled, and in what direction it finally left.

## Concepts this component realises

- **`KB1`** — everything here is a walk over the lineage graph.
  `rank_paths_by_energy` follows each leaf back to its source and sorts the
  routes by the brightness that arrived. `detect_tir_traps` looks for
  segments whose ancestry contains many consecutive total internal
  reflections — light that got in and could not get out.
  `check_energy_conservation` compares each segment's brightness to the sum
  of its children's. None of these would be a short function over a flat
  list; each is a few lines over a graph.

- **`KB4`** — the two path-length functions exist because the engine now
  keeps the medium index on every segment. `geometric_path_length` adds up
  the lengths of the segments along a route. `optical_path_length` adds
  each length multiplied by the refractive index the segment was travelling
  through, which is what a time-of-flight measurement responds to. Before
  the index was recorded, the second number could not be computed at all.
  They are deliberately not named `path_length`, because that word already
  means *number of segments* in this module's ranking output.

## Modules

| File | What it holds |
|---|---|
| `analysis/lineage_analysis.py` | Six functions: energy ranking, branching statistics, trap detection, angular distribution and its histogram, energy conservation; plus the two path-length functions. |

## What it produces

Nothing that other components depend on as a structure. Every function
returns plain numbers, lists or records. This is a consumer of the lineage,
not a producer of a new thing.

## What it needs from elsewhere

- **`P-RAY-LINEAGE`** from `core_simulator` — the whole module is built on
  `RayLineage`'s *give me the full path*, *give me the children*, *give me
  the leaves*.
- **`P-HIT-RECORD`** from `core_scene_objects` — the natural way to use the
  path-length functions is over a detector's recorded hits: *for each ray
  that reached the sensor, how far did it travel optically*.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-SIG-01` | **Relies** on it, loosely. The `path_types` list in a ranking result — the sequence of events along a route — is the same information a signature is built from, but the signature itself is built in `analysis_signature`. |

No contract names this module as its main party. One is missing: an optical
path length silently falls back to the geometric one for any segment that
has no recorded medium index, and nothing states that. It is noted rather
than invented here.

## How it is shipped

Core package.
