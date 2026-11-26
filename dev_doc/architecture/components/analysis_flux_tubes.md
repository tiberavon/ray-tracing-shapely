# `analysis_flux_tubes`

Where the light of a design goes, as a few bands instead of a cloud of rays,
those bands traced again on their own after an edit, and what a small edit of
a designed surface does to them before anything is traced. For an SMS design,
also its edge bundles and Map A: how far each edge ray's optical path length
to its target point is from the bundle's mean.

A trace of a source gives hundreds of rays. A designer, or an agent, asks
coarser questions: which part of the source's light reaches the receiver,
by which route, and what an edit did to it. This component cuts each
source's light into K *flux tubes* that each deliver the same share of the
receiver's power, keeps every ray of a tube as a replayable seed, and traces
the seeds again on an edited scene.

## Concepts this component realises

- **`KB3`**: a tube is described by its routes, each a sequence of
  (surface name, edge index, event), the same reduction signatures use, so a
  tube that changed route after an edit is seen as such.
- **`KC3`**: K, the fewest delivering rays per tube, the weak-ray threshold
  and the trace's cap are numerical parameters (`TubeSettings`), given apart
  from the scene.
- **`KB6`**: the sculpt layer's every element carries what it stands for (a
  tube, a bundle and seed, an edge and span, a handle) and the value its
  colour shows, so a caller that cannot see the colours reads the numbers.
- **`KD5`**: checked on the Example 9.1 RR lens of Chaves: the edge rays
  through its designed points have the book's S to round-off.

## Modules

