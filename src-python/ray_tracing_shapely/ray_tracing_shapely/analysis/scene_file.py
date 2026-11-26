"""
Python-specific module: scene file -- a whole 2D scene as a file, designed elements as recipes
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
SCENE FILE -- save a scene, open it again, change one of its parameters
===============================================================================
A scene built in a notebook lives only as long as the notebook's kernel. This
module writes the whole scene to a file and reads it back: its settings and
every object, sources and detectors included, in the scene's order.

An object is written in one of three ways:

- **A primitive** (a mirror, a glass polygon, a beam, a detector: the objects
  the 2D engine reads from its JSON) as its own ``serialize()`` dict, under the
  type name the JavaScript simulator uses (``"Mirror"``, ``"Glass"``, ...).
- **A designed element** (a prism, a lens, a collimator, an SMS element, an
  exact curved mirror) as a **recipe**: the constructor's name and the
  arguments it was called with. Opening the file calls the constructor again,
  so the geometry is computed from the requirement every time
  ([KC2: elements are built from optical requirements, not vertices]). That is
  what lets a parameter study change ``cavity_depth`` and get the collimator
  that depth gives, rather than the old outline.
- **A part** of a designed element (an XR concentrator's primary mirrors,
  which its constructor builds as objects of their own) as a reference to the
  element and the attribute holding it. Opening the file rebuilds the element,
  then takes the part from it, so the two cannot disagree.

Every object carries its name, and names are unique where given: a study
compares runs object by object ([C-LABEL-01]).

**Each object is checked where it is written** ([KD3: assertions go where a
failure would be silent]). It is rebuilt from what the file will hold, and
the rebuilt object's ``serialize()`` is compared with the original's. An
object that does not come back the same is refused, by name: a designed
element moved or edited after it was built (``move``, ``rotate``, a changed
``refIndex``) would otherwise be saved as the element it was before the edit.
So is an argument that is not plain data, and a class neither registry knows.

The arguments a designed element was built with are recorded by the object
itself, when it is constructed (`BaseSceneObj`'s construction record), so a
scene built in any notebook can be saved without having been built through
this module.

A package outside the core adds its own designed elements with
`register_recipe`. The file has a schema version; a file of a later major
version is refused rather than misread.
===============================================================================
"""

from __future__ import annotations

import enum
import importlib
import inspect
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

#: What a scene file says it is, and the version it is written in. A reader
#: refuses another schema, and a version whose major number is not its own.
SCHEMA = "ray_tracing_shapely.scene"
VERSION = "1.1"
# 1.1: a Glass has straight and arc edges only, as upstream's (one with curved
# edges is a CurvedGlass); ground_glass is GroundGlass. Objects keep the
# JavaScript simulator's key names (emisAngle, irradMap,
# binSize, twoSided, cauchyB, defBy, notDone), and Detector's twoSided defaults
# to true, as upstream's; `max_ray_depth` is a setting. A 1.0 file still reads:
# its old key names load, with a DeprecationWarning. A 1.0 Detector that left
# two_sided out was one-sided and now reads two-sided.

#: The scene settings the file keeps: `Scene` attribute names.
SETTINGS: Tuple[str, ...] = (
    "name", "mode", "color_mode", "simulate_colors", "show_ray_arrows", "length_scale",
    "ray_mode_density", "image_mode_density", "min_brightness_exp", "max_ray_depth",
    "grid_size", "snap_to_grid",
    "grazing_angle_threshold", "grazing_polarization_ratio_threshold",
    "grazing_transmission_threshold",
)

