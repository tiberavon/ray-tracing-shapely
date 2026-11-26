"""
Python-specific module: sculpt session -- the scene builder's sculpt mode, its state and its rules
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
PYTHON-SPECIFIC MODULE: sculpt session
===============================================================================
The scene builder's sculpt mode (`SceneEditor`'s ``sculpt_*`` messages): a
designed glass is edited by its handles, with its light in view.

**Start.** The glass becomes a `SculptedGlass` (its recipe kept as the base,
no edits yet; undoable like any change). Its source's light is cut into flux
tubes at the receiver (`flux_tubes.partition`), and, for an RR lens, its edge
bundles are aimed (`edge_bundles`). The cut is kept: every later trace replays
the same seeds, so a tube is the same tube before and after an edit.

**Preview (a drag).** Nothing is traced: the first-order change of each
tube's arrivals and each bundle ray's S (`first_order.predict`,
`edge_bundles.predict`), and the edited outline. Each edge has a preview
limit, a drag ratio past which the estimate is not trusted; the view fades
the preview past it. It starts at `first_order.PREVIEW_LIMIT` and is measured
at every apply: the estimate made before the edit is compared with the
re-trace after it, and the limit set so that the estimate's error stays
within `TARGET_ERROR` of the change. The entrance and exit of a lens differ
by two orders of magnitude here, so one limit for all would be wrong for one
of them.

**Apply (a release).** The edit is appended to the glass's edit list, through
the scene file like any change (a refused edit leaves the scene as it was:
`C-SCULPT-04`), and the tubes and bundles are traced again. What changed in
kind is reported as events:

- ``tube_split``: a tube's main route changed, or it gained a route carrying
  at least `ROUTE_SHARE` of its light;
- ``tir_switched``: a route with total internal reflection appeared in, or
  left, a tube (at `ROUTE_SHARE`);
- ``receiver_missed``: a tube's delivered fraction fell by `LOSS` or more;
- ``bundle_off_route``: rays of a bundle left its designed route;
- ``outline_refused``: the edit broke the outline and was not applied.

**Undo** is the builder's: the scene goes back, and the tubes and bundles are
traced again on it. ``sculpt_repartition`` cuts the tubes again on the scene
as it is, after a tube has split.
===============================================================================
"""

from __future__ import annotations

import dataclasses
import math
import time
from typing import Any, Dict, List, Optional

from ..analysis import edge_bundles as eb
from ..analysis import first_order as fo
from ..analysis import flux_tubes as ft
from ..analysis import scene_file as sf

#: The preview's error, relative to the change it estimates, that its limit is set to keep.
TARGET_ERROR = 0.1
#: A route carrying this share of a tube's light counts for an event.
ROUTE_SHARE = 0.05
#: A drop of a tube's delivered fraction this large is a receiver missed.
LOSS = 0.05
#: The bundles' weak-ray threshold (10^-2). A bundle ray is read along its designed route, which
#: carries about 0.9 of its power on the RR lens; the partial reflections below this are off that
#: route, and tracing them doubled the time (Map A is the same at 10^-6).
BUNDLE_THRESHOLD_EXP = 2
#: The fine-drag scale: scene units of move per scene unit of pointer travel, by default.
FINE = 0.02


class SculptError(ValueError):
    """A sculpt message the session cannot follow, with the reason."""


def _routes_with(routes: Any, share: float) -> set:
    return {r for r, w in routes if w >= share}


def _has_tir(route: Any) -> bool:
    return any(ev == "tir" for _, _, ev in route)


