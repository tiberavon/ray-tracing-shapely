# `optiland_nsq_run_registry`

Saving a 3D trace to disk in a form that can be queried, the same way
`analysis_run_registry` saves a 2D one.

## Concepts this component realises

- **`KB8`** — a saved 3D run is a sibling of a saved 2D run, not a variant.
  A 3D trace records *events* — a ray at a point, with a direction, a flux
  and a bounce count — while the 2D engine records *segments* with
  precomputed relationships to glasses and edges. Forcing one table to hold
  both would mean either dropping real 3D fields or inventing 2D-only ones.
  So there are two schemas, side by side, in the same `design/run/` folder
  layout with the same `params.json`. The saved run carries the exact
  settings it was traced with, including whether path recording was on,
  because a reader later cannot tell an empty run from a run that recorded
  nothing.

- **`KA6`** — the same query surface as the 2D registry. `execute_query`
  is reused unchanged, because it does not care what the tables are called;
  `get_nsq_schema_description` describes the 3D columns so an assistant can
  write queries against them without guessing.

- **`KD4`** — this database was the subject of a test of whether an
  artefact explains itself. A separate assistant was handed only the
  `.sqlite` file — no notebook, no schema description, and told not to read
  any source that might describe it — and asked one question about which
  surfaces rays reached. It worked out the schema from the file, answered,
  and its answer differed from the notebook's. The difference was real, and
  tracing it found a structural fact neither query had been written to look
  for.

## Modules

| File | What it holds |
|---|---|
| `ray_tracing_shapely_optiland/nsq_db.py` | `create_nsq_database`, `persist_nsq_run`, `get_nsq_schema_description`, and the reused `execute_query`. |

## What it produces

- **`P-NSQ-RUN-BUNDLE`** — `nsq_events.sqlite` with one events table (ray
  id, event type, position, direction, flux, wavelength, bounce, component
  name) and `params.json`, in the same folder layout as a 2D run bundle.

## What it needs from elsewhere

- The traced scene from Optiland, via `optiland_scene_bridge`.
- `execute_query` from `analysis_run_registry`, unchanged.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-NSQ-RUN-01` | **Owns** it. A run is never saved with an empty events table unless path recording was genuinely off — an empty table is otherwise a silent failure. |
| `C-NSQ-RUN-02` | **Owns** it. The exact `record_paths` setting used is written into `params.json`. |
| `C-NSQ-RUN-03` | **Owns** it. The query machinery stays table-name-agnostic, so the 2D and 3D databases share one implementation. |
| `C-RUN-01`, `C-RUN-02` | **Relies** on them. Same schema-versioning promise and same physical/numerical split as the 2D bundle. |

## How it is shipped

In `ray_tracing_shapely_optiland`.
