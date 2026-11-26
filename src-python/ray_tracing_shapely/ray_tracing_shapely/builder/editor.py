"""
Python-specific module: scene editor
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
SceneEditor -- the scene builder's model: every rule in Python, no view
===============================================================================
A view (the notebook widget, later a VS Code editor or a solveit page) draws
what `state()` returns and sends back what the person did, as messages
(`handle`). The geometry rules are the scene objects' own editing hooks, as
the JavaScript simulator has them (`core.mouse.Mouse`, `check_mouse_over`,
`on_drag`, `on_construct_mouse_*`): a drag is applied here, once, on release.

Messages (JSON; positions in scene coordinates, y up):

- ``{"type": "press", "x", "y", "ctrl", "shift", "alt", "target"?}``: the pointer goes
  down. With a primitive tool, construction starts (or a polygon gets its next
  point); otherwise the object part under the pointer is found and kept for
  the release, and returned as ``state()["drag"]`` so the view can preview it.
- ``{"type": "move", "x", "y", ...}``: the pointer moving while an object is
  built (a view sends it only then); the object follows it.
- ``{"type": "release", "x", "y", "ctrl", "shift", "alt"}``: the pointer comes
  up. Construction moves and ends; a recipe tool places its element; a drag
  is applied (ctrl on a whole-object drag leaves a copy behind, as upstream).
- ``{"type": "tool", "name": <primitive type | recipe | null>, "args": {..}}``:
  the palette. A recipe needs its required arguments; one with a
  ``position`` is placed where the pointer is released.
- ``{"type": "select", "name": <name | null>}``, ``{"type": "delete", "name"}``.
- ``{"type": "set", "name", "key", "value"}``: a primitive's property by its
  key path (``property_schema``), or a recipe's argument (``recipe_parameters``).
- ``{"type": "undo"}``, ``{"type": "redo"}``.
- ``{"type": "save", "path"}``, ``{"type": "open", "path"}``: the scene file.
  Open also reads the web simulator's files, converted; ``{"type":
  "export_web", "path"}`` writes the scene in that format. What either left
  out is said in ``state()["notice"]``.
- ``{"type": "view", "zoom": f, "x", "y"}`` (about a point), ``{"type": "view",
  "pan": [dx, dy]}`` (scene units), ``{"type": "view", "fit": true}``.
- ``{"type": "settings", "grid_size", "snap_to_grid", "ray_density",
  "quick_max_rays"}``.
- The sculpt mode (`builder.sculpt`): ``{"type": "sculpt_start", "glass"?,
  "receiver"?, "tubes"?, "bundles"?}`` (the glass becomes a `SculptedGlass`;
  its light is cut into tubes at the receiver, its edge bundles aimed);
  ``{"type": "sculpt_preview", "handle_id", "kind", "delta"}`` (the
  first-order estimate, nothing traced, nothing changed; ``"clear": true``
  drops it);
  ``{"type": "sculpt_apply", ...}`` (the same move, recorded as an edit, the
  light traced again, events reported); ``{"type": "sculpt_undo"}``;
  ``{"type": "sculpt_repartition"}``; ``{"type": "sculpt_settings", "map",
  "opl_scale", "fine"}``; ``{"type": "sculpt_stop"}``.

A designed element is moved by its placement only: a drag anywhere on it
moves its ``position`` (or the arguments its class names as
``placement_points``, when it has none),
because dragging a vertex would make it something its constructor did not
build. Its other parameters are its form. After every change the scene is
traced quickly (``quick_max_rays`` segments) so the person sees what the edit
did; the full trace belongs to a flow.
===============================================================================
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..analysis import scene_file as sf
from ..core.key_path import get_by_key_path, set_by_key_path
from ..core.mouse import Mouse, MousePoint
from ..core.scene import Scene
from ..core.simulator import Simulator
from ..core.svg_renderer import SVGRenderer
from .sculpt import SculptError, SculptSession, sculptable

#: The primitives the palette offers, in its order: the JavaScript
#: simulator's, then this package's.
PALETTE_PRIMITIVES = [
    "PointSource", "Beam", "SingleRay", "AngleSource",
    "Mirror", "IdealMirror", "Glass", "SphericalLens", "IdealLens",
    "Blocker", "Detector", "Photodetector", "GroundGlass",
]

#: Undo depth.
HISTORY = 100


class _Attr(dict):
    """A serialized object read with dots, as upstream's `originalObj` is read."""

    def __getattr__(self, key: str) -> Any:
        try:
            value = self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc
        return _Attr(value) if isinstance(value, dict) else value


