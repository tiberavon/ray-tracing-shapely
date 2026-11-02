"""
Python-specific module: test surface merging
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

Test script to verify surface merging fix for coupled prisms.
This creates a minimal test case with two coupled prisms.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator

def test_coupled_prisms():
    """Test that coupled prisms with same n don't refract at interface."""

    scene = Scene()
    scene.ray_density = 0.1

    # Create two prisms sharing an edge at y=50
    # Bottom prism
    prism1 = Glass(scene)
    prism1.path = [
        {'x': 40, 'y': 50, 'arc': False},  # Shared edge
        {'x': 60, 'y': 50, 'arc': False},  # Shared edge
        {'x': 50, 'y': 30, 'arc': False}   # Bottom vertex
    ]
    prism1.not_done = False
    prism1.refIndex = 1.5

    # Top prism
    prism2 = Glass(scene)
    prism2.path = [
        {'x': 40, 'y': 50, 'arc': False},  # Shared edge
        {'x': 60, 'y': 50, 'arc': False},  # Shared edge
        {'x': 50, 'y': 70, 'arc': False}   # Top vertex
    ]
    prism2.not_done = False
    prism2.refIndex = 1.5

    scene.add_object(prism1)
    scene.add_object(prism2)

    # Create a ray that enters bottom prism and crosses interface
    # Slightly offset from center to avoid hitting vertex
    ray_source = SingleRay(scene)
    ray_source.p1 = {'x': 50.5, 'y': 20}  # Below bottom prism
    ray_source.p2 = {'x': 50.5, 'y': 21}  # Pointing upward
    ray_source.brightness = 1.0

    scene.add_object(ray_source)

    # Run simulation with verbose output
    print("="*60)
    print("Testing surface merging with coupled prisms")
    print("="*60)
    print(f"Prism1 (bottom): vertices at y=30, y=50 (shared edge), n={prism1.refIndex}")
    print(f"Prism2 (top): vertices at y=50 (shared edge), y=70, n={prism2.refIndex}")
    print(f"Ray: vertical from (50,20) upward")
    print()

    simulator = Simulator(scene, max_rays=20, verbose=2)
    segments = simulator.run()

    print()
    print("="*60)
    print(f"Total segments: {len(segments)}")
    print("="*60)

    # Analyze the results
    print("\nRay segments:")
    for i, seg in enumerate(segments):
        p1_y = seg.p1['y']
        p2_y = seg.p2['y']
        brightness = seg.total_brightness
        print(f"  Segment {i}: y={p1_y:.1f} -> y={p2_y:.1f}, brightness={brightness:.4f}")

    # Check if ray crosses interface at y=50 without refracting
    interface_crossings = []
    for i, seg in enumerate(segments):
        p1_y = seg.p1['y']
        p2_y = seg.p2['y']
        # Check if segment crosses y=50
        if (p1_y < 50 < p2_y) or abs(p1_y - 50) < 0.1 or abs(p2_y - 50) < 0.1:
            interface_crossings.append((i, seg))

    print(f"\nSegments crossing interface (y=50): {len(interface_crossings)}")

    # For vertical ray, if it refracts at y=50, direction will change
    # Check if ray remains vertical across interface
    crossed_correctly = False
    for i, seg in interface_crossings:
        p1_x = seg.p1['x']
        p2_x = seg.p2['x']
        dx = abs(p2_x - p1_x)
        if dx < 1.0:  # Still nearly vertical
            print(f"  [OK] Segment {i} crosses interface without horizontal deflection (dx={dx:.4f})")
            crossed_correctly = True
        else:
            print(f"  [FAIL] Segment {i} has horizontal deflection at interface (dx={dx:.4f}) - REFRACTION BUG!")

    print()
    if crossed_correctly:
        print("[OK] TEST PASSED: Ray crosses interface without refracting")
    else:
        print("[FAIL] TEST FAILED: Ray refracted at glass-glass interface with same n")

    return crossed_correctly

if __name__ == '__main__':
    success = test_coupled_prisms()
    sys.exit(0 if success else 1)
