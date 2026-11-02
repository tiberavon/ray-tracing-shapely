"""
Original work Copyright 2024 The Ray Optics Simulation authors and contributors
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
"""

from .geometry import geometry, Point, Line, Circle, Geometry
from . import constants
from .equation import evaluate_latex, evaluate_latex_single_var
from .ray import Ray
from .scene import Scene
from .simulator import Simulator
from .svg_renderer import SVGRenderer

__all__ = [
    'geometry', 'Point', 'Line', 'Circle', 'Geometry',
    'constants',
    'evaluate_latex', 'evaluate_latex_single_var',
    'Ray',
    'Scene',
    'Simulator',
    'SVGRenderer'
]