def _plain(value: Any) -> Any:
    """JSON-safe: tuples to lists, MousePoints to dicts, infinities to None."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "x") and hasattr(value, "y") and not isinstance(value, (int, float, str)):
        return {"x": value.x, "y": value.y}
    return value


class EditorError(ValueError):
    """A message the editor refuses: an unknown name, key or tool, or a bad argument."""


class SceneEditor:
    """The scene builder's model.

    Args:
        scene: The scene to edit; a new empty one if None.
        path: A scene file to open instead.
        width, height: The view's size in screen pixels.
        quick_max_rays: Segments traced after each change (0: no trace).
    """

    def __init__(self, scene: Optional[Scene] = None, *, path: Optional[str] = None,
                 width: int = 800, height: int = 520, quick_max_rays: int = 4000) -> None:
        self.width, self.height = width, height
        self.quick_max_rays = quick_max_rays
        self.path: Optional[str] = None
        self.tool: Optional[Dict[str, Any]] = None
        self.selected: Optional[str] = None
        self.error: Optional[str] = None
        self.notice: Optional[str] = None
        self._constructing: Optional[Any] = None
        self._pending: Optional[Dict[str, Any]] = None
        self._undo: List[Dict[str, Any]] = []
        self._redo: List[Dict[str, Any]] = []
        self._segments: List[Any] = []
        self._trace_note: Optional[str] = None
        self.sculpt: Optional[SculptSession] = None
        self.center = MousePoint(0.0, 0.0)
        if path is not None:
            self.scene = self._read(path)
            self.path = str(path)
        else:
            self.scene = scene if scene is not None else Scene()
        self.scene.scale = 4.0              # screen pixels per unit, until fitted to the objects
        self._name_all()
        self.fit()
        self._trace()

    # --- names and kinds ------------------------------------------------------

    def _names(self) -> List[str]:
        return [o.name for o in self.scene.objs if o.name]

    def _new_name(self, base: str) -> str:
        names, k = set(self._names()), 1
        while f"{base}{k}" in names:
            k += 1
        return f"{base}{k}"

    def _name_all(self) -> None:
        for obj in self.scene.objs:
            if not obj.name:
                obj.name = self._new_name(type(obj).type or type(obj).__name__)

    def _obj(self, name: Optional[str]) -> Any:
        for obj in self.scene.objs:
            if obj.name == name:
                return obj
        raise EditorError(f"no object named {name!r}; objects: {', '.join(self._names())}")

    @staticmethod
    def _owner(obj: Any) -> Any:
        """The designed element an object is a part of (an RXI's mirror), else itself."""
        while getattr(obj, "_built_inside", None) is not None:
            obj = obj._built_inside
        return obj

    @staticmethod
    def _recipe(obj: Any) -> Optional[str]:
        return sf._recipe_name(obj) if getattr(obj, "_construction_args", None) is not None else None

    # --- the scene file as the record -------------------------------------------

    def _dump(self) -> Dict[str, Any]:
        return sf.scene_to_dict(self.scene)

    def _load(self, data: Dict[str, Any]) -> None:
        scale, grid, snap = self.scene.scale, self.scene.grid_size, self.scene.snap_to_grid
        self.scene = sf.scene_from_dict(data)
        self.scene.scale = scale
        if "grid_size" not in data.get("settings", {}):
            self.scene.grid_size, self.scene.snap_to_grid = grid, snap
        self._name_all()

    def _commit(self, before: Dict[str, Any]) -> None:
        """Record a change for undo (`before` is the scene file before it)."""
        self._undo.append(before)
        del self._undo[:-HISTORY]
        self._redo.clear()
        self._trace()

    def _rebuild(self, change) -> None:
        """Change the scene through its file (a recipe's arguments, its parts): all or nothing."""
        before = self._dump()
        data = copy.deepcopy(before)
        change(data)
        try:
            self._load(data)
        except Exception:
            self._load(before)
            raise
        self._commit(before)

    # --- the quick trace and the drawing -------------------------------------

    def _trace(self) -> None:
        self._segments, self._trace_note = [], None
        if not self.quick_max_rays or getattr(self, "sculpt", None) is not None:
            return                                   # sculpting draws the tubes and bundles, not the rays
        try:
            sim = Simulator(self.scene, max_rays=self.quick_max_rays)
            self._segments = sim.run()
            if sim.processed_ray_count >= self.quick_max_rays:
                self._trace_note = f"quick trace stopped at {self.quick_max_rays} segments"
        except Exception as exc:                    # noqa: BLE001 -- shown, the scene kept
            self._trace_note = f"the quick trace failed: {type(exc).__name__}: {exc}"

    def viewbox(self) -> List[float]:
        """The visible region, y up: [min_x, min_y, width, height] in scene units."""
        w, h = self.width / self.scene.scale, self.height / self.scene.scale
        return [self.center.x - w / 2, self.center.y - h / 2, w, h]

    def svg(self) -> str:
        renderer = SVGRenderer(width=self.width, height=self.height, viewbox=tuple(self.viewbox()))
        px = 1.0 / self.scene.scale                 # one screen pixel, in scene units
        renderer.draw_scene(self.scene, self._segments, draw_rays=bool(self._segments) and self.sculpt is None,
                            draw_edge_labels=False, edge_stroke_width=2 * px, ray_stroke_width=1.2 * px,
                            object_label_font_size=f"{11 * px:.6g}px", point_radius=5 * px)
        if self.sculpt is not None:
            self._draw_sculpt(renderer, px)
        return renderer.to_string()

    def _draw_sculpt(self, renderer: SVGRenderer, px: float) -> None:
        from ..analysis import first_order as fo  # noqa: PLC0415
        from ..analysis.glass_geometry import outline_coords  # noqa: PLC0415
        from ..analysis.sculpt_layer import draw_sculpt_layer  # noqa: PLC0415
        s, p = self.sculpt, self.sculpt.preview
        outline, changes = None, None
        if p is not None:
            handle = s.handle(self.scene, p["handle_id"], p["kind"])
            outline = outline_coords(fo.edited_path(self.scene, handle, p["delta"]))
            changes = p.get("bundle_changes")
        draw_sculpt_layer(renderer, self.scene, tubes=s.tubes if s.map in ("B", "both") else None,
                          bundles=s.bundles if s.map in ("A", "both") else None, handles_of=s.glass,
                          opl_scale=s.opl_scale, preview=changes, pixel=px, preview_outline=outline,
                          trusted=p is None or p["trusted"])

    def _points(self, obj: Any) -> List[MousePoint]:
        out: List[MousePoint] = []
        for key in ("p1", "p2"):
            p = getattr(obj, key, None)
            if isinstance(p, dict) and "x" in p:
                out.append(MousePoint(p["x"], p["y"]))
        if isinstance(getattr(obj, "x", None), (int, float)) and isinstance(getattr(obj, "y", None), (int, float)):
            out.append(MousePoint(obj.x, obj.y))
        for p in getattr(obj, "path", None) or []:
            out.append(MousePoint(p["x"], p["y"]))
        return out

    def fit(self) -> None:
        """Centre and scale the view on the scene's objects."""
        pts = [p for o in self.scene.objs for p in self._points(o)]
        if not pts:
            self.center = MousePoint(0.0, 0.0)
            return
        xs, ys = [p.x for p in pts], [p.y for p in pts]
        w, h = max(max(xs) - min(xs), 1e-9), max(max(ys) - min(ys), 1e-9)
        self.center = MousePoint((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)
        self.scene.scale = 0.8 * min(self.width / w, self.height / h)

    # --- the state a view draws ---------------------------------------------

    def _handles(self, obj: Any) -> List[Dict[str, Any]]:
        if self._recipe(self._owner(obj)):
            return []
        out = []
        for entry in type(obj).property_schema(obj, self.scene):
            if entry["type"] == "point":
                p = get_by_key_path(obj, entry["key"])
                if p is not None:
                    out.append({"key": entry["key"], "x": _xy(p)[0], "y": _xy(p)[1]})
            elif entry["type"] == "array" and entry["key"] == "path":
                for i, p in enumerate(obj.path or []):
                    out.append({"key": f"path.{i}", "x": p["x"], "y": p["y"]})
        return out

    def _selection(self) -> Optional[Dict[str, Any]]:
        if self.selected is None:
            return None
        try:
            obj = self._obj(self.selected)
        except EditorError:
            self.selected = None
            return None
        recipe = self._recipe(obj)
        out: Dict[str, Any] = {"name": obj.name, "uuid": obj.uuid, "type": type(obj).type,
                               "kind": "recipe" if recipe else "primitive",
                               "handles": self._handles(obj)}
        if recipe:
            args = obj._construction_args
            out["recipe"] = recipe
            out["parameters"] = [dict(p, value=_plain(args.get(p["name"]))) for p in sf.recipe_parameters(recipe)
                                 if p["name"] not in ("name", "role")]
        else:
            out["properties"] = [dict(e, value=_plain(get_by_key_path(obj, e["key"], type(obj).serializable_defaults)))
                                 for e in type(obj).property_schema(obj, self.scene)
                                 if e["key"] != ""]
        return out

    def state(self, draw: bool = True) -> Dict[str, Any]:
        """Everything a view draws: the drawing, the objects, the selection, the palette.

        ``draw=False`` leaves the drawing out (``"svg"`` is None): for a caller with no view, such
        as an agent's tools, which read the numbers.
        """
        objects = []
        for obj in self.scene.objs:
            owner = self._owner(obj)
            entry = {"name": obj.name, "uuid": obj.uuid, "type": type(obj).type,
                     "kind": "recipe" if self._recipe(owner) else "primitive",
                     "owner": owner.name if owner is not obj else None,
                     "recipe": self._recipe(owner)}
            x, y = getattr(obj, "x", None), getattr(obj, "y", None)
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not hasattr(obj, "p1"):
                entry["at"] = [x, y]                  # a point object: the page picks it within a click extent
            objects.append(entry)
        drag = None
        if self._pending is not None and self._pending.get("obj") is not None:
            ctx = self._pending["context"]
            tp = ctx.get("targetPoint")
            drag = {"name": self._pending["obj"].name, "part": ctx.get("part"),
                    "index": ctx.get("index"),
                    "point": None if tp is None else {"x": _xy(tp)[0], "y": _xy(tp)[1]},
                    "whole": ctx.get("part") == 0 or self._pending.get("recipe") is not None}
        return {
            "svg": self.svg() if draw else None,
            "view": {"viewbox": self.viewbox(), "scale": self.scene.scale,
                     "width": self.width, "height": self.height},
            "objects": objects,
            "selected": self._selection(),
            "tool": self.tool and {"name": self.tool["name"], "kind": self.tool["kind"]},
            "constructing": self._constructing is not None,
            "drag": drag,
            "palette": {"primitives": PALETTE_PRIMITIVES,
                        "recipes": [{"name": r, "parameters": [p for p in sf.recipe_parameters(r)
                                                               if p["name"] not in ("name", "role")]}
                                    for r in sf.list_recipes()]},
            "settings": {"grid_size": self.scene.grid_size, "snap_to_grid": self.scene.snap_to_grid,
                         "ray_density": self.scene.ray_density, "quick_max_rays": self.quick_max_rays},
            "trace": {"segments": len(self._segments), "note": self._trace_note},
            "path": self.path,
            "can_undo": bool(self._undo), "can_redo": bool(self._redo),
            "error": self.error,
            "notice": self.notice,
            "sculpt": None if self.sculpt is None else self.sculpt.state(self.scene),
        }

    # --- messages -------------------------------------------------------------

    def handle(self, message: Dict[str, Any], draw: bool = True) -> Dict[str, Any]:
        """Apply one message from a view; the new state. A refused message leaves the
        scene as it was and says why in ``state()["error"]``. ``draw=False``: the state without
        its drawing."""
        self.error, self.notice = None, None
        kind = message.get("type")
        try:
            handler = getattr(self, f"_on_{kind}", None)
            if handler is None:
                raise EditorError(f"unknown message type {kind!r}")
            handler(message)
        except (EditorError, sf.SceneFileError, ValueError, TypeError, KeyError) as exc:
            self.error = str(exc) if isinstance(exc, (EditorError, sf.SceneFileError, SculptError)) \
                else f"{type(exc).__name__}: {exc}"
        return self.state(draw)

    def _mouse(self, m: Dict[str, Any]) -> Mouse:
        return Mouse(MousePoint(float(m["x"]), float(m["y"])), self.scene,
                     override_grid=1 if m.get("alt") else 0)

    # pointer ---------------------------------------------------------------------

    def _on_press(self, m: Dict[str, Any]) -> None:
        mouse, ctrl, shift = self._mouse(m), bool(m.get("ctrl")), bool(m.get("shift"))
        self._pending = None
        if self.tool and self.tool["kind"] == "primitive":
            if self._constructing is None:
                cls = sf._resolve(sf._PRIMITIVES[self.tool["name"]])
                obj = cls(self.scene)
                obj.name = self._new_name(self.tool["name"])
                self._constructing = obj
                self._construct_before = self._dump()
                self.scene.add_object(obj)
            self._constructing.on_construct_mouse_down(mouse, ctrl, shift)
            return
        if self.tool and self.tool["kind"] == "recipe":
            self._pending = {"press": mouse.get_pos_snapped_to_grid(), "recipe_tool": True,
                             "obj": None, "context": {}}
            return
        for obj in reversed(self.scene.objs):
            owner = self._owner(obj)
            ctx = obj.check_mouse_over(mouse) if hasattr(obj, "check_mouse_over") else None
            if not ctx:
                continue
            ctx = dict(ctx)
            self.selected = owner.name
            recipe = self._recipe(owner)
            if recipe:
                ctx = {"part": 0}
            ctx["originalObj"] = _Attr(copy.deepcopy(obj.serialize()))
            self._pending = {"obj": obj if not recipe else owner, "context": ctx, "recipe": recipe,
                             "press": mouse.get_pos_snapped_to_grid(), "before": self._dump()}
            return
        # an element with no editing hooks (a curved mirror), grabbed where the page drew it
        target = m.get("target")
        if target and target in self._names():
            owner = self._owner(self._obj(target))
            recipe = self._recipe(owner)
            self.selected = owner.name
            if recipe:
                self._pending = {"obj": owner, "context": {"part": 0}, "recipe": recipe,
                                 "press": mouse.get_pos_snapped_to_grid(), "before": self._dump()}
            return
        self.selected = None

    def _on_move(self, m: Dict[str, Any]) -> None:
        """The pointer moving while an object is built: the object follows it, by its own rule."""
        if self._constructing is not None:
            self._constructing.on_construct_mouse_move(self._mouse(m), bool(m.get("ctrl")), bool(m.get("shift")))

    def _on_release(self, m: Dict[str, Any]) -> None:
        mouse, ctrl, shift = self._mouse(m), bool(m.get("ctrl")), bool(m.get("shift"))
        if self._constructing is not None:
            obj = self._constructing
            obj.on_construct_mouse_move(mouse, ctrl, shift)
            ret = obj.on_construct_mouse_up(mouse, ctrl, shift) or {}
            if ret.get("isCancelled"):
                self.scene.remove_object(obj)
                self._constructing = None
            elif ret.get("isDone"):
                self._constructing = None
                self.selected = obj.name
                self.tool = None
                self._commit(self._construct_before)
            return
        pending, self._pending = self._pending, None
        if pending is None:
            return
        if pending.get("recipe_tool"):
            self._place_recipe(pending["press"], mouse.get_pos_snapped_to_grid())
            return
        obj, ctx = pending["obj"], pending["context"]
        moved = mouse.get_pos_snapped_to_grid()
        if (moved.x, moved.y) == (pending["press"].x, pending["press"].y) and not shift:
            return                                       # a click: selection only
        if pending["recipe"]:
            self._move_recipe(obj, moved.x - pending["press"].x, moved.y - pending["press"].y)
            return
        if ctx.get("part") == 0 and ctrl:
            # upstream: ctrl while dragging the whole object leaves a copy where it was
            copy_obj = type(obj)(self.scene, dict(ctx["originalObj"]))
            copy_obj.name = self._new_name(type(obj).type)
            self.scene.objs.insert(self.scene.objs.index(obj), copy_obj)
            if getattr(copy_obj, "is_optical", False):
                self.scene.optical_objs.append(copy_obj)
        obj.on_drag(mouse, ctx, ctrl, shift)
        self._commit(pending["before"])

    def _place_recipe(self, press: MousePoint, release: MousePoint) -> None:
        name, args = self.tool["name"], copy.deepcopy(self.tool["args"])
        params = {p["name"]: p for p in sf.recipe_parameters(name)}
        if "position" in params:
            args["position"] = [release.x, release.y]
        new_name = self._new_name(name)
        self._rebuild(lambda data: data["objects"].append({"name": new_name, "recipe": name,
                                                           "args": _plain(args)}))
        self.selected, self.tool = new_name, None

    def _move_recipe(self, owner: Any, dx: float, dy: float) -> None:
        name = owner.name

        def change(data):
            entry = next(e for e in data["objects"] if e.get("name") == name)
            _shift_args(name, entry["recipe"], entry["args"], dx, dy)

        self._rebuild(change)

    # palette, selection, properties --------------------------------------------

    def _on_tool(self, m: Dict[str, Any]) -> None:
        name = m.get("name")
        if self._constructing is not None:               # leaving a construction drops it
            self.scene.remove_object(self._constructing)
            self._constructing = None
        if name is None:
            self.tool = None
        elif name in PALETTE_PRIMITIVES:
            self.tool = {"name": name, "kind": "primitive"}
        elif name in sf.list_recipes():
            args = dict(m.get("args") or {})
            missing = [p["name"] for p in sf.recipe_parameters(name)
                       if p["required"] and p["name"] not in args and p["name"] not in ("position",)]
            if missing:
                raise EditorError(f"{name} needs {', '.join(missing)} before it is placed")
            self.tool = {"name": name, "kind": "recipe", "args": args}
        else:
            raise EditorError(f"no tool {name!r}")
        self._pending = None

    def _on_select(self, m: Dict[str, Any]) -> None:
        name = m.get("name")
        self.selected = None if name is None else self._owner(self._obj(name)).name

    def _on_delete(self, m: Dict[str, Any]) -> None:
        owner = self._owner(self._obj(m["name"]))
        before = self._dump()
        for obj in [o for o in self.scene.objs if self._owner(o) is owner]:
            self.scene.remove_object(obj)
        if self.selected == owner.name:
            self.selected = None
        self._commit(before)

    def _on_set(self, m: Dict[str, Any]) -> None:
        obj = self._owner(self._obj(m["name"]))
        key, value = m["key"], m.get("value")
        recipe = self._recipe(obj)
        if recipe:
            if key not in {p["name"] for p in sf.recipe_parameters(recipe)} or key in ("name", "role"):
                raise EditorError(f"{recipe} has no argument {key!r}")
            name = obj.name

            def change(data):
                next(e for e in data["objects"] if e.get("name") == name)["args"][key] = _plain(value)

            self._rebuild(change)
            return
        keys = {e["key"] for e in type(obj).property_schema(obj, self.scene)}
        if key not in keys and key.split(".")[0] not in keys:
            raise EditorError(f"{type(obj).type} has no property {key!r}; properties: {', '.join(sorted(keys))}")
        before = self._dump()
        set_by_key_path(obj, key, value)
        try:
            self._dump()                                 # the object still saves, and comes back the same
        except Exception:
            self._load(before)
            raise
        self._commit(before)

    # history, files, view, settings ------------------------------------------

    def _on_undo(self, m: Dict[str, Any]) -> None:
        if not self._undo:
            raise EditorError("nothing to undo")
        self._redo.append(self._dump())
        self._load(self._undo.pop())
        self._trace()
        self._sculpt_follow()

    def _on_redo(self, m: Dict[str, Any]) -> None:
        if not self._redo:
            raise EditorError("nothing to redo")
        self._undo.append(self._dump())
        self._load(self._redo.pop())
        self._trace()
        self._sculpt_follow()

    def _on_save(self, m: Dict[str, Any]) -> None:
        path = m.get("path") or self.path
        if not path:
            raise EditorError("save needs a path")
        self.path = str(sf.save_scene(self.scene, Path(path).expanduser()))

    def _on_open(self, m: Dict[str, Any]) -> None:
        scale = self.scene.scale
        self.scene = self._read(Path(m["path"]).expanduser())
        self.scene.scale = scale
        self.path = str(m["path"])
        self._name_all()
        self.selected, self.tool, self._constructing, self._pending = None, None, None, None
        self.sculpt = None
        self._undo.clear()
        self._redo.clear()
        self.fit()
        self._trace()

    def _read(self, path: Any) -> Scene:
        """A scene file: this package's, or the web simulator's, converted (what it left out said)."""
        import json  # noqa: PLC0415
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise sf.SceneFileError(f"{path}: not JSON: {exc}") from exc
        if sf.is_web_scene(data):
            scene, report = sf.scene_from_web_dict(data)
            self.notice = _web_notice("read from the web simulator's format", report)
            return scene
        return sf.scene_from_dict(data)

    def _on_export_web(self, m: Dict[str, Any]) -> None:
        if not m.get("path"):
            raise EditorError("export_web needs a path")
        report = sf.save_web_scene(self.scene, Path(m["path"]).expanduser())
        self.notice = _web_notice(f"exported to {m['path']} in the web simulator's format", report)

    def _on_view(self, m: Dict[str, Any]) -> None:
        if m.get("fit"):
            self.fit()
        if "zoom" in m:
            f = float(m["zoom"])
            if not f > 0:
                raise EditorError("zoom must be positive")
            x, y = float(m.get("x", self.center.x)), float(m.get("y", self.center.y))
            # keep (x, y) where it is on the screen
            self.center = MousePoint(x + (self.center.x - x) / f, y + (self.center.y - y) / f)
            self.scene.scale *= f
        if "pan" in m:
            dx, dy = m["pan"]
            self.center = MousePoint(self.center.x + float(dx), self.center.y + float(dy))

    def _on_settings(self, m: Dict[str, Any]) -> None:
        if "grid_size" in m:
            if not float(m["grid_size"]) > 0:
                raise EditorError("grid_size must be positive")
            self.scene.grid_size = float(m["grid_size"])
        if "snap_to_grid" in m:
            self.scene.snap_to_grid = bool(m["snap_to_grid"])
        if "ray_density" in m:
            self.scene.ray_density = float(m["ray_density"])
        if "quick_max_rays" in m:
            self.quick_max_rays = int(m["quick_max_rays"])
        self._trace()


    # the sculpt mode --------------------------------------------------------------

    def _session(self) -> SculptSession:
        if self.sculpt is None:
            raise EditorError("not sculpting: send sculpt_start first")
        return self.sculpt

    def _sculpt_follow(self) -> None:
        """After an undo or redo: the light traced again on the scene as it now is, or the mode left
        if the glass is no longer a sculpted glass (the undo went back past the start)."""
        s = self.sculpt
        if s is None:
            return
        obj = next((o for o in self.scene.objs if o.name == s.glass), None)
        if obj is None or self._recipe(obj) != "SculptedGlass":
            self.sculpt = None
            self._trace()
            return
        s.preview, s.events = None, []
        s.retrace(self.scene)

    def _on_sculpt_start(self, m: Dict[str, Any]) -> None:
        from ..core.scene_objs.other.detector import Detector  # noqa: PLC0415
        name = m.get("glass") or self.selected
        if not name:
            raise EditorError("sculpt_start needs a glass: select one, or name it")
        recipe = sculptable(self.scene, name)
        receiver = m.get("receiver")
        if receiver is None:
            detectors = [o.name for o in self.scene.objs if isinstance(o, Detector)]
            receiver = detectors[0] if len(detectors) == 1 else None
        session = SculptSession(name, receiver, int(m.get("tubes", 8)), bool(m.get("bundles", True)))
        before, converted = self._dump(), recipe != "SculptedGlass"
        if converted:
            def change(data):
                entry = next(e for e in data["objects"] if e.get("name") == name)
                entry["args"] = {"base": {"recipe": entry["recipe"], "args": entry.get("args", {})}, "edits": []}
                entry["recipe"] = "SculptedGlass"
            self._rebuild(change)
        try:
            session.cut_tubes(self.scene)
            session.aim_bundles(self.scene)
            if session.cut is None and session.aimed is None:
                raise SculptError(f"nothing to sculpt by: no receiver (a detector; the scene has "
                                  f"{'none' if receiver is None else 'several'} to choose from, name one) "
                                  f"and no edge bundles (written for an RR lens only)")
        except Exception:
            if converted:                                 # all or nothing: the glass as it was
                self._load(before)
                self._undo.pop()
                self._trace()
            raise
        self.sculpt, self.selected, self.tool = session, name, None
        self._trace()                                    # no rays drawn while sculpting

    def _sculpt_move(self, m: Dict[str, Any]):
        s = self._session()
        if "handle_id" not in m or "delta" not in m:
            raise EditorError("a sculpt move needs handle_id and delta")
        delta = float(m["delta"])
        if not math.isfinite(delta):
            raise EditorError(f"delta must be finite, got {delta}")
        return s, s.handle(self.scene, m["handle_id"], m.get("kind", "position")), delta

    def _on_sculpt_preview(self, m: Dict[str, Any]) -> None:
        if m.get("clear"):
            self._session().preview = None
            return
        s, handle, delta = self._sculpt_move(m)
        s.preview = s.estimate(self.scene, handle, delta)

    def _on_sculpt_apply(self, m: Dict[str, Any]) -> None:
        s, handle, delta = self._sculpt_move(m)
        estimate = s.estimate(self.scene, handle, delta)
        old_tubes, old_bundles = s.tubes, s.bundles
        edit = {"edge": handle.label or handle.edge, "index": handle.index, "kind": handle.kind, "delta": delta}

        def change(data):
            entry = next(e for e in data["objects"] if e.get("name") == s.glass)
            entry["args"]["edits"] = list(entry["args"].get("edits") or []) + [edit]
        s.preview = None
        try:
            self._rebuild(change)
        except Exception as exc:
            s.events = [{"kind": "outline_refused", "handle_id": handle.handle_id, "detail": str(exc)}]
            raise
        s.retrace(self.scene)
        s.events = s.events_between(old_tubes, old_bundles)
        s.learn(estimate, old_bundles, old_tubes, handle)

    def _on_sculpt_undo(self, m: Dict[str, Any]) -> None:
        self._session()
        self._on_undo(m)

    def _on_sculpt_repartition(self, m: Dict[str, Any]) -> None:
        s = self._session()
        s.cut_tubes(self.scene)
        s.preview, s.events = None, []

    def _on_sculpt_settings(self, m: Dict[str, Any]) -> None:
        s = self._session()
        if "map" in m:
            if m["map"] not in ("A", "B", "both"):
                raise EditorError(f"map is 'A', 'B' or 'both', got {m['map']!r}")
            s.map = m["map"]
        if "opl_scale" in m:
            if not float(m["opl_scale"]) > 0:
                raise EditorError("opl_scale must be positive")
            s.opl_scale = float(m["opl_scale"])
        if "fine" in m:
            if not float(m["fine"]) > 0:
                raise EditorError("fine must be positive")
            s.fine = float(m["fine"])

    def _on_sculpt_stop(self, m: Dict[str, Any]) -> None:
        self.sculpt = None
        self._trace()


def _web_notice(what: str, report: Dict[str, Any]) -> str:
    left = [f"{x.get('name') or x['type']} ({x['reason']})" for x in report.get("skipped", [])]
    ignored = report.get("ignored_settings") or []
    out = what + "."
    if left:
        out += " Left out: " + "; ".join(left) + "."
    if ignored:
        out += " Settings not read: " + ", ".join(ignored) + "."
    return out


def _xy(p: Any):
    return (p["x"], p["y"]) if isinstance(p, dict) else (p.x, p.y)



def _shift_args(name: str, recipe: str, args: Dict[str, Any], dx: float, dy: float) -> None:
    """A recipe's arguments moved by (dx, dy): its ``position``, or its placement points.

    A sculpted glass moves by its base: its edits are along its own normals and turns of its own
    tangents, so they move with it unchanged.
    """
    if recipe == "SculptedGlass":
        base = args.get("base") or {}
        _shift_args(name, base.get("recipe", ""), base.setdefault("args", {}), dx, dy)
        return
    params = {p["name"]: p for p in sf.recipe_parameters(recipe)}
    if "position" in params:
        x, y = args.get("position") or params["position"]["default"] or [0.0, 0.0]
        args["position"] = [x + dx, y + dy]
        return
    points = [k for k in getattr(sf.recipe_class(recipe), "placement_points", ()) if args.get(k) is not None]
    if not points:
        raise EditorError(f"{name}: a {recipe} has no position to move; change its arguments instead")
    for k in points:                                 # a point, or a sequence of points
        value = args[k]
        if value and isinstance(value[0], (list, tuple)):
            args[k] = [[x + dx, y + dy] for x, y in value]
        else:
            x, y = value
            args[k] = [x + dx, y + dy]


__all__ = ["EditorError", "PALETTE_PRIMITIVES", "SceneEditor"]
