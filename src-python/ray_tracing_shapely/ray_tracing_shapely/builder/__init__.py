"""
Python-specific package: builder
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
The scene builder
===============================================================================
`SceneEditor` (`builder.editor`) is the model: every rule in Python, driven
by JSON messages, usable with no browser. `scene_builder` (`builder.widget`,
the ``widgets`` extra) is its notebook view.
===============================================================================
"""

from .editor import EditorError, PALETTE_PRIMITIVES, SceneEditor

__all__ = ["EditorError", "PALETTE_PRIMITIVES", "SceneEditor", "scene_builder"]


def __getattr__(name):
    if name == "scene_builder":           # the view needs anywidget; the model does not
        from .widget import scene_builder
        return scene_builder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