| File | What it holds |
|---|---|
| `analysis/edge_bundles.py` | Edge bundles and Map A (`BundleSpec`, `rr_bundles`: the RR lens's E1 to R2 and E2 to R1; `edge_bundles`, `trace_bundles`; `EdgeBundle` with its mean, spread, rms and per-ray deviation; `BundleSet.map_a`; `BundleSettings`), each ray's S completed to the target point and its miss, and `predict`, the first order of S to the target for a handle's move. |
| `analysis/sculpt_layer.py` | `draw_sculpt_layer`: tubes (a band per route, by Map B), bundle rays (by Map A, a preview optional), surface spans (the mean Map A of the rays meeting each), wavefront isolines and handles (a marker and an outward-normal tick), drawn as an `SVGRenderer`'s `layer-sculpt`, each element with its id and value; `diverging_color`, `sequential_color`, `opl_scale_for`. |
| `analysis/sculpted_glass.py` | `SculptedGlass`, a recipe made of a base recipe and an edit list (`{edge, index, kind, delta}`, by functional label or index), applied to the spline edges' Hermite points and tangents, labels, roles and mechanisms kept; `bake` to a plain `BasePrism` through its profile; `SculptError`. |
| `analysis/first_order.py` | Handles (`handles`, `Handle`: an interior Hermite point of a spline edge, moved along the outward normal or its tangent turned), the edited path (`edited_path`, `edited_descriptor`), and the estimate (`predict`: per arrival, the change of S at its old end point and the turn of its direction at each hit on the moved edge; `turn_factor`; `drag_ratio`, `PREVIEW_LIMIT`; `opl_at_old_end` for comparing with a re-trace). |
| `analysis/flux_tubes.py` | `partition` (trace once, cut each source into tubes), `replay` and `tube_scene` (trace the tubes' seeds again), `TubeSet` with `power_map` (Map B: per tube, its share of the source's power and how much of it is delivered), `FluxTube`, `RaySeed`, `Arrival`, `TubeSettings`. |

**How the rays are cut.** In emission order (a point source by angle, read
round from just after its longest run of rays that deliver nothing; a beam
by position). A delivering ray goes to the tube its cumulative delivered
power falls in. A ray that delivers nothing between two delivering rays of
one tube stays in it, so its loss shows in the tube's delivered fraction; a
run between two tubes is split between them; rays outside the outermost
delivering rays are in no tube (`outside_fraction`).

**The first order.** A ray meeting the moved edge changes its S by
``(p_in - p_out) . dx`` (Fermat), dx the displacement of the spline at the
hit, taken from the curve itself (moving a point rescales its spans'
tangents, which the spline's chord scaling couples to it). Its direction turns
by the refraction's or reflection's factor times the normal's turn where the
ray now meets the surface, the curvature term included.

**Edge bundles.** A fan from a source edge point aimed at the designed
entrance edge, through each knot (a designed point) and between them. A ray is read along the designed route
(entrance refracted, exit refracted); S is summed to the exit and completed
to the target, so a re-traced S needs no end-point correction. Each ray also
carries its miss, the target's distance from its outgoing line, since rays
leaving by one point (the corner the design's first fan aims at) have the
design's S whatever their direction. In the first order of S to the target,
the exit point's slide along the exit surface counts: the completion is not
the ray's outgoing direction, by its aberration.

**An edit is a recipe.** A designed element's outline is not edited by hand
(`KC2`). A `SculptedGlass` makes the edit a requirement: the file holds the
base recipe and the edits, the glass is rebuilt from them, and every copy of a
scene (the tubes', the bundles', the builder's) carries them. An edit that
breaks the outline is refused before the glass exists.

**The drawing.** The sculpt layer is drawn onto a renderer from here, not by
the renderer: `core` does not import `analysis`. A tube is drawn as one band per
route its rays take, between that route's first and last rays: a band between
two routes (a ray through the lens and one that misses it) would cover where no
light went. Map A's scale is symmetric and given by the caller, so one kept for
a session keeps colours comparable across edits; Map B's is fixed, 0 to 1.

**Every ray on its own.** Both traces run on a copy of the scene with an
explicit weak-ray threshold. Under the automatic one, a glass keeps one dim
ray in so many by its index in the emission and amplifies it, so a ray's fate
would depend on its neighbours and no tube could be replayed alone.

## What it produces

- A `TubeSet`, JSON-ready (`to_dict`, `from_dict`): per tube its seeds, its
  boundary rays, its routes and their shares, and every arrival at the
  receiver with its optical path length and power.

## What it needs from elsewhere

- **`P-RAY-LINEAGE`** from `core_simulator`, with the surface hits recorded
  (`record_surface_hits`), and `analysis_lineage`'s optical path length.
- The edge count of `analysis_bidirectional` (`_surface_spans`), so a route's
  edge index is the one signatures use.
- `RaySetSource` from `optical_elements_physics`, to replay the seeds.
- The scene file (`analysis.scene_file`), to copy a scene.
- **`P-SCENE-NAMES`**: tubes find their sources and the receiver by name.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-SCULPT-02` | **Owns** it. The estimate of S and of the direction agrees with a re-trace to second order; its error per unit drag ratio is measured and bounded. |
| `C-SCULPT-03` | **Owns** it. A sculpted glass with no edits is its base; with edits it is rebuilt from the base and the edits alone, labels kept. |
| `C-SCULPT-04` | **Owns** it. An edit that breaks the outline, or names no handle, is refused with the reason, the scene unchanged. |
| `C-SCULPT-05` | **Owns** it. Map A's S reads each segment's index; a segment without one is reported and its ray left out, never counted with n = 1. |
| `C-SCULPT-01` | **Owns** it. A tube replayed on the scene it was cut from gives back every arrival, its route, optical path length and power. |
| `C-LABEL-01` | **Relies** on it: a replay on an edited scene matches routes by name. |
| `C-DET-01` | **Relies** on it: a tube's delivered power is what the receiver counts, signed for a two-sided detector. |
| `C-HIT-01` | **Relies** on it: a route is read from the segments' own surface hits. |

## Known gaps

- A gradient-index glass is refused: its segments do not carry the index
  they travel in, so an optical path length through one would be wrong. No
  gradient-index glass is ported yet.
- Edge bundles are written for the RR lens only (`rr_bundles`); another
  recipe's are added when they are written down and checked against its book
  example.
- Tubes are 2D sections; a revolved optic's skew rays are not in them.
