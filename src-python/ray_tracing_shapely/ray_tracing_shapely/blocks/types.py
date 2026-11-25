"""
Python-specific module: block value types
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
The value types a block's inputs and outputs have: what a wire carries
===============================================================================
Each type has two forms:
- a **JSON form**, what a graph document, an agent's call or a flow's answer
  holds (a quantity is text with its unit, "7 mm"; a scene is a scene file's
  content or its path);
- a **live form**, what the block's function receives in the kernel (a
  quantity as a float in the type's unit; a scene as a `Scene`).

``parse`` takes the JSON form (or a live value, which passes) to the live
form, and refuses anything else with the reason, as a `BlockTypeError`;
``format`` goes back. ``accepts`` says whether an output of one type may feed
an input of another: the rule a graph editor checks a wire by.
``describe`` is the type as JSON, and `from_description` reads it back, so a
catalogue of blocks is itself JSON.

The vocabulary is closed in the core distribution: adding a type is a
decision, written here. A satellite adds its own by `register_type`.

**Units.** A physical magnitude is a `Quantity` with a unit: the block
surface is where a unit error is stopped (`KC4`), and the string parsing is
`P-QUANTITY-PARSING`'s. Scene coordinates stay plain numbers in the scene
unit (`Position`, `Direction`), as everywhere in the core; the scene unit is
the millimetre (`SCENE_UNIT`), `PhysicalScene`'s default and every designed
element's.
===============================================================================
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

#: The unit scene coordinates and lengths are in.
SCENE_UNIT = "mm"


class BlockTypeError(ValueError):
    """A value refused by its type: what was given, what was expected."""


def _refuse(where: str, expected: str, got: Any) -> BlockTypeError:
    shown = repr(got)
    if len(shown) > 80:
        shown = shown[:77] + "..."
    return BlockTypeError(f"{where}: expected {expected}, got {shown}")


class ValueType:
    """A type a block's port has."""

    name = "value"

    def parse(self, value: Any, where: str = "value") -> Any:
        """The JSON form (or a live value) as the live form; `BlockTypeError` if neither."""
        raise NotImplementedError

    def format(self, live: Any) -> Any:
        """The live form as the JSON form."""
        return live

    def accepts(self, source: "ValueType") -> bool:
        """Whether an output of type `source` may feed an input of this type."""
        return source.describe() == self.describe()

    def describe(self) -> Dict[str, Any]:
        """The type as JSON."""
        return {"type": self.name}

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, ValueType) and other.describe() == self.describe()

    def __hash__(self) -> int:
        return hash(repr(sorted(self.describe().items(), key=str)))

    def __repr__(self) -> str:
        d = self.describe()
        rest = ", ".join(f"{k}={v!r}" for k, v in d.items() if k != "type")
        return f"{d['type']}({rest})" if rest else d["type"]


# --- scalars --------------------------------------------------------------------

