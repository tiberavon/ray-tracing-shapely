"""
Python-specific module: sculpted glass -- a designed glass and the edits made to its surfaces, as one recipe
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
PYTHON-SPECIFIC MODULE: sculpted glass
===============================================================================
A designed element is built from its requirements (`KC2`), and its outline is
not edited by hand. Sculpting does edit the outline, so the edit is made a
requirement too: a `SculptedGlass` is a *base* recipe (any registered recipe
that builds a glass with spline edges, an `RRLens` say) and a list of
*edits*, each one handle moved (`first_order`):

    {"recipe": "SculptedGlass", "name": "lens",
     "args": {"base": {"recipe": "RRLens", "args": {"e1": [-1, 2], ...}},
              "edits": [{"edge": "N", "index": 26, "kind": "position", "delta": 0.001},
                        {"edge": "X", "index": 20, "kind": "normal", "delta": -0.2}]}}

The constructor builds the base, takes its outline, labels, roles and
mechanisms as they are (`KA1`, `C-LABEL-01`), and applies the edits in order
to the named spline edges' Hermite points and tangents: ``"position"`` moves
point ``index`` by ``delta`` along the glass's outward normal there (scene
units), ``"normal"`` turns its tangent by ``delta`` degrees, counter-clockwise.
An edit names its edge by the edge's functional label (``"N"``) or its index.
``handle_id`` (``"lens/N/26"``, as `first_order.Handle` writes it) is read
too; its glass part is not checked, so a renamed glass keeps its edits.

The file holds the base and the edits, not the edited outline: the shape is
rebuilt from them, so it is reproducible, and a sweep can vary an edit's
delta as any other argument (`KD8`). With no edits the glass is its base:
the same outline, labels and profile (`C-SCULPT-03`).

**Refused, with the reason, before the glass exists** (`C-SCULPT-04`): a base
that is not a registered recipe or builds no glass; an edit naming no edge,
an edge that is not a spline, a point that is not interior (an end point is
the outline's vertex, shared with the next edge), an unknown kind, a delta
that is not a finite number; and an edit list whose outline is no longer a
simple closed curve (an edge folded or crossing another). The scene is
untouched by a refusal: nothing is added to it.

`bake` turns a sculpted glass into a plain `BasePrism` through its profile
(`export_profile`, `BasePrism.from_profile`): the same outline and labels,
the edits' history gone.
===============================================================================
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional, Sequence

from ..optical_elements.prisms.base_prism import BasePrism
from .first_order import _label


class SculptError(ValueError):
    """A base or an edit a sculpted glass cannot be built from, with the reason."""


#: The instance attributes of the base not taken over: the object's own identity and records.
_NOT_TAKEN = {"_uuid", "uuid", "scene", "_construction_args", "_built_inside", "_curve_cache", "name"}


def _base_object(scene: Any, base: Dict[str, Any]) -> Any:
    from . import scene_file as sf  # noqa: PLC0415
    if not isinstance(base, dict) or "recipe" not in base:
        raise SculptError(f"base is {{'recipe': name, 'args': {{...}}}}, got {base!r}")
    name = base["recipe"]
    if name == SculptedGlass.type:
        raise SculptError("a sculpted glass's base is the designed recipe itself, not another sculpted glass: "
                          "its edits go in one list")
    try:
        cls = sf.recipe_class(name)
    except sf.SceneFileError as exc:
        raise SculptError(str(exc)) from exc
    args = sf._decode_args(cls, sf._encode(base.get("args") or {}, f"base.{name}"))
    try:
        obj = cls(scene, **args)
    except Exception as exc:                          # noqa: BLE001 -- refused by name, with the reason
        raise SculptError(f"the base {name} could not be built from its arguments: "
                          f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(obj, BasePrism) or not getattr(obj, "path", None):
        raise SculptError(f"the base {name} builds a {type(obj).__name__}, not a glass with an outline")
    return obj


def _spline_edges(glass: Any) -> Dict[int, Any]:
    from ..core.glass_spans import glass_spans  # noqa: PLC0415
    return {s.index: s for s in glass_spans(glass.path)}




def _edit_fields(k: int, edit: Any) -> Dict[str, Any]:
    if not isinstance(edit, dict):
        raise SculptError(f"edit {k}: an edit is a dict (edge, index, kind, delta), got {edit!r}")
    out = dict(edit)
    if "handle_id" in out:
        parts = str(out.pop("handle_id")).split("/")
        if len(parts) < 3:
            raise SculptError(f"edit {k}: a handle id is 'glass/edge/index', got {edit['handle_id']!r}")
        out.setdefault("edge", parts[-2])
        out.setdefault("index", parts[-1])
    missing = [f for f in ("edge", "index", "kind", "delta") if f not in out]
    if missing:
        raise SculptError(f"edit {k}: missing {', '.join(missing)}")
    try:
        out["index"] = int(out["index"])
        out["delta"] = float(out["delta"])
    except (TypeError, ValueError) as exc:
        raise SculptError(f"edit {k}: index is an integer and delta a number: {exc}") from exc
    if not math.isfinite(out["delta"]):
        raise SculptError(f"edit {k}: delta must be finite, got {out['delta']}")
    return out


def _edge_index(glass: Any, spans: Dict[int, Any], k: int, edge: Any) -> int:
    if isinstance(edge, int) or (isinstance(edge, str) and edge.isdigit()):
        index = int(edge)
        if index not in spans:
            raise SculptError(f"edit {k}: the glass has no edge {index}; edges: {sorted(spans)}")
        return index
    found = [i for i in spans if _label(glass, i) == edge]
    if not found:
        labels = sorted({_label(glass, i) for i in spans} - {""})
        raise SculptError(f"edit {k}: no edge labelled {edge!r}; labels: {', '.join(labels) or 'none'}")
    return found[0]


def _check_outline(path: List[Dict[str, Any]]) -> None:
    from shapely.geometry import Polygon  # noqa: PLC0415
    from shapely.validation import explain_validity  # noqa: PLC0415

    from ..core.glass_curves import curve_from_descriptor  # noqa: PLC0415
    from .glass_geometry import outline_coords  # noqa: PLC0415
    n = len(path)
    for i, entry in enumerate(path):
        if entry.get("curve") and not entry.get("arc"):
            nxt = path[(i + 1) % n]
            try:
                curve_from_descriptor(entry["curve"], (entry["x"], entry["y"]), (nxt["x"], nxt["y"]))
            except ValueError as exc:
                raise SculptError(f"the edits break edge {i}: {exc}") from exc
    polygon = Polygon(outline_coords(path))
    if not polygon.is_valid:
        raise SculptError(f"the edits break the outline: it is no longer a simple closed curve "
                          f"({explain_validity(polygon)})")


class SculptedGlass(BasePrism):
    """A designed glass (its base recipe) with edits to its spline edges, kept as a recipe.

    Args:
        scene: The scene it is built in (not added to it).
        base: ``{"recipe": name, "args": {...}}``, the arguments as a scene file writes them.
        edits: Each ``{"edge": label or index, "index": i, "kind": "position" | "normal",
            "delta": d}`` (or ``"handle_id"`` for edge and index), applied in order.
        name: The glass's name.

    Raises:
        SculptError: A base or an edit it cannot be built from, with the reason (see the
            module's docstring).
    """

    _supports_refinement = False
    type = 'SculptedGlass'

    def __init__(self, scene: Any, base: Dict[str, Any], edits: Sequence[Dict[str, Any]] = (),
                 name: Optional[str] = None) -> None:
        from ..core.scene_objs.glass.glass import Glass  # noqa: PLC0415
        from . import first_order as fo  # noqa: PLC0415
        original = _base_object(scene, base)
        Glass.__init__(self, scene, json_obj=None)
        own = {k: self.__dict__[k] for k in _NOT_TAKEN if k in self.__dict__}
        for k, v in original.__dict__.items():
            if k not in _NOT_TAKEN:
                self.__dict__[k] = copy.deepcopy(v)
        self.__dict__.update(own)
        self.base_recipe = base["recipe"]
        spans = _spline_edges(self)
        self.edits: List[Dict[str, Any]] = []
        for k, raw in enumerate(edits):
            edit = _edit_fields(k, raw)
            edge = _edge_index(self, spans, k, edit["edge"])
            span = spans[edge]
            if span.kind != "spline":
                raise SculptError(f"edit {k}: edge {edit['edge']!r} is a {span.kind}, not a spline: it has no "
                                  f"handles")
            handle = fo.Handle(self.name or "", edge, edit["index"], edit["kind"], _label(self, edge))
            try:
                desc = fo.edited_descriptor(self, span, handle, edit["delta"])
            except fo.FirstOrderError as exc:
                raise SculptError(f"edit {k}: {exc}") from exc
            self.path[span.path_indices[0]]["curve"] = desc
            self.edits.append({"edge": _label(self, edge) or edge, "index": handle.index,
                               "kind": handle.kind, "delta": edit["delta"]})
            spans = _spline_edges(self)               # the edited edge, for the next edit's normal
        _check_outline(self.path)
        self.__dict__.pop("_curve_cache", None)
        self.name = name if name is not None else original.name

    def bake(self, scene: Optional[Any] = None) -> BasePrism:
        """This glass as a plain `BasePrism`, through its profile: its outline and labels, its edits'
        history gone."""
        from ..optical_elements.prisms.profile_export import export_profile  # noqa: PLC0415
        profile = export_profile(self, symmetry={"kind": "free"}, physical_params={}, numerical_params={})
        baked = BasePrism.from_profile(scene or self.scene, profile, n=float(self.refIndex))
        baked.name = self.name
        return baked


__all__ = ["SculptError", "SculptedGlass"]
