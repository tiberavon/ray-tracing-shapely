"""
Original work Copyright 2026 The Ray Optics Simulation authors and contributors
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

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
Key paths: the address of a value inside an object (propertyUtils/keyPath.js)
===============================================================================
A property schema entry (`BaseSceneObj.property_schema`) names the value it
describes by a key path: dot-separated segments, numeric ones indexing a list
(``"p1"``, ``"path.3"``, ``"path.3.arc"``), the empty path naming the object
itself (a `PointSource` is its own point). These two functions read and write
by such a path, on a serialized dict or on a scene object, whose properties
are attributes (PYTHON-SPECIFIC: the JavaScript objects are indexed the same
way either way).

``for`` and ``if`` are module-template keys whose absence means ``[]`` and
``true``; they are kept for fidelity with upstream, though this package has
no module objects yet.
===============================================================================
"""

import copy
import json
from typing import Any

#: The defaults of the module-template keys, which a path may end in.
FOR_IF_DEFAULTS = {"for": [], "if": True}


def get_for_if_default(key: str) -> Any:
    """The default of a ``for``/``if`` key, or None for any other key."""
    return copy.deepcopy(FOR_IF_DEFAULTS[key]) if key in FOR_IF_DEFAULTS else None


def _segment(seg: str) -> Any:
    try:
        return int(seg)
    except ValueError:
        return seg


def _child(current: Any, key: Any) -> Any:
    """``current[key]``: a list item, a dict entry or (PYTHON-SPECIFIC) an attribute."""
    if isinstance(current, (list, tuple)):
        return current[key] if isinstance(key, int) and -len(current) <= key < len(current) else None
    if isinstance(current, dict):
        return current.get(key)
    return getattr(current, str(key), None)


def _assign(current: Any, key: Any, value: Any) -> None:
    if isinstance(current, list):
        while len(current) <= key:
            current.append(None)
        current[key] = value
    elif isinstance(current, dict):
        current[key] = value
    else:
        setattr(current, str(key), value)


def get_by_key_path(obj: Any, path: str, defaults: Any = None) -> Any:
    """The value at `path` in `obj`; from `defaults` (the same shape) where `obj` has none.

    Args:
        obj: A serialized dict or a scene object (the root).
        path: Dot-separated key path; ``""`` is `obj` itself.
        defaults: Where to look when the value is missing (`serializable_defaults`).

    Returns:
        The value, or None (the default of a ``for``/``if`` key) when missing.
    """
    if path == "":
        return obj
    segments = path.split(".")
    current = obj
    for seg in segments:
        if current is None:
            if defaults is not None:
                return get_by_key_path(defaults, path)
            return get_for_if_default(segments[-1])
        current = _child(current, _segment(seg))
    if current is None and defaults is not None:
        return get_by_key_path(defaults, path)
    if current is None:
        return get_for_if_default(segments[-1])
    return current


def set_by_key_path(obj: Any, path: str, value: Any, defaults: Any = None) -> None:
    """Set the value at `path` in `obj`, making the containers on the way.

    A missing container is copied from `defaults` when it has one there, else
    made: a list if the next segment is numeric, a dict otherwise. A value
    equal to its default (a ``for``/``if`` default, or `defaults`' value) is
    removed from a dict rather than written, outside list items, as upstream
    stores only what differs.

    Raises:
        ValueError: `path` is empty.
    """
    if path == "":
        raise ValueError("keyPath: empty path is not valid for set_by_key_path")
    segments = path.split(".")
    current = obj
    partial = ""
    inside_array_element = False
    for i, seg in enumerate(segments[:-1]):
        key = _segment(seg)
        next_is_array = isinstance(_segment(segments[i + 1]), int)
        if isinstance(current, list):
            inside_array_element = True
        if _child(current, key) is None:
            nxt = partial + "." + seg if partial else seg
            default = get_by_key_path(defaults, nxt) if defaults is not None else None
            _assign(current, key, copy.deepcopy(default) if default is not None
                    else ([] if next_is_array else {}))
        partial = partial + "." + seg if partial else seg
        current = _child(current, key)
    last = segments[-1]
    last_key = _segment(last)

    is_default = False
    for_if = get_for_if_default(last)
    if for_if is not None and json.dumps(value) == json.dumps(for_if):
        is_default = True
    elif defaults is not None:
        default = get_by_key_path(defaults, path)
        if default is not None and json.dumps(value, sort_keys=True) == json.dumps(default, sort_keys=True):
            is_default = True

    if (is_default and (not inside_array_element or for_if is not None)
            and isinstance(current, dict)):
        current.pop(last_key, None)
    else:
        _assign(current, last_key, value)


__all__ = ["FOR_IF_DEFAULTS", "get_by_key_path", "get_for_if_default", "set_by_key_path"]
