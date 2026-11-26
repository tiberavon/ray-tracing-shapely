"""
Python-specific module: agentic (sculpt) -- an agent sculpts a designed glass through the builder's own rules
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
PYTHON-SPECIFIC MODULE: agentic (sculpt)
===============================================================================
Eight tools with which an agent sculpts a designed glass, by the same
messages the scene builder's page sends (`SceneEditor`'s ``sculpt_*``), so a
person and an agent follow one set of rules:

    sculpt_start(glass, receiver, tubes, bundles)   begin: the glass made sculptable, its light cut
    list_flux_tubes()                               the tubes: shares, Map B, main route
    describe_flux_tube(tube_id)                     a tube's routes, its crossings, the handles near them
    list_sculpt_handles(edge, tube_id, max_items)   the handles: where, which way, their limits, who crosses
    preview_handle_move(handle_id, delta, kind)     the first-order change of the maps; nothing traced
    apply_handle_move(handle_id, delta, kind)       the edit recorded, the light traced again, events
    undo_handle_move()                              the last edit undone
    sculpt_report(svg_path)                         the edits, the maps and routes against the start, a drawing

The scene they work on is attached by the notebook, explicitly (`KA5`):
``attach(scene)``, ``attach(editor)``, or ``attach(builder)`` with a scene
builder widget, whose page then shows each step as the agent takes it, on the
same kernel (`KD7`). They are added to the core's tool lists by `register()`,
called explicitly, never at import (`KA7`). Every tool answers ``{"status":
"ok", "data": ...}`` or ``{"status": "error", "message": ...}`` and never
raises (`KA3`, `KA4`); a tool that takes a name says where the names are
listed (`KA2`), and every argument is checked here (`KA9`). Lists are capped
and say so (`KA8`); the drawing is written to a file and described, not
returned.

A natural loop: preview several handles, apply the one whose predicted
spread is lowest within its limit, read the events, repeat. That is
coordinate descent on the first-order gradient.
===============================================================================
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from .editor import SceneEditor

#: The most handles `list_sculpt_handles` returns by default (KA8).
MAX_HANDLES = 40
#: Where `sculpt_report` writes its drawing when not told: a run folder, not the working folder itself.
DEFAULT_REPORT = "_sculpt_runs/sculpt_report.svg"
#: The most handles `describe_flux_tube` names near one crossing.
NEAR = 3

_STATE: Dict[str, Any] = {"editor": None, "widget": None, "baseline": None}


def _ok(data: Any) -> Dict[str, Any]:
    return {"status": "ok", "data": data}


def _error(message: str) -> Dict[str, str]:
    return {"status": "error", "message": message}


def attach(target: Any) -> SceneEditor:
    """The scene the sculpt tools work on: a `Scene`, a `SceneEditor`, or a scene builder widget.

    A scene is wrapped in an editor of its own (its rays not traced: the tools trace the tubes
    and bundles); the editor's scene is then the one edited (``attach(scene).scene``). A widget's
    page is refreshed after every tool that changes something, so a person watches the agent work.
    """
    widget = target if hasattr(target, "editor") and hasattr(target, "refresh") else None
    if widget is not None:
        editor = widget.editor
    elif isinstance(target, SceneEditor):
        editor = target
    else:
        editor = SceneEditor(target, quick_max_rays=0)
    _STATE.update(editor=editor, widget=widget, baseline=None)
    return editor


def detach() -> None:
    """Forget the attached scene."""
    _STATE.update(editor=None, widget=None, baseline=None)


def _editor() -> SceneEditor:
    if _STATE["editor"] is None:
        raise LookupError("no scene attached: the notebook calls "
                          "ray_tracing_shapely.builder.agentic.attach(scene or builder) first")
    return _STATE["editor"]


def _session() -> Any:
    e = _editor()
    if e.sculpt is None:
        raise LookupError("not sculpting: call sculpt_start(glass) first")
    return e.sculpt


def _send(message: Dict[str, Any]) -> Dict[str, Any]:
    e = _editor()
    state = e.handle(message, draw=False)                 # the numbers; a widget draws its own
    if _STATE["widget"] is not None:
        _STATE["widget"].refresh()
    return state


def _number(value: Any, name: str) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, got {value!r}") from None
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite, got {x}")
    return x


def _kind(kind: Any) -> str:
    if kind not in ("position", "normal"):
        raise ValueError(f"kind is 'position' (the point moved along the glass's outward normal, scene units) "
                         f"or 'normal' (its tangent turned counter-clockwise, degrees), got {kind!r}")
    return kind


def _map_a(state: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    bundles = state["sculpt"]["bundles"]
    if bundles is None:
        return None
    return [{"bundle_id": b["bundle_id"], "spread": b["spread"], "rms": b["rms"], "max_miss": b["max_miss"],
             "rays_counted": b["counted"], "rays_off_route": len(b["off_route"])} for b in bundles]


def _map_b(state: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    tubes = state["sculpt"]["tubes"]
    if tubes is None:
        return None
    return [{"tube_id": t["tube_id"], "delivered_fraction": round(t["delivered_fraction"], 6)} for t in tubes]


def _route_text(route: Any) -> str:
    from ..analysis.flux_tubes import route_text  # noqa: PLC0415
    return route_text(route)


def _limits(session: Any, scene: Any) -> List[Dict[str, Any]]:
    out, seen = [], set()
    for h in session.handles_state(scene):
        if h["edge"] in seen:
            continue
        seen.add(h["edge"])
        measured = session.limits.get(h["edge"], {})
        out.append({"edge": h["label"] or h["edge"], "limit": h["limit"], "measured": bool(measured.get("measured")),
                    "error_per_unit_ratio": measured.get("per_ratio")})
    return out


# --- the tools ----------------------------------------------------------------------------


def sculpt_start(glass: str, receiver: Optional[str] = None, tubes: int = 8, bundles: bool = True) -> Dict[str, Any]:
    """Begin sculpting ``glass``: it becomes a sculpted glass (its recipe kept, no edits), its source's
    light is cut into tubes at ``receiver``, and an RR lens's edge bundles are aimed."""
    try:
        e = _editor()
        if not isinstance(glass, str) or not glass:
            raise ValueError("glass is the name of a designed glass in the scene")
        tubes = int(tubes)
        if not 2 <= tubes <= 20:
            raise ValueError(f"tubes is 2 to 20, got {tubes}")
        names = [o.name for o in e.scene.objs]
        if glass not in names:
            from .sculpt import SculptError, sculptable  # noqa: PLC0415
            ok = []
            for n in names:
                try:
                    sculptable(e.scene, n)
                    ok.append(n)
                except SculptError:
                    pass
            raise LookupError(f"no object named {glass!r}; designed glasses that can be sculpted: "
                              f"{', '.join(ok) or 'none'}")
        state = _send({"type": "sculpt_start", "glass": glass, "receiver": receiver, "tubes": tubes,
                       "bundles": bool(bundles)})
        if state["error"]:
            return _error(state["error"])
        sc = state["sculpt"]
        _STATE["baseline"] = {"map_a": _map_a(state), "map_b": _map_b(state),
                              "routes": _tube_routes(e.sculpt),
                              "edits": len(e._obj(glass)._construction_args["edits"])}
        return _ok({"glass": sc["glass"], "receiver": sc["receiver"],
                    "tubes": None if sc["tubes"] is None else len(sc["tubes"]),
                    "map_a": _map_a(state), "map_b": _map_b(state),
                    "handles": len(sc["handles"]), "edges": _limits(e.sculpt, e.scene),
                    "note": "Map A is the spread of each edge bundle's optical path length to its target (0 is "
                            "perfect); Map B the share of each tube's light that reaches the receiver."})
    except Exception as exc:  # noqa: BLE001 -- errors are values (KA4)
        return _error(f"{type(exc).__name__}: {exc}")


