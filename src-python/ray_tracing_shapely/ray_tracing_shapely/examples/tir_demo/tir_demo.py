"""
Python-specific module: tir demo
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
"""

import sys
import os
from typing import List

# Add parent directories to path to from ray_tracing_shapely import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.glass.ideal_lens import IdealLens
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.svg_renderer import SVGRenderer
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay

def tir_demo():
    """Total Internal Reflection demonstration.
    
    Problem Statement
    Demonstrate Total Internal Reflection (TIR) in a glass prism when a light ray 
    hits an internal surface at an angle greater than the critical angle.

    Physics Background
    Critical angle: θ_c = arcsin(n₂/n₁) = arcsin(1/1.5) ≈ 41.8°
    For TIR to occur: incident angle (from normal) must be > 41.8°
    When TIR occurs: ray reflects instead of refracting
    
    Expected Behavior
    Ray enters prism through left face (refracts inward due to n=1.5)
    Ray travels to opposite face
    If angle > 41.8° from normal: TIR occurs → ray reflects internally
    Ray exits through another face
    
    My Plan
    Prism: Equilateral triangle (60° angles)
    Ray entry: Aim at left face at ~45° to create steep internal angle
    Check: Ray should reflect off right face instead of exiting"""

    output_dir = os.path.join(os.path.dirname(__file__), 'output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)     
    print("Setting up Total Internal Reflection in a Prism...\n")

    # Create scene
    scene = Scene()
    scene.ray_density = 0.1

    # Create equilateral triangle prism
    # Vertices at (100, 200), (200, 200), (150, 113.4) for 60° angles
    prism = Glass(scene)
    prism.path = [
        {'x': 100, 'y': 200, 'arc': False},
        {'x': 200, 'y': 200, 'arc': False},
        {'x': 150, 'y': 113.4, 'arc': False}
    ]
    prism.not_done = False
    prism.refIndex = 1.5

    ray_list: List[SingleRay] = []

    # Create 25 rays at different angles to demonstrate TIR
    for i in range(10):
        new_ray_source = SingleRay(scene)
        new_ray_source.p1 = {'x': 90, 'y': 140}
        new_ray_source.p2 = {'x': 120, 'y': 200 - i*3}  # Sweep downward
        new_ray_source.brightness = 1.0
        ray_list.append(new_ray_source)

    
#    # Create point source at origin
#     point_source = PointSource(scene)
#     point_source.x = 50
#     point_source.y = 150
#     point_source.brightness = 1.0


    # Add to scene
    scene.add_object(prism)
    for ray_source in ray_list:
        scene.add_object(ray_source)

    # Run simulation
    # verbose levels: 0=silent (default), 1=verbose (ray processing), 2=debug (detailed refraction)
    simulator = Simulator(scene, max_rays=1000, verbose=0)
    segments = simulator.run()

    print(f"Rays traced: {simulator.processed_ray_count}")
    print(f"Segments: {len(segments)}")

    # Render
    renderer = SVGRenderer(width=800, height=600, viewbox=(0, 50, 300, 200))
    renderer.draw_line_segment(prism.path[0], prism.path[1], color='blue', stroke_width=2, label='Prism')
    renderer.draw_line_segment(prism.path[1], prism.path[2], color='blue', stroke_width=2)
    renderer.draw_line_segment(prism.path[2], prism.path[0], color='blue', stroke_width=2)

    for seg in segments:
        renderer.draw_ray_segment(seg, color='red', opacity=0.8, stroke_width=1.5, draw_gap_rays=True)

    output_file = output_dir + '/prism_tir.svg'
    renderer.save(output_file)
    print(f"\nSaved to: {output_file}")

    # =========================================================================
    # Demonstrate edge labeling with cardinal directions (Python-specific)
    # =========================================================================
    print("\n--- Edge Labeling Visualization ---")

    # Apply cardinal labels to the prism
    prism.auto_label_cardinal()
    print("Applied cardinal labels to prism:")
    for i in range(prism._get_edge_count()):
        label = prism.get_edge_label(i)
        print(f"  Edge {i}: {label[0]} ({label[1]})")

    # Create a new renderer with edge labels
    renderer_labeled = SVGRenderer(width=800, height=600, viewbox=(0, 50, 300, 200))
    renderer_labeled.draw_line_segment(prism.path[0], prism.path[1], color='blue', stroke_width=2)
    renderer_labeled.draw_line_segment(prism.path[1], prism.path[2], color='blue', stroke_width=2)
    renderer_labeled.draw_line_segment(prism.path[2], prism.path[0], color='blue', stroke_width=2)

    for seg in segments:
        renderer_labeled.draw_ray_segment(seg, color='red', opacity=0.8, stroke_width=1.5, draw_gap_rays=True)

    # Draw the edge labels (using larger font for visibility)
    renderer_labeled.draw_glass_edge_labels(prism, color='darkgreen', font_size='16px', offset_factor=0.25)

    output_file_labeled = output_dir + '/prism_tir_labeled.svg'
    renderer_labeled.save(output_file_labeled)
    print(f"Saved labeled version to: {output_file_labeled}")


def edge_labeling_demo():
    """
    Demonstrate the edge labeling feature (Python-specific).

    This feature allows labeling individual edges of glass objects with
    short labels and long names for identification and tracking.
    """
    print("\n" + "="*60)
    print("Edge Labeling Demo (Python-specific feature)")
    print("="*60)

    scene = Scene()

    # Create a square glass for simple testing
    print("\n--- Test 1: Square Glass with Default Numeric Labels ---")
    square = Glass(scene)
    square.path = [
        {'x': 0, 'y': 0, 'arc': False},
        {'x': 100, 'y': 0, 'arc': False},
        {'x': 100, 'y': 100, 'arc': False},
        {'x': 0, 'y': 100, 'arc': False}
    ]
    square.not_done = False
    square.refIndex = 1.5

    # Default labels are numeric
    print(f"Edge count: {square._get_edge_count()}")
    print("Default numeric labels:")
    for i in range(square._get_edge_count()):
        label = square.get_edge_label(i)
        print(f"  Edge {i}: short='{label[0]}', long='{label[1]}'")

    # Test manual labeling
    print("\n--- Test 2: Manual Edge Labeling ---")
    square.label_edge(0, "bottom", "Bottom Edge")
    square.label_edge(1, "right", "Right Edge")
    square.label_edge(2, "top", "Top Edge")
    square.label_edge(3, "left", "Left Edge")

    print("After manual labeling:")
    for i in range(square._get_edge_count()):
        short = square.get_edge_short_label(i)
        long = square.get_edge_long_name(i)
        print(f"  Edge {i}: short='{short}', long='{long}'")

    # Test find methods
    print("\n--- Test 3: Finding Edges by Label ---")
    idx = square.find_edge_by_short_label("top")
    print(f"find_edge_by_short_label('top') = {idx}")

    idx = square.find_edge_by_long_name("Left Edge")
    print(f"find_edge_by_long_name('Left Edge') = {idx}")

    idx = square.find_edge_by_short_label("nonexistent")
    print(f"find_edge_by_short_label('nonexistent') = {idx}")

    # Test cardinal auto-labeling on square
    print("\n--- Test 4: Cardinal Auto-Labeling (Square) ---")
    square2 = Glass(scene)
    square2.path = [
        {'x': 0, 'y': 0, 'arc': False},      # bottom-left
        {'x': 100, 'y': 0, 'arc': False},    # bottom-right
        {'x': 100, 'y': 100, 'arc': False},  # top-right
        {'x': 0, 'y': 100, 'arc': False}     # top-left
    ]
    square2.not_done = False

    print(f"Centroid: {square2._get_centroid()}")
    print("Edge midpoints:")
    for i in range(4):
        mid = square2._get_edge_midpoint(i)
        print(f"  Edge {i}: midpoint=({mid[0]:.1f}, {mid[1]:.1f})")

    square2.auto_label_cardinal()
    print("\nAfter auto_label_cardinal():")
    for i in range(square2._get_edge_count()):
        label = square2.get_edge_label(i)
        print(f"  Edge {i}: short='{label[0]}', long='{label[1]}'")

    # Test cardinal auto-labeling on triangle (the TIR prism)
    print("\n--- Test 5: Cardinal Auto-Labeling (Equilateral Triangle) ---")
    triangle = Glass(scene)
    triangle.path = [
        {'x': 100, 'y': 200, 'arc': False},   # bottom-left
        {'x': 200, 'y': 200, 'arc': False},   # bottom-right
        {'x': 150, 'y': 113.4, 'arc': False}  # top
    ]
    triangle.not_done = False

    print(f"Centroid: {triangle._get_centroid()}")
    triangle.auto_label_cardinal()
    print("After auto_label_cardinal():")
    for i in range(triangle._get_edge_count()):
        label = triangle.get_edge_label(i)
        mid = triangle._get_edge_midpoint(i)
        print(f"  Edge {i}: short='{label[0]}', long='{label[1]}' (midpoint: {mid[0]:.1f}, {mid[1]:.1f})")

    # Test hexagon (6 edges -> 8 directions)
    print("\n--- Test 6: Cardinal Auto-Labeling (Hexagon - 6 edges) ---")
    import math
    hexagon = Glass(scene)
    # Create regular hexagon centered at (100, 100) with radius 50
    hexagon.path = []
    for i in range(6):
        angle = i * math.pi / 3  # 60 degrees apart
        x = 100 + 50 * math.cos(angle)
        y = 100 + 50 * math.sin(angle)
        hexagon.path.append({'x': x, 'y': y, 'arc': False})
    hexagon.not_done = False

    hexagon.auto_label_cardinal()
    print("After auto_label_cardinal() (uses 8-direction system):")
    for i in range(hexagon._get_edge_count()):
        label = hexagon.get_edge_label(i)
        print(f"  Edge {i}: short='{label[0]}', long='{label[1]}'")

    # Test error handling
    print("\n--- Test 7: Error Handling ---")
    try:
        square.label_edge(10, "bad", "Bad Edge")
        print("ERROR: Should have raised IndexError")
    except IndexError as e:
        print(f"Correctly raised IndexError: {e}")

    print("\n" + "="*60)
    print("Edge Labeling Demo Complete!")
    print("="*60)


if __name__ == '__main__':
    tir_demo()
    edge_labeling_demo()