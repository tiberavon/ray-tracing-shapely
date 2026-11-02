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

from .base_scene_obj import BaseSceneObj, ConstructReturn, SimulationReturn
from .line_obj_mixin import LineObjMixin
from .circle_obj_mixin import CircleObjMixin
from .param_curve_obj_mixin import ParamCurveObjMixin
from .base_filter import BaseFilter
from .base_glass import BaseGlass
from .base_custom_surface import BaseCustomSurface
from .base_grin_glass import BaseGrinGlass
from .blocker import Blocker
from .light_source import PointSource, Beam, SingleRay, AngleSource
from .glass import IdealLens, Glass, SphericalLens
from .other import Detector
from .ground_glass import GroundGlass

__all__ = ['BaseSceneObj', 'ConstructReturn', 'SimulationReturn', 'LineObjMixin', 'CircleObjMixin', 'ParamCurveObjMixin', 'BaseFilter', 'BaseGlass', 'BaseCustomSurface', 'BaseGrinGlass', 'Blocker', 'PointSource', 'Beam', 'SingleRay', 'AngleSource', 'IdealLens', 'Glass', 'SphericalLens', 'Detector', 'GroundGlass']