def _tube_routes(session: Any) -> Dict[str, List[List[Any]]]:
    if session.tubes is None:
        return {}
    return {t.tube_id: [[_route_text(r), round(w, 4)] for r, w in t.routes] for t in session.tubes.tubes}


def list_flux_tubes() -> Dict[str, Any]:
    """The tubes: each one's share of the source's power, the share of it delivered (Map B), and its
    main route with that route's share of the tube's light."""
    try:
        s = _session()
        if s.tubes is None:
            return _error("the sculpting has no tubes (no receiver was found); its map is Map A only")
        out = []
        for t in s.tubes.tubes:
            main = t.routes[0] if t.routes else None
            out.append({"tube_id": t.tube_id, "power_fraction": round(t.power_fraction, 6),
                        "delivered_fraction": round(t.delivered_fraction, 6),
                        "main_route": None if main is None else _route_text(main[0]),
                        "main_route_share": None if main is None else round(main[1], 4),
                        "other_routes": max(0, len(t.routes) - 1)})
        return _ok({"tubes": out, "outside_fraction": {k: round(v, 6) for k, v in s.tubes.outside_fraction.items()},
                    "note": "étendue dilution (Map C) is not computed"})
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


def _crossings(s: Any, scene: Any, tube: Any) -> List[Dict[str, Any]]:
    """For the tube's main route, each hit on a spline edge of the sculpted glass, with the handles
    nearest where the tube's rays cross it."""
    from ..analysis import first_order as fo  # noqa: PLC0415
    if not tube.routes:
        return []
    main = tube.routes[0][0]
    glass = fo._glass(scene, s.glass)
    params: Dict[int, List[float]] = {}
    for a in tube.arrivals:
        if a.route != main:
            continue
        for h in a.hits:
            if h.surface != s.glass or h.edge is None:
                continue
            try:
                span = fo._span(glass, h.edge)
            except fo.FirstOrderError:
                continue
            params.setdefault(h.edge, []).append(span.shape.nearest(h.point)[1])
    labels = {x["edge"]: x["label"] for x in s.handles_state(scene)}
    out = []
    for step, (surface, edge, event) in enumerate(main):
        entry = {"step": step, "surface": surface, "edge": labels.get(edge, edge), "event": event}
        if surface == s.glass and edge in params:
            lo, hi = min(params[edge]), max(params[edge])
            n = len(fo._span(glass, edge).shape.points)
            centre = (lo + hi) / 2
            near = sorted(range(1, n - 1), key=lambda i: abs(i - centre))[:max(NEAR, math.ceil(hi) - math.floor(lo) + 1)]
            entry["crossed_between_points"] = [round(lo, 3), round(hi, 3)]
            entry["handles"] = [f"{s.glass}/{labels.get(edge, edge)}/{i}" for i in sorted(near)]
        out.append(entry)
    return out


