"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Targeted Re-simulation (Ray Lineage, 15_p9 Tier 1)
===============================================================================
Given a path already identified as interesting (typically via
analysis.signature_analysis.audit_paths / path_surfaces,
dev_doc/roadmap/proposed/15_p8_bidirectional_path_auditing.md), build a
narrow secondary AngleSource reproducing just that path's entry condition
and re-run it in isolation at much higher density -- "get more samples of
exactly this class," without touching the original run's energy budget.

Sibling of analysis.bidirectional / analysis.signature_analysis (own module,
not folded into either), because it needs core.simulator.Simulator and
mutates a live core.scene.Scene -- a different kind of dependency than the
pure graph/lineage reductions those two modules stick to.

Scene-isolation design (resolved here, not speculated on any more -- see
dev_doc/roadmap/proposed/15_p9_targeted_resimulation_and_importance_sampling.md's
"Open questions"): every BaseSceneObj stores `self.scene` ONCE at
construction and never re-reads it from whatever Scene container currently
holds it (confirmed: base_glass.py/glass.py read self.scene.simulate_colors/
color_mode/min_brightness_exp/grazing_*_threshold/length_scale/rng()
throughout their ray-interaction code, not just UI methods). So wrapping
REUSED glass/detector instances in a second, lightweight Scene would silently
run their physics against the ORIGINAL scene's config regardless of anything
set on the new wrapper -- exactly wrong for this feature's own precondition
(relaxing min_brightness_exp so a rare class isn't pruned again). The
targeted source is therefore built against the SAME live Scene, and
run_targeted_resimulation() swaps it in for the original source, runs, and
restores -- there is never more than one Scene object involved.
===============================================================================
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.scene import Scene
    from ..core.scene_objs.light_source.angle_source import AngleSource
    from ..analysis.bidirectional import BidirectionalResult
    from ..analysis.simulation_result import SimulationResult


def targeted_source_for_path(
    path_dict: Dict[str, Any],
    result: 'BidirectionalResult',
    original_source: 'AngleSource',
    *,
    cone_half_angle_deg: float = 1.0,
    brightness: Optional[float] = None,
) -> 'AngleSource':
    """
    Build a narrow AngleSource reproducing one identified path's entry
    condition (15_p9 Tier 1).

    Same origin and reference direction as the path's own forward root
    (``path_dict['path_uuids'][0]``, always the true light-source-emitted
    ray -- see analysis.bidirectional._summarise_path), so the returned
    source's fan is centred exactly on the ray that produced this path, not
    a re-derived approximation. Symmetric fan of full width
    ``2 * cone_half_angle_deg`` instead of ``original_source.emis_angle``.

    brightness defaults to ``original_source.brightness`` (unchanged total
    flux concentrated into a narrower cone -- deliberately NOT re-normalized,
    since Tier 1 studies this class on its own terms, not as a
    statistically-corrected contribution to the whole scene's energy budget;
    that correction is what Tier 2's per-ray weight field is for, not this
    function).

    Args:
        path_dict: One entry from extract_ranked_paths()/audit_paths()'s
            flagged_paths -- must have 'path_uuids' whose first element is
            the path's forward root uuid.
        result: The BidirectionalResult path_dict was extracted from
            (needs .forward_lineage to resolve the root uuid to its Ray).
        original_source: The AngleSource that actually emitted the path's
            forward root. The returned source is built against
            ``original_source.scene`` -- the same live Scene, not a copy;
            see the module docstring for why.
        cone_half_angle_deg: Half-width of the new source's symmetric fan,
            in degrees. Must be positive. Default 1.0 (2 degree full fan).
        brightness: Optional override; defaults to
            ``original_source.brightness``.

    Returns:
        A new AngleSource instance (not yet added to any scene's objs list --
        pass it to run_targeted_resimulation() to actually run it).

    Raises:
        ValueError: If path_dict['path_uuids'] is empty, the root uuid isn't
            found in result.forward_lineage, the found segment isn't
            actually a forward root (has a parent_uuid), or
            cone_half_angle_deg isn't positive.
    """
    from ..core.scene_objs.light_source.angle_source import AngleSource

    path_uuids = path_dict.get('path_uuids') or []
    if not path_uuids:
        raise ValueError("path_dict['path_uuids'] is empty -- nothing to target")

    root_uuid = path_uuids[0]
    root_ray = result.forward_lineage.get_segment(root_uuid)
    if root_ray is None:
        raise ValueError(
            f"path_uuids[0] ({root_uuid!r}) not found in result.forward_lineage -- "
            f"path_dict must come from this same result (e.g. "
            f"extract_ranked_paths(result.combined), rank_bidirectional_paths(), "
            f"or audit_paths(result)['flagged_paths'])"
        )
    if root_ray.parent_uuid is not None:
        raise ValueError(
            f"path_uuids[0] ({root_uuid!r}) is not a forward root (it has a "
            f"parent_uuid) -- extract_ranked_paths() always orders path_uuids "
            f"source-to-detector, so index 0 should be the forward root; this "
            f"path_dict may not have come from result.combined"
        )
    if cone_half_angle_deg <= 0:
        raise ValueError(
            f"cone_half_angle_deg must be positive, got {cone_half_angle_deg}"
        )

    targeted = AngleSource(original_source.scene, {
        'p1': dict(root_ray.p1),
        'p2': dict(root_ray.p2),
        'brightness': brightness if brightness is not None else original_source.brightness,
        'wavelength': original_source.wavelength,
        'emis_angle': 2.0 * cone_half_angle_deg,
        'symmetric': True,
    })
    targeted.name = f"{original_source.get_display_name()}_targeted"
    return targeted


def run_targeted_resimulation(
    scene: 'Scene',
    original_source: 'AngleSource',
    targeted_source: 'AngleSource',
    *,
    max_rays: int = 100_000,
    record_surface_hits: bool = False,
    min_brightness_exp: Optional[int] = None,
    ray_density: Optional[float] = None,
    name: Optional[str] = None,
) -> 'SimulationResult':
    """
    Run ``targeted_source`` in isolation against ``scene``, then restore the
    scene exactly as it was (15_p9 Tier 1).

    Temporarily swaps ``targeted_source`` in for ``original_source`` in
    ``scene.objs``/``scene.optical_objs`` (same list positions, so any other
    ordering-sensitive code is unaffected), runs a fresh Simulator, then
    restores the original source -- whether or not the run raises. See the
    module docstring for why this mutate-then-restore approach was chosen
    over building a second, lightweight Scene.

    Preconditions (both real, not formalities):

    - **Ray density.** `AngleSource.on_simulation_start()` derives its root
      ray COUNT from `fan_width_radians / (2*pi / (scene.ray_density * 500))`
      -- a narrower `emis_angle` at the SAME `scene.ray_density` emits FEWER
      absolute rays, not more, exactly backwards from Tier 1's purpose.
      Pass `ray_density` (e.g. 10-50x the original scene's) to actually
      concentrate more samples into the narrow cone; see
      15_p9_targeted_resimulation_and_importance_sampling.md's "Quantifying
      how much noise reduction to expect" for how to size it from a target
      relative uncertainty.
    - **Flux/adaptive-sampling threshold.** If the identified path class is
      rare, the scene's adaptive-sampling threshold that made it rare to
      find in the ORIGINAL run will keep pruning it in this re-run too,
      unless relaxed -- pass `min_brightness_exp` (e.g. 6, matching
      TracePro's own guidance of a much lower flux threshold "for stray
      light and importance sampling" than an ordinary run uses; see the
      same document's cross-check section).

    Args:
        scene: The live Scene ``original_source``/``targeted_source`` both
            belong to (``targeted_source_for_path`` already builds against
            ``original_source.scene``, so pass that same scene here).
        original_source: The source currently in ``scene.objs`` to swap out.
        targeted_source: The narrow source to run instead (typically from
            ``targeted_source_for_path``).
        max_rays: Passed through to Simulator -- set high; a narrow, dense
            cone can still produce many ray segments through a multi-bounce
            path.
        record_surface_hits: Passed through to Simulator (Step B). Needed if
            the isolated run's own paths will be inspected with
            path_surfaces()/audit_paths(), not needed for e.g. only
            checking polarization spread at leaves.
        min_brightness_exp: Optional override for ``scene.min_brightness_exp``
            for the duration of this run only (restored after) -- see the
            flux-threshold precondition above.
        ray_density: Optional override for ``scene.ray_density`` for the
            duration of this run only (restored after) -- see the ray
            density precondition above. Note this affects EVERY optical
            object's `on_simulation_start()`/geometry that reads
            `self.scene.ray_density`, but since `targeted_source` is the
            only object emitting rays, in practice only its own root-ray
            count changes.
        name: Optional name for the returned SimulationResult.

    Returns:
        The SimulationResult from tracing ``targeted_source`` alone against
        the scene's other (unchanged) objects.

    Raises:
        ValueError: If ``original_source`` is not currently in
            ``scene.objs``.
    """
    from ..core.simulator import Simulator

    if original_source not in scene.objs:
        raise ValueError(
            "original_source is not currently in scene.objs -- nothing to "
            "swap out (has it already been removed, or does it belong to a "
            "different scene?)"
        )

    obj_index = scene.objs.index(original_source)
    optical_index = (
        scene.optical_objs.index(original_source)
        if original_source in scene.optical_objs else None
    )
    original_min_brightness_exp = scene.min_brightness_exp
    original_ray_density = scene.ray_density

    scene.objs[obj_index] = targeted_source
    if optical_index is not None:
        scene.optical_objs[optical_index] = targeted_source
    if min_brightness_exp is not None:
        scene.min_brightness_exp = min_brightness_exp
    if ray_density is not None:
        scene.ray_density = ray_density

    try:
        simulator = Simulator(
            scene, max_rays=max_rays, record_surface_hits=record_surface_hits,
        )
        return simulator.run_with_result(name=name)
    finally:
        scene.objs[obj_index] = original_source
        if optical_index is not None:
            scene.optical_objs[optical_index] = original_source
        scene.min_brightness_exp = original_min_brightness_exp
        scene.ray_density = original_ray_density


__all__ = [
    'targeted_source_for_path',
    'run_targeted_resimulation',
]