class _Number(ValueType):
    name = "number"

    def parse(self, value, where="value"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise _refuse(where, "a finite number", value)
        return float(value)

    def accepts(self, source):
        return source.name in ("number", "integer")


class _Integer(ValueType):
    name = "integer"

    def parse(self, value, where="value"):
        if isinstance(value, bool) or not (isinstance(value, int) or (isinstance(value, float) and value.is_integer())):
            raise _refuse(where, "a whole number", value)
        return int(value)


class _Bool(ValueType):
    name = "bool"

    def parse(self, value, where="value"):
        if not isinstance(value, bool):
            raise _refuse(where, "true or false", value)
        return value


class _Text(ValueType):
    name = "text"

    def parse(self, value, where="value"):
        if not isinstance(value, str):
            raise _refuse(where, "text", value)
        return value


NUMBER, INTEGER, BOOL, TEXT = _Number(), _Integer(), _Bool(), _Text()


class Choice(ValueType):
    """One of a fixed set of values (text or numbers)."""

    name = "choice"

    def __init__(self, options: Sequence[Any]) -> None:
        self.options = tuple(options)

    def parse(self, value, where="value"):
        if value not in self.options:
            raise _refuse(where, f"one of {list(self.options)}", value)
        return value

    def accepts(self, source):
        return isinstance(source, Choice) and set(source.options) <= set(self.options)

    def describe(self):
        return {"type": self.name, "options": list(self.options)}


class Quantity(ValueType):
    """A physical magnitude with its unit: "7 mm", "30 mW/cm^2".

    The live form is a float in `unit`, what the library's functions take; a
    `pint.Quantity` given live is converted. A bare number is refused: it says
    nothing of its unit. A quantity is checked as the eye-safety layer checks
    one (`parse_radiometric_quantity`, `ensure_radiometric_quantity`): its
    dimensionality, then its kind, since pint counts radian and steradian
    dimensionless and so cannot tell an irradiance from a radiance, or an
    angle from a pure number, by dimensionality alone.
    """

    name = "quantity"

    def __init__(self, unit: str) -> None:
        self.unit = unit

    def _kind(self) -> str:
        """The unit's kind: its base units, radian and steradian kept, as the eye-safety layer
        checks them (`units._base_units_match`). An irradiance and a radiance, or an angle and
        a pure number, share a pint dimensionality but not a kind."""
        from ..optical_elements.units import ureg  # noqa: PLC0415
        return str(ureg.Quantity(1.0, self.unit).to_base_units().units)

    def parse(self, value, where="value"):
        from ..optical_elements.units import (  # noqa: PLC0415
            ensure_radiometric_quantity, parse_radiometric_quantity, ureg,
        )
        if isinstance(value, ureg.Quantity):
            try:
                q = ensure_radiometric_quantity(value, self.unit, name=where)   # dimensionality, then the kind
            except ValueError as exc:
                raise BlockTypeError(f"{where}: {exc}") from None
        elif isinstance(value, str):
            try:
                q = parse_radiometric_quantity(value, self.unit)   # dimensionality, then the kind
            except ValueError as exc:
                raise BlockTypeError(f"{where}: {exc}") from None
        else:
            raise _refuse(where, f"a quantity with its unit, as text (e.g. \"1 {self.unit}\")", value)
        magnitude = float(q.to(self.unit).magnitude)
        if not math.isfinite(magnitude):
            raise _refuse(where, "a finite quantity", value)
        return magnitude

    def format(self, live):
        text = repr(float(live))                      # the shortest text that reads back the same float
        return f"{text[:-2] if text.endswith('.0') else text} {self.unit}"

    def accepts(self, source):
        return isinstance(source, Quantity) and source._kind() == self._kind()

    def describe(self):
        return {"type": self.name, "unit": self.unit, "kind": self._kind()}


# --- geometry, in the scene unit -------------------------------------------------

def _pair(value, where, what):
    if isinstance(value, dict) and set(value) >= {"x", "y"}:
        value = [value["x"], value["y"]]
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value)):
        raise _refuse(where, what, value)
    return (float(value[0]), float(value[1]))


class _Position(ValueType):
    name = "position"

    def parse(self, value, where="value"):
        return _pair(value, where, f"a position [x, y] in {SCENE_UNIT}")

    def format(self, live):
        return [live[0], live[1]]


class _Direction(ValueType):
    name = "direction"

    def parse(self, value, where="value"):
        x, y = _pair(value, where, "a direction [dx, dy]")
        if x == 0 and y == 0:
            raise _refuse(where, "a direction that is not zero", value)
        return (x, y)

    def format(self, live):
        return [live[0], live[1]]


POSITION, DIRECTION = _Position(), _Direction()


# --- containers --------------------------------------------------------------------

class Optional_(ValueType):
    """`inner`, or null."""

    name = "optional"

    def __init__(self, inner: ValueType) -> None:
        self.inner = inner

    def parse(self, value, where="value"):
        return None if value is None else self.inner.parse(value, where)

    def format(self, live):
        return None if live is None else self.inner.format(live)

    def accepts(self, source):
        if isinstance(source, Optional_):
            return self.inner.accepts(source.inner)
        return self.inner.accepts(source)

    def describe(self):
        return {"type": self.name, "of": self.inner.describe()}


