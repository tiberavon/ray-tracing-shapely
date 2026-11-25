"""
Python-specific module: block library
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
The constructors as blocks: every designed element, every primitive
===============================================================================
A constructor needs a live scene; a block's output must travel. So a
constructor block gives the element's **scene entry** (`P-SCENE-FILE`): a
designed element's recipe and arguments, a primitive's `serialize()` dict.
The element is built once, in a scratch scene, so a value its constructor
refuses is refused by the block, with the constructor's reason.

**A designed element's arguments** are typed from `recipe_parameters` by the
rules below, written out so a wrong one can be seen and corrected; a recipe
class's ``argument_types`` (name -> type) overrides them:

| Argument | Type |
|---|---|
| ``n``, ``n_*``, ``conic``, ``*_fraction`` (a float) | a number (refractive index, conic constant, share) |
| ``*_deg``, ``rotation`` (a float) | `Quantity("deg")` |
| any other float | `Quantity("mm")`: a length in the scene unit (2D étendue too) |
| ``position``, ``vertex``, and a ``Point`` named in ``placement_points`` | a position |
| ``axis``, ``n0``, and a ``Point`` that is not a placement point | a direction |
| ``points`` / ``normals`` (sequences of points) | a list of positions / of directions |
| ``int``, ``str`` | an integer, text |
| ``Optional[...]`` | the same, or null |
| a pair that is not a point (``n_sample_range``, ``extent``, ``mirror_band_deg``) | a list of numbers / lengths / angles |

**A primitive's inputs** are its `property_schema`: a point is a position, a
number with a unit is a quantity in it (``nm``, ``°``, ``μm²``), a number
whose schema has no unit is a number, except the lengths named in
``PRIMITIVE_LENGTHS``. A primitive with no schema is not a block.
===============================================================================
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from .registry import Block, Port, _REGISTRY, add_block
from .types import (
    BOOL, DIRECTION, GLASS_VERTEX, INTEGER, JSON, NUMBER, POSITION, SCENE_ENTRY, TEXT, BlockTypeError,
    Choice, ListOf, Optional_, Quantity, ValueType,
)

LENGTH = Quantity("mm")
DEGREES = Quantity("deg")

#: A primitive's numbers that are lengths, though its schema gives no unit (upstream's labels have none).
PRIMITIVE_LENGTHS = {"focalLength", "binSize"}

#: Units in a property schema, as the quantities they are.
SCHEMA_UNITS = {"nm": Quantity("nm"), "°": DEGREES, "μm²": Quantity("um^2")}


def _scalar(name: str) -> ValueType:
    if name == "n" or name.startswith("n_") or name == "conic" or name.endswith("_fraction"):
        return NUMBER
    if name.endswith("_deg") or name == "rotation":
        return DEGREES
    return LENGTH


def recipe_argument_type(cls: type, name: str, annotation: str) -> ValueType:
    """The block type of a designed element's argument (the rules of this module's table)."""
    override = getattr(cls, "argument_types", {}).get(name)
    if override is not None:
        return override
    optional = annotation.startswith("Optional[")
    inner = annotation[len("Optional["):-1] if optional else annotation
    placement = set(getattr(cls, "placement_points", ()))
    if inner == "float":
        t: ValueType = _scalar(name)
    elif inner == "int":
        t = INTEGER
    elif inner == "str":
        t = TEXT
    elif inner in ("Point", "XY"):
        if name in ("axis", "n0") or (placement and name not in placement):
            t = DIRECTION                             # a class that names its positions: the rest are directions
        else:
            t = POSITION
    elif inner == "Tuple[float, float]":
        t = POSITION if name == "position" else ListOf(_scalar(name) if name.endswith("_deg") else NUMBER)
    elif inner == "Sequence[XY]":
        t = ListOf(DIRECTION if name == "normals" else POSITION)
    else:
        t = JSON
    if name == "extent":
        t = ListOf(LENGTH)
    elif name == "mirror_band_deg":
        t = ListOf(DEGREES)
    return Optional_(t) if optional else t


def _live_default(t: ValueType, value: Any) -> Any:
    """A constructor's default as the live form: already in the unit, so a quantity's is its number."""
    if value is None:
        return None
    if isinstance(t, Optional_):
        return _live_default(t.inner, value)
    if isinstance(t, Quantity):
        return float(value)
    if isinstance(t, ListOf):
        return [_live_default(t.inner, v) for v in value]
    return t.parse(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def _check_built(entry: Dict[str, Any], who: str) -> None:
    """Build the entry once, in a scratch scene: the constructor's refusal is the block's."""
    from ..analysis import scene_file as sf  # noqa: PLC0415
    from ..core.scene import Scene  # noqa: PLC0415
    try:
        sf._build_entry(Scene(), copy.deepcopy(entry))
    except sf.SceneFileError as exc:
        raise BlockTypeError(f"{who}: {exc}") from None


def _recipe_block(recipe: str) -> Block:
    from ..analysis import scene_file as sf  # noqa: PLC0415
    cls = sf.recipe_class(recipe)
    inputs: List[Port] = []
    for p in sf.recipe_parameters(recipe):
        if p["name"] in ("name", "role"):
            continue
        t = recipe_argument_type(cls, p["name"], p["annotation"])
        default = None if p["required"] else _live_default(t, p["default"])
        doc = {POSITION: "[x, y] in mm", DIRECTION: "[dx, dy], a direction"}.get(t, "")
        inputs.append(Port(p["name"], t, required=p["required"], default=default, doc=doc))
    inputs.append(Port("name", Optional_(TEXT), required=False, doc="the element's name in the scene"))
    arg_names = [p.name for p in inputs if p.name != "name"]
    required = {p.name for p in inputs if p.required}

    def call(live: Dict[str, Any]) -> Dict[str, Any]:
        # a required argument goes in even as null (a flat face's radius); an optional one only if set
        args = {k: _json_safe(live.get(k)) for k in arg_names if k in required or live.get(k) is not None}
        entry: Dict[str, Any] = {"recipe": recipe, "args": args}
        if live.get("name"):
            entry["name"] = live["name"]
        _check_built(entry, recipe)
        return {"entry": entry}

    return Block(recipe, "recipe", inputs, [Port("entry", SCENE_ENTRY)], call,
                 doc=(cls.__doc__ or "").strip().split("\n")[0], origin=f"{cls.__module__}:{cls.__qualname__}")


def _port_name(key: str) -> str:
    return "position" if key == "" else key.replace(".", "_")


def _primitive_block(kind: str) -> Block:
    from ..analysis import scene_file as sf  # noqa: PLC0415
    from ..core.key_path import get_by_key_path, set_by_key_path  # noqa: PLC0415
    cls = sf._resolve(sf._PRIMITIVES[kind])
    schema = cls.property_schema()
    defaults = cls.serializable_defaults
    inputs: List[Port] = []
    keys: Dict[str, str] = {}
    for entry in schema:
        key, kind_ = entry["key"], entry["type"]
        if kind_ == "point":
            t: ValueType = POSITION
        elif kind_ == "array" and key == "path":
            t = ListOf(GLASS_VERTEX)
        elif kind_ == "number":
            t = SCHEMA_UNITS.get(entry.get("unit")) or (LENGTH if key in PRIMITIVE_LENGTHS else NUMBER)
        elif kind_ == "boolean":
            t = BOOL
        elif kind_ == "dropdown":
            t = Choice(list(entry.get("options", {})))
        elif kind_ == "text":
            t = TEXT
        else:
            t = JSON
        required = kind_ in ("point", "array")
        default = None
        if not required:
            default = _live_default(t, get_by_key_path(defaults, key))
        name = _port_name(key)
        keys[name] = key
        doc = entry.get("label", "") + (" [x, y] in mm" if t is POSITION else "")
        inputs.append(Port(name, t, required=required, default=default, doc=doc.strip()))
    inputs.append(Port("name", Optional_(TEXT), required=False, doc="the object's name in the scene"))

    def call(live: Dict[str, Any]) -> Dict[str, Any]:
        from ..core.scene import Scene  # noqa: PLC0415
        data: Dict[str, Any] = {}
        default_of = {p.name: p.default for p in inputs}
        for name, key in keys.items():
            value = live.get(name)
            if value is None or (value == default_of.get(name) and name in default_of):
                continue                              # a default is not written, as serialize() leaves it out
            if key == "":
                data["x"], data["y"] = value
            elif isinstance(value, tuple) and len(value) == 2:
                set_by_key_path(data, key, {"x": value[0], "y": value[1]})
            else:
                set_by_key_path(data, key, _json_safe(value))
        scene = Scene()
        obj = cls(scene, data)
        if scene.error:
            raise BlockTypeError(f"{kind}: {scene.error}")
        entry: Dict[str, Any] = {"object": obj.serialize()}
        if live.get("name"):
            entry["name"] = live["name"]
        _check_built(entry, kind)
        return {"entry": _json_safe(entry)}

    return Block(kind, "primitive", inputs, [Port("entry", SCENE_ENTRY)], call,
                 doc=(cls.__doc__ or "").strip().split("\n")[0], origin=f"{cls.__module__}:{cls.__qualname__}")


def constructor_blocks(refresh: bool = False) -> List[str]:
    """Register a block for every recipe and every primitive with a schema; their names.

    Each call adds what is new (a satellite's recipe registered since); with
    ``refresh`` the existing ones are made again.
    """
    from ..analysis import scene_file as sf  # noqa: PLC0415
    made = []
    for recipe in sf.list_recipes():
        if refresh or recipe not in _REGISTRY:
            _REGISTRY.pop(recipe, None)
            made.append(add_block(_recipe_block(recipe)).name)
    for kind in sf.list_primitives():
        cls = sf._resolve(sf._PRIMITIVES[kind])
        if not cls.property_schema():
            continue
        if refresh or kind not in _REGISTRY:
            _REGISTRY.pop(kind, None)
            made.append(add_block(_primitive_block(kind)).name)
    return made


__all__ = ["PRIMITIVE_LENGTHS", "SCHEMA_UNITS", "constructor_blocks", "recipe_argument_type"]