#: The primitives: the JavaScript simulator's type names, each with the class
#: that reads its ``serialize()`` dict (``Class(scene, json_obj)``).
_PRIMITIVES: Dict[str, str] = {
    "AngleSource": "ray_tracing_shapely.core.scene_objs.light_source.angle_source:AngleSource",
    "Beam": "ray_tracing_shapely.core.scene_objs.light_source.beam:Beam",
    "Blocker": "ray_tracing_shapely.core.scene_objs.blocker.blocker:Blocker",
    "Detector": "ray_tracing_shapely.core.scene_objs.other.detector:Detector",
    "Glass": "ray_tracing_shapely.core.scene_objs.glass.glass:Glass",
    "CurvedGlass": "ray_tracing_shapely.optical_elements.curved_glass:CurvedGlass",
    "IdealLens": "ray_tracing_shapely.core.scene_objs.glass.ideal_lens:IdealLens",
    "IdealMirror": "ray_tracing_shapely.core.scene_objs.mirror.ideal_mirror:IdealMirror",
    "Mirror": "ray_tracing_shapely.core.scene_objs.mirror.mirror:Mirror",
    "Photodetector": "ray_tracing_shapely.optical_elements.sensors.photodetector:Photodetector",
    "PointSource": "ray_tracing_shapely.core.scene_objs.light_source.point_source:PointSource",
    "RaySetSource": "ray_tracing_shapely.optical_elements.sources.ray_set_source:RaySetSource",
    "SingleRay": "ray_tracing_shapely.core.scene_objs.light_source.single_ray:SingleRay",
    "SphericalLens": "ray_tracing_shapely.core.scene_objs.glass.spherical_lens:SphericalLens",
    "GroundGlass": "ray_tracing_shapely.optical_elements.ground_glass:GroundGlass",
}

#: The designed elements: a recipe name (the class's ``type``) and its
#: constructor, ``Class(scene, **args)``.
_RECIPES: Dict[str, str] = {
    "CircularArcMirror": "ray_tracing_shapely.optical_elements.mirrors.conic:CircularArcMirror",
    "ConicMirror": "ray_tracing_shapely.optical_elements.mirrors.conic:ConicMirror",
    "DTIRCPrism": "ray_tracing_shapely.optical_elements.prisms.dtirc:DTIRCPrism",
    "EquilateralPrism": "ray_tracing_shapely.optical_elements.prisms.equilateral:EquilateralPrism",
    "FresnelLens": "ray_tracing_shapely.optical_elements.lenses.fresnel:FresnelLens",
    "RRLens": "ray_tracing_shapely.optical_elements.prisms.rr_lens:RRLens",
    "RXConcentrator": "ray_tracing_shapely.optical_elements.prisms.rx_concentrator:RXConcentrator",
    "RXIOptic": "ray_tracing_shapely.optical_elements.prisms.rxi:RXIOptic",
    "RXIOpticDirect": "ray_tracing_shapely.optical_elements.prisms.rxi_direct:RXIOpticDirect",
    "SculptedGlass": "ray_tracing_shapely.analysis.sculpted_glass:SculptedGlass",
    "RefractometerPrism": "ray_tracing_shapely.optical_elements.prisms.refractometer:RefractometerPrism",
    "RightAnglePrism": "ray_tracing_shapely.optical_elements.prisms.right_angle:RightAnglePrism",
    "SingletLens": "ray_tracing_shapely.optical_elements.lenses.singlet:SingletLens",
    "SplineMirror": "ray_tracing_shapely.optical_elements.mirrors.spline:SplineMirror",
    "TIRCollimator": "ray_tracing_shapely.optical_elements.lenses.tir_collimator:TIRCollimator",
    "XRConcentrator": "ray_tracing_shapely.optical_elements.prisms.xr_concentrator:XRConcentrator",
}

#: The enums a recipe argument may hold, by the name the file writes.
_ENUMS: Dict[str, str] = {
    "Role": "ray_tracing_shapely.optical_elements.roles:Role",
    "Mechanism": "ray_tracing_shapely.optical_elements.roles:Mechanism",
}


class SceneFileError(ValueError):
    """A scene cannot be written or read as a scene file: the message names the object and why."""


# ---------------------------------------------------------------------------
# The registries
# ---------------------------------------------------------------------------

def _resolve(path: str) -> Any:
    module, _, name = path.partition(":")
    target: Any = importlib.import_module(module)
    for part in name.split("."):
        target = getattr(target, part)
    return target


def register_recipe(name: str, path: str) -> None:
    """Add a designed element a scene file can hold, by its constructor's import path.

    The class is imported when a file names it, not here, so registering one
    costs nothing.

    Args:
        name: The recipe's name in the file: the class's ``type``.
        path: ``"package.module:Class"``; ``Class(scene, **args)`` builds it.

    Raises:
        ValueError: The name is a primitive's, or already a different recipe's.
    """
    if name in _PRIMITIVES:
        raise ValueError(f"{name!r} is a primitive's type name, not a recipe's")
    if _RECIPES.get(name, path) != path:
        raise ValueError(f"recipe {name!r} is already registered as {_RECIPES[name]!r}")
    _RECIPES[name] = path


