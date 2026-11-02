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

Ray Tracing Shapely
===================

A Python ray tracing library using Shapely for computational geometry.

Main modules:
- core: Core simulation engine (Scene, Simulator, Ray, optical objects)
- analysis: Python-specific analysis utilities (geometry analysis)
- examples: Example simulations and demonstrations

Quick start:
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs import Glass, SingleRay
    from ray_tracing_shapely.core.simulator import Simulator
"""

__version__ = "0.1.0"

# Convenience imports for common usage
from .core.scene import Scene
from .core.simulator import Simulator
from .core.ray import Ray

__all__ = [
    'Scene',
    'Simulator',
    'Ray',
    '__version__',
]