def describe_flux_tube(tube_id: str) -> Dict[str, Any]:
    """One tube: its routes with their shares, and the crossings of its main route in order, each
    with the handles nearest where the tube's rays cross (the ones that move its light)."""
    try:
        s = _session()
        if s.tubes is None:
            return _error("the sculpting has no tubes")
        ids = [t.tube_id for t in s.tubes.tubes]
        if tube_id not in ids:
            return _error(f"no tube {tube_id!r}; tubes: {', '.join(ids)} (list_flux_tubes)")
        t = s.tubes.tube(tube_id)
        return _ok({"tube_id": tube_id, "power_fraction": round(t.power_fraction, 6),
                    "delivered_fraction": round(t.delivered_fraction, 6),
                    "routes": [{"route": _route_text(r), "share": round(w, 4)} for r, w in t.routes[:8]],
                    "routes_not_shown": max(0, len(t.routes) - 8),
                    "rays": len(t.seeds), "arrivals": len(t.arrivals),
                    "crossings": _crossings(s, _editor().scene, t)})
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


def list_sculpt_handles(edge: Optional[str] = None, tube_id: Optional[str] = None,
                        max_items: int = MAX_HANDLES) -> Dict[str, Any]:
    """The handles: each one's id, edge, point, outward normal, the shorter adjacent chord, its preview
    limit as a move (scene units for a point, degrees for a tangent), and the tubes and bundle rays
    that cross its two spans. Filter by edge label or by a tube; at most ``max_items``."""
    try:
        s, e = _session(), _editor()
        from ..analysis import first_order as fo  # noqa: PLC0415
        max_items = int(max_items)
        if max_items < 1:
            raise ValueError(f"max_items is at least 1, got {max_items}")
        handles = s.handles_state(e.scene)
        labels = sorted({str(h["label"] or h["edge"]) for h in handles})
        if edge is not None and str(edge) not in labels:
            return _error(f"no edge {edge!r} with handles; edges: {', '.join(labels)}")
        glass = fo._glass(e.scene, s.glass)
        crossed: Dict[tuple, Counter] = {}
        if s.tubes is not None:
            if tube_id is not None and tube_id not in [t.tube_id for t in s.tubes.tubes]:
                return _error(f"no tube {tube_id!r} (list_flux_tubes)")
            for t in s.tubes.tubes:
                for a in t.arrivals:
                    for h in a.hits:
                        if h.surface == s.glass and h.edge is not None:
                            try:
                                p = fo._span(glass, h.edge).shape.nearest(h.point)[1]
                            except fo.FirstOrderError:
                                continue
                            crossed.setdefault((h.edge, int(p)), Counter())[t.tube_id] += 1
        elif tube_id is not None:
            return _error("the sculpting has no tubes")
        bundle_hits: Counter = Counter()
        if s.bundles is not None:
            for b in s.bundles.bundles:
                for r in b.counted:
                    for h in r.hits:
                        bundle_hits[(h.edge, int(fo._span(glass, h.edge).shape.nearest(h.point)[1]))] += 1
        out = []
        for h in handles:
            if edge is not None and str(h["label"] or h["edge"]) != str(edge):
                continue
            spans = [(h["edge"], h["index"] - 1), (h["edge"], h["index"])]
            tubes = Counter()
            for sp in spans:
                tubes.update(crossed.get(sp, Counter()))
            if tube_id is not None and tube_id not in tubes:
                continue
            out.append({"handle_id": h["handle_id"], "edge": h["label"] or h["edge"], "index": h["index"],
                        "point": [round(h["x"], 6), round(h["y"], 6)],
                        "outward_normal": [round(v, 6) for v in h["normal"]], "chord": round(h["chord"], 6),
                        "limit_position": round(h["limit"] * h["chord"], 8),
                        "limit_normal_deg": round(math.degrees(h["limit"]), 6),
                        "tubes": sorted(tubes), "bundle_rays": sum(bundle_hits.get(sp, 0) for sp in spans)})
        return _ok({"handles": out[:max_items], "shown": min(len(out), max_items), "total": len(out),
                    "truncated": len(out) > max_items,
                    "note": "a 'position' move of delta pushes the point delta along its outward normal; a "
                            "'normal' move turns its tangent delta degrees counter-clockwise; past the limit "
                            "the first-order preview is not trusted (apply re-traces). The limit is how far the "
                            "preview can be trusted, not a step size."})
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


