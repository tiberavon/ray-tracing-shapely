"""
Python-specific module: targeted re-simulation flow
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
PYTHON-SPECIFIC MODULE: the targeted re-simulation flow
===============================================================================
`targeted_source_for_path` and `run_targeted_resimulation` as a flow an agent
starts by name (``flow_start("targeted_resimulation")``): one path of a
bidirectional run, re-run alone at high density, its result a new named
context beside the run it came from.

    start -> awaiting_context -> awaiting_path -> awaiting_source
          -> awaiting_options -> awaiting_go_ahead -> resimulating -> done

- **awaiting_context:** the context holding the run: a live one (its scene,
  not a saved run) with a bidirectional result. None: the active one.
- **awaiting_path:** a rank in the context's ``rank_bidirectional_paths``
  (1 is the most energy; the question's context lists the first ten), or a
  path's ``path_uuids``.
- **awaiting_source:** the source that emitted the path. None: the one its
  first segment names (``source_uuid``).
- **awaiting_options:** the narrow cone's half-angle, how many rays to start
  in it, the brightness threshold, the segment limit (sized from the rays by
  default, refused past `MAX_SEGMENTS`), the new context's
  name, and where it runs (``executor``, with ``chunk_rays``). The rays are
  what is asked, not a ray density: the density that starts them is worked
  out from the cone. An executor other than the kernel needs the scene sent
  as plain data (`portable_scene`): a scene that cannot be is refused here,
  by name.
- **awaiting_go_ahead** is always entered. The estimate starts from a pilot:
  about `PILOT_RAYS` of the narrow cone's rays run here, which give the
  run's segments a ray and this machine's seconds a segment for this scene.
  It counts the simulation where it runs (a job's start; on Modal, its
  speed and the time each chunk adds) and the work here once the rays are
  back (merging, the context's database, grouping, saving), a measured rate
  a segment. An estimate within a minute goes on; a longer one is asked
  (``false`` goes back to the options).
- **resimulating** runs it in this kernel (the live route: the scene is the
  one the run was traced in, swapped and restored by
  `run_targeted_resimulation`), or, on the portable route, samples the
  narrow cone's rays here, cuts them into chunks and follows a job per chunk
  as one step (`submit_group`, `simulate_rays_2d_segments_job`), then merges
  their segments, mapped back to the live scene by name
  (`merge_segment_results`): the same result as the kernel's. The scene's
  other sources are silenced for the run, and the summary counts only the
  narrow source's rays. The result goes into a new named context,
  never the active one (C-AGENT-04), and is saved in the run's folder as a
  run bundle (C-AGENT-05), so ``load_run_context`` reloads it after a
  restart.
- **done** holds the grouped summary: the rays that reached the detector,
  grouped by the interactions along their path, most energy first.

On the kernel the run blocks it while it runs; the estimate says how long,
and where, before it starts. A long run goes to ``local_process`` or
``modal``, and is followed with ``flow_wait``.
===============================================================================
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..flows import persistence
from ..flows.budgets import ASK_OVER_S, JOB_START_S, MODAL_PER_JOB_S, MODAL_SPEED, estimate_s, format_duration
from ..flows.fields import FlowField, explain_field
from ..flows.flow_base import ObservableFlow
from . import agentic_tools

#: The options and their defaults.
OPTIONS: Dict[str, Any] = {"cone_half_angle_deg": 1.0, "rays": 1000, "min_brightness_exp": 6,
                           "max_rays": None, "context_name": None, "executor": "kernel", "chunk_rays": 1000}
#: The segment limit, by default, is the rays asked times the source's segments per ray in the run
#: it came from, times this: the path re-run may branch more than the run's average ray.
SEGMENTS_HEADROOM = 4.0
#: No run is sized past this many segments: the result is held in the kernel, a Python object and
#: a database row per segment. A run expected past it is refused, with the rays that fit.
MAX_SEGMENTS = 2_000_000
#: Rays run here before the estimate (about as many: a fan starts at least this many): the run's segments a ray and this machine's
#: seconds a segment, measured on the run's own scene and source.
PILOT_RAYS = 100
#: Where the re-simulation runs: ``kernel`` is the live route (this kernel, the live scene);
#: the others are the portable route (the scene as plain data, the rays in chunks, a job each).
EXECUTORS = ("kernel", "in_process", "local_process", "modal")
#: The deployed Modal app the ``modal`` executor sends the chunks to.
MODAL_APP = os.environ.get("RTS_MODAL_APP", "rts-jobs")
#: The chunk jobs' procedure.
SEGMENTS_JOB = "ray_tracing_shapely.analysis.ray_jobs:simulate_rays_2d_segments_job"
#: How many ranked paths the path question lists.
LISTED_PATHS = 10
#: How many groups the result lists.
LISTED_GROUPS = 20

FIELDS: Dict[str, FlowField] = {
    "awaiting_context": FlowField(
        "context_name", "json",
        "Which context holds the run? A live context with a bidirectional result (list_contexts); null for "
        "the active one.",
        "the path is chosen from its bidirectional result, and re-run in its scene",
        'e.g. null, or "default"', default=None),
    "awaiting_path": FlowField(
        "path", "json",
        "Which path? Its rank in rank_bidirectional_paths (1 is the most energy; the first ten are in the "
        "question's context), or its path_uuids.",
        "the narrow source starts where the path's first segment starts, along it",
        "e.g. 3"),
    "awaiting_source": FlowField(
        "source", "json",
        "Which source emitted the path (list_sources)? null for the one its first segment names.",
        "the narrow source takes its place for the run, with its brightness and wavelength",
        'e.g. null, or "led"', default=None),
    "awaiting_options": FlowField(
        "options", "json",
        "Options? {} for the defaults, or any of: cone_half_angle_deg (1.0), rays (1000: at least this many rays start "
        "in the cone), min_brightness_exp (6: rays dimmer than 10^-6 are dropped), max_rays (the segment "
        "limit; by default the rays times the run's segments per ray times 4, at most 2,000,000), context_name (the new context's name; targeted_<rank> by default), executor "
        "(kernel: here, on the live scene; in_process, local_process or modal: the scene sent as plain data, "
        "the rays in chunks, a job each -- every object named, each exportable), chunk_rays (1000: rays per "
        "job; local_process uses at most one job per two cores).",
        "rays sets the density; a low threshold keeps a rare path's dim branches; a long run goes to modal",
        'e.g. {} or {"rays": 5000, "cone_half_angle_deg": 0.5, "executor": "modal"}', default={}),
    "awaiting_go_ahead": FlowField(
        "go_ahead", "bool",
        "The re-simulation is estimated over a minute (the estimate, and where it runs, are in the "
        "question's context). Go ahead? false goes back to the options.",
        "a box may spend a minute without asking",
        "e.g. true"),
}

STATES = ["start", "awaiting_context", "awaiting_path", "awaiting_source", "awaiting_options",
          "awaiting_go_ahead", "resimulating", "done"]

TRANSITIONS = [
    {"trigger": "begin", "source": "start", "dest": "awaiting_context"},
    {"trigger": "provide_context_name", "source": "awaiting_context", "dest": "awaiting_path",
     "before": "_provide_context"},
    {"trigger": "provide_path", "source": "awaiting_path", "dest": "awaiting_source", "before": "_provide_path"},
    {"trigger": "provide_source", "source": "awaiting_source", "dest": "awaiting_options",
     "before": "_provide_source"},
    {"trigger": "provide_options", "source": "awaiting_options", "dest": "awaiting_go_ahead",
     "before": "_provide_options"},
    {"trigger": "_advance", "source": "awaiting_go_ahead", "dest": "resimulating"},
    {"trigger": "provide_go_ahead", "source": "awaiting_go_ahead", "dest": "resimulating", "conditions": "_go",
     "prepare": "_provide_go_ahead"},
    {"trigger": "provide_go_ahead", "source": "awaiting_go_ahead", "dest": "awaiting_options"},
    {"trigger": "_advance", "source": "resimulating", "dest": "done"},
    {"trigger": "resimulated", "source": "resimulating", "dest": "done", "before": "_merge_chunks"},
    {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
]


def density_for(rays: int, emis_angle_deg: float) -> float:
    """The ray density at which an AngleSource of ``emis_angle_deg`` starts at least ``rays`` rays.

    An AngleSource steps by ``2 pi / int(density * 500)`` across its fan and
    stops 1e-5 rad short of its edge, so the divisions of the full circle are
    set to fit ``rays`` steps in what remains of the fan.
    """
    usable = math.radians(emis_angle_deg) - 1e-5
    if usable <= 0:
        raise ValueError(f"a fan of {emis_angle_deg} degrees is narrower than the source's own end margin")
    divisions = math.ceil(rays * 2.0 * math.pi / usable) + 1
    return (divisions + 0.5) / 500.0


def bounce_groups(result: Any, detector_uuid: Optional[str],
                  source_uuid: Optional[str] = None) -> Dict[str, Any]:
    """The rays that reached the detector, grouped by the interactions along their path.

    Args:
        result: The re-simulation's SimulationResult (with lineage and detector_hits).
        detector_uuid: The detector whose hits are grouped.
        source_uuid: Only the rays this source emitted (each ray carries its
            emitter's ``source_uuid``). None: every source's.

    Returns:
        {'roots', 'emitted', 'hits', 'energy_at_detector', 'groups': [{'path_types',
        'count', 'total_energy', 'share'}, ...]}, most energy first.
    """
    from .lineage_analysis import rank_paths_by_energy

    def _from_source(seg: Any) -> bool:
        return source_uuid is None or getattr(seg, 'source_uuid', None) == source_uuid

    roots = [s for s in result.segments if getattr(s, 'parent_uuid', None) is None and _from_source(s)]
    emitted = sum(s.brightness_s + s.brightness_p for s in roots)
    records = (result.detector_hits or {}).get(detector_uuid, []) if detector_uuid else []
    by_uuid = {s.uuid: s for s in result.segments} if source_uuid is not None else {}
    leaves = list(dict.fromkeys(r['ray_uuid'] for r in records if r['ray_uuid'] is not None
                                and (source_uuid is None or _from_source(by_uuid.get(r['ray_uuid'])))))
    groups: Dict[tuple, Dict[str, Any]] = {}
    for entry in rank_paths_by_energy(result.lineage, leaf_uuids=leaves) if leaves else []:
        key = tuple(entry['path_types'])
        g = groups.setdefault(key, {'path_types': list(key), 'count': 0, 'total_energy': 0.0})
        g['count'] += 1
        g['total_energy'] += entry['energy']
    total = sum(g['total_energy'] for g in groups.values())
    ordered = sorted(groups.values(), key=lambda g: -g['total_energy'])
    for g in ordered:
        g['share'] = g['total_energy'] / total if total else 0.0
    return {'roots': len(roots), 'emitted': emitted, 'hits': len(leaves), 'energy_at_detector': total,
            'groups': ordered}


class _Quiet:
    """A job context that reports nowhere: the pilot runs a job's function directly, here."""

    def progress(self, *_a: Any, **_k: Any) -> None:
        pass


class TargetedResimulationFlow(ObservableFlow):
    """One path of a bidirectional run, re-run alone at high density, into a new context.

    Construct it (``begin()`` is called), then answer each question
    (``answer(value)``). At ``done``, ``self.result`` holds the grouped
    summary, the new context's name and the saved bundle's folder.

    Args:
        base_dir: Where the run's folder is written.
        run_id: An explicit run id, or None for a generated one.
        render_svg: Re-render ``state.svg`` on every move (needs Graphviz's ``dot``).
    """

    FIELDS = FIELDS
    PURPOSE = ("Re-run one path of a bidirectional run alone, at high density: a narrow source where the path "
               "starts, its result a new named context (the run it came from stays active) and a saved bundle.")

    def __init__(self, base_dir: Path, run_id: Optional[str] = None, render_svg: bool = True) -> None:
        self._clear()
        super().__init__(name="targeted_resimulation", states=STATES, transitions_list=TRANSITIONS,
                         initial="start", base_dir=base_dir, run_id=run_id, render_svg=render_svg)
        self.begin()

    def _clear(self) -> None:
        self.context_name: Optional[str] = None
        self.ctx: Dict[str, Any] = {}
        self.ranked: List[Dict[str, Any]] = []
        self.path: Optional[Dict[str, Any]] = None
        self.rank: Optional[int] = None
        self.source: Any = None
        self.options: Dict[str, Any] = dict(OPTIONS)
        self.estimate: Optional[Dict[str, Any]] = None
        self._going = False
        self.result: Optional[Dict[str, Any]] = None
        self.portable: Optional[Dict[str, Any]] = None
        self.segments_expected: Dict[str, Any] = {}
        self.pilot: Dict[str, Any] = {}
        self._targeted: Any = None
        self._density: Optional[float] = None

    def _on_reset(self, *args: Any, **kwargs: Any) -> None:
        super()._on_reset(*args, **kwargs)
        self._clear()

    def _ask(self) -> None:
        field = self.FIELDS[self.state]
        explanation = field.explanation()
        self.set_explanation(explanation)
        self.emit_event(field=field.name, message=explanation.message)
        self.update_detail(waiting_on=field.name)

    def question_context(self) -> Optional[Dict[str, Any]]:
        if self.state == "awaiting_context":
            return agentic_tools.list_contexts()["data"]
        if self.state == "awaiting_path":
            return {"paths": [{"rank": i + 1, "energy": p["energy"], "path_length": len(p["path_uuids"]),
                               "path_types": p["path_types"], "connection_surface": p["connection_surface"]}
                              for i, p in enumerate(self.ranked[:LISTED_PATHS])],
                    "of": len(self.ranked)}
        if self.state == "awaiting_source":
            return {"sources": self._sources(), "emitted_by": self._emitter_name()}
        if self.state == "awaiting_options":
            return {"options": self.options, "source_emis_angle_deg": getattr(self.source, "emis_angle", None),
                    "scene_ray_density": self.ctx["scene"].ray_density}
        if self.state == "awaiting_go_ahead":
            return self.estimate
        return None

    # -- the context and the path -------------------------------------------------

    def on_enter_awaiting_context(self, *_a: Any, **_k: Any) -> None:
        self._ask()

    def _provide_context(self, value: Any) -> None:
        name = agentic_tools.list_contexts()["data"]["active"] if value is None else value
        if not isinstance(name, str):
            raise ValueError(f"context_name takes a name or null, got {value!r}")
        ctx = agentic_tools.get_context(name)
        if not ctx:
            raise ValueError(f"no context named {name!r} (list_contexts)")
        if ctx.get("scene") is None:
            raise ValueError(f"context {name!r} has no live scene (a saved run is not re-simulated: re-run the "
                             "notebook that built it)")
        bidir = ctx.get("bidirectional")
        if bidir is None or getattr(bidir, "forward_lineage", None) is None or bidir.combined is None:
            raise ValueError(f"context {name!r} holds no bidirectional result with its graph: the path is "
                             "chosen from one (set_bidirectional_context)")
        from .bidirectional import extract_ranked_paths

        self.ranked = extract_ranked_paths(bidir.combined, top_n=10_000)
        if not self.ranked:
            raise ValueError(f"context {name!r}'s bidirectional result has no source-to-detector path")
        self.context_name, self.ctx = name, ctx

    def on_enter_awaiting_path(self, *_a: Any, **_k: Any) -> None:
        self._ask()

    def _provide_path(self, value: Any) -> None:
        if isinstance(value, int) and not isinstance(value, bool):
            if not 1 <= value <= len(self.ranked):
                raise ValueError(f"path rank must be 1 to {len(self.ranked)}, got {value}")
            self.path, self.rank = self.ranked[value - 1], value
            return
        if isinstance(value, list) and value and all(isinstance(u, str) for u in value):
            match = [i for i, p in enumerate(self.ranked) if p["path_uuids"] == value]
            self.path = self.ranked[match[0]] if match else {"path_uuids": list(value)}
            self.rank = match[0] + 1 if match else None
            root = self.ctx["bidirectional"].forward_lineage.get_segment(value[0])
            if root is None:
                raise ValueError(f"path_uuids[0] ({value[0]!r}) is not a segment of this run's forward pass")
            return
        raise ValueError(f"path takes a rank (a whole number) or a list of path_uuids, got {value!r}")

    # -- the source ----------------------------------------------------------------

    def _sources(self) -> List[Dict[str, Any]]:
        objs = self.ctx["scene"].objs
        return [{"name": getattr(o, "name", None), "type": getattr(o.__class__, "type", None),
                 "uuid": o.uuid} for o in objs
                if (getattr(o.__class__, "type", None) or o.__class__.__name__) in agentic_tools.SOURCE_TYPES]

    def _root(self) -> Any:
        return self.ctx["bidirectional"].forward_lineage.get_segment(self.path["path_uuids"][0])

    def _emitter_name(self) -> Optional[str]:
        root = self._root()
        uuid = getattr(root, "source_uuid", None) if root is not None else None
        return next((s["name"] for s in self._sources() if s["uuid"] == uuid), None)

    def on_enter_awaiting_source(self, *_a: Any, **_k: Any) -> None:
        self._ask()

    def _provide_source(self, value: Any) -> None:
        sources = self._sources()
        if value is None:
            root = self._root()
            uuid = getattr(root, "source_uuid", None) if root is not None else None
            if uuid is None:
                raise ValueError("the path's first segment names no source: name it (list_sources)")
            match = [s for s in sources if s["uuid"] == uuid]
        else:
            if not isinstance(value, str):
                raise ValueError(f"source takes a name or null, got {value!r}")
            match = [s for s in sources if s["name"] == value]
            if len(match) > 1:
                raise ValueError(f"two sources are named {value!r}: name each uniquely")
        if not match:
            raise ValueError(f"no source {value!r} in the scene; its sources: {[s['name'] for s in sources]}")
        self.source = next(o for o in self.ctx["scene"].objs if o.uuid == match[0]["uuid"])

    # -- the options and the estimate ---------------------------------------------

    def on_enter_awaiting_options(self, *_a: Any, **_k: Any) -> None:
        self.options["context_name"] = self.options["context_name"] or self._default_name()
        self._ask()

    def _default_name(self) -> str:
        base = f"targeted_{self.rank}" if self.rank is not None else "targeted"
        name, k = base, 2
        while agentic_tools.get_context(name):
            name, k = f"{base}_{k}", k + 1
        return name

    def _provide_options(self, value: Any = None) -> None:
        value = {} if value is None else value
        if not isinstance(value, dict):
            raise ValueError(f"options takes an object, got {value!r}")
        unknown = sorted(set(value) - set(OPTIONS))
        if unknown:
            raise ValueError(f"options: unknown {unknown}; known {sorted(OPTIONS)}")
        out = {**OPTIONS, "context_name": self.options["context_name"] or self._default_name()}
        for key in ("rays", "max_rays"):
            if key in value:
                v = value[key]
                if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                    raise ValueError(f"options.{key} must be a positive whole number, got {v!r}")
                out[key] = v
        if "min_brightness_exp" in value:
            v = value["min_brightness_exp"]
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError(f"options.min_brightness_exp must be a whole number >= 0, got {v!r}")
            out["min_brightness_exp"] = v
        if "cone_half_angle_deg" in value:
            v = value["cone_half_angle_deg"]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= 90:
                raise ValueError(f"options.cone_half_angle_deg must be in (0, 90], got {v!r}")
            out["cone_half_angle_deg"] = float(v)
        if "context_name" in value:
            v = value["context_name"]
            if not isinstance(v, str) or not v.strip() or "/" in v or "\\" in v or v in (".", ".."):
                raise ValueError(f"options.context_name must be a plain name, got {v!r}")
            out["context_name"] = v
        if agentic_tools.get_context(out["context_name"]):
            raise ValueError(f"a context named {out['context_name']!r} is already loaded: choose another")
        per_ray = self._segments_per_ray()
        expected = math.ceil(out["rays"] * per_ray)
        if out["max_rays"] is None:
            sized = max(1000, math.ceil(expected * SEGMENTS_HEADROOM))
            if sized > MAX_SEGMENTS:
                fit = int(MAX_SEGMENTS / (per_ray * SEGMENTS_HEADROOM))
                raise ValueError(f"options.rays: {out['rays']} rays at {per_ray:.1f} segments a ray (the run's) need "
                                 f"a limit of {sized:,} segments, over the {MAX_SEGMENTS:,} a run may hold; ask at "
                                 f"most {fit:,} rays, or give max_rays")
            out["max_rays"] = sized
        self.segments_expected = {"per_ray": per_ray, "segments": expected, "max_rays": out["max_rays"],
                                  "may_truncate": expected >= out["max_rays"]}
        if "chunk_rays" in value:
            v = value["chunk_rays"]
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ValueError(f"options.chunk_rays must be a positive whole number, got {v!r}")
            out["chunk_rays"] = v
        if "executor" in value:
            if value["executor"] not in EXECUTORS:
                raise ValueError(f"options.executor is one of {list(EXECUTORS)}, got {value['executor']!r}")
            out["executor"] = value["executor"]
        self.portable = None
        if out["executor"] != "kernel":
            if out["executor"] == "modal" and not _modal_installed():
                raise ValueError("options.executor modal: the Modal client is not installed here; choose "
                                 "local_process or kernel")
            from .portable_scene import NotPortable, portable_scene  # noqa: PLC0415
            try:
                self.portable = portable_scene(self.ctx["scene"])
            except NotPortable as exc:
                raise ValueError(f"options.executor {out['executor']}: the scene cannot be sent as plain data "
                                 f"({exc}); choose kernel") from exc
        self.options = out

    def _segments_per_ray(self) -> float:
        """The run's segments per root ray, for the chosen source's rays (all rays if none carry it)."""
        segs = self.ctx.get("segments") or []
        uuid = getattr(self.source, "uuid", None)
        own = [s for s in segs if getattr(s, "source_uuid", None) == uuid] or list(segs)
        roots = sum(1 for s in own if getattr(s, "parent_uuid", None) is None)
        return len(own) / roots if roots else 1.0

    def _chunk_size(self) -> int:
        o = self.options
        if o["executor"] == "local_process":     # one worker process per job: at most one per two cores
            workers = max(1, (os.cpu_count() or 2) // 2)
            return max(o["chunk_rays"], math.ceil(o["rays"] / workers))
        return o["chunk_rays"]

    def _run_pilot(self) -> Dict[str, Any]:
        """A few of the run's own rays, here, before the estimate: its segments a ray, and this
        machine's seconds a segment, for this scene and this source (the broad run's are another
        source's, and a measured rate another scene's).

        The rays are the run's own, sampled at its density and taken evenly across the cone: a
        source shares its brightness among its rays, and a brighter ray's partial reflections stay
        above the brightness threshold for more bounces, so a sparser fan would have more segments
        a ray than the run. They run as a chunk does (`simulate_rays_2d_segments_job`).
        """
        from .portable_scene import NotPortable, portable_scene  # noqa: PLC0415
        from .ray_jobs import sample_source_rays, simulate_rays_2d_segments_job  # noqa: PLC0415
        from .targeted_resimulation import targeted_source_for_path  # noqa: PLC0415

        o = self.options
        try:
            described = self.portable or portable_scene(self.ctx["scene"])
        except NotPortable as exc:
            return {"skipped": f"the scene is not portable: {exc}"}
        targeted = targeted_source_for_path(self.path, self.ctx["bidirectional"], self.source,
                                            cone_half_angle_deg=o["cone_half_angle_deg"])
        rays = sample_source_rays(targeted, density_for(o["rays"], targeted.emis_angle))
        n = len(rays["points"])
        k = min(PILOT_RAYS, n)
        pick = sorted({round(i * (n - 1) / max(1, k - 1)) for i in range(k)})
        sample = {key: [v[i] for i in pick] for key, v in rays.items()}
        out = simulate_rays_2d_segments_job(
            {"scene": described, "rays": sample, "source_name": targeted.name,
             "min_brightness_exp": o["min_brightness_exp"],
             "max_rays": max(1000, math.ceil(o["max_rays"] * len(pick) / max(1, o["rays"])))}, _Quiet())
        roots = sum(1 for parent in out["segments"]["parent"] if parent == -1)
        if not roots or not out["count"]:
            return {"rays": roots, "segments": out["count"], "s": round(out["sim_s"], 3)}
        return {"rays": roots, "segments": out["count"], "s": round(out["sim_s"], 3),
                "per_ray": out["count"] / roots, "s_per_segment": out["sim_s"] / out["count"]}

    def _sim_rate(self) -> Dict[str, float]:
        """Segments a ray and seconds a segment here: the pilot's, else the broad run's and the measured rate."""
        p = self.pilot or {}
        return {"per_ray": p.get("per_ray") or self.segments_expected.get("per_ray") or 1.0,
                "s_per_segment": p.get("s_per_segment") or estimate_s("simulate_2d_segment", 1)}

    def _estimate(self) -> Dict[str, Any]:
        o = self.options
        others = [s["name"] for s in self._sources() if s["uuid"] != self.source.uuid]
        self.pilot = self._run_pilot()
        rate = self._sim_rate()
        segments = math.ceil(o["rays"] * rate["per_ray"])
        after = estimate_s("context_2d_segment", segments)
        seg_info = {**self.segments_expected, "pilot_per_ray": self.pilot.get("per_ray"),
                    "expected_from_pilot": segments,
                    "may_truncate": bool(self.segments_expected.get("may_truncate"))
                    or segments >= o["max_rays"]}
        common = {"rays": o["rays"], "after_s": round(after, 1),
                  "after": "here, once the rays are back: merging, the context's database, grouping, saving",
                  "pilot": self.pilot, "other_sources_silenced": others, "segments": seg_info}
        if o["executor"] == "kernel":
            simulate = segments * rate["s_per_segment"]
            seconds = simulate + after
            return {**common, "simulate_s": round(simulate, 1), "total_s": seconds, "total": format_duration(seconds),
                    "where": "this kernel (blocks it while it runs)"}
        size = self._chunk_size()
        chunks = math.ceil(o["rays"] / size)
        per_chunk = self._chunk_budget_s(min(size, o["rays"]))
        if o["executor"] == "in_process":
            simulate = per_chunk * chunks
        elif o["executor"] == "modal":
            simulate = per_chunk + MODAL_PER_JOB_S * chunks
        else:
            simulate = per_chunk
        seconds = simulate + after
        out = {**common, "chunks": chunks, "chunk_rays": size, "simulate_s": round(simulate, 1), "total_s": seconds,
               "total": format_duration(seconds), "executor": o["executor"],
               "where": {"in_process": "this kernel, chunk after chunk (blocks it while it runs)",
                         "local_process": "worker processes on this machine, side by side",
                         "modal": f"Modal ({MODAL_APP}), a container per chunk, side by side"}[o["executor"]]}
        if o["executor"] == "modal":
            from ..flows.modal_executor import CPU_USD_PER_CORE_S, MEMORY_USD_PER_GIB_S  # noqa: PLC0415
            per_s = CPU_USD_PER_CORE_S + 2.0 * MEMORY_USD_PER_GIB_S      # the jobs' function: 1 core, 2 GiB
            out["cost_usd_est"] = round(per_chunk * chunks * per_s, 6)
            out["cost_note"] = ("the chunks' run time at Modal's rates; the bill also counts each container's "
                                "start and idle time")
        return out

    def _chunk_budget_s(self, rays: int) -> float:
        """How long one chunk of ``rays`` should take where it runs, its start included."""
        o = self.options
        rate = self._sim_rate()
        speed = MODAL_SPEED["simulate_2d_segment"] if o["executor"] == "modal" else 1.0
        return rays * rate["per_ray"] * rate["s_per_segment"] * speed + JOB_START_S[o["executor"]]

    def on_enter_awaiting_go_ahead(self, *_a: Any, **_k: Any) -> None:
        self.estimate = self._estimate()
        if self.estimate["total_s"] <= ASK_OVER_S:
            self.set_explanation(explain_field("go_ahead", f"Estimated at {self.estimate['total']}: no need to ask.",
                                               "a box may spend a minute without asking", ""))
            self.emit_event(message=f"estimated at {self.estimate['total']}; going on", estimate=self.estimate)
            self._advance()
            return
        self._ask()

    def _provide_go_ahead(self, value: Any) -> None:
        self._going = bool(value)

    def _go(self, *_a: Any, **_k: Any) -> bool:
        if not self._going:
            self.emit_event(message="not confirmed: back to the options")
        return self._going

    # -- the run -------------------------------------------------------------------

    def on_enter_resimulating(self, *_a: Any, **_k: Any) -> None:
        from .targeted_resimulation import run_targeted_resimulation, targeted_source_for_path

        o = self.options
        scene, bidir = self.ctx["scene"], self.ctx["bidirectional"]
        where = "in this kernel" if o["executor"] == "kernel" else f"in chunks, on {o['executor']}"
        self.set_explanation(explain_field("resimulating", f"Re-running path {self.rank or ''} with {o['rays']} "
                                           "rays.", where, ""))
        targeted = targeted_source_for_path(self.path, bidir, self.source,
                                            cone_half_angle_deg=o["cone_half_angle_deg"])
        self._targeted, self._density = targeted, density_for(o["rays"], targeted.emis_angle)
        if o["executor"] == "kernel":
            result = run_targeted_resimulation(
                scene, self.source, targeted, max_rays=o["max_rays"], record_surface_hits=True,
                min_brightness_exp=o["min_brightness_exp"], ray_density=self._density, name=o["context_name"])
            self._keep(result, truncated=result.processed_ray_count >= o["max_rays"])
            self._advance()
            return
        self._submit_chunks()

    def _executor(self) -> Any:
        from ..flows.executors import InProcessExecutor, LocalProcessExecutor  # noqa: PLC0415

        kind = self.options["executor"]
        if kind == "in_process":
            return InProcessExecutor()
        if kind == "modal":
            from ..flows.modal_executor import ModalExecutor  # noqa: PLC0415
            return ModalExecutor(MODAL_APP)
        return LocalProcessExecutor(Path(self.base_dir) / "jobs")

    def _submit_chunks(self) -> None:
        from ..flows.executors import Job  # noqa: PLC0415
        from .ray_jobs import chunk_rays, sample_source_rays  # noqa: PLC0415

        o = self.options
        rays = sample_source_rays(self._targeted, self._density)
        n = len(rays["points"])
        chunks = chunk_rays(rays, self._chunk_size())
        self._chunk_caps = [math.ceil(o["max_rays"] * len(c["points"]) / n) for c in chunks]
        jobs = [Job(SEGMENTS_JOB, {"scene": self.portable, "rays": c, "source_name": self._targeted.name,
                                   "min_brightness_exp": o["min_brightness_exp"], "max_rays": cap},
                    budget_s=self._chunk_budget_s(len(c["points"])),
                    label=f"chunk {i + 1} of {len(chunks)}")
                for i, (c, cap) in enumerate(zip(chunks, self._chunk_caps))]
        self.emit_event(message=f"{n} rays in {len(chunks)} chunks to {o['executor']}")
        self.submit_group(self._executor(), jobs, on_done="resimulated", label="re-simulation chunks",
                          budget_s=self.estimate["total_s"] if self.estimate else None)

    def _merge_chunks(self, results: List[Dict[str, Any]], *_a: Any, **_k: Any) -> None:
        from .ray_jobs import merge_segment_results  # noqa: PLC0415

        o = self.options
        result = merge_segment_results(results, self.ctx["scene"], source=self._targeted, max_rays=o["max_rays"],
                                       name=o["context_name"])
        truncated = any(r["processed"] >= cap for r, cap in zip(results, self._chunk_caps))
        self._keep(result, truncated=truncated, chunks=len(results),
                   sim_s=sum(r["sim_s"] for r in results))

    def _keep(self, result: Any, *, truncated: bool, **extra: Any) -> None:
        """Put a re-simulation's result into its new context, save it, and summarise it."""
        o = self.options
        scene, bidir = self.ctx["scene"], self.ctx["bidirectional"]
        agentic_tools.set_context_from_result(scene, result, context_name=o["context_name"],
                                              origin="targeted re-simulation")
        detector = next((d for d in scene.objs if getattr(d, "name", None) == bidir.detector_name
                         and hasattr(d, "get_hit_records")), None)
        summary = bounce_groups(result, detector.uuid if detector is not None else None, self._targeted.uuid)
        folder = persistence.run_dir(Path(self.base_dir), self.run_id)
        numerical = {**o, "ray_density": self._density, "root_uuid": self.path["path_uuids"][0]}
        saved = agentic_tools.save_context_tool(str(folder), "targeted", o["context_name"],
                                                physical_params={}, numerical_params=numerical,
                                                context_name=o["context_name"])
        if saved["status"] != "ok":
            raise RuntimeError(f"the re-simulation ran, but its bundle was not saved: {saved['message']}")
        bundle = Path(saved["data"]["run_dir"])
        self.result = {
            "context_name": o["context_name"], "from_context": self.context_name, "path_rank": self.rank,
            "source": getattr(self.source, "name", None), "detector": bidir.detector_name,
            "options": o, "ray_density": self._density, "segments": result.segment_count,
            "truncated": truncated, "executor": o["executor"], **extra,
            **{k: summary[k] for k in ("roots", "emitted", "hits", "energy_at_detector")},
            "groups": summary["groups"][:LISTED_GROUPS], "group_count": len(summary["groups"]),
            "bundle": str(bundle.resolve()),
        }
        self.emit_event(message=f"{summary['roots']} rays, {summary['hits']} at the detector in "
                                f"{len(summary['groups'])} groups; context {o['context_name']!r}")

    def on_enter_done(self, *_a: Any, **_k: Any) -> None:
        self.finish(self.result)
        self.set_explanation(explain_field(
            "done", f"The re-simulation is in context {self.result['context_name']!r} (not active: "
            "set_active_context to read it) and saved at its bundle.", "result: the grouped summary", ""))
        self.emit_event(message="done")


def _modal_installed() -> bool:
    """Whether the Modal client can be imported here."""
    import importlib.util  # noqa: PLC0415
    import sys  # noqa: PLC0415

    if sys.modules.get("modal") is not None:
        return True
    try:
        return importlib.util.find_spec("modal") is not None
    except (ImportError, ValueError):
        return False


__all__ = ["EXECUTORS", "FIELDS", "OPTIONS", "STATES", "TRANSITIONS", "TargetedResimulationFlow", "bounce_groups", "density_for"]
