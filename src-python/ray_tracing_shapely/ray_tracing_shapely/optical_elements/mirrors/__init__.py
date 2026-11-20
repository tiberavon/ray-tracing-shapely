"""
Python-specific module: mirrors
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

Exact curved mirrors: ConicMirror and its circle case ArcMirror, SplineMirror
on a curve through designed points and normals; and the 2D mirrors a sheet
profile is the half-section of (mirrors_from_sheet_profile).
"""

from .conic import ArcMirror, ConicMirror, conic_sag, max_single_valued_s
from .sheet_profile import mirrors_from_sheet_profile
from .spline import SplineMirror

__all__ = ["ConicMirror", "ArcMirror", "SplineMirror", "conic_sag", "max_single_valued_s", "mirrors_from_sheet_profile"]