#: Recipe names a file may still hold, each the current name it reads as; not
#: listed by `list_recipes`. ``ArcMirror`` is the JavaScript simulator's
#: three-point mirror's type name, so this package's circle mirror left it.
_RECIPE_ALIASES: Dict[str, str] = {"ArcMirror": "CircularArcMirror"}


def list_recipes() -> List[str]:
    """The names of the designed elements a scene file can hold, sorted."""
    return sorted(_RECIPES)


def list_primitives() -> List[str]:
    """The type names of the primitives a scene file can hold, sorted."""
    return sorted(_PRIMITIVES)


def recipe_class(name: str) -> type:
    """The constructor a recipe names.

    Raises:
        SceneFileError: No such recipe; the message lists those that exist.
    """
    name = _RECIPE_ALIASES.get(name, name)
    if name not in _RECIPES:
        raise SceneFileError(f"no recipe {name!r}; recipes: {', '.join(list_recipes())}")
    return _resolve(_RECIPES[name])


def recipe_parameters(name: str) -> List[Dict[str, Any]]:
    """A recipe's parameters, in the constructor's order, as a form would ask them.

    Args:
        name: A recipe's name (`list_recipes`).

    Returns:
        One dict per parameter: ``name``; ``annotation`` (the constructor's,
        as text, or None); ``required`` (no default); ``default`` (as the file
        writes it, or None). Lengths are in the scene's length unit, angles in
        degrees where the name ends ``_deg``.
    """
    cls = recipe_class(name)
    out: List[Dict[str, Any]] = []
    for pname, p in list(inspect.signature(cls.__init__).parameters.items())[2:]:
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        required = p.default is inspect.Parameter.empty
        annotation = None if p.annotation is inspect.Parameter.empty else str(p.annotation)
        out.append({
            "name": pname,
            "annotation": annotation,
            "required": required,
            "default": None if required else _encode(p.default, f"{name}.{pname}"),
        })
    return out


# ---------------------------------------------------------------------------
# Values: a recipe's arguments as JSON, and back
# ---------------------------------------------------------------------------

