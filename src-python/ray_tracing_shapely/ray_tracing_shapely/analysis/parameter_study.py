"""
Python-specific module: parameter study -- one scene, a parameter swept, a detector read
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
PYTHON-SPECIFIC MODULE: parameter study
===============================================================================
What a parameter study needs besides its flow (`parameter_study_flow`): the
scene as a scene file's content (`scene_file`), a parameter of it changed, the
scene built, traced and read at a detector, and that done for every point of a
sweep, in a job.

**A parameter** is named by its object and a path into the object's entry in
the scene file:
- for a designed element, an argument of its recipe (``"cavity_depth"``), or a
  part of one (``"p1.x"`` for a point argument);
- for any other object, a number in its ``serialize()`` (``"refIndex"``,
  ``"p1.y"``, ``"path.2.x"``: a glass's third vertex);
- for any object in the scene, three more, applied after it is built:
  ``rotate_deg`` (about its default centre, counter-clockwise), ``move_x`` and
  ``move_y``. A designed element's parts are turned and moved with it, about
  the element's centre.

So a designed element is rebuilt from its requirement at every point (`KC2`),
and a primitive changed the way the file would be edited.

**A point** is a list of changes, ``{object, parameter, value}``. The scene is
the file's content with those changes, built (`scene_from_dict`), then traced
at the study's numerical settings, and read at the named detector: its power,
the share of the sources' emitted power, the power-weighted mean position along
it (from ``p1``), its hits, and, when asked, its profile in the detector's own
bins. A point that cannot be built or traced is recorded as failed, with its
reason, and the job goes on (`study_points_job`).
===============================================================================
"""

from __future__ import annotations

import copy
import itertools
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, TypedDict

#: The parameters every object in the scene has, applied after it is built.
TRANSFORMS: Tuple[str, ...] = ("rotate_deg", "move_x", "move_y")
#: What a detector is read for. Every point records all of them but the
#: profile; the one asked is the study's headline column.
MEASURES: Tuple[str, ...] = ("power", "share", "centroid", "profile")
#: How many points one study may have.
MAX_POINTS = 400
#: Source types, by the JavaScript simulator's names.
SOURCE_TYPES: Tuple[str, ...] = ("AngleSource", "PointSource", "Beam", "SingleRay", "RaySetSource")


class StudyError(ValueError):
    """A parameter, a sweep or a measure that cannot be used; the message says why."""


# ---------------------------------------------------------------------------
# The parameters of a scene file
# ---------------------------------------------------------------------------

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _leaves(node: Any, prefix: str = "") -> Iterator[Tuple[str, Any]]:
    """Every number under ``node``, by its dotted path; a ``{"$point": [x, y]}`` as ``.x``, ``.y``."""
    if isinstance(node, dict):
        if set(node) == {"$point"}:
            for axis, v in zip("xy", node["$point"]):
                yield f"{prefix}{axis}", v
            return
        if set(node) == {"$enum", "value"}:
            return
        for k, v in node.items():
            yield from _leaves(v, f"{prefix}{k}.")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, f"{prefix}{i}.")
    elif _is_number(node):
        yield prefix[:-1], node


