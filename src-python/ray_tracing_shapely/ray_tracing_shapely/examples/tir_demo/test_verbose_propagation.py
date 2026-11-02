"""
Python-specific module: test verbose propagation
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

Test script to verify verbose flag propagation to all scene objects."""

import sys
import os

# Add parent directories to path to from ray_tracing_shapely import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.scene_objs.glass.ideal_lens import IdealLens
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay

def test_verbose_propagation():
    """Test that verbose flag propagates to all object types."""

    print("=" * 70)
    print("Testing Verbose Flag Propagation to All Scene Objects")
    print("=" * 70)

    # Test 1: Glass object (already tested, but include for completeness)
    print("\n" + "=" * 70)
    print("TEST 1: Glass object with verbose=1")
    print("=" * 70)

    scene = Scene()
    scene.ray_density = 0.1

    # Create a simple prism
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

    # Run with verbose=1
    simulator = Simulator(scene, max_rays=50, verbose=1)
    segments = simulator.run()
    print(f"Result: {len(segments)} ray segments traced")

    # Test 2: Ideal Lens
    print("\n" + "=" * 70)
    print("TEST 2: Ideal Lens with verbose=1")
    print("=" * 70)

    scene2 = Scene()
    scene2.ray_density = 0.1

    # Create ideal lens
    lens = IdealLens(scene2)
    lens.p1 = {'x': 200, 'y': 100}
    lens.p2 = {'x': 200, 'y': 300}
    lens.focalLength = 100

    # Create a ray that will hit the lens
    ray2 = SingleRay(scene2)
    ray2.p1 = {'x': 100, 'y': 200}
    ray2.p2 = {'x': 300, 'y': 200}
    ray2.brightness = 1.0

    # Add to scene
    scene2.add_object(lens)
    scene2.add_object(ray2)

    # Run with verbose=1
    simulator2 = Simulator(scene2, max_rays=50, verbose=1)
    segments2 = simulator2.run()
    print(f"Result: {len(segments2)} ray segments traced")

    # Test 3: Blocker
    print("\n" + "=" * 70)
    print("TEST 3: Blocker with verbose=1")
    print("=" * 70)

    scene3 = Scene()
    scene3.ray_density = 0.1

    # Create blocker
    blocker = Blocker(scene3)
    blocker.p1 = {'x': 200, 'y': 100}
    blocker.p2 = {'x': 200, 'y': 300}

    # Create a ray that will hit the blocker
    ray3 = SingleRay(scene3)
    ray3.p1 = {'x': 100, 'y': 200}
    ray3.p2 = {'x': 300, 'y': 200}
    ray3.brightness = 1.0

    # Add to scene
    scene3.add_object(blocker)
    scene3.add_object(ray3)

    # Run with verbose=1
    simulator3 = Simulator(scene3, max_rays=50, verbose=1)
    segments3 = simulator3.run()
    print(f"Result: {len(segments3)} ray segments traced")

    # Test 4: All objects with verbose=0 (should be silent)
    print("\n" + "=" * 70)
    print("TEST 4: All objects with verbose=0 (should be silent)")
    print("=" * 70)

    scene4 = Scene()
    scene4.ray_density = 0.1

    # Create all types of objects
    prism4 = Glass(scene4)
    prism4.path = [
        {'x': 100, 'y': 200, 'arc': False},
        {'x': 200, 'y': 200, 'arc': False},
        {'x': 150, 'y': 113.4, 'arc': False}
    ]
    prism4.not_done = False
    prism4.refIndex = 1.5

    lens4 = IdealLens(scene4)
    lens4.p1 = {'x': 250, 'y': 100}
    lens4.p2 = {'x': 250, 'y': 300}
    lens4.focalLength = 50

    blocker4 = Blocker(scene4)
    blocker4.p1 = {'x': 350, 'y': 100}
    blocker4.p2 = {'x': 350, 'y': 300}

    ray4 = SingleRay(scene4)
    ray4.p1 = {'x': 50, 'y': 150}
    ray4.p2 = {'x': 400, 'y': 150}
    ray4.brightness = 1.0

    # Add to scene
    scene4.add_object(prism4)
    scene4.add_object(lens4)
    scene4.add_object(blocker4)
    scene4.add_object(ray4)

    # Run with verbose=0 (should be completely silent)
    simulator4 = Simulator(scene4, max_rays=100, verbose=0)
    segments4 = simulator4.run()
    print(f"Result: {len(segments4)} ray segments traced (no debug output above)")

    print("\n" + "=" * 70)
    print("Testing Complete!")
    print("=" * 70)
    print("\nSummary:")
    print(f"  Glass object:  {len(segments)} segments")
    print(f"  Ideal Lens:    {len(segments2)} segments")
    print(f"  Blocker:       {len(segments3)} segments")
    print(f"  Mixed scene:   {len(segments4)} segments")

if __name__ == '__main__':
    test_verbose_propagation()