def _encode(value: Any, where: str) -> Any:
    """A constructor argument as JSON: numbers, strings, lists, dicts; a point as
    ``{"$point": [x, y]}``; a role or mechanism as ``{"$enum": "Role", "value": ...}``."""
    from ..core.geometry import Point  # noqa: PLC0415

    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, enum.Enum):
        kind = type(value).__name__
        if kind not in _ENUMS:
            raise SceneFileError(f"{where}: the enum {kind} cannot be written; known: {', '.join(_ENUMS)}")
        return {"$enum": kind, "value": value.value}
    if isinstance(value, Point):
        return {"$point": [float(value.x), float(value.y)]}
    if isinstance(value, (int, float)):
        return value
    if hasattr(value, "tolist") and callable(value.tolist):   # a numpy array or scalar
        return _encode(value.tolist(), where)
    if isinstance(value, (list, tuple)):
        return [_encode(v, f"{where}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return {k: _encode(v, f"{where}.{k}") for k, v in value.items()}
    raise SceneFileError(f"{where}: a {type(value).__name__} is not plain data, and cannot be written")


def _decode(value: Any, *, as_tuple: bool = False) -> Any:
    """`_encode`'s inverse. A list becomes a tuple, at the top and inside, when the
    parameter takes tuples (its default is one, or its annotation names one)."""
    from ..core.geometry import Point  # noqa: PLC0415

    if isinstance(value, dict):
        if set(value) == {"$point"}:
            x, y = value["$point"]
            return Point(x, y)
        if set(value) == {"$enum", "value"}:
            if value["$enum"] not in _ENUMS:
                raise SceneFileError(f"unknown enum {value['$enum']!r}; known: {', '.join(_ENUMS)}")
            return _resolve(_ENUMS[value["$enum"]])(value["value"])
        return {k: _decode(v, as_tuple=as_tuple) for k, v in value.items()}
    if isinstance(value, list):
        items = [_decode(v, as_tuple=as_tuple) for v in value]
        return tuple(items) if as_tuple else items
    return value


def _takes_tuples(parameter: Optional[inspect.Parameter]) -> bool:
    if parameter is None:
        return False
    if isinstance(parameter.default, tuple):
        return True
    annotation = str(parameter.annotation)
    return "Tuple" in annotation or "tuple" in annotation or "Point" in annotation


def _decode_args(cls: type, args: Dict[str, Any]) -> Dict[str, Any]:
    params = inspect.signature(cls.__init__).parameters
    return {k: _decode(v, as_tuple=_takes_tuples(params.get(k))) for k, v in args.items()}


# ---------------------------------------------------------------------------
# One object: written, rebuilt, compared
# ---------------------------------------------------------------------------

def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, default=str)


def _primitive_type(obj: Any) -> Optional[str]:
    t = getattr(type(obj), "type", "")
    if t in _PRIMITIVES and _resolve(_PRIMITIVES[t]) is type(obj):
        return t
    return None


def _recipe_name(obj: Any) -> Optional[str]:
    t = getattr(type(obj), "type", "")
    if t in _RECIPES and _resolve(_RECIPES[t]) is type(obj):
        return t
    return None


def _edge_labels(obj: Any) -> Optional[Dict[str, List[str]]]:
    """An object's edge labels as JSON, or None when it has none set."""
    labels = obj.__dict__.get("_edge_labels")
    if not labels:
        return None
    return {str(k): [str(v[0]), str(v[1])] for k, v in sorted(labels.items())}


def _role(obj: Any) -> Optional[str]:
    role = getattr(obj, "_role", None)
    return None if role is None else str(role.value)


def _apply_meta(obj: Any, entry: Dict[str, Any]) -> None:
    if "name" in entry:
        obj.name = entry["name"]
    if entry.get("role") is not None:
        obj.role = _resolve(_ENUMS["Role"])(entry["role"])
    if entry.get("edge_labels") is not None:
        obj.edge_labels = {int(k): (v[0], v[1]) for k, v in entry["edge_labels"].items()}


def _build_entry(scene: Any, entry: Dict[str, Any]) -> Any:
    """One top-level entry built in `scene` (not added to it)."""
    if "object" in entry:
        data = entry["object"]
        t = data.get("type")
        if t not in _PRIMITIVES:
            raise SceneFileError(f"{entry.get('name')!r}: no primitive type {t!r}; "
                                 f"primitives: {', '.join(list_primitives())}")
        scene.error = None
        obj = _resolve(_PRIMITIVES[t])(scene, data)
        if scene.error:
            raise SceneFileError(f"{entry.get('name')!r}: {scene.error}")
    elif "recipe" in entry:
        cls = recipe_class(entry["recipe"])
        try:
            obj = cls(scene, **_decode_args(cls, entry.get("args", {})))
        except Exception as exc:                          # noqa: BLE001 -- refused by name, with the reason
            raise SceneFileError(f"{entry.get('name')!r}: {entry['recipe']} could not be built from its "
                                 f"arguments: {type(exc).__name__}: {exc}") from exc
    else:
        raise SceneFileError(f"{entry.get('name')!r}: an entry needs 'object', 'recipe' or 'part_of'")
    _apply_meta(obj, entry)
    return obj


def _find_part(owner: Any, part: Any) -> Optional[Dict[str, Any]]:
    """Where `owner` keeps `part`: ``{"attribute": a}`` or ``{"attribute": a, "index": i}``."""
    for attr, value in vars(owner).items():
        if attr == "scene":
            continue
        if value is part:
            return {"attribute": attr}
        if isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                if v is part:
                    return {"attribute": attr, "index": i}
    return None


def _take_part(owner: Any, entry: Dict[str, Any]) -> Any:
    value = getattr(owner, entry["attribute"], None)
    if "index" in entry:
        try:
            value = value[entry["index"]]
        except (TypeError, IndexError):
            value = None
    if value is None:
        raise SceneFileError(f"{entry.get('name')!r}: its owner has no {entry['attribute']}"
                             f"{'[%d]' % entry['index'] if 'index' in entry else ''}")
    return value


def _describe(obj: Any, label: str) -> Dict[str, Any]:
    """A top-level entry for `obj` (a primitive or a recipe), without the check."""
    entry: Dict[str, Any] = {}
    if obj.name is not None:
        entry["name"] = obj.name
    recipe = _recipe_name(obj)
    if recipe is not None:
        if obj._construction_args is None:
            raise SceneFileError(f"{label} ({recipe}): its constructor's arguments were not recorded")
        entry["recipe"] = recipe
        entry["args"] = _encode(obj._construction_args, f"{label}.{recipe}")
    elif _primitive_type(obj) is not None:
        entry["object"] = json.loads(_canonical(obj.serialize()))
    else:
        raise SceneFileError(
            f"{label}: {type(obj).__name__} is neither a primitive nor a registered recipe; "
            f"a designed element from another package is added with register_recipe")
    if _role(obj) is not None:
        entry["role"] = _role(obj)
    if _edge_labels(obj) is not None:
        entry["edge_labels"] = _edge_labels(obj)
    return entry


def _check_same(original: Any, rebuilt: Any, label: str) -> None:
    """Refuse an object that its entry does not rebuild the same."""
    a, b = original.serialize(), rebuilt.serialize()
    if _canonical(a) != _canonical(b):
        keys = sorted(k for k in set(a) | set(b) if _canonical(a.get(k)) != _canonical(b.get(k)))
        how = ("it was changed after it was built (moved, rotated or edited), and its recipe "
               "builds it as it was; rebuild it with the new arguments instead"
               if _recipe_name(original) else "its serialize() does not rebuild it")
        raise SceneFileError(f"{label} ({type(original).__name__}) would not come back the same: "
                             f"{how}; differs in {', '.join(keys)}")
    if _edge_labels(original) != _edge_labels(rebuilt) and _edge_labels(original) is not None:
        raise SceneFileError(f"{label}: its edge labels would not come back the same")


# ---------------------------------------------------------------------------
# The scene
# ---------------------------------------------------------------------------

def _label(obj: Any, index: int) -> str:
    return repr(obj.name) if obj.name else f"object {index} ({type(obj).__name__}, unnamed)"


def scene_to_dict(scene: Any) -> Dict[str, Any]:
    """Describe a scene as a scene file's content, every object checked.

    Args:
        scene: The live `Scene`.

    Returns:
        ``{"schema", "version", "settings", "objects"}``. ``objects`` lists the
        scene's objects in order; each is ``{"name"?, "object": {...}}`` for a
        primitive, ``{"name"?, "recipe": ..., "args": {...}}`` for a designed
        element, or ``{"name"?, "part_of": i, "attribute": ..., "index"?}``
        for a part of the element at entry ``i``. An element that is in the
        scene only through its parts is an entry too, with ``"in_scene": false``.
        ``role`` and ``edge_labels`` are written where they were set.

    Raises:
        SceneFileError: Two objects share a name, or an object cannot be
            written or would not come back the same; the message names it.
    """
    from ..core.scene import Scene  # noqa: PLC0415

    names = [o.name for o in scene.objs if o.name]
    shared = sorted({n for n in names if names.count(n) > 1})
    if shared:
        raise SceneFileError(f"names must be unique (C-LABEL-01); shared: {', '.join(shared)}")

    order: List[Any] = list(scene.objs)
    in_scene = {id(o) for o in order}
    # An element the scene holds only through its parts is written too, after the scene's objects.
    i = 0
    while i < len(order):
        owner = order[i]._built_inside
        if owner is not None and not any(owner is o for o in order):
            order.append(owner)
        i += 1
    index_of = {id(o): k for k, o in enumerate(order)}

    entries: List[Dict[str, Any]] = []
    for k, obj in enumerate(order):
        label = _label(obj, k)
        owner = obj._built_inside
        if owner is not None:
            where = _find_part(owner, obj)
            if where is None:
                raise SceneFileError(f"{label} was built inside {type(owner).__name__}, which does not "
                                     f"keep it in an attribute; it cannot be rebuilt from its owner")
            entry: Dict[str, Any] = {"part_of": index_of[id(owner)], **where}
            if obj.name is not None:
                entry = {"name": obj.name, **entry}
            if _role(obj) is not None:
                entry["role"] = _role(obj)
            if _edge_labels(obj) is not None:
                entry["edge_labels"] = _edge_labels(obj)
        else:
            entry = _describe(obj, label)
        if id(obj) not in in_scene:
            entry["in_scene"] = False
        entries.append(entry)

    data = {
        "schema": SCHEMA,
        "version": VERSION,
        "settings": {k: _scene_setting(scene, k) for k in SETTINGS},
        "objects": entries,
    }

    # The check: every object rebuilt from what the file holds, and compared.
    rebuilt = _build_objects(Scene(), json.loads(_canonical(entries)))
    for k, (obj, again) in enumerate(zip(order, rebuilt)):
        _check_same(obj, again, _label(obj, k))
    return data


def _scene_setting(scene: Any, key: str) -> Any:
    if key == "min_brightness_exp":
        return scene._min_brightness_exp
    if key == "max_ray_depth":       # JSON has no infinity: no limit is null
        depth = scene.max_ray_depth
        return None if depth == float("inf") else depth
    return getattr(scene, key)


def _build_objects(scene: Any, entries: List[Dict[str, Any]]) -> List[Any]:
    """Every entry built in `scene`, in order: top-level entries first, then parts."""
    built: List[Any] = [None] * len(entries)
    for k, entry in enumerate(entries):
        if "part_of" not in entry:
            built[k] = _build_entry(scene, entry)
    for k, entry in enumerate(entries):
        if "part_of" in entry:
            owner_index = entry["part_of"]
            if not (isinstance(owner_index, int) and 0 <= owner_index < len(entries)) \
                    or "part_of" in entries[owner_index]:
                raise SceneFileError(f"{entry.get('name')!r}: part_of {owner_index!r} is not an element's entry")
            built[k] = _take_part(built[owner_index], entry)
            _apply_meta(built[k], entry)
    return built


def _from_1_0(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A 1.0 file's entries, read as they meant. Since 1.1: a Detector is
    two-sided by default (one left its side out was one-sided in 1.0); a Glass
    with a curved edge is a CurvedGlass; a ground glass is a GroundGlass."""
    out = []
    for entry in entries:
        data = entry.get("object")
        if data and data.get("type") == "Detector" and not ({"two_sided", "twoSided"} & set(data)):
            entry = {**entry, "object": {**data, "twoSided": False}}
        elif data and data.get("type") == "Glass" and any(
                isinstance(p, dict) and p.get("curve") for p in data.get("path") or []):
            entry = {**entry, "object": {**data, "type": "CurvedGlass"}}
        elif data and data.get("type") == "ground_glass":
            entry = {**entry, "object": {**data, "type": "GroundGlass"}}
        out.append(entry)
    return out


def scene_from_dict(data: Dict[str, Any]) -> Any:
    """Build a scene from a scene file's content.

    Args:
        data: What `scene_to_dict` returned, or a file's JSON.

    Returns:
        A new `Scene` with the settings and the objects, in the file's order;
        an element written only for its parts is built and not added.

    Raises:
        SceneFileError: Another schema, a later major version, an unknown type
            or recipe, or an object that cannot be built; the message names it.
    """
    from ..core.scene import Scene  # noqa: PLC0415

    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise SceneFileError(f"not a scene file: its schema is {data.get('schema') if isinstance(data, dict) else None!r}, "
                             f"not {SCHEMA!r}")
    version = str(data.get("version", ""))
    if version.split(".")[0] != VERSION.split(".")[0]:
        raise SceneFileError(f"scene file version {version!r}; this package reads version "
                             f"{VERSION.split('.')[0]}.x")
    scene = Scene()
    for key, value in data.get("settings", {}).items():
        if key not in SETTINGS:
            raise SceneFileError(f"unknown scene setting {key!r}; settings: {', '.join(SETTINGS)}")
        setattr(scene, key, value)
    entries = data.get("objects", [])
    if version.split(".")[:2] == ["1", "0"]:
        entries = _from_1_0(entries)
    names = [e["name"] for e in entries if e.get("name")]
    shared = sorted({n for n in names if names.count(n) > 1})
    if shared:
        raise SceneFileError(f"names must be unique (C-LABEL-01); shared: {', '.join(shared)}")
    built = _build_objects(scene, entries)
    # A constructor may add objects of its own to the scene (an RXI adds its
    # mirror); the file's order and membership decide instead.
    scene.objs.clear()
    scene.optical_objs.clear()
    for entry, obj in zip(entries, built):
        if entry.get("in_scene", True):
            scene.add_object(obj)
    return scene


def assemble(entries: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> Any:
    """A scene from its entries, in order: what a scene file of them would give.

    Args:
        entries: Scene-file entries (``{"name"?, "object": ...}``,
            ``{"name"?, "recipe": ..., "args": ...}``), as a constructor block
            or `RayfileSlice.scene_entry` gives them.
        settings: Scene settings (`SETTINGS`), or None for the defaults.

    Raises:
        SceneFileError: As `scene_from_dict`: a name shared (C-LABEL-01), an
            unknown setting, or an entry that cannot be built.
    """
    return scene_from_dict({"schema": SCHEMA, "version": VERSION, "settings": dict(settings or {}),
                            "objects": list(entries)})


def save_scene(scene: Any, path: Union[str, Path]) -> Path:
    """Write a scene to a file, whole or not at all.

    Args:
        scene: The live `Scene`.
        path: Where to write it; ``.scene.json`` is the convention.

    Returns:
        The path written.

    Raises:
        SceneFileError: As `scene_to_dict`; nothing is written.
    """
    path = Path(path)
    text = json.dumps(scene_to_dict(scene), indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def load_scene(path: Union[str, Path]) -> Any:
    """Read a scene file.

    Args:
        path: A file `save_scene` wrote.

    Returns:
        The `Scene`.

    Raises:
        SceneFileError: As `scene_from_dict`, or the file is not JSON.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SceneFileError(f"{path}: not JSON: {exc}") from exc
    return scene_from_dict(data)


# =============================================================================
# The JavaScript simulator's own scene files (phydemo.app/ray-optics)
# =============================================================================

#: The web simulator's scene format version this reads and writes.
WEB_VERSION = 5

#: The web simulator's types this package has, each read by the class that
#: reads its `serialize()` dict: the same names and, since the realignment,
#: the same keys.
WEB_TYPES: Tuple[str, ...] = (
    "AngleSource", "Beam", "Blocker", "Detector", "Glass", "IdealLens", "IdealMirror",
    "Mirror", "PointSource", "SingleRay", "SphericalLens",
)

#: The web scene's settings this package keeps, and the `Scene` attribute each is.
WEB_SETTINGS: Dict[str, str] = {
    "name": "name", "mode": "mode", "rayModeDensity": "ray_mode_density",
    "imageModeDensity": "image_mode_density", "colorMode": "color_mode",
    "simulateColors": "simulate_colors", "showRayArrows": "show_ray_arrows",
    "lengthScale": "length_scale", "maxRayDepth": "max_ray_depth",
    "gridSize": "grid_size", "snapToGrid": "snap_to_grid",
}

#: Keys of a web scene that describe its view or its editor, not its optics:
#: read by nothing here, and not reported.
WEB_VIEW_KEYS = {"version", "objs", "width", "height", "origin", "scale", "showGrid", "lockObjs",
                 "theme", "observer", "importedFromBeta"}


def scene_from_web_dict(data: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
    """A scene from the web simulator's scene file content.

    Every object of a type this package has (`WEB_TYPES`) is built from its
    entry as it stands, and named by its type and a number (the web format has
    no names; `C-LABEL-01` wants them). Anything else is left out and listed.

    Args:
        data: The parsed JSON of a scene the web simulator saved (version 5).

    Returns:
        ``(scene, report)``: ``report["skipped"]`` lists ``{"index", "type",
        "reason"}`` for each object left out, ``report["ignored_settings"]``
        the settings with no counterpart here.

    Raises:
        SceneFileError: Not a web scene, or another version (open and save it
            in the web simulator, which updates old files, then read it again).
    """
    from ..core.scene import Scene  # noqa: PLC0415

    if not isinstance(data, dict) or "objs" not in data:
        raise SceneFileError("not a web simulator scene: it has no 'objs'")
    version = data.get("version")
    if version != WEB_VERSION:
        raise SceneFileError(f"web scene version {version!r}; this reads version {WEB_VERSION}. Open and save "
                             "it in the web simulator, which updates older files, then read it again")
    scene = Scene()
    report: Dict[str, Any] = {"skipped": [], "ignored_settings": []}
    for key, value in data.items():
        if key in WEB_SETTINGS:
            setattr(scene, WEB_SETTINGS[key], value)
        elif key not in WEB_VIEW_KEYS and value not in ({}, [], None):
            report["ignored_settings"].append(key)
    counts: Dict[str, int] = {}
    for index, entry in enumerate(data["objs"]):
        kind = entry.get("type") if isinstance(entry, dict) else None
        if kind not in WEB_TYPES:
            report["skipped"].append({"index": index, "type": kind, "reason": "not a type this package has"})
            continue
        scene.error = None
        obj = _resolve(_PRIMITIVES[kind])(scene, {k: v for k, v in entry.items()})
        if scene.error:
            report["skipped"].append({"index": index, "type": kind, "reason": scene.error})
            scene.error = None
            continue
        counts[kind] = counts.get(kind, 0) + 1
        obj.name = f"{kind}{counts[kind]}"
        scene.add_object(obj)
    return scene, report


def load_web_scene(path: Union[str, Path]) -> Tuple[Any, Dict[str, Any]]:
    """Read a scene file the web simulator saved: ``(scene, report)`` (`scene_from_web_dict`)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SceneFileError(f"{path}: not JSON: {exc}") from exc
    return scene_from_web_dict(data)


def is_web_scene(data: Any) -> bool:
    """Whether parsed JSON is the web simulator's format rather than this package's."""
    return isinstance(data, dict) and "objs" in data and data.get("schema") != SCHEMA


def web_scene_dict(scene: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The scene in the web simulator's format, to open at phydemo.app/ray-optics.

    A primitive of a web type is written as its `serialize()` dict; a designed
    element whose outline is straight edges and arcs, as the `Glass` it traces
    as (what it was built from is not kept: the web format has no recipes).
    Anything else (a curved edge, a type the web simulator lacks) is left out
    and listed.

    Returns:
        ``(data, report)``: ``report["skipped"]`` lists ``{"name", "type", "reason"}``.
    """
    from ..core.scene_objs.glass.glass import Glass  # noqa: PLC0415

    data: Dict[str, Any] = {"version": WEB_VERSION}
    for key, attr in WEB_SETTINGS.items():
        value = getattr(scene, attr, None)
        if key == "maxRayDepth" and value == float("inf"):
            continue
        if value is not None and key != "name":
            data[key] = value
    if getattr(scene, "name", None):
        data["name"] = scene.name
    objs: List[Dict[str, Any]] = []
    report: Dict[str, Any] = {"skipped": []}
    glass_defaults = Glass.serializable_defaults
    for obj in scene.objs:
        kind = getattr(type(obj), "type", "")
        if kind in WEB_TYPES and _primitive_type(obj) == kind:
            objs.append(json.loads(json.dumps(obj.serialize())))
        elif isinstance(obj, Glass) and obj.path and not any(p.get("curve") for p in obj.path):
            entry: Dict[str, Any] = {"type": "Glass",
                                     "path": [{"x": p["x"], "y": p["y"], "arc": bool(p.get("arc"))} for p in obj.path]}
            for key in ("refIndex", "cauchyB", "partialReflect"):
                value = getattr(obj, key, glass_defaults[key])
                if value != glass_defaults[key]:
                    entry[key] = value
            objs.append(entry)
        else:
            reason = ("it has curved edges, which the web simulator's Glass does not"
                      if isinstance(obj, Glass) else "the web simulator has no such type")
            report["skipped"].append({"name": obj.name, "type": kind, "reason": reason})
    data["objs"] = objs
    return data, report


def save_web_scene(scene: Any, path: Union[str, Path]) -> Dict[str, Any]:
    """Write the scene in the web simulator's format (`web_scene_dict`); the report."""
    data, report = web_scene_dict(scene)
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return report


__all__ = [
    "SCHEMA", "SETTINGS", "VERSION", "SceneFileError",
    "WEB_SETTINGS", "WEB_TYPES", "WEB_VERSION",
    "assemble", "is_web_scene", "list_primitives", "list_recipes", "load_scene", "load_web_scene",
    "recipe_class", "recipe_parameters", "register_recipe", "save_scene", "save_web_scene",
    "scene_from_dict", "scene_from_web_dict", "scene_to_dict", "web_scene_dict",
]