def _target(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What a parameter path points into: a recipe's arguments, or a primitive's object."""
    if "recipe" in entry:
        return entry["args"]
    if "object" in entry:
        return entry["object"]
    return None


def _defaults(entry: Dict[str, Any]) -> Dict[str, Any]:
    """A primitive's values left out of its ``serialize()`` because they are its type's defaults."""
    from .scene_file import _PRIMITIVES, _resolve  # noqa: PLC0415

    if "object" not in entry or entry["object"].get("type") not in _PRIMITIVES:
        return {}
    cls = _resolve(_PRIMITIVES[entry["object"]["type"]])
    return {k: v for k, v in getattr(cls, "serializable_defaults", {}).items() if k not in entry["object"]}


def _readable(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What a parameter is read from: `_target`, a primitive's defaults filled in."""
    target = _target(entry)
    return None if target is None else {**target, **copy.deepcopy(_defaults(entry))}


def _writable(entry: Dict[str, Any], parameter: str) -> Dict[str, Any]:
    """`_target`, with the default the parameter's path starts in copied in, so it can be set."""
    target = _target(entry)
    top = parameter.split(".")[0]
    defaults = _defaults(entry)
    if top not in target and top in defaults:
        target[top] = copy.deepcopy(defaults[top])
    return target


def _entries(data: Dict[str, Any]) -> Dict[str, Tuple[int, Dict[str, Any]]]:
    return {e["name"]: (i, e) for i, e in enumerate(data.get("objects", [])) if e.get("name")}


def _type(entry: Dict[str, Any]) -> str:
    if "recipe" in entry:
        return entry["recipe"]
    if "object" in entry:
        return entry["object"].get("type", "?")
    return "part"


def parameter_table(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every object of a scene file that has parameters, with them and their values.

    Args:
        data: A scene file's content (`scene_file.scene_to_dict`, or the file's JSON).

    Returns:
        ``[{"object", "type", "recipe": bool, "parameters": [{"parameter", "value",
        "integer"}]}]``, in the file's order. A part of an element has none of its own:
        it is changed through its element. The transforms (`TRANSFORMS`) are listed
        for every object in the scene, at 0.
    """
    out = []
    for entry in data.get("objects", []):
        target = _readable(entry)
        if target is None or not entry.get("name"):
            continue
        params = [{"parameter": p, "value": v, "integer": _is_integer_argument(data, entry["name"], p)}
                  for p, v in _leaves(target)]
        if entry.get("in_scene", True):
            params += [{"parameter": t, "value": 0.0, "integer": False} for t in TRANSFORMS]
        out.append({"object": entry["name"], "type": _type(entry), "recipe": "recipe" in entry,
                    "parameters": params})
    return out


def _walk(node: Any, path: str) -> Tuple[Any, Any]:
    """The container holding the leaf at ``path``, and its key there."""
    keys = path.split(".")
    for i, key in enumerate(keys):
        last = i == len(keys) - 1
        if isinstance(node, dict) and set(node) == {"$point"} and key in ("x", "y") and last:
            return node["$point"], "xy".index(key)
        if isinstance(node, list):
            if not key.isdigit() or int(key) >= len(node):
                raise KeyError(path)
            key = int(key)
        elif not isinstance(node, dict) or key not in node:
            raise KeyError(path)
        if last:
            return node, key
        node = node[key]
    raise KeyError(path)


def current_value(data: Dict[str, Any], obj: str, parameter: str) -> Any:
    """A parameter's value in the scene file (0 for a transform).

    Raises:
        StudyError: No object of that name, or no such parameter of it; the message
            lists what there is.
    """
    entries = _entries(data)
    if obj not in entries:
        raise StudyError(f"no object named {obj!r} in the scene; its objects: {sorted(entries)}")
    _, entry = entries[obj]
    target = _readable(entry)
    if target is None:
        owner = data["objects"][entry["part_of"]].get("name")
        raise StudyError(f"{obj!r} is a part of {owner!r}: change it through {owner!r}'s parameters")
    if parameter in TRANSFORMS:
        if not entry.get("in_scene", True):
            raise StudyError(f"{obj!r} is not in the scene (only its parts are): turn or move its parts")
        return 0.0
    try:
        container, key = _walk(target, parameter)
    except KeyError:
        known = [p for p, _ in _leaves(target)] + list(TRANSFORMS)
        raise StudyError(f"{obj!r} has no parameter {parameter!r}; its parameters: {known}") from None
    value = container[key]
    if not _is_number(value):
        raise StudyError(f"{obj!r}.{parameter} is {value!r}, not a number: only numbers are swept")
    return value


# ---------------------------------------------------------------------------
# A sweep: its axes and its points
# ---------------------------------------------------------------------------

def sweep_axes(data: Dict[str, Any], spec: Any) -> List[Dict[str, Any]]:
    """A sweep's axes, checked against the scene file.

    Args:
        data: The scene file's content.
        spec: One axis or a list of one or two: ``{"object", "parameter", "values": [...]}``
            or ``{"object", "parameter", "from", "to", "steps"}``. Two axes are a grid.

    Returns:
        ``[{"object", "parameter", "values", "current", "integer"}]``.

    Raises:
        StudyError: A shape, object, parameter or value that cannot be used.
    """
    axes = [spec] if isinstance(spec, dict) else spec
    if not isinstance(axes, list) or not 1 <= len(axes) <= 2:
        raise StudyError("parameters takes one axis, or a list of one or two (two are a grid)")
    out, seen = [], set()
    for i, ax in enumerate(axes):
        where = f"axis {i + 1}"
        if not isinstance(ax, dict) or not isinstance(ax.get("object"), str) \
                or not isinstance(ax.get("parameter"), str):
            raise StudyError(f"{where}: an axis is an object with 'object' and 'parameter' (names)")
        keys = set(ax) - {"object", "parameter"}
        if keys == {"values"}:
            values = ax["values"]
            if not isinstance(values, list) or not values or not all(_is_number(v) for v in values):
                raise StudyError(f"{where}: values is a non-empty list of numbers")
            values = list(values)
        elif keys == {"from", "to", "steps"}:
            a, b, n = ax["from"], ax["to"], ax["steps"]
            if not (_is_number(a) and _is_number(b)):
                raise StudyError(f"{where}: from and to are numbers")
            if isinstance(n, bool) or not isinstance(n, int) or n < 2:
                raise StudyError(f"{where}: steps is a whole number, at least 2 (the ends included)")
            values = [a + (b - a) * k / (n - 1) for k in range(n)]
        else:
            raise StudyError(f"{where}: give 'values', or 'from', 'to' and 'steps'; got {sorted(keys)}")
        key = (ax["object"], ax["parameter"])
        if key in seen:
            raise StudyError(f"{where}: {ax['object']}.{ax['parameter']} is already an axis")
        seen.add(key)
        current = current_value(data, *key)
        integer = _is_integer_argument(data, *key)
        if integer:
            if not all(float(v).is_integer() for v in values):
                raise StudyError(f"{where}: {ax['object']}.{ax['parameter']} is a whole number; "
                                 f"its values must be too, got {values}")
            values = [int(v) for v in values]
        out.append({"object": ax["object"], "parameter": ax["parameter"], "values": values,
                    "current": current, "integer": integer})
    count = math.prod(len(a["values"]) for a in out)
    if count > MAX_POINTS:
        raise StudyError(f"{count} points; a study has at most {MAX_POINTS}")
    return out


def _is_integer_argument(data: Dict[str, Any], obj: str, parameter: str) -> bool:
    """Whether a parameter is a designed element's argument annotated ``int`` (a count of zones,
    of points). A primitive's numbers are all real, as in the JavaScript simulator."""
    from .scene_file import recipe_parameters  # noqa: PLC0415

    entry = _entries(data)[obj][1]
    if "recipe" not in entry or "." in parameter:
        return False
    return any(p["name"] == parameter and p["annotation"] == "int" for p in recipe_parameters(entry["recipe"]))


