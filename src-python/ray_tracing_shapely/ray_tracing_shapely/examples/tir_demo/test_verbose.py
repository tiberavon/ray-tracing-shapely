"""
Python-specific module: test verbose
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

Test script to demonstrate the verbose levels in the simulator."""

import sys
import os

# Add parent directories to path to from ray_tracing_shapely import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay

def test_verbose_levels():
    """Test the different verbose levels."""

    print("=" * 70)
    print("Testing Simulator Verbose Levels")
    print("=" * 70)

    # Create a simple scene with one ray and a prism
    scene = Scene()
    scene.ray_density = 0.1

    # Create equilateral triangle prism
    prism = Glass(scene)
    prism.path = [
        {'x': 100, 'y': 200, 'arc': False},
        {'x': 200, 'y': 200, 'arc': False},
        {'x': 150, 'y': 113.4, 'arc': False}
    ]
    prism.not_done = False
    prism.refIndex = 1.5

    # Create a single ray
    ray = SingleRay(scene)
    ray.p1 = {'x': 90, 'y': 140}
    ray.p2 = {'x': 120, 'y': 200}
    ray.brightness = 1.0

    # Add to scene
    scene.add_object(prism)
    scene.add_object(ray)

    # Test verbose=0 (silent)
    print("\n" + "=" * 70)
    print("TEST 1: verbose=0 (SILENT - no debug output)")
    print("=" * 70)
    simulator = Simulator(scene, max_rays=100, verbose=0)
    segments = simulator.run()
    print(f"Result: {len(segments)} ray segments traced")

    # Test verbose=1 (verbose - ray processing info)
    print("\n" + "=" * 70)
    print("TEST 2: verbose=1 (VERBOSE - show ray processing)")
    print("=" * 70)
    simulator = Simulator(scene, max_rays=100, verbose=1)
    segments = simulator.run()
    print(f"Result: {len(segments)} ray segments traced")

    # Test verbose=2 (debug - detailed refraction)
    print("\n" + "=" * 70)
    print("TEST 3: verbose=2 (DEBUG - detailed refraction calculations)")
    print("=" * 70)
    simulator = Simulator(scene, max_rays=100, verbose=2)
    segments = simulator.run()
    print(f"Result: {len(segments)} ray segments traced")

    print("\n" + "=" * 70)
    print("Testing Complete!")
    print("=" * 70)

if __name__ == '__main__':
    test_verbose_levels()