class SculptSession:
    """One sculpting session on one glass."""

    def __init__(self, glass: str, receiver: Optional[str], tubes: int, bundles: bool) -> None:
        self.glass = glass
        self.receiver = receiver
        self.want_tubes, self.want_bundles = tubes, bundles
        self.cut: Optional[ft.TubeSet] = None           # the tubes as cut: their seeds are replayed
        self.tubes: Optional[ft.TubeSet] = None         # the tubes on the scene as it is
        self.aimed: Optional[eb.BundleSet] = None       # the bundles as aimed
        self.bundles: Optional[eb.BundleSet] = None     # the bundles on the scene as it is
        self.opl_scale: Optional[float] = None
        self.map = "A"
        self.fine = FINE
        self.limits: Dict[int, Dict[str, Any]] = {}
        self.preview: Optional[Dict[str, Any]] = None
        self.events: List[Dict[str, Any]] = []
        self.trace_seconds = 0.0

    # --- the light ------------------------------------------------------------------------

    def cut_tubes(self, scene: Any) -> None:
        if self.receiver is None or not self.want_tubes:
            self.cut = self.tubes = None
            return
        self.cut = ft.partition(scene, self.receiver, ft.TubeSettings(tubes=self.want_tubes))
        self.tubes = self.cut

    def aim_bundles(self, scene: Any) -> None:
        self.aimed = self.bundles = None
        if not self.want_bundles:
            return
        glass = _glass(scene, self.glass)
        base = glass._construction_args.get("base") or {}
        if base.get("recipe") != "RRLens":
            return                                       # bundles are written for the RR lens only
        from ..analysis.sculpted_glass import _base_object  # noqa: PLC0415
        from ..core.scene import Scene  # noqa: PLC0415
        lens = _base_object(Scene(), base)
        self.aimed = eb.edge_bundles(scene, eb.rr_bundles(lens, glass=self.glass),
                                     eb.BundleSettings(per_span=1, min_brightness_exp=BUNDLE_THRESHOLD_EXP))
        self.bundles = self.aimed
        self.opl_scale = self.opl_scale or _scale(self.bundles)

    def retrace(self, scene: Any) -> None:
        """The cut tubes and the aimed bundles traced again on the scene as it is."""
        t0 = time.perf_counter()
        if self.cut is not None:
            rep = ft.replay(scene, self.cut)
            tubes = []
            for t in self.cut.tubes:
                r = rep.tubes.get(t.tube_id)
                tubes.append(t if r is None else dataclasses.replace(
                    t, delivered_fraction=r.delivered_fraction, routes=r.routes, arrivals=r.arrivals))
            self.tubes = dataclasses.replace(self.cut, tubes=tuple(tubes))
        if self.aimed is not None:
            self.bundles = eb.trace_bundles(scene, self.aimed)
        self.trace_seconds = time.perf_counter() - t0

    # --- handles ----------------------------------------------------------------------------

    def handle(self, scene: Any, handle_id: str, kind: str) -> fo.Handle:
        for h in fo.handles(scene, self.glass):
            if h.handle_id == handle_id and h.kind == kind:
                return h
        if kind not in fo.KINDS:
            raise SculptError(f"a handle moves by {' or '.join(fo.KINDS)}, not {kind!r}")
        raise SculptError(f"no handle {handle_id!r} on {self.glass!r}")

    def limit(self, edge: int) -> float:
        return self.limits.get(edge, {}).get("limit", fo.PREVIEW_LIMIT)

    def handles_state(self, scene: Any) -> List[Dict[str, Any]]:
        glass = _glass(scene, self.glass)
        out = []
        for h in fo.handles(scene, self.glass, kinds=("position",)):
            span = fo._span(glass, h.edge)
            pts = glass.path[span.path_indices[0]]["curve"]["points"]
            x, y = pts[h.index]
            nx, ny = fo.outward_normal(glass, span, h.index)
            chord = min(math.dist(pts[h.index - 1], pts[h.index]), math.dist(pts[h.index], pts[h.index + 1]))
            out.append({"handle_id": h.handle_id, "edge": h.edge, "label": h.label, "index": h.index,
                        "x": x, "y": y, "normal": [nx, ny], "chord": chord, "limit": self.limit(h.edge)})
        return out

    # --- preview and apply ----------------------------------------------------------------

    def estimate(self, scene: Any, handle: fo.Handle, delta: float) -> Dict[str, Any]:
        """The first-order estimate of a move: per bundle ray and per tube arrival, nothing traced."""
        out: Dict[str, Any] = {"handle_id": handle.handle_id, "kind": handle.kind, "delta": delta,
                               "ratio": fo.drag_ratio(scene, handle, delta), "limit": self.limit(handle.edge)}
        out["trusted"] = out["ratio"] <= out["limit"]
        if self.bundles is not None:
            out["bundle_changes"] = eb.predict(scene, self.bundles, handle, delta)
            summary = {}
            for b in self.bundles.bundles:
                ch = out["bundle_changes"][b.bundle_id]
                moved = [r.opl + ch.get(r.seed, 0.0) for r in b.counted]
                mean = sum(moved) / len(moved) if moved else 0.0
                summary[b.bundle_id] = {"spread_before": b.spread,
                                        "spread_after": (max(moved) - min(moved)) if moved else None,
                                        "rms_before": b.rms,
                                        "rms_after": math.sqrt(sum((x - mean) ** 2 for x in moved) / len(moved))
                                        if moved else None}
            out["bundles"] = summary
        if self.tubes is not None:
            changes = fo.predict(scene, self.tubes, handle, delta)
            out["tubes"] = {tid: {"mean_dopl": (sum(c.dopl for c in cs) / len(cs)) if cs else 0.0,
                                  "arrivals_moved": sum(1 for c in cs if c.dopl != 0.0)}
                            for tid, cs in changes.items()}
            out["tube_changes"] = changes
        return out

    def learn(self, before: Dict[str, Any], old_bundles: Any, old_tubes: Any, handle: fo.Handle) -> None:
        """The edge's preview limit from the estimate made before an edit and the re-trace after it."""
        err, big = 0.0, 0.0
        if old_bundles is not None and self.bundles is not None and "bundle_changes" in before:
            for b, nb in zip(old_bundles.bundles, self.bundles.bundles):
                now = {r.seed: r.opl for r in nb.counted}
                for r in b.counted:
                    if r.seed in now:
                        d = now[r.seed] - r.opl
                        err = max(err, abs(d - before["bundle_changes"][b.bundle_id].get(r.seed, 0.0)))
                        big = max(big, abs(d))
        if big <= 0.0 and old_tubes is not None and self.tubes is not None and "tube_changes" in before:
            # no bundles: the tubes' arrivals, S brought back to the old end point, by seed and route
            for a, b in zip(old_tubes.tubes, self.tubes.tubes):
                now = {(x.seed, x.route): x for x in b.arrivals}
                for old, ch in zip(a.arrivals, before["tube_changes"][a.tube_id]):
                    new = now.get((old.seed, old.route))
                    if new is None or not ch.hits:
                        continue
                    d = fo.opl_at_old_end(new, old) - old.opl
                    err, big = max(err, abs(d - ch.dopl)), max(big, abs(d))
        if big <= 0.0 or before["ratio"] <= 0.0:
            return
        per_ratio = err / big / before["ratio"]
        limit = min(0.2, TARGET_ERROR / per_ratio) if per_ratio > 0 else 0.2
        self.limits[handle.edge] = {"limit": limit, "per_ratio": per_ratio, "measured": True}

    def events_between(self, old_tubes: Any, old_bundles: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if old_tubes is not None and self.tubes is not None:
            for a, b in zip(old_tubes.tubes, self.tubes.tubes):
                ra, rb = _routes_with(a.routes, ROUTE_SHARE), _routes_with(b.routes, ROUTE_SHARE)
                main_a = a.routes[0][0] if a.routes else None
                main_b = b.routes[0][0] if b.routes else None
                if main_a != main_b or (rb - ra):
                    out.append({"kind": "tube_split", "tube_id": a.tube_id,
                                "detail": "; ".join(ft.route_text(r) for r in sorted(rb - ra, key=str))
                                or f"main route now {ft.route_text(main_b) if main_b else 'none'}"})
                if {r for r in ra if _has_tir(r)} != {r for r in rb if _has_tir(r)}:
                    out.append({"kind": "tir_switched", "tube_id": a.tube_id,
                                "detail": "a route with total internal reflection appeared or left"})
                if a.delivered_fraction - b.delivered_fraction >= LOSS:
                    out.append({"kind": "receiver_missed", "tube_id": a.tube_id,
                                "detail": f"delivered {a.delivered_fraction:.3f} -> {b.delivered_fraction:.3f}"})
        if old_bundles is not None and self.bundles is not None:
            for a, b in zip(old_bundles.bundles, self.bundles.bundles):
                if len(b.counted) < len(a.counted):
                    out.append({"kind": "bundle_off_route", "bundle_id": a.bundle_id,
                                "detail": f"{len(a.counted) - len(b.counted)} rays left the designed route"})
        return out

    # --- the state ----------------------------------------------------------------------------

    def state(self, scene: Any) -> Dict[str, Any]:
        preview = None
        if self.preview is not None:
            preview = {k: v for k, v in self.preview.items() if k not in ("bundle_changes", "tube_changes")}
        return {
            "glass": self.glass, "receiver": self.receiver, "map": self.map,
            "opl_scale": self.opl_scale, "fine": self.fine,
            "handles": self.handles_state(scene),
            "tubes": None if self.tubes is None else self.tubes.power_map(),
            "bundles": None if self.bundles is None else self.bundles.map_a(),
            "preview": preview, "events": self.events,
            "limits": {str(k): v for k, v in self.limits.items()},
            "trace_seconds": self.trace_seconds,
        }


def _glass(scene: Any, name: str) -> Any:
    for o in scene.objs:
        if o.name == name:
            return o
    raise SculptError(f"no object named {name!r}")


def _scale(bundles: Any) -> float:
    from ..analysis.sculpt_layer import opl_scale_for  # noqa: PLC0415
    return opl_scale_for(bundles)


def sculptable(scene: Any, name: str) -> str:
    """The recipe of a glass that can be sculpted (a registered recipe with a spline edge), or why not."""
    from ..core.glass_spans import glass_spans  # noqa: PLC0415
    obj = _glass(scene, name)
    recipe = sf._recipe_name(obj) if getattr(obj, "_construction_args", None) is not None else None
    if recipe is None:
        raise SculptError(f"{name!r} is not a designed element: sculpting edits a designed glass's spline "
                          f"edges, recorded as edits of its recipe")
    if not getattr(obj, "path", None) or not any(s.kind == "spline" for s in glass_spans(obj.path)):
        raise SculptError(f"{name!r} ({recipe}) has no spline edge to sculpt")
    return recipe


__all__ = ["FINE", "LOSS", "ROUTE_SHARE", "SculptError", "SculptSession", "TARGET_ERROR", "sculptable"]