def sweep_points(axes: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Every point of the sweep, the last axis fastest: each a list of ``{object, parameter, value}``."""
    return [[{"object": a["object"], "parameter": a["parameter"], "value": v} for a, v in zip(axes, combo)]
            for combo in itertools.product(*(a["values"] for a in axes))]


def corner_points(axes: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """The sweep's ends: both ends of one axis, the four corners of a grid."""
    ends = [sorted({a["values"][0], a["values"][-1]}, key=a["values"].index) for a in axes]
    return [[{"object": a["object"], "parameter": a["parameter"], "value": v} for a, v in zip(axes, combo)]
            for combo in itertools.product(*ends)]


def point_label(changes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """A point as ``{"object.parameter": value}``."""
    return {f"{c['object']}.{c['parameter']}": c["value"] for c in changes}


# ---------------------------------------------------------------------------
# A point: built, traced, read
# ---------------------------------------------------------------------------

def build_point(data: Dict[str, Any], changes: Sequence[Dict[str, Any]]) -> Any:
    """The scene at one point: the file's content with ``changes``, built.

    Raises:
        StudyError: A change that names nothing in the file.
        scene_file.SceneFileError: The changed scene cannot be built.
    """
    from .scene_file import scene_from_dict  # noqa: PLC0415

    data = copy.deepcopy(data)
    entries = _entries(data)
    transforms: List[Dict[str, Any]] = []
    for c in changes:
        current_value(data, c["object"], c["parameter"])          # names something, or StudyError
        if c["parameter"] in TRANSFORMS:
            transforms.append(c)
            continue
        container, key = _walk(_writable(entries[c["object"]][1], c["parameter"]), c["parameter"])
        container[key] = c["value"]
    scene = scene_from_dict(data)
    for c in transforms:
        _transform(scene, data, c)
    return scene


def _transform(scene: Any, data: Dict[str, Any], change: Dict[str, Any]) -> None:
    index, _ = _entries(data)[change["object"]]
    by_name = {getattr(o, "name", None): o for o in scene.objs}
    owner = by_name[change["object"]]
    parts = [by_name[e["name"]] for e in data["objects"]
             if e.get("part_of") == index and e.get("name") in by_name]
    v = float(change["value"])
    if v == 0.0:
        return
    if change["parameter"] == "rotate_deg":
        center = owner.get_default_center()
        for obj in [owner, *parts]:
            if obj.rotate(math.radians(v), center) is False:
                raise StudyError(f"{getattr(obj, 'name', obj)!r} cannot be rotated")
    else:
        dx, dy = (v, 0.0) if change["parameter"] == "move_x" else (0.0, v)
        for obj in [owner, *parts]:
            if obj.move(dx, dy) is False:
                raise StudyError(f"{getattr(obj, 'name', obj)!r} cannot be moved")


def sources_and_detectors(scene: Any) -> Tuple[List[str], List[str]]:
    """The names of a scene's sources and of its detectors."""
    sources = [o.name for o in scene.objs if getattr(type(o), "type", "") in SOURCE_TYPES]
    detectors = [o.name for o in scene.objs if hasattr(o, "get_hit_records")]
    return sources, detectors


class DetectorReading(TypedDict, total=False):
    """What `read_detector` gives (the block type ``detector_reading``): ``power`` and ``hits``
    always; ``profile`` only when asked for."""

    power: float
    emitted: float
    share: Optional[float]
    centroid: Optional[float]
    hits: int
    profile: Dict[str, Any]


def read_detector(scene: Any, result: Any, detector: str, *, profile: bool = False) -> DetectorReading:
    """What one detector measured in a traced scene.

    Returns:
        ``power`` (the detector's own: a `Detector`'s is signed by the crossing's direction,
        a `Photodetector`'s is the absorbed power, C-DET-01), ``emitted`` (the sources' rays' brightness at their
        start), ``share`` (power over emitted), ``centroid`` (the power-weighted mean distance
        from the detector's ``p1``, None without hits), ``hits``, and with ``profile`` the power
        in each of the detector's bins (``bin_size`` along it, from ``p1``).
    """
    det = next((o for o in scene.objs if getattr(o, "name", None) == detector), None)
    if det is None or not hasattr(det, "get_hit_records"):
        raise StudyError(f"no detector named {detector!r} in the scene")
    records = det.get_hit_records()
    emitted = sum(s.brightness_s + s.brightness_p for s in result.segments
                  if getattr(s, "parent_uuid", None) is None)
    weights = [r["sign"] * r["brightness_total"] for r in records]
    total = sum(weights)
    centroid = (sum(w * r["position"] for w, r in zip(weights, records)) / total) if total else None
    out: DetectorReading = {"power": det.power, "emitted": emitted, "share": det.power / emitted if emitted else None,
                           "centroid": centroid, "hits": len(records)}
    if profile:
        bins = det.bin_count if det.bin_size > 0 else 0
        values = [0.0] * bins
        for w, r in zip(weights, records):
            if r["bin_index"] is not None and 0 <= r["bin_index"] < bins:
                values[r["bin_index"]] += w
        out["profile"] = {"bin_size": det.bin_size, "power": values}
    return out


def trace_point(data: Dict[str, Any], changes: Sequence[Dict[str, Any]], *, detector: str,
                ray_density: float, min_brightness_exp: Optional[int], max_rays: int,
                profile: bool = False) -> Tuple[Any, Any, Dict[str, Any]]:
    """One point built, traced and read: ``(scene, result, reading)``; the reading has
    ``segments``, ``truncated`` (the segment limit was reached) and ``sim_s`` besides
    `read_detector`'s."""
    from ..core.simulator import Simulator  # noqa: PLC0415

    scene = build_point(data, changes)
    scene.ray_density = ray_density
    if min_brightness_exp is not None:
        scene.min_brightness_exp = min_brightness_exp
    t0 = time.perf_counter()
    sim = Simulator(scene, max_rays=max_rays)
    result = sim.run_with_result()
    sim_s = time.perf_counter() - t0
    reading: Dict[str, Any] = dict(read_detector(scene, result, detector, profile=profile))
    reading.update(segments=result.segment_count, truncated=sim.processed_ray_count >= max_rays,
                   sim_s=sim_s)
    return scene, result, reading


def study_points_job(inputs: Dict[str, Any], ctx: Any) -> Dict[str, Any]:
    """Some points of a study, traced one after another: a job's procedure.

    Args:
        inputs: ``scene`` (the scene file's content), ``points`` (``[{"index", "changes"}]``),
            ``detector``, ``measure``, ``ray_density``, ``min_brightness_exp``, ``max_rays``;
            ``runs_dir`` and ``study_id`` to save each point as a run bundle
            (`persist_run_artifacts`), or None.
        ctx: The job's context, for progress.

    Returns:
        ``{"points": [...]}``: each point's ``index``, ``ok``, and its reading, or its
        ``error``. A point that fails does not stop the others.
    """
    from .run_registry import persist_run_artifacts  # noqa: PLC0415

    points = inputs["points"]
    out = []
    for k, point in enumerate(points):
        ctx.progress(k, len(points), note="points done")
        row: Dict[str, Any] = {"index": point["index"]}
        try:
            scene, result, reading = trace_point(
                inputs["scene"], point["changes"], detector=inputs["detector"],
                ray_density=inputs["ray_density"], min_brightness_exp=inputs["min_brightness_exp"],
                max_rays=inputs["max_rays"], profile=inputs["measure"] == "profile")
            row.update(ok=True, **reading)
            if inputs.get("runs_dir"):
                numerical = {k2: inputs[k2] for k2 in ("ray_density", "min_brightness_exp", "max_rays")}
                run = persist_run_artifacts(scene, result, out_dir=Path(inputs["runs_dir"]),
                                            design_id=inputs["study_id"], run_id=f"point_{point['index']:03d}",
                                            physical_params=point_label(point["changes"]),
                                            numerical_params=numerical)
                row["run_dir"] = str(run)
        except Exception as exc:  # noqa: BLE001 -- a point that fails is recorded; the study goes on
            row.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        out.append(row)
    ctx.progress(len(points), len(points), note="points done")
    return {"points": out}


# ---------------------------------------------------------------------------
# The result as a table, arrays and a plot
# ---------------------------------------------------------------------------

#: A point's readings, as the table's and the arrays' columns, in order (``profile`` when read).
READINGS: Tuple[str, ...] = ("power", "share", "centroid", "hits", "segments", "sim_s")


def study_result(source: Any) -> Dict[str, Any]:
    """A study's result, from what is at hand.

    Args:
        source: A `ParameterStudyFlow` (finished), its ``result`` dict, or a run's folder
            (``<base_dir>/<run_id>``, read from its ``result.json``: a study run earlier, or in
            another process).

    Raises:
        StudyError: The flow has not finished, or the folder holds no finished study.
    """
    if isinstance(source, dict):
        return source
    if isinstance(source, (str, Path)):
        import json  # noqa: PLC0415

        path = Path(source) / "result.json"
        if not path.is_file():
            raise StudyError(f"no result.json in {source}: not a finished run's folder")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved.get("result"), dict) or "rows" not in saved["result"]:
            raise StudyError(f"{source} did not end with a study's result (status: {saved.get('status', '?')})")
        return saved["result"]
    result = getattr(source, "result", None)
    if not result:
        raise StudyError(f"the study has no result yet: it is in {getattr(source, 'state', '?')!r}")
    return result


def _axis_keys(result: Dict[str, Any]) -> List[str]:
    return [f"{a['object']}.{a['parameter']}" for a in result["axes"]]


def study_rows(source: Any) -> List[Dict[str, Any]]:
    """The study as flat rows, one a point: its index, each axis's value, the readings, ``ok``
    and the ``error`` of a point that failed."""
    result = study_result(source)
    keys = _axis_keys(result)
    out = []
    for r in result["rows"]:
        row = {"index": r["index"], **{k: r["point"][k] for k in keys}}
        row.update({k: r.get(k) for k in READINGS})
        row["ok"] = bool(r.get("ok"))
        if not row["ok"]:
            row["error"] = r.get("error")
        out.append(row)
    return out


def study_arrays(source: Any, *, grid: bool = True) -> Dict[str, Any]:
    """The study as numpy arrays, one a column, ready to plot.

    Args:
        source: As `study_result`.
        grid: With two axes, shape each reading as the grid, ``(n1, n2)``, the axes' own
            values as 1-D arrays (``plt.pcolormesh(a[x2], a[x1], a["power"])``). False, or one
            axis: every array 1-D, one entry a point, the axis values repeated per point.

    Returns:
        ``{axis key: values, reading: values, "ok": bools}``, and ``"profile"`` (one row of
        bins a point) when the profile was read. A failed point's readings are NaN.
    """
    import numpy as np  # noqa: PLC0415

    result = study_result(source)
    keys = _axis_keys(result)
    rows = sorted(result["rows"], key=lambda r: r["index"])
    out: Dict[str, Any] = {}
    shape = tuple(len(a["values"]) for a in result["axes"])
    as_grid = grid and len(shape) == 2
    if as_grid:
        for k, a in zip(keys, result["axes"]):
            out[k] = np.asarray(a["values"], dtype=float)
    else:
        for k in keys:
            out[k] = np.asarray([r["point"][k] for r in rows], dtype=float)
    for k in READINGS:
        col = np.asarray([r.get(k) if r.get("ok") and r.get(k) is not None else np.nan for r in rows], dtype=float)
        out[k] = col.reshape(shape) if as_grid else col
    ok = np.asarray([bool(r.get("ok")) for r in rows])
    out["ok"] = ok.reshape(shape) if as_grid else ok
    profiles = [r.get("profile") for r in rows]
    if any(p for p in profiles):
        bins = max(len(p["power"]) for p in profiles if p)
        table = np.full((len(rows), bins), np.nan)
        for i, p in enumerate(profiles):
            if p:
                table[i, :len(p["power"])] = p["power"]
        out["profile"] = table.reshape(shape + (bins,)) if as_grid else table
        out["profile_bin_size"] = np.asarray(next(p["bin_size"] for p in profiles if p))
    return out


def study_table_markdown(source: Any, *, digits: int = 6) -> str:
    """The study as a markdown table, one row a point (``IPython.display.Markdown`` shows it)."""
    rows = study_rows(source)
    keys = list(rows[0]) if rows else []
    if any("error" in r for r in rows) and "error" not in keys:
        keys.append("error")

    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.{digits}g}"
        return "" if v is None else str(v).replace("|", "\\|")

    lines = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    lines += ["| " + " | ".join(fmt(r.get(k)) for k in keys) + " |" for r in rows]
    return "\n".join(lines)