def _check_handle(handle_id: Any) -> str:
    s, e = _session(), _editor()
    ids = [h["handle_id"] for h in s.handles_state(e.scene)]
    if handle_id not in ids:
        raise LookupError(f"no handle {handle_id!r}; handles are '{s.glass}/<edge>/<index>', e.g. "
                          f"{', '.join(ids[:3])} (list_sculpt_handles)")
    return handle_id


def preview_handle_move(handle_id: str, delta: float, kind: str = "position") -> Dict[str, Any]:
    """The first-order change of a move, nothing traced: per bundle the mean change of S and the spread
    it would give, per tube the mean change of its arrivals' S, and whether the move is within the
    edge's preview limit (past it, apply to know)."""
    try:
        state = _send({"type": "sculpt_preview", "handle_id": _check_handle(handle_id),
                       "kind": _kind(kind), "delta": _number(delta, "delta")})
        if state["error"]:
            return _error(state["error"])
        p, full = state["sculpt"]["preview"], _session().preview
        out = {"handle_id": handle_id, "kind": kind, "delta": p["delta"], "drag_ratio": p["ratio"],
               "limit": p["limit"], "trusted": p["trusted"]}
        if "bundles" in p:
            out["bundles"] = []
            for bid, v in p["bundles"].items():
                ch = list(full["bundle_changes"][bid].values())
                out["bundles"].append({"bundle_id": bid, "spread_before": v["spread_before"],
                                       "spread_after": v["spread_after"], "rms_before": v["rms_before"],
                                       "rms_after": v["rms_after"],
                                       "mean_change": sum(ch) / len(ch) if ch else 0.0})
        if "tubes" in p:
            out["tubes"] = [{"tube_id": tid, "mean_change": v["mean_dopl"], "arrivals_moved": v["arrivals_moved"]}
                            for tid, v in p["tubes"].items() if v["arrivals_moved"]]
        return _ok(out)
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