class ListOf(ValueType):
    """A list of `inner`."""

    name = "list"

    def __init__(self, inner: ValueType) -> None:
        self.inner = inner

    def parse(self, value, where="value"):
        if not isinstance(value, (list, tuple)):
            raise _refuse(where, f"a list of {self.inner!r}", value)
        return [self.inner.parse(v, f"{where}[{i}]") for i, v in enumerate(value)]

    def format(self, live):
        return [self.inner.format(v) for v in live]

    def accepts(self, source):
        return isinstance(source, ListOf) and self.inner.accepts(source.inner)

    def describe(self):
        return {"type": self.name, "of": self.inner.describe()}


class _Json(ValueType):
    """Any JSON value: an argument no other type describes yet. Shown as such in the
    catalogue, so what is still untyped is visible, not hidden."""

    name = "json"

    def parse(self, value, where="value"):
        import json  # noqa: PLC0415
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            raise _refuse(where, "a JSON value", value) from None
        return copy.deepcopy(value)

    def accepts(self, source):
        return True


JSON = _Json()


# --- the package's own values --------------------------------------------------------

class _SceneEntry(ValueType):
    """One object of a scene file (`P-SCENE-FILE`): ``{"object": {"type", ...}}`` for a
    primitive, ``{"recipe", "args"}`` for a designed element; a ``name`` optional."""

    name = "scene_entry"

    def parse(self, value, where="value"):
        from ..analysis import scene_file as sf  # noqa: PLC0415
        if not isinstance(value, dict):
            raise _refuse(where, "a scene entry", value)
        if "object" in value:
            kind = (value["object"] or {}).get("type") if isinstance(value["object"], dict) else None
            if kind not in sf.list_primitives():
                raise _refuse(where, f"a primitive's type (one of {', '.join(sf.list_primitives())})", kind)
        elif "recipe" in value:
            try:
                sf.recipe_class(value["recipe"])
            except sf.SceneFileError as exc:
                raise BlockTypeError(f"{where}: {exc}") from None
            if not isinstance(value.get("args", {}), dict):
                raise _refuse(where, "a recipe's args as an object", value.get("args"))
        else:
            raise _refuse(where, "a scene entry ({\"object\": ...} or {\"recipe\": ..., \"args\": ...})", value)
        return copy.deepcopy(value)

    def format(self, live):
        return copy.deepcopy(live)


class _Scene(ValueType):
    """A whole scene (`P-SCENE-FILE`): a scene file's content, or its path."""

    name = "scene"

    def parse(self, value, where="value"):
        from ..analysis import scene_file as sf  # noqa: PLC0415
        from ..core.scene import Scene  # noqa: PLC0415
        if isinstance(value, Scene):
            return value
        try:
            if isinstance(value, str):
                return sf.load_scene(value)
            if isinstance(value, dict):
                return sf.scene_from_dict(value)
        except (sf.SceneFileError, OSError) as exc:
            raise BlockTypeError(f"{where}: {exc}") from None
        raise _refuse(where, "a scene file's content or path", value)

    def format(self, live):
        from ..analysis import scene_file as sf  # noqa: PLC0415
        return sf.scene_to_dict(live)


class _FilePath(ValueType):
    """A path to an existing file or folder, read into its live form by `reader`."""

    def __init__(self, name: str, what: str, reader: Optional[Callable[[Path], Any]] = None,
                 back: Optional[Callable[[Any], Any]] = None, folder: bool = False) -> None:
        self.name, self.what, self.reader, self.back, self.folder = name, what, reader, back, folder

    def parse(self, value, where="value"):
        if not isinstance(value, (str, Path)):
            if self.reader is not None and not isinstance(value, (dict, list, int, float, bool)) and value is not None:
                return value                          # already live
            raise _refuse(where, f"the path of {self.what}", value)
        path = Path(value).expanduser()
        if not (path.is_dir() if self.folder else path.is_file()):
            raise _refuse(where, f"an existing {'folder' if self.folder else 'file'}: {self.what}", str(value))
        return self.reader(path) if self.reader else path

    def format(self, live):
        if self.back is not None:
            return self.back(live)
        return str(live)

    def describe(self):
        return {"type": self.name}


def _read_rayfile(path: Path) -> Any:
    from ..optical_elements.sources import read_rayfile  # noqa: PLC0415
    return read_rayfile(path)