def plot_svg(rows: Sequence[Dict[str, Any]], axes: Sequence[Dict[str, Any]], measure: str,
             path: Path, *, width: int = 640, height: int = 400) -> Optional[Path]:
    """The measure against the first axis, one line per value of the second: an SVG.

    Returns:
        The path written, or None when there is nothing to plot (a profile, or no
        point measured).
    """
    import svgwrite  # noqa: PLC0415

    if measure == "profile":
        return None
    x_key = f"{axes[0]['object']}.{axes[0]['parameter']}"
    second = f"{axes[1]['object']}.{axes[1]['parameter']}" if len(axes) > 1 else None
    pts = [(r["point"][x_key], r[measure], r["point"].get(second)) for r in rows
           if r.get("ok") and r.get(measure) is not None]
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 == x0:
        x0, x1 = x0 - 1, x1 + 1
    if y1 == y0:
        pad = abs(y0) * 0.05 or 1.0
        y0, y1 = y0 - pad, y1 + pad
    left, right, top, bottom = 80, 20, 20, 50
    pw, ph = width - left - right, height - top - bottom

    def sx(x: float) -> float:
        return left + (x - x0) / (x1 - x0) * pw

    def sy(y: float) -> float:
        return top + (1 - (y - y0) / (y1 - y0)) * ph

    dwg = svgwrite.Drawing(str(path), size=(f"{width}px", f"{height}px"))
    dwg.add(dwg.rect((0, 0), (width, height), fill="white"))
    dwg.add(dwg.rect((left, top), (pw, ph), fill="none", stroke="#888"))
    for k in range(5):
        fx, fy = x0 + (x1 - x0) * k / 4, y0 + (y1 - y0) * k / 4
        dwg.add(dwg.text(f"{fx:.4g}", insert=(sx(fx), height - bottom + 18), font_size=11,
                         text_anchor="middle", font_family="sans-serif"))
        dwg.add(dwg.text(f"{fy:.4g}", insert=(left - 6, sy(fy) + 4), font_size=11, text_anchor="end",
                         font_family="sans-serif"))
    dwg.add(dwg.text(x_key, insert=(left + pw / 2, height - 10), font_size=12, text_anchor="middle",
                     font_family="sans-serif"))
    dwg.add(dwg.text(measure, insert=(14, top + ph / 2), font_size=12, text_anchor="middle",
                     font_family="sans-serif", transform=f"rotate(-90 14 {top + ph / 2})"))
    colors = ["#1f6fb4", "#d1661c", "#2a9d4a", "#b33a3a", "#7b57b0", "#8a6a3a"]
    groups: Dict[Any, List[Tuple[float, float]]] = {}
    for x, y, g in pts:
        groups.setdefault(g, []).append((x, y))
    for i, (g, line) in enumerate(groups.items()):
        line.sort()
        color = colors[i % len(colors)]
        dwg.add(dwg.polyline([(sx(x), sy(y)) for x, y in line], fill="none", stroke=color, stroke_width=1.5))
        for x, y in line:
            dwg.add(dwg.circle((sx(x), sy(y)), 3, fill=color))
        if second is not None:
            dwg.add(dwg.text(f"{second} = {g:.4g}", insert=(left + 8, top + 16 + 14 * i), font_size=11,
                             fill=color, font_family="sans-serif"))
    dwg.save()
    return Path(path)


__all__ = ["DetectorReading", "MAX_POINTS", "MEASURES", "READINGS", "SOURCE_TYPES", "StudyError", "TRANSFORMS", "build_point",
           "study_arrays", "study_result", "study_rows", "study_table_markdown",
           "corner_points", "current_value", "parameter_table", "plot_svg", "point_label", "read_detector",
           "sources_and_detectors", "study_points_job", "sweep_axes", "sweep_points", "trace_point"]
