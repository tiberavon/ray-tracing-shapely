"""
Python-specific module: parameter study flow
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
PYTHON-SPECIFIC MODULE: the parameter study flow
===============================================================================
A scene file, one of its parameters swept (or two, as a grid), the scene traced
at every point and read at a detector: a flow an agent or a person starts by
name (``flow_start("parameter_study")``), so the study is a record.

    start -> awaiting_scene -> loading -> awaiting_parameters -> checking_parameters
          -> awaiting_measure -> awaiting_executor -> awaiting_go_ahead -> tracing
          -> collecting -> done

- **awaiting_scene:** the scene file's path (`scene_file.save_scene`).
- **loading** builds it: every object, the names unique, at least one source
  and one detector. A scene that does not build sends the flow back, with the
  reason.
- **awaiting_parameters:** one axis, or two as a grid: ``{object, parameter,
  values}`` or ``{object, parameter, from, to, steps}``. The question's context
  is the scene's parameter table (`parameter_study.parameter_table`): every
  object, every parameter, its value. Values are in the scene's own units.
- **checking_parameters** builds the scene at the sweep's ends (both ends of an
  axis, a grid's four corners) before anything is traced (`KA9`). One that does
  not build sends the flow back to the parameters, with the reason.
- **awaiting_measure:** the detector, what is read on it (``power``, ``share``
  of the sources' emitted power, ``centroid``: the power-weighted position
  along it, or ``profile``), and the numerical settings: ray density, the
  brightness threshold, the segment limit, whether each point is saved as a
  run.
- **awaiting_executor:** where the points run: ``in_process`` (this kernel,
  one after another), ``local_process`` (worker processes here, at most one per
  two cores, the points shared among them) or ``modal`` (a container per
  point).
- **awaiting_go_ahead** is always entered. A pilot traces the first point here
  at a few of its rays: its segments a ray and this machine's seconds a segment.
  An estimate within a minute goes on; a longer one is asked (``false`` goes
  back to the executor).
- **tracing** follows the jobs as one step (`submit_group`). A point that
  cannot be built or traced is recorded as failed with its reason, and the
  study goes on.
- **collecting** writes the table (``table.csv``), the plot (``plot.svg``) and
  the result; each point saved as a run bundle when asked, its swept values as
  physical parameters and the ray settings as numerical ones (`KC3`), so any
  two can be compared (`compare_run_dirs`).
===============================================================================
"""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..flows import persistence
from ..flows.budgets import ASK_OVER_S, JOB_START_S, MODAL_PER_JOB_S, MODAL_SPEED, estimate_s, format_duration
from ..flows.fields import FlowField, explain_field
from ..flows.flow_base import ObservableFlow
from . import parameter_study as ps

EXECUTORS = ("in_process", "local_process", "modal")
#: The deployed Modal app the ``modal`` executor sends the points to.
MODAL_APP = os.environ.get("RTS_MODAL_APP", "rts-jobs")
POINTS_JOB = "ray_tracing_shapely.analysis.parameter_study:study_points_job"
#: About this many of a point's rays are traced here before the estimate.
PILOT_RAYS = 50
#: The segment limit, by default, is a point's expected segments times this, at least `MIN_SEGMENTS`.
SEGMENTS_HEADROOM = 4.0
MIN_SEGMENTS = 10_000
#: No point is sized past this many segments.
MAX_SEGMENTS = 2_000_000
#: The measure's options and their defaults (None: the scene file's own, or sized from the pilot).
MEASURE_OPTIONS: Dict[str, Any] = {"detector": None, "measure": "power", "ray_density": None,
                                   "min_brightness_exp": None, "max_rays": None, "save_runs": True}