def _rayfile_back(live: Any) -> Any:
    if getattr(live, "path", None):
        return str(live.path)
    raise BlockTypeError("a rayfile not read from a file has no JSON form; write it first (write_tm25)")


def _read_profile(path: Path) -> Any:
    import json  # noqa: PLC0415
    return json.loads(path.read_text(encoding="utf-8"))


class _Record(ValueType):
    """A JSON object with required and optional keys, each typed."""

    def __init__(self, name: str, required: Dict[str, ValueType], optional: Dict[str, ValueType]) -> None:
        self.name, self.required, self.optional = name, required, optional

    def parse(self, value, where="value"):
        if not isinstance(value, dict):
            raise _refuse(where, f"a {self.name} object", value)
        missing = [k for k in self.required if k not in value]
        if missing:
            raise _refuse(where, f"a {self.name} with {', '.join(missing)}", value)
        out = {}
        for key, item in value.items():
            t = self.required.get(key) or self.optional.get(key)
            out[key] = t.parse(item, f"{where}.{key}") if t is not None else copy.deepcopy(item)
        return out

    def format(self, live):
        return {k: (self.required.get(k) or self.optional.get(k) or JSON).format(v) for k, v in live.items()}


SCENE_ENTRY = _SceneEntry()
SCENE = _Scene()
RAYFILE = _FilePath("rayfile", "a rayfile (IES TM-25, positions in mm)", _read_rayfile, _rayfile_back)
PROFILE = _FilePath("profile", "a profile.json", _read_profile)


class _RayfileSlice(ValueType):
    """A rayfile's slice (`RayfileSlice`). Its JSON form is what it is made again from:
    ``{"rayfile": path, "position": [a, b], "direction_deg", "max_offset_mm", "roll_deg"?}``."""

    name = "rayfile_slice"
    _KEYS = ("rayfile", "position", "direction_deg", "max_offset_mm", "roll_deg")

    def parse(self, value, where="value"):
        from ..optical_elements.sources import RayfileSlice, slice_rayfile  # noqa: PLC0415
        if isinstance(value, RayfileSlice):
            return value
        if not isinstance(value, dict) or any(k not in value for k in self._KEYS[:4]):
            raise _refuse(where, "a rayfile slice ({" + ", ".join(self._KEYS[:4]) + "})", value)
        unknown = sorted(set(value) - set(self._KEYS))
        if unknown:
            raise _refuse(where, f"a rayfile slice's keys ({', '.join(self._KEYS)})", unknown)
        rayfile = RAYFILE.parse(value["rayfile"], f"{where}.rayfile")
        position = POSITION.parse(value["position"], f"{where}.position")
        numbers = {k: NUMBER.parse(value.get(k, 0.0), f"{where}.{k}") for k in self._KEYS[2:]}
        try:
            return slice_rayfile(rayfile, position, numbers["direction_deg"],
                                 max_offset_mm=numbers["max_offset_mm"], roll_deg=numbers["roll_deg"])
        except ValueError as exc:
            raise BlockTypeError(f"{where}: {exc}") from None

    def format(self, live):
        if not getattr(live, "rayfile_path", None):
            raise BlockTypeError("a slice of a rayfile not read from a file has no JSON form; write it first "
                                 "(write_tm25)")
        return {"rayfile": live.rayfile_path, "position": list(live.position), "direction_deg": live.direction_deg,
                "max_offset_mm": live.max_offset_mm, "roll_deg": live.roll_deg}


class Trace:
    """A traced scene (the block type ``trace``): the scene, every named detector's reading,
    the live result while in the kernel, and the run's folder once saved.

    Its JSON form is that folder: a run bundle (`P-RUN-BUNDLE`) with ``scene.json``
    and ``readings.json`` beside it, which is all a block reads back.
    """

    def __init__(self, scene: Any, readings: Dict[str, Any], result: Any = None,
                 folder: Optional[Path] = None) -> None:
        self.scene, self.readings, self.result, self.folder = scene, readings, result, folder

    def __repr__(self) -> str:
        return f"Trace(detectors={sorted(self.readings)}, folder={self.folder})"


