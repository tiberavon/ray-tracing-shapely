# `analysis_bidirectional`

Tracing light backwards from a detector, joining it up with the forward
trace, and auditing the routes that result.

In a concentrator, most rays from the source never reach the sensor. Tracing
forward means paying for every miss. This component adds a second pass that
starts *at the detector* and traces outward, then finds where the two passes
touched the same surface and joins them. A route from source to detector is
then one path through the combined graph, found by a standard shortest-path
search.

## Concepts this component realises

- **`KB2`** — the second pass. `BackwardDetectorSource` is a temporary
  light source placed along the detector line, aimed back along the
  directions the forward rays arrived from. `connect_trees` finds matches:
  a forward hit and a backward hit on the *same surface*, close together
  along it, with the forward ray's continuation pointing the opposite way to
  the backward ray's arrival. Both "close" and "opposite" are numbers the
  caller sets, because the right values depend on how densely the surface
  was sampled, and a helper reports typical nearest-neighbour distances so
  they can be chosen from the run rather than guessed.

- **`KB1`** — why a graph, and not a tree, was needed. Joining two passes
  gives some segments more than one predecessor, which a tree cannot hold.
  `build_combined_graph` puts forward edges, reversed backward edges, and the
  matches into one graph, adds a single artificial source in front of every
  real source and a single artificial sink behind the detector, and weights
  each edge by how much brightness was lost across it. The maximum-energy
  route from source to detector is then a shortest path — one library call.

- **`KD5`** — the physics of a reversed ray was tested, not assumed. Whether
  a ray is entering or leaving a glass is worked out from geometry, not from
  which way the simulation is going, so a backward ray gets the right
  refraction without any special code. A test fires a ray, reverses it, and
  confirms it retraces its own path.

- **`KD2`** — one piece of this component is documented as having been built
  differently from its plan, on purpose. Reconstructing which surfaces a
  route touched was specified as "look at the next node's event". That is
  only right for forward segments; backward segments have their edges the
  other way round, and applying the rule uniformly would have mis-paired
  every backward hop while producing plausible output. `path_surfaces` looks
  ahead or behind depending on which pass a segment came from.

## Modules

| File | What it holds |
|---|---|
| `analysis/bidirectional.py` | `connect_trees`, `build_combined_graph`, `extract_ranked_paths`, the auditing functions (`path_surfaces`, `audit_paths`, `path_physical_summary`), and the `Connection` and `BidirectionalResult` records. |
| `core/scene_objs/light_source/backward_detector_source.py` | The temporary backward source. It is never saved with a scene. |

## What it produces

Nothing new as a structure. A bidirectional result is still a lineage —
forward and backward segments, connected — so it extends `P-RAY-LINEAGE`
rather than defining a port of its own.

## What it needs from elsewhere

- **`P-RAY-LINEAGE`** from `core_simulator`.
- **`P-HIT-RECORD`** from `core_scene_objects` — the detector's recorded
  hits are what the backward source aims along.
- **`P-SIGNATURE`** from `analysis_signature` — the auditing tools compare
  routes using the same *(surface, edge, event)* tuple.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-MATCH-01` | **Owns** it. A match requires an explicit spatial and angular tolerance; there are no defaults, because a default would be wrong for some sampling density and would not say so. |
| `C-DET-01` | **Found** the problem it fixes. This component's own test fixture — a receiver cavity — produced a negative light reading, which traced back to the detector counting light from both sides as a signed sum. The fix lives in `core_scene_objects`; the case that exposed it lives here. |
| `C-CONV-01` | **Relies** on it. A comparison of two audited routes is only meaningful if the sampling density and the surface discretisation were the same for both. |

## How it is shipped

Core package.