FIELDS: Dict[str, FlowField] = {
    "awaiting_scene": FlowField(
        "scene_path", "path",
        "Which scene? The path of a scene file (save_scene writes one).",
        "every point is this scene with the swept parameters changed",
        'e.g. "abbe.scene.json"', pattern="*.scene.json"),
    "awaiting_parameters": FlowField(
        "parameters", "json",
        "Which parameter, over which values? One axis, or a list of two (a grid): {object, parameter, values: "
        "[...]} or {object, parameter, from, to, steps}. The scene's objects and their parameters are in the "
        "question's context; values are in the scene's own units. Every object also has rotate_deg, move_x "
        "and move_y.",
        "the scene is built at the sweep's ends before anything is traced",
        'e.g. {"object": "medium", "parameter": "refIndex", "from": 1.33, "to": 1.5, "steps": 8}'),
    "awaiting_measure": FlowField(
        "measure", "json",
        "What is read, and how finely? {detector (required unless the scene has one), measure (power, share, "
        "centroid or profile; power by default), ray_density, min_brightness_exp (both the scene file's by "
        "default), max_rays (the segment limit a point; sized from a pilot by default), save_runs (true: each "
        "point saved as a run)}.",
        "power and share are the light crossing it (a Photodetector's: absorbed, never negative; a Detector's: signed "
        "by the direction it crosses); centroid is where along it, from its p1; profile is its bins",
        'e.g. {"detector": "eyepiece", "measure": "centroid"}'),
    "awaiting_executor": FlowField(
        "executor", "choice",
        "Where do the points run? in_process (this kernel, one after another: blocks it), local_process "
        "(worker processes here, side by side) or modal (a container a point).",
        "the estimate, next, says how long each would take",
        'e.g. "local_process"', default="local_process", choices=EXECUTORS),
    "awaiting_go_ahead": FlowField(
        "go_ahead", "bool",
        "The study is estimated over a minute (the estimate is in the question's context). Go ahead? false "
        "goes back to the executor.",
        "a box may spend a minute without asking",
        "e.g. true"),
}

STATES = ["start", "awaiting_scene", "loading", "awaiting_parameters", "checking_parameters", "awaiting_measure",
          "awaiting_executor", "awaiting_go_ahead", "tracing", "collecting", "done"]