def apply_handle_move(handle_id: str, delta: float, kind: str = "position") -> Dict[str, Any]:
    """Make the move: the edit recorded in the glass's edit list, the tubes and bundles traced again.
    Returns the maps after it, the events (a tube split, total internal reflection switched, light
    leaving the receiver, rays leaving a bundle's route), and the edge's preview limit, measured from
    this move. An edit that breaks the outline is refused, the scene unchanged."""
    try:
        state = _send({"type": "sculpt_apply", "handle_id": _check_handle(handle_id),
                       "kind": _kind(kind), "delta": _number(delta, "delta")})
        sc = state["sculpt"]
        if state["error"]:
            return {"status": "error", "message": state["error"], "events": sc["events"] if sc else []}
        s = _session()
        return _ok({"edits": len(_editor()._obj(s.glass)._construction_args["edits"]),
                    "map_a": _map_a(state), "map_b": _map_b(state), "events": sc["events"],
                    "edges": _limits(s, _editor().scene), "trace_seconds": round(sc["trace_seconds"], 3)})
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


def undo_handle_move() -> Dict[str, Any]:
    """Undo the last change (an applied move), the light traced again. Undoing past sculpt_start ends
    the session with the glass as it was."""
    try:
        _session()
        state = _send({"type": "sculpt_undo"})
        if state["error"]:
            return _error(state["error"])
        if state["sculpt"] is None:
            return _ok({"sculpting": False, "note": "undone past sculpt_start: the glass is its recipe again"})
        s = _session()
        return _ok({"sculpting": True, "edits": list(_editor()._obj(s.glass)._construction_args["edits"]),
                    "map_a": _map_a(state), "map_b": _map_b(state)})
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


def sculpt_report(svg_path: Optional[str] = None) -> Dict[str, Any]:
    """The session so far: the edits made since sculpt_start (and how many the glass held before), Map A
    and Map B against the start, the tube routes gained and lost, and the drawing written to
    ``svg_path`` (default `DEFAULT_REPORT`), described, not returned (KA8)."""
    try:
        s, e = _session(), _editor()
        state = e.state(draw=True)
        base = _STATE["baseline"] or {}
        now_routes = _tube_routes(s)
        diff = []
        for tid, routes in now_routes.items():
            before = {r for r, w in base.get("routes", {}).get(tid, []) if w >= 0.05}
            after = {r for r, w in routes if w >= 0.05}
            if before != after:
                diff.append({"tube_id": tid, "gained": sorted(after - before), "lost": sorted(before - after)})
        path = Path(svg_path or DEFAULT_REPORT).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state["svg"], encoding="utf-8")
        counts = Counter()
        for cls in ("sculpt-tube", "sculpt-bundle-ray", "sculpt-span", "sculpt-isoline", "sculpt-handle"):
            counts[cls] = state["svg"].count(f'class="{cls}"')
        edits = list(e._obj(s.glass)._construction_args["edits"])
        earlier = min(base.get("edits", 0), len(edits))
        return _ok({"glass": s.glass, "edits": edits[earlier:], "edits_before_start": earlier,
                    "map_a": {"start": base.get("map_a"), "now": _map_a(state)},
                    "map_b": {"start": base.get("map_b"), "now": _map_b(state)},
                    "route_changes": diff,
                    "svg": {"path": str(path), "bytes": path.stat().st_size, "elements": dict(counts),
                            "showing": f"Map {s.map}"}})
    except Exception as exc:  # noqa: BLE001
        return _error(f"{type(exc).__name__}: {exc}")


# --- the registration ----------------------------------------------------------------------

_HANDLE = {"type": "string", "description": "A handle's id, 'glass/edge/index', as list_sculpt_handles gives it."}
_DELTA = {"type": "number", "description": "The move: scene units along the outward normal for 'position' "
                                           "(positive outward), degrees counter-clockwise for 'normal'."}
_KIND = {"type": "string", "enum": ["position", "normal"], "default": "position",
         "description": "'position' moves the point; 'normal' turns its tangent."}

