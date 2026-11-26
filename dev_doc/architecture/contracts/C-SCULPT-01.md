---
id: C-SCULPT-01
title: A flux tube's seeds, traced again on the scene it was cut from, give back every arrival with its route, optical path length and power
parties:
  provides: analysis_flux_tubes (flux_tubes.partition, flux_tubes.replay)
  relies:   whoever edits a design by its tubes (a person in the builder, an agent), and whatever compares a tube before and after an edit
binds: analysis_flux_tubes (flux_tubes.py)
port: null
viewpoint: behavioural
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flux_tubes.py::test_the_seeds_replayed_give_back_every_arrival
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flux_tubes.py::test_the_tubes_deliver_equal_shares; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flux_tubes.py::test_light_lost_inside_a_tube_stays_in_it
tracked_by: null
conflicts_with: null
refines: null
rationale: KB3
since: 0.4
---

# C-SCULPT-01 — A replayed tube is the tube it was cut as

**Assumptions.** The scene a tube set is replayed on is the scene it was cut
from, or an edit of it in which the receiver and the other objects keep their
names (`C-LABEL-01`). No gradient-index glass is in it: its segments do not
carry the index they travel in.

**Guarantees.**
- `partition` traces a copy of the scene with an explicit weak-ray threshold
  (`TubeSettings.min_brightness_exp`), so every emitted ray is traced on its
  own: its fate does not depend on its index in the source's emission, as it
  would under the automatic threshold's adaptive sampling.
- `replay` traces the tubes' seeds, one `RaySetSource` per tube, on a copy of
  the scene with the same threshold. On the scene the tubes were cut from,
  each tube's arrivals come back one for one: the same seed, the same route
  (surface, edge index, event), an optical path length equal to 1e-9 and a
  power equal to 1e-12. So do the delivered fraction and the signature.
- On an edited scene, the difference between a tube's arrivals and its
  replay's is the edit's effect, and nothing else's.

**Invariants.** A seed is an emitted ray's start, unit direction and
brightness (s + p, scaled into a replay source's (0, 1] by the set's
`brightness_scale`, undone in the replay's powers). A polarised source ray
is refused: a replayed ray is unpolarised.

**Units and frames.** Positions and optical path lengths in scene units;
powers in the source's brightness, as the receiver counts them (signed for
a two-sided detector, `C-DET-01`).

**If the assumption is violated.** Silent if a renamed object leaves a route
unmatched: the replay would report the route as gone. A gradient-index glass,
a duplicated name, a receiver that is not a detector and a trace stopped by
its cap are refused, loudly, before anything is cut.

**Checked by.** `test_flux_tubes.py`: on the Example 9.1 RR lens (Chaves),
a point source at E1 cut into 8 tubes and replayed; every arrival compared.