class _Trace(ValueType):
    name = "trace"

    def parse(self, value, where="value"):
        import json  # noqa: PLC0415
        from ..analysis import scene_file as sf  # noqa: PLC0415
        if isinstance(value, Trace):
            return value
        if not isinstance(value, (str, Path)):
            raise _refuse(where, "a trace's run folder", value)
        folder = Path(value).expanduser()
        if not (folder / "readings.json").is_file() or not (folder / "scene.json").is_file():
            raise _refuse(where, "a run folder a trace block wrote (scene.json, readings.json)", str(value))
        try:
            scene = sf.load_scene(folder / "scene.json")
        except sf.SceneFileError as exc:
            raise BlockTypeError(f"{where}: {exc}") from None
        return Trace(scene, json.loads((folder / "readings.json").read_text(encoding="utf-8")), folder=folder)

    def format(self, live):
        if live.folder is None:
            raise BlockTypeError("a trace not saved has no JSON form; give the trace block a runs_dir")
        return str(live.folder)


RAYFILE_SLICE = _RayfileSlice()
TRACE = _Trace()
IRRADIANCE = Quantity("W/m^2")
#: What one detector measured in a traced scene (`analysis.parameter_study.read_detector`).
DETECTOR_READING = _Record(
    "detector_reading",
    required={"power": NUMBER, "hits": INTEGER},
    optional={"emitted": NUMBER, "share": Optional_(NUMBER), "centroid": Optional_(NUMBER), "profile": JSON},
)
#: One vertex of a glass outline: a point, an arc's through-point, or the start of a curved edge.
GLASS_VERTEX = _Record("glass_vertex", required={"x": NUMBER, "y": NUMBER},
                       optional={"arc": BOOL, "curve": JSON})
RADIANCE = Quantity("W/(m^2*sr)")
#: A hazard classification: its group, and each limit it was checked against
#: (``{"hazard", "group", "value", "limit", "unit", "within"}``).
CLASSIFICATION = _Record("classification", required={"group": Choice(["Exempt", "RG1", "RG2", "RG3"])},
                         optional={"limits": JSON})


# --- the vocabulary, by name ---------------------------------------------------------

_SIMPLE: Dict[str, ValueType] = {t.name: t for t in (
    NUMBER, INTEGER, BOOL, TEXT, POSITION, DIRECTION, JSON, SCENE_ENTRY, SCENE, RAYFILE, RAYFILE_SLICE, PROFILE,
    TRACE, DETECTOR_READING, CLASSIFICATION, GLASS_VERTEX)}


def register_type(value_type: ValueType) -> None:
    """Add a satellite's type to the vocabulary (its name must be new)."""
    if value_type.name in _SIMPLE:
        raise ValueError(f"a value type named {value_type.name!r} exists")
    _SIMPLE[value_type.name] = value_type


def from_description(description: Dict[str, Any]) -> ValueType:
    """A type from its `describe()` JSON."""
    kind = description.get("type")
    if kind == "quantity":
        return Quantity(description["unit"])
    if kind == "choice":
        return Choice(description["options"])
    if kind == "optional":
        return Optional_(from_description(description["of"]))
    if kind == "list":
        return ListOf(from_description(description["of"]))
    if kind in _SIMPLE:
        return _SIMPLE[kind]
    raise BlockTypeError(f"no value type {kind!r}; types: {', '.join(sorted(_SIMPLE))}, quantity, choice, "
                         "optional, list")


def vocabulary() -> Dict[str, Dict[str, Any]]:
    """Every named type, described."""
    return {name: t.describe() for name, t in sorted(_SIMPLE.items())}


__all__ = [
    "BOOL", "BlockTypeError", "CLASSIFICATION", "GLASS_VERTEX", "Choice", "DETECTOR_READING", "DIRECTION", "INTEGER",
    "IRRADIANCE", "JSON", "ListOf", "NUMBER", "Optional_", "POSITION", "PROFILE", "Quantity", "RAYFILE",
    "RADIANCE", "RAYFILE_SLICE", "SCENE", "SCENE_ENTRY", "SCENE_UNIT", "TEXT", "TRACE", "Trace", "ValueType", "from_description",
    "register_type", "vocabulary",
]