TOOLS = [
    (sculpt_start, "Begin sculpting a designed glass of the attached scene (a recipe with spline edges, such as "
                   "an RR lens): it becomes a sculpted glass whose edits are recorded, its source's light is cut "
                   "into flux tubes at the receiver (a detector), and an RR lens's two edge bundles are aimed. "
                   "Returns Map A (each bundle's optical path length spread to its target: 0 is a perfect "
                   "design), Map B (each tube's delivered share) and each edge's preview limit.",
     {"type": "object", "properties": {
         "glass": {"type": "string", "description": "The designed glass's name in the scene."},
         "receiver": {"type": "string", "description": "The detector the tubes are cut at; the scene's only "
                                                       "detector if not given."},
         "tubes": {"type": "integer", "description": "How many tubes, 2 to 20.", "default": 8},
         "bundles": {"type": "boolean", "description": "Aim the edge bundles (RR lens only).", "default": True}},
      "required": ["glass"]}),
    (list_flux_tubes, "The flux tubes of the sculpting session: each one's share of the source's power, the "
                      "share of it delivered to the receiver (Map B), and its main route.",
     {"type": "object", "properties": {}}),
    (describe_flux_tube, "One flux tube: its routes with their shares, and the surfaces its main route crosses, "
                         "in order, each with the handles nearest where the tube's rays cross it.",
     {"type": "object", "properties": {"tube_id": {"type": "string",
                                                   "description": "A tube's id, as list_flux_tubes gives it."}},
      "required": ["tube_id"]}),
    (list_sculpt_handles, "The handles of the sculpted glass: each one's id, edge, point, outward normal, the "
                          "shorter adjacent chord, its preview limit as a move, and the tubes and bundle rays "
                          "that cross it. Filter by edge label or by tube.",
     {"type": "object", "properties": {
         "edge": {"type": "string", "description": "An edge label (an RR lens: 'N' faces the source, 'X' the "
                                                   "receiver)."},
         "tube_id": {"type": "string", "description": "Only the handles this tube crosses."},
         "max_items": {"type": "integer", "description": "At most this many.", "default": MAX_HANDLES}}}),
    (preview_handle_move, "Estimate a handle move at first order, with nothing traced and nothing changed: per "
                          "bundle the mean change of S and the spread and rms the move would give (the rms is "
                          "smooth in the move, the spread is not), per tube the mean "
                          "change. 'trusted' is false past the edge's preview limit: then apply it to know.",
     {"type": "object", "properties": {"handle_id": _HANDLE, "delta": _DELTA, "kind": _KIND},
      "required": ["handle_id", "delta"]}),
    (apply_handle_move, "Make a handle move: the edit is recorded and the light traced again (about a second). "
                        "Returns Map A and Map B after it, the events (a tube split, total internal reflection "
                        "switched, light leaving the receiver, rays leaving a bundle's route; an outline broken "
                        "is refused), and the preview limits, measured from this move.",
     {"type": "object", "properties": {"handle_id": _HANDLE, "delta": _DELTA, "kind": _KIND},
      "required": ["handle_id", "delta"]}),
    (undo_handle_move, "Undo the last applied move; the light is traced again.",
     {"type": "object", "properties": {}}),
    (sculpt_report, "The sculpting session so far: the edit list, Map A and Map B at the start and now, the "
                    "tube routes gained and lost, and the drawing written to an SVG file (its path, size and "
                    "element counts are returned, not the drawing).",
     {"type": "object", "properties": {"svg_path": {"type": "string", "description": "Where to write the "
                                                    "drawing; _sculpt_runs/sculpt_report.svg if not given."}}}),
]


def register() -> bool:
    """Add the eight sculpt tools to the core's tool lists, once. Call before the MCP server starts.

    Returns:
        True if they were added now, False if they already were.

    Raises:
        RuntimeError: If the MCP server is already running (`register_tool`).
    """
    from ..analysis.tool_registry import get_agentic_tools, register_tool  # noqa: PLC0415

    present = {t["name"] for t in get_agentic_tools()}
    if all(fn.__name__ in present for fn, _, _ in TOOLS):
        return False
    for fn, description, schema in TOOLS:
        if fn.__name__ not in present:
            register_tool(fn, description, schema, module="ray_tracing_shapely.builder.agentic")
    return True


__all__ = ["MAX_HANDLES", "TOOLS", "apply_handle_move", "attach", "describe_flux_tube", "detach", "list_flux_tubes",
           "list_sculpt_handles", "preview_handle_move", "register", "sculpt_report", "sculpt_start",
           "undo_handle_move"]