TRANSITIONS = [
    {"trigger": "begin", "source": "start", "dest": "awaiting_scene"},
    {"trigger": "provide_scene_path", "source": "awaiting_scene", "dest": "loading", "before": "_provide_scene"},
    {"trigger": "_advance", "source": "loading", "dest": "awaiting_parameters"},
    {"trigger": "_back", "source": "loading", "dest": "awaiting_scene"},
    {"trigger": "provide_parameters", "source": "awaiting_parameters", "dest": "checking_parameters",
     "before": "_provide_parameters"},
    {"trigger": "_advance", "source": "checking_parameters", "dest": "awaiting_measure"},
    {"trigger": "_back", "source": "checking_parameters", "dest": "awaiting_parameters"},
    {"trigger": "provide_measure", "source": "awaiting_measure", "dest": "awaiting_executor",
     "before": "_provide_measure"},
    {"trigger": "provide_executor", "source": "awaiting_executor", "dest": "awaiting_go_ahead",
     "before": "_provide_executor"},
    {"trigger": "_advance", "source": "awaiting_go_ahead", "dest": "tracing"},
    {"trigger": "provide_go_ahead", "source": "awaiting_go_ahead", "dest": "tracing", "conditions": "_go",
     "prepare": "_provide_go_ahead"},
    {"trigger": "provide_go_ahead", "source": "awaiting_go_ahead", "dest": "awaiting_executor"},
    {"trigger": "traced", "source": "tracing", "dest": "collecting", "before": "_keep_points"},
    {"trigger": "_advance", "source": "collecting", "dest": "done"},
    {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
]


class _Quiet:
    """A job context that reports nowhere: the pilot runs here."""

    def progress(self, *_a: Any, **_k: Any) -> None:
        pass


class ParameterStudyFlow(ObservableFlow):
    """A scene file with a parameter swept, traced at every point and read at a detector.

    Construct it (``begin()`` is called), then answer each question
    (``answer(value)``). At ``done``, ``self.result`` holds the table, one row
    a point, and the paths of the table's CSV, the plot and the saved runs.

    Args:
        base_dir: Where the run's folder is written.
        run_id: An explicit run id, or None for a generated one.
        render_svg: Re-render ``state.svg`` on every move (needs Graphviz's ``dot``).
    """

    FIELDS = FIELDS
    PURPOSE = ("Sweep one parameter of a scene file (or two, as a grid), trace the scene at every point and read "
               "a detector: a table, a plot, and each point saved as a run.")

    def __init__(self, base_dir: Path, run_id: Optional[str] = None, render_svg: bool = True) -> None:
        self._clear()
        super().__init__(name="parameter_study", states=STATES, transitions_list=TRANSITIONS, initial="start",
                         base_dir=base_dir, run_id=run_id, render_svg=render_svg)
        self.begin()

    def _clear(self) -> None:
        self.scene_path: Optional[Path] = None
        self.data: Optional[Dict[str, Any]] = None
        self.sources: List[str] = []
        self.detectors: List[str] = []
        self.axes: List[Dict[str, Any]] = []
        self.points: List[List[Dict[str, Any]]] = []
        self.options: Dict[str, Any] = dict(MEASURE_OPTIONS)
        self.executor: str = "local_process"
        self.pilot: Dict[str, Any] = {}
        self.estimate: Optional[Dict[str, Any]] = None
        self.result: Optional[Dict[str, Any]] = None
        self._going = False
        self._back_reason: Optional[str] = None
        self._batches: List[List[int]] = []

    def _on_reset(self, *args: Any, **kwargs: Any) -> None:
        super()._on_reset(*args, **kwargs)
        self._clear()

    def _ask(self) -> None:
        field = self.FIELDS[self.state]
        explanation = field.explanation()
        self.set_explanation(explanation)
        self.emit_event(field=field.name, message=explanation.message)
        self.update_detail(waiting_on=field.name)

    def _say(self, what: str, why: str) -> None:
        self.set_explanation(explain_field(self.state, what, why, ""))
        self.emit_event(message=what)

    def send_back_reason(self) -> Optional[str]:
        return self._back_reason

    def _send_back(self, reason: str) -> None:
        self._back_reason = reason
        self.emit_event(message=f"sent back: {reason}", sent_back=True)
        self._back()
        self.set_explanation(explain_field(self.state, f"{reason}. {self.FIELDS[self.state].question}",
                                           self.FIELDS[self.state].why, self.FIELDS[self.state].example))

    def question_context(self) -> Optional[Dict[str, Any]]:
        if self.state == "awaiting_parameters":
            return {"objects": ps.parameter_table(self.data), "transforms": list(ps.TRANSFORMS),
                    "max_points": ps.MAX_POINTS}
        if self.state == "awaiting_measure":
            settings = self.data.get("settings", {})
            return {"detectors": self.detectors, "sources": self.sources, "measures": list(ps.MEASURES),
                    "scene_ray_density": settings.get("ray_mode_density"),
                    "scene_min_brightness_exp": settings.get("min_brightness_exp"),
                    "points": len(self.points)}
        if self.state == "awaiting_executor":
            return {"executors": list(EXECUTORS), "points": len(self.points), "cores": os.cpu_count()}
        if self.state == "awaiting_go_ahead":
            return self.estimate
        return None

    def question_form(self) -> Optional[Dict[str, Any]]:
        """The sweep and the measure as forms: choices from the scene, defaults from the file."""
        if self.state == "awaiting_parameters":
            return _sweep_form(ps.parameter_table(self.data))
        if self.state == "awaiting_measure":
            settings = self.data.get("settings", {})
            return {"kind": "object", "prompt": "What is read at every point, and how finely is it traced?", "fields": [
                {"name": "detector", "label": "detector", "kind": "choice", "choices": list(self.detectors),
                 "help": "the detector read at every point"},
                {"name": "measure", "label": "what is read", "kind": "choice", "default": "power",
                 "choices": [{"value": "power", "label": "power: the light reaching it"},
                             {"value": "share", "label": "share: power over the sources' emitted power"},
                             {"value": "centroid", "label": "centroid: where along it the light lands, from p1"},
                             {"value": "profile", "label": "profile: the light in each of its bins"}]},
                {"name": "ray_density", "label": "ray density", "kind": "number",
                 "default": settings.get("ray_mode_density"), "help": "the scene file's, by default"},
                {"name": "min_brightness_exp", "label": "brightness threshold, 10^-n", "kind": "integer",
                 "default": settings.get("min_brightness_exp"), "optional": True,
                 "help": "rays dimmer than 10^-n are dropped; blank: the scene's colour mode decides"},
                {"name": "max_rays", "label": "segment limit a point", "kind": "integer", "optional": True,
                 "help": "blank: sized from a pilot of the first point"},
                {"name": "save_runs", "label": "save each point as a run", "kind": "bool", "default": True},
            ]}
        return None

    # -- the scene ------------------------------------------------------------------

    def on_enter_awaiting_scene(self, *_a: Any, **_k: Any) -> None:
        if self._back_reason is None:
            self._ask()

    def _provide_scene(self, value: str) -> None:
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError(f"no file at {value!r}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{value!r} is not a scene file: {exc}") from exc
        self.scene_path, self.data = path.resolve(), data
        self._back_reason = None

    def on_enter_loading(self, *_a: Any, **_k: Any) -> None:
        try:
            scene = ps.build_point(self.data, [])
        except Exception as exc:  # noqa: BLE001 -- a scene that does not build goes back, with why
            self._send_back(f"the scene does not build: {type(exc).__name__}: {exc}")
            return
        self.sources, self.detectors = ps.sources_and_detectors(scene)
        missing = [what for what, names in (("source", self.sources), ("detector", self.detectors)) if not names]
        unnamed = [type(o).__name__ for o in scene.objs if not getattr(o, "name", None)]
        if missing or unnamed:
            why = [f"it has no {m}" for m in missing] + ([f"objects without a name: {unnamed}"] if unnamed else [])
            self._send_back(f"the scene cannot be studied: {'; '.join(why)}")
            return
        self._say(f"Loaded {self.scene_path.name}: {len(scene.objs)} objects, sources {self.sources}, "
                  f"detectors {self.detectors}.", "every object built from the file")
        self._advance()

    # -- the parameters -------------------------------------------------------------

    def on_enter_awaiting_parameters(self, *_a: Any, **_k: Any) -> None:
        if self._back_reason is None:
            self._ask()

    def _provide_parameters(self, value: Any) -> None:
        try:
            self.axes = ps.sweep_axes(self.data, value)
        except ps.StudyError as exc:
            raise ValueError(str(exc)) from exc
        self.points = ps.sweep_points(self.axes)
        self._back_reason = None

    def on_enter_checking_parameters(self, *_a: Any, **_k: Any) -> None:
        corners = ps.corner_points(self.axes)
        for changes in corners:
            try:
                ps.build_point(self.data, changes)
            except Exception as exc:  # noqa: BLE001 -- an end that does not build goes back, with why
                self._send_back(f"the scene does not build at {ps.point_label(changes)}: "
                                f"{type(exc).__name__}: {exc}")
                return
        span = ", ".join(f"{a['object']}.{a['parameter']} {a['values'][0]:g} to {a['values'][-1]:g} "
                         f"({len(a['values'])} values; now {a['current']:g})" for a in self.axes)
        self._say(f"The scene builds at the sweep's {len(corners)} ends: {span}; {len(self.points)} points.",
                  "checked before anything is traced")
        self._advance()

    # -- the measure ----------------------------------------------------------------

    def on_enter_awaiting_measure(self, *_a: Any, **_k: Any) -> None:
        self._ask()

    def _provide_measure(self, value: Any) -> None:
        value = {} if value is None else value
        if not isinstance(value, dict):
            raise ValueError(f"measure takes an object, got {value!r}")
        unknown = sorted(set(value) - set(MEASURE_OPTIONS))
        if unknown:
            raise ValueError(f"measure: unknown {unknown}; known {sorted(MEASURE_OPTIONS)}")
        out = {**MEASURE_OPTIONS, **value}
        if out["detector"] is None:
            if len(self.detectors) != 1:
                raise ValueError(f"measure.detector: the scene has {len(self.detectors)} detectors, name one: "
                                 f"{self.detectors}")
            out["detector"] = self.detectors[0]
        if out["detector"] not in self.detectors:
            raise ValueError(f"measure.detector: no detector {out['detector']!r}; the scene's: {self.detectors}")
        if out["measure"] not in ps.MEASURES:
            raise ValueError(f"measure.measure is one of {list(ps.MEASURES)}, got {out['measure']!r}")
        settings = self.data.get("settings", {})
        if out["ray_density"] is None:
            out["ray_density"] = settings.get("ray_mode_density")
        v = out["ray_density"]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not v > 0:
            raise ValueError(f"measure.ray_density must be a number above 0, got {v!r}")
        if out["min_brightness_exp"] is None:
            out["min_brightness_exp"] = settings.get("min_brightness_exp")
        v = out["min_brightness_exp"]
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            raise ValueError(f"measure.min_brightness_exp must be a whole number >= 0, got {v!r}")
        v = out["max_rays"]
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MAX_SEGMENTS):
            raise ValueError(f"measure.max_rays must be a whole number from 1 to {MAX_SEGMENTS:,}, got {v!r}")
        if not isinstance(out["save_runs"], bool):
            raise ValueError(f"measure.save_runs takes true or false, got {out['save_runs']!r}")
        self.options = out

    # -- the executor and the estimate ------------------------------------------------

    def on_enter_awaiting_executor(self, *_a: Any, **_k: Any) -> None:
        self._ask()

    def _provide_executor(self, value: str) -> None:
        if value == "modal" and not _modal_installed():
            raise ValueError("executor modal: the Modal client is not installed here; choose local_process or "
                             "in_process")
        self.executor = value

    def _run_pilot(self) -> Dict[str, Any]:
        """A few of the first point's rays traced here: its rays, its segments a ray, the seconds a segment."""
        from .ray_jobs import sample_source_rays  # noqa: PLC0415

        o = self.options
        first = self.points[0]
        scene = ps.build_point(self.data, first)
        sources = [obj for obj in scene.objs if getattr(type(obj), "type", "") in ps.SOURCE_TYPES]
        rays = sum(len(sample_source_rays(s, o["ray_density"])["points"]) for s in sources)
        density = o["ray_density"] if rays <= PILOT_RAYS else o["ray_density"] * PILOT_RAYS / rays
        _, result, reading = ps.trace_point(self.data, first, detector=o["detector"], ray_density=density,
                                            min_brightness_exp=o["min_brightness_exp"],
                                            max_rays=o["max_rays"] or MAX_SEGMENTS)
        roots = sum(1 for s in result.segments if getattr(s, "parent_uuid", None) is None)
        out = {"point": ps.point_label(first), "rays_a_point": rays, "ray_density": density, "rays": roots,
               "segments": reading["segments"], "s": round(reading["sim_s"], 3), "hits": reading["hits"]}
        if roots and reading["segments"]:
            out.update(per_ray=reading["segments"] / roots, s_per_segment=reading["sim_s"] / reading["segments"])
        return out

    def _batches_for(self, executor: str) -> List[List[int]]:
        n = len(self.points)
        if executor == "local_process":
            workers = min(n, max(1, (os.cpu_count() or 2) // 2))
            return [list(range(n))[k::workers] for k in range(workers)]
        return [[i] for i in range(n)]

    def _estimate(self) -> Dict[str, Any]:
        o = self.options
        self.pilot = self._run_pilot()
        per_ray = self.pilot.get("per_ray") or 1.0
        s_seg = self.pilot.get("s_per_segment") or estimate_s("simulate_2d_segment", 1)
        segments = math.ceil(self.pilot["rays_a_point"] * per_ray)
        if o["max_rays"] is None:
            o["max_rays"] = min(MAX_SEGMENTS, max(MIN_SEGMENTS, math.ceil(segments * SEGMENTS_HEADROOM)))
        speed = MODAL_SPEED["simulate_2d_segment"] if self.executor == "modal" else 1.0
        # saving a point as a run costs about what an agent context's database does, a segment
        save_s = estimate_s("context_2d_segment", segments) if o["save_runs"] and self.executor != "modal" else 0.0
        point_s = segments * s_seg * speed + save_s
        self._batches = self._batches_for(self.executor)
        job_s = [len(b) * point_s + JOB_START_S[self.executor] for b in self._batches]
        if self.executor == "in_process":
            total = sum(job_s)
        elif self.executor == "modal":
            total = max(job_s) + MODAL_PER_JOB_S * len(job_s)
        else:
            total = max(job_s)
        where = {"in_process": "this kernel, one point after another (blocks it while it runs)",
                 "local_process": f"{len(self._batches)} worker processes on this machine, side by side",
                 "modal": f"Modal ({MODAL_APP}), a container a point, side by side"}[self.executor]
        out = {"points": len(self.points), "jobs": len(self._batches), "executor": self.executor, "where": where,
               "segments_a_point": segments, "max_rays": o["max_rays"], "point_s": round(point_s, 2),
               "total_s": total, "total": format_duration(total), "pilot": self.pilot,
               "may_truncate": segments >= o["max_rays"]}
        if not self.pilot["hits"]:
            out["warning"] = (f"the pilot put nothing on {o['detector']!r} at the first point: if that is not "
                              "expected, check where the detector is and, if it is one-sided, which side is "
                              "its front (twoSided, absorbingSide)")
        if self.executor == "modal":
            out["runs_saved"] = False
            out["note"] = ("on Modal the points are read there and not saved as runs; the deployed app must "
                           "include this package's parameter_study module")
        return out

    def on_enter_awaiting_go_ahead(self, *_a: Any, **_k: Any) -> None:
        self.estimate = self._estimate()
        if self.estimate["total_s"] <= ASK_OVER_S:
            self._say(f"Estimated at {self.estimate['total']} for {len(self.points)} points: no need to ask.",
                      "a box may spend a minute without asking")
            self._advance()
            return
        self._ask()

    def _provide_go_ahead(self, value: Any) -> None:
        self._going = bool(value)

    def _go(self, *_a: Any, **_k: Any) -> bool:
        if not self._going:
            self.emit_event(message="not confirmed: back to the executor")
        return self._going

    # -- the points -------------------------------------------------------------------

    def _executor(self) -> Any:
        from ..flows.executors import InProcessExecutor, LocalProcessExecutor  # noqa: PLC0415

        if self.executor == "in_process":
            return InProcessExecutor()
        if self.executor == "modal":
            from ..flows.modal_executor import ModalExecutor  # noqa: PLC0415
            return ModalExecutor(MODAL_APP)
        return LocalProcessExecutor(Path(self.base_dir) / "jobs")

    def _runs_dir(self) -> Optional[Path]:
        if not self.options["save_runs"] or self.executor == "modal":
            return None
        # absolute: a worker process starts in its own job folder
        return (persistence.run_dir(Path(self.base_dir), self.run_id) / "runs").resolve()

    def on_enter_tracing(self, *_a: Any, **_k: Any) -> None:
        from ..flows.executors import Job  # noqa: PLC0415

        o = self.options
        runs_dir = self._runs_dir()
        point_s = self.estimate["point_s"] if self.estimate else None
        jobs = [Job(POINTS_JOB,
                    {"scene": self.data, "points": [{"index": i, "changes": self.points[i]} for i in batch],
                     "detector": o["detector"], "measure": o["measure"], "ray_density": o["ray_density"],
                     "min_brightness_exp": o["min_brightness_exp"], "max_rays": o["max_rays"],
                     "runs_dir": str(runs_dir) if runs_dir else None, "study_id": "points"},
                    budget_s=(len(batch) * point_s + JOB_START_S[self.executor]) if point_s is not None else None,
                    label=f"points {batch[0] + 1}..{batch[-1] + 1}" if len(batch) > 1 else f"point {batch[0] + 1}")
                for batch in self._batches]
        self.set_explanation(explain_field("tracing", f"Tracing {len(self.points)} points in {len(jobs)} jobs "
                                           f"on {self.executor}.", self.estimate["where"], ""))
        self.submit_group(self._executor(), jobs, on_done="traced", label="study points",
                          budget_s=self.estimate["total_s"] if self.estimate else None)

    def _keep_points(self, results: List[Dict[str, Any]], *_a: Any, **_k: Any) -> None:
        o = self.options
        by_index = {p["index"]: p for r in results for p in r["points"]}
        rows = []
        for i, changes in enumerate(self.points):
            got = by_index.get(i, {"ok": False, "error": "no result came back for this point"})
            rows.append({"index": i, "point": ps.point_label(changes), **{k: v for k, v in got.items()
                                                                          if k != "index"}})
        folder = persistence.run_dir(Path(self.base_dir), self.run_id).resolve()
        table = folder / "table.csv"
        keys = [f"{a['object']}.{a['parameter']}" for a in self.axes]
        columns = ["power", "share", "centroid", "hits", "segments", "truncated", "ok", "error", "run_dir"]
        with open(table, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["index", *keys, *columns])
            for r in rows:
                w.writerow([r["index"], *(r["point"][k] for k in keys), *(r.get(c) for c in columns)])
        plot = ps.plot_svg(rows, self.axes, o["measure"], folder / "plot.svg")
        arrays = folder / "arrays.npz"
        failed = [r for r in rows if not r.get("ok")]
        runs_dir = self._runs_dir()
        self.result = {
            "scene_path": str(self.scene_path), "axes": [{k: a[k] for k in ("object", "parameter", "values",
                                                                              "current")} for a in self.axes],
            "detector": o["detector"], "measure": o["measure"],
            "numerical": {k: o[k] for k in ("ray_density", "min_brightness_exp", "max_rays")},
            "executor": self.executor, "points": len(rows), "failed": len(failed), "rows": rows,
            "table": str(table), "plot": str(plot) if plot else None, "arrays": str(arrays),
            "runs_dir": str(runs_dir) if runs_dir else None,
            "truncated": sum(1 for r in rows if r.get("truncated")),
        }
        import numpy as np  # noqa: PLC0415

        np.savez(arrays, **ps.study_arrays(self.result))
        self.emit_event(message=f"{len(rows)} points, {len(failed)} failed; the table at {table.name}",
                        failed=[{"index": r["index"], "error": r["error"]} for r in failed])

    def on_enter_collecting(self, *_a: Any, **_k: Any) -> None:
        self._say("Collected the points into the table and the plot.", "table.csv, plot.svg, result.json")
        self._advance()

    def on_enter_done(self, *_a: Any, **_k: Any) -> None:
        self.finish(self.result)
        r = self.result
        self.set_explanation(explain_field(
            "done", f"{r['points']} points, {r['failed']} failed: {r['measure']} at {r['detector']!r} in the "
            "table.", "result: rows, table, plot, runs_dir", ""))
        self.emit_event(message="done")


def _sweep_form(table: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One axis or two, each an object, one of its parameters, and a range or a list of values."""
    objects = [o for o in table if o["parameters"]]

    def order(p: Dict[str, Any]) -> int:          # the object's own numbers first, then its points, then a move
        name = p["parameter"]
        return 2 if name in ps.TRANSFORMS else 1 if "." in name else 0

    axis = {"kind": "object", "fields": [
        {"name": "object", "label": "object", "kind": "choice",
         "choices": [{"value": o["object"], "label": f"{o['object']} ({o['type']})"} for o in objects]},
        {"name": "parameter", "label": "parameter", "kind": "choice",
         "choices_by": {"field": "object", "map": {
             o["object"]: [{"value": p["parameter"], "label": f"{p['parameter']} (now {p['value']:g})"}
                           for p in sorted(o["parameters"], key=order)] for o in objects}}},
        {"name": "mode", "label": "values", "kind": "choice", "local": True, "default": "range",
         "choices": [{"value": "range", "label": "a range: from, to, steps"},
                     {"value": "values", "label": "a list of values"}]},
        {"name": "from", "label": "from", "kind": "number", "when": {"field": "mode", "is": ["range"]}},
        {"name": "to", "label": "to", "kind": "number", "when": {"field": "mode", "is": ["range"]}},
        {"name": "steps", "label": "steps (the ends included)", "kind": "integer", "default": 5,
         "when": {"field": "mode", "is": ["range"]}},
        {"name": "values", "label": "values", "kind": "numbers", "help": "numbers separated by commas",
         "when": {"field": "mode", "is": ["values"]}},
    ]}
    return {"kind": "list", "prompt": "Which parameter is swept, over which values? Two axes make a grid.",
            "item": axis, "min": 1, "max": 2, "item_label": "axis",
            "add_label": "add a second axis (a grid)"}


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


__all__ = ["EXECUTORS", "FIELDS", "MEASURE_OPTIONS", "ParameterStudyFlow", "STATES", "TRANSITIONS"]
