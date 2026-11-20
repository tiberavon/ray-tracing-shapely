"""
Python-specific module: portable scene -- a 2D scene as plain data a job can rebuild
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
PORTABLE SCENE -- a live 2D scene's optical objects as plain data
===============================================================================
A job's inputs are JSON, so a live `Scene` cannot be one. `portable_scene`
describes a scene's optical objects as plain data, in their order, and
`build_portable_scene` rebuilds them anywhere the package is installed:

- **a designed element** (a `BasePrism`: a prism, a lens, a collimator, an SMS
  element) as its profile (`export_profile`, symmetry ``free``), rebuilt by
  `BasePrism.from_profile` with its labels, roles and coated spans;
- **any other optical object** as its class's import path and its own
  ``serialize()``, rebuilt by calling the class with it (glass, detectors,
  mirrors, blockers: the objects the 2D engine reads from its JSON).

Every object carries its name. A rebuilt object has a new uuid, and segments
name the surface they hit by uuid, so what a job returns is mapped back to
the live scene's objects by name: names unique and present on every object
described is the precondition (`C-LABEL-01`), and `portable_scene` refuses a
scene that breaks it.

Each description is checked where it is made: rebuilt once here, its
``serialize()`` (or its outline, for a profile) compared with the original.
An object that does not come back the same is refused, by name, rather than
sent to be traced as something else.

Sources are not described: a job brings its own rays.
===============================================================================
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

#: The scene settings a job's scene takes from the live one.
SETTINGS = ('mode', 'color_mode', 'simulate_colors', 'length_scale')


class NotPortable(ValueError):
    """The scene cannot be described as plain data: an object, or its name, is why."""


def _class_path(obj: Any) -> str:
    cls = type(obj)
    return f"{cls.__module__}:{cls.__qualname__}"


def _resolve(path: str) -> Any:
    import importlib  # noqa: PLC0415

    module, _, name = path.partition(':')
    target: Any = importlib.import_module(module)
    for part in name.split('.'):
        target = getattr(target, part)
    return target


def _is_source(obj: Any) -> bool:
    from .agentic_tools import SOURCE_TYPES  # noqa: PLC0415

    return any(cls.__name__ in SOURCE_TYPES for cls in type(obj).__mro__)


def _outline(glass: Any) -> List[List[float]]:
    return [[round(float(p['x']), 9), round(float(p['y']), 9)] for p in glass.path]


def _describe(scene: Any, obj: Any) -> Dict[str, Any]:
    from ..core.scene import Scene  # noqa: PLC0415
    from ..optical_elements.prisms.base_prism import BasePrism  # noqa: PLC0415
    from ..optical_elements.prisms.profile_export import export_profile  # noqa: PLC0415

    name = obj.name
    if isinstance(obj, BasePrism):
        try:
            profile = export_profile(obj, symmetry={'kind': 'free'}, physical_params={}, numerical_params={})
        except Exception as exc:                          # noqa: BLE001 -- refused by name, with the reason
            raise NotPortable(f"{name!r} ({type(obj).__name__}) does not export as a profile: {exc}") from exc
        out = {'name': name, 'profile': profile, 'n': float(obj.refIndex)}
        rebuilt = _build_one(Scene(), out)
        if len(rebuilt.path) != len(obj.path) or _outline(rebuilt) != _outline(obj):
            raise NotPortable(f"{name!r} ({type(obj).__name__}): its profile does not rebuild the same outline")
        return out
    try:
        data = json.loads(json.dumps(obj.serialize()))
    except (TypeError, ValueError) as exc:
        raise NotPortable(f"{name!r} ({type(obj).__name__}) does not serialize as JSON: {exc}") from exc
    out = {'name': name, 'class': _class_path(obj), 'json': data}
    try:
        rebuilt = _build_one(Scene(), out)
    except Exception as exc:                              # noqa: BLE001 -- refused by name, with the reason
        raise NotPortable(f"{name!r} ({type(obj).__name__}) is not rebuilt from its serialize(): {exc}") from exc
    if json.dumps(rebuilt.serialize(), sort_keys=True) != json.dumps(data, sort_keys=True):
        raise NotPortable(f"{name!r} ({type(obj).__name__}) is not rebuilt the same from its serialize()")
    return out


def _build_one(scene: Any, d: Dict[str, Any]) -> Any:
    if 'profile' in d:
        from ..optical_elements.prisms.base_prism import BasePrism  # noqa: PLC0415

        obj = BasePrism.from_profile(scene, d['profile'], n=float(d['n']))
    else:
        obj = _resolve(d['class'])(scene, d['json'])
    obj.name = d['name']
    return obj


def portable_scene(scene: Any, *, exclude: Sequence[Any] = ()) -> Dict[str, Any]:
    """Describe a scene's optical objects, other than sources, as plain data a job rebuilds.

    Args:
        scene: The live Scene.
        exclude: Objects left out, besides the sources.

    Returns:
        ``{"settings": {...}, "objects": [{"name", "profile", "n"} | {"name", "class", "json"}]}``,
        the objects in the scene's order.

    Raises:
        NotPortable: An object is unnamed, shares its name, does not export, or does not
            rebuild the same; the message names it.
    """
    objs = [o for o in scene.optical_objs if not _is_source(o) and not any(o is e for e in exclude)]
    unnamed = [type(o).__name__ for o in objs if not getattr(o, 'name', None)]
    if unnamed:
        raise NotPortable(f"every object needs a name to be mapped back (C-LABEL-01); unnamed: "
                          f"{', '.join(unnamed)}")
    names = [o.name for o in objs]
    shared = sorted({n for n in names if names.count(n) > 1})
    if shared:
        raise NotPortable(f"names must be unique to be mapped back (C-LABEL-01); shared: {', '.join(shared)}")
    return {'settings': {k: getattr(scene, k) for k in SETTINGS},
            'objects': [_describe(scene, o) for o in objs]}


def build_portable_scene(description: Dict[str, Any], *, min_brightness_exp: Optional[int] = None) -> Any:
    """Rebuild a described scene: a new Scene with the settings and the objects, in order.

    Args:
        description: What `portable_scene` returned.
        min_brightness_exp: The scene's brightness threshold (None: the scene's own default).

    Returns:
        The Scene.
    """
    from ..core.scene import Scene  # noqa: PLC0415

    scene = Scene()
    for k, v in description.get('settings', {}).items():
        setattr(scene, k, v)
    if min_brightness_exp is not None:
        scene.min_brightness_exp = int(min_brightness_exp)
    for d in description['objects']:
        scene.add_object(_build_one(scene, d))
    return scene


__all__ = ['NotPortable', 'SETTINGS', 'build_portable_scene', 'portable_scene']
