"""
Python-specific module: ray jobs -- a set of 2D rays simulated as a job
Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

===============================================================================
RAY JOBS -- a set of 2D rays through elements rebuilt from their profiles
===============================================================================
`simulate_rays_2d_job` is a procedure an executor runs anywhere the package
is installed (`flows.executors`): plain data in, plain data out. Its rays
come as lists (a rayfile's slice, cut into chunks by the caller), so the job
needs no rayfile; its elements come as profile files, rebuilt by
`BasePrism.from_profile` (a solid) or `mirrors_from_sheet_profile` (a sheet),
and optionally absorbers, line segments that stop a ray (a 2D mirror reflects
on both faces, so an absorber just behind one gives it a face that does not).

What it returns adds up: the flux that entered, the flux stopped on a
surface, and a histogram of the flux that left by its angle from an axis.
`merge_ray_results` sums the chunks; `fate_shares` reads the shares a
collimator is judged by from any of them.

A chunk is exact and reproducible: the same rays give the same sums,
wherever they run. Whether chunks merged are the same as all the rays at
once depends on how dim rays are dropped:
- by default (``min_brightness_exp`` None), the 2D simulator keeps one in
  ``amp`` of a dim Fresnel reflection by its count of the rays processed so
  far (``base_glass``), and that count depends on what was processed before:
  the merge agrees with one run in expectation, not ray for ray;
- with ``min_brightness_exp`` given, a ray dimmer than its threshold is
  dropped whatever ran before: the merge is the whole run, to the order of
  the sums.
===============================================================================
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

#: The histogram's bin, in degrees from the axis.
DEFAULT_BIN_DEG = 0.1


def _elements(scene: Any, profiles: Sequence[Mapping[str, Any]]) -> List[Any]:
    from ..optical_elements.mirrors import mirrors_from_sheet_profile  # noqa: PLC0415
    from ..optical_elements.prisms.base_prism import BasePrism  # noqa: PLC0415

    out = []
    for p in profiles:
        profile = json.loads(Path(p["path"]).read_text(encoding="utf-8"))
        if profile.get("body") == "sheet":
            out.extend(mirrors_from_sheet_profile(scene, profile))
        else:
            out.append(BasePrism.from_profile(scene, profile, n=float(p["n"])))
    return out


def _absorbers(scene: Any, segments: Any) -> List[Any]:
    """``[[[x1, y1], [x2, y2]], ...]`` as blockers: each a segment that stops any ray meeting it."""
    from ..core.scene_objs.blocker.blocker import Blocker  # noqa: PLC0415

    out = []
    for k, seg in enumerate(segments or []):
        try:
            (x1, y1), (x2, y2) = ((float(a), float(b)) for a, b in seg)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"absorbers[{k}]: a segment is two points [[x1, y1], [x2, y2]], got {seg!r}") from exc
        if not all(math.isfinite(v) for v in (x1, y1, x2, y2)) or (x1, y1) == (x2, y2):
            raise ValueError(f"absorbers[{k}]: the two points must be finite and distinct, got {seg!r}")
        blocker = Blocker(scene, {"p1": {"x": x1, "y": y1}, "p2": {"x": x2, "y": y2}})
        blocker.name = f"absorber {k}"
        out.append(blocker)
    return out


def simulate_rays_2d_job(inputs: Dict[str, Any], ctx: Any) -> Dict[str, Any]:
    """Simulate a set of 2D rays through the profiles' elements; the sums of where their flux went.

    Inputs:
        profiles: ``[{"path", "n"}]`` for a solid, ``[{"path"}]`` for a sheet.
        absorbers: Line segments ``[[[x1, y1], [x2, y2]], ...]`` that stop any
            ray meeting them; its flux counts in ``stopped_flux`` (default none).
            A 2D mirror reflects on both faces: an absorber just behind one,
            over the same span, makes its back face absorb.
        rays: ``{"points": [[a, b]], "directions": [[da, db]], "flux": [f]}``.
        flux_per_brightness: The flux of a ray of brightness 1: the same for
            every chunk of one source (its peak ray's flux), so the chunks'
            sums are on one scale.
        axis_deg: The axis the exit angles are measured from (default 0, +a).
        bin_deg: The histogram's bin (`DEFAULT_BIN_DEG`).
        max_rays: The simulator's limit on rays processed (default 10,000,000).
        min_brightness_exp: Drop rays dimmer than ``10**-min_brightness_exp``,
            whatever ran before, so chunks merge into the whole run exactly;
            None (the default): the simulator's own thinning (see above).

    Returns:
        ``rays``, ``total_flux`` (what entered), ``stopped_flux`` (branches that
        ended on a surface), ``left_flux``, ``dropped_flux`` (what entered and
        neither left nor stopped: rays too dim to follow, less what the
        thinning amplified), ``exits`` (branches that left),
        ``segments``, ``bin_deg``, ``hist`` (the flux that left, by angle from the
        axis, ``180 / bin_deg`` bins from 0), ``sim_s``.
    """
    import numpy as np  # noqa: PLC0415

    from ..core.scene import Scene  # noqa: PLC0415
    from ..core.simulator import Simulator  # noqa: PLC0415
    from ..optical_elements.sources.ray_set_source import RaySetSource  # noqa: PLC0415
    from .irradiance import exit_rays_2d  # noqa: PLC0415

    rays = inputs["rays"]
    peak = float(inputs["flux_per_brightness"])
    flux = np.asarray(rays["flux"], dtype=float)
    if not len(rays["points"]) == len(rays["directions"]) == len(flux):
        raise ValueError("rays: points, directions and flux differ in length")
    if np.any(flux <= 0.0) or np.any(flux > peak * (1.0 + 1e-12)):
        raise ValueError("rays: every flux must be in (0, flux_per_brightness]")
    bin_deg = float(inputs.get("bin_deg", DEFAULT_BIN_DEG))
    axis = math.radians(float(inputs.get("axis_deg", 0.0)))
    u = np.array([math.cos(axis), math.sin(axis)])

    scene = Scene()
    if inputs.get("min_brightness_exp") is not None:
        scene.min_brightness_exp = int(inputs["min_brightness_exp"])
    for element in _elements(scene, inputs["profiles"]) + _absorbers(scene, inputs.get("absorbers")):
        scene.add_object(element)
    scene.add_object(RaySetSource.from_rays(scene, rays["points"], rays["directions"], np.minimum(flux / peak, 1.0),
                                            flux_per_brightness=peak))
    ctx.progress(0, len(flux), "simulating")
    t0 = time.perf_counter()
    segments = Simulator(scene, max_rays=int(inputs.get("max_rays", 10_000_000)),
                         record_surface_hits=True).run_with_result(name="ray_job").segments
    sim_s = time.perf_counter() - t0
    _, directions, left = exit_rays_2d(segments, flux_per_brightness=peak)
    parents = {s.parent_uuid for s in segments}
    stopped = sum(s.total_brightness for s in segments if s.uuid not in parents and s.hit_surface_uuid is not None)
    total = sum(s.total_brightness for s in segments if s.parent_uuid is None)
    n_bins = int(round(180.0 / bin_deg))
    hist = np.zeros(n_bins)
    if len(left):
        d = np.asarray(directions, dtype=float)
        angle = np.degrees(np.arccos(np.clip((d @ u) / np.linalg.norm(d, axis=1), -1.0, 1.0)))
        np.add.at(hist, np.minimum((angle / bin_deg).astype(int), n_bins - 1), np.asarray(left, dtype=float))
    ctx.progress(len(flux), len(flux), "simulated")
    left_flux = float(np.sum(left))
    return {"rays": int(len(flux)), "total_flux": float(total * peak), "stopped_flux": float(stopped * peak),
            "left_flux": left_flux, "dropped_flux": float(total * peak - stopped * peak - left_flux),
            "exits": int(len(left)), "segments": len(segments),
            "bin_deg": bin_deg, "hist": hist.tolist(), "sim_s": sim_s}


def merge_ray_results(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The chunks' results as one: every sum summed, the histograms added bin by bin.

    Raises:
        ValueError: For no results, or histograms of different bins.
    """
    if not results:
        raise ValueError("no results to merge")
    bins = {(r["bin_deg"], len(r["hist"])) for r in results}
    if len(bins) != 1:
        raise ValueError(f"the results' histograms differ: {sorted(bins)}")
    out: Dict[str, Any] = {k: sum(r[k] for r in results)
                           for k in ("rays", "total_flux", "stopped_flux", "left_flux", "dropped_flux", "exits",
                                     "segments", "sim_s")}
    out["bin_deg"] = results[0]["bin_deg"]
    out["hist"] = [sum(col) for col in zip(*(r["hist"] for r in results))]
    out["chunks"] = len(results)
    return out


def fate_shares(result: Mapping[str, Any], beam_deg: float = 3.0) -> Dict[str, float]:
    """Where the flux went, as shares of what entered: left within 1 deg of the axis, within
    ``beam_deg``, stray (10 to 90 deg), backwards (90 deg or more), and stopped on a surface."""
    total, b, h = result["total_flux"], result["bin_deg"], result["hist"]

    def below(deg: float) -> float:
        return sum(h[: int(round(deg / b))])
    return {"within 1 deg": below(1.0) / total, f"within {beam_deg:g} deg": below(beam_deg) / total,
            "stray, 10-90 deg": (below(90.0) - below(10.0)) / total,
            "backwards": (sum(h) - below(90.0)) / total, "absorbed": result["stopped_flux"] / total}


# ---------------------------------------------------------------------------
# The segments job: a chunk's segments back, to be merged into one result here
# ---------------------------------------------------------------------------

#: A segment's plain fields, sent back as columns (the points as [x, y]).
SEGMENT_FIELDS = ("brightness_s", "brightness_p", "wavelength", "gap", "is_new", "is_tir_result", "caused_tir",
                  "tir_count", "is_grazing_result__angle", "caused_grazing__angle", "is_grazing_result__polar",
                  "caused_grazing__polar", "is_grazing_result__transm", "caused_grazing__transm",
                  "interaction_type", "incident_angle", "medium_index")
_POINTS = ("p1", "p2", "hit_point", "hit_normal")
_HIT_FIELDS = ("bin_index", "position", "incident_point", "brightness_s", "brightness_p", "brightness_total",
               "sign", "wavelength", "incident_angle")


def sample_source_rays(source: Any, ray_density: float) -> Dict[str, Any]:
    """The rays a source starts at ``ray_density``, as a job's ``rays`` input.

    Returns:
        ``{"points", "directions", "brightness", "wavelength"}``, one entry per ray; a
        ray's brightness is its s and p summed, as `RaySetSource` splits it back.
    """
    scene = source.scene
    kept = scene.ray_density
    scene.ray_density = ray_density
    try:
        rays = source.on_simulation_start()["newRays"]
    finally:
        scene.ray_density = kept
    def xy(p: Any) -> List[float]:
        return [p.x, p.y] if hasattr(p, "x") else [p["x"], p["y"]]
    ends = [(xy(r.p1), xy(r.p2)) for r in rays]
    return {"points": [a for a, _ in ends],
            "directions": [[b[0] - a[0], b[1] - a[1]] for a, b in ends],
            "brightness": [r.brightness_s + r.brightness_p for r in rays],
            "wavelength": [getattr(r, "wavelength", None) for r in rays]}


def chunk_rays(rays: Mapping[str, Sequence[Any]], size: int) -> List[Dict[str, List[Any]]]:
    """``rays`` cut into chunks of at most ``size`` rays, in order."""
    n = len(rays["points"])
    return [{k: list(v[a:a + size]) for k, v in rays.items()} for a in range(0, n, max(1, int(size)))]


def simulate_rays_2d_segments_job(inputs: Dict[str, Any], ctx: Any) -> Dict[str, Any]:
    """Simulate a chunk of 2D rays through a portable scene; its segments and detector hits back.

    Inputs:
        scene: A `portable_scene` description (the scene's optical objects, sources left out).
        rays: ``{"points", "directions", "brightness", "wavelength"?}`` (`sample_source_rays`).
        source_name: The name the rays' source carries.
        min_brightness_exp: Required: a ray dimmer than ``10**-min_brightness_exp`` is
            dropped whatever ran before, so the chunks merged are the whole run (see the
            module docstring).
        max_rays: The simulator's limit on segments for this chunk.

    Returns:
        ``segments``: the columns (``SEGMENT_FIELDS``, the points as ``[x, y]`` or None,
        ``parent`` as an index into the chunk's segments or -1, ``hit`` as the name of the
        object hit or None); ``detector_hits``: ``{detector name: [record, with ``ray`` the
        segment's index]}``; ``count``, ``processed``, ``truncation``, ``undefined``,
        ``sim_s``.
    """
    from ..core.simulator import Simulator  # noqa: PLC0415
    from ..optical_elements.sources.ray_set_source import RaySetSource  # noqa: PLC0415
    from .portable_scene import build_portable_scene  # noqa: PLC0415

    if inputs.get("min_brightness_exp") is None:
        raise ValueError("min_brightness_exp is required: without it the chunks do not merge into one run")
    rays = inputs["rays"]
    n = len(rays["points"])
    if not len(rays["directions"]) == len(rays["brightness"]) == n:
        raise ValueError("rays: points, directions and brightness differ in length")
    scene = build_portable_scene(inputs["scene"], min_brightness_exp=inputs["min_brightness_exp"])
    waves = rays.get("wavelength") or [None] * n
    entries = []
    for p, d, b, w in zip(rays["points"], rays["directions"], rays["brightness"], waves):
        e = {"p": [float(p[0]), float(p[1])], "d": [float(d[0]), float(d[1])], "brightness": float(b)}
        if w is not None:
            e["wavelength"] = w
        entries.append(e)
    source = RaySetSource(scene, {"rays": entries})
    source.name = inputs.get("source_name") or "source"
    scene.add_object(source)
    ctx.progress(0, n, "simulating")
    t0 = time.perf_counter()
    sim = Simulator(scene, max_rays=int(inputs.get("max_rays", 10_000_000)), record_surface_hits=True)
    result = sim.run_with_result(name="segments_job")
    sim_s = time.perf_counter() - t0
    segs = result.segments
    index = {s.uuid: i for i, s in enumerate(segs)}
    names = {o.uuid: o.name for o in scene.objs}

    def xy(v: Any) -> Any:
        return None if v is None else [v["x"], v["y"]]
    cols: Dict[str, List[Any]] = {f: [getattr(s, f) for s in segs] for f in SEGMENT_FIELDS}
    cols.update({f: [xy(getattr(s, f)) for s in segs] for f in _POINTS})
    cols["parent"] = [index.get(s.parent_uuid, -1) for s in segs]
    cols["hit"] = [names.get(s.hit_surface_uuid) if s.hit_surface_uuid else None for s in segs]
    hits = {names[uuid]: [{"ray": index.get(r.get("ray_uuid"), -1), **{k: r.get(k) for k in _HIT_FIELDS}}
                          for r in records]
            for uuid, records in result.detector_hits.items()}
    ctx.progress(n, n, "simulated")
    return {"rays": n, "segments": cols, "count": len(segs), "detector_hits": hits,
            "processed": result.processed_ray_count, "truncation": result.total_truncation,
            "undefined": result.undefined_behavior_count, "sim_s": sim_s}


def merge_segment_results(results: Sequence[Mapping[str, Any]], scene: Any, *, source: Any,
                          max_rays: int, name: Optional[str] = None) -> Any:
    """The chunks' segments as one SimulationResult against the live scene, mapped back by name.

    Each segment gets a new uuid; its parent, the object it hit and its detector hits are
    mapped to the live scene's objects by name; its source is ``source``.

    Args:
        results: The chunks' `simulate_rays_2d_segments_job` results, in order.
        scene: The live Scene the chunks were described from.
        source: The live source the rays are attributed to (its uuid and name).
        max_rays: The whole run's segment limit, as reported.
        name: The result's name.

    Raises:
        ValueError: A name in a chunk is not an object of the live scene.
    """
    import uuid as uuid_module  # noqa: PLC0415

    from ..core.ray import Ray  # noqa: PLC0415
    from ..core.ray_lineage import RayLineage  # noqa: PLC0415
    from .simulation_result import SceneSnapshot, SimulationResult  # noqa: PLC0415

    live = {o.name: o for o in scene.objs if getattr(o, "name", None)}

    def uuid_of(obj_name: Optional[str]) -> Optional[str]:
        if obj_name is None:
            return None
        if obj_name not in live:
            raise ValueError(f"the chunk names {obj_name!r}, which is not an object of the live scene")
        return live[obj_name].uuid

    def pt(v: Any) -> Any:
        return None if v is None else {"x": v[0], "y": v[1]}
    segments: List[Any] = []
    lineage = RayLineage()
    hits: Dict[str, List[Dict[str, Any]]] = {}
    for res in results:
        cols, n = res["segments"], res["count"]
        ids = [str(uuid_module.uuid4()) for _ in range(n)]
        for i in range(n):
            ray = Ray(pt(cols["p1"][i]), pt(cols["p2"][i]))
            for f in SEGMENT_FIELDS:
                setattr(ray, f, cols[f][i])
            ray.hit_point, ray.hit_normal = pt(cols["hit_point"][i]), pt(cols["hit_normal"][i])
            ray.uuid = ids[i]
            ray.parent_uuid = ids[cols["parent"][i]] if cols["parent"][i] >= 0 else None
            ray.hit_surface_uuid = uuid_of(cols["hit"][i])
            ray.source_uuid, ray.source_label = source.uuid, getattr(source, "name", None)
            segments.append(ray)
            lineage.register(ray)
        for det_name, records in res["detector_hits"].items():
            hits.setdefault(uuid_of(det_name), []).extend(
                {"ray_uuid": ids[r["ray"]] if r["ray"] >= 0 else None, **{k: r[k] for k in _HIT_FIELDS}}
                for r in records)
    return SimulationResult(
        uuid=str(uuid_module.uuid4()), name=name, timestamp=datetime.now().isoformat(),
        scene_snapshot=SceneSnapshot.from_scene(scene), segments=segments, max_rays=int(max_rays),
        processed_ray_count=sum(r["processed"] for r in results),
        total_truncation=sum(r["truncation"] for r in results),
        undefined_behavior_count=sum(r["undefined"] for r in results), lineage=lineage, detector_hits=hits)


__all__ = ["DEFAULT_BIN_DEG", "SEGMENT_FIELDS", "chunk_rays", "fate_shares", "merge_ray_results",
           "merge_segment_results", "sample_source_rays", "simulate_rays_2d_job", "simulate_rays_2d_segments_job"]
