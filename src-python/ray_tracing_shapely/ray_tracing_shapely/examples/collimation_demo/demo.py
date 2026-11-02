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

"""
Collimation Demo - Point Source at Focal Point

This example demonstrates the fundamental optical principle of collimation:
when a point source is placed at the focal point of a converging lens,
the output rays become parallel (collimated).

Setup:
- Point source at (0, 0) emitting rays in all directions
- Ideal lens at x=100 with focal length f=100 (so source is at focal point)
- Blocker/screen at x=300 to show the collimated beam

Expected behavior:
- Rays diverge from the point source
- After passing through the lens, rays become parallel
- Parallel rays hit the screen at nearly the same vertical position
"""

import sys
import os

# Add parent directories to path to from ray_tracing_shapely import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.glass.ideal_lens import IdealLens
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.svg_renderer import SVGRenderer


def main():
    """Run the collimation demonstration.
    this is with a """

    print("Collimation Demo - Point Source at Focal Point")
    print("=" * 60)

    # Create scene
    scene = Scene()
    scene.ray_density = 0.3  # radians between rays (smaller = more rays)

    # Create point source at origin
    source = PointSource(scene)
    source.x = 0
    source.y = 300
    source.brightness = 1.0

    # Create ideal lens at x=100 with focal length 100
    # This places the source exactly at the focal point
    lens = IdealLens(scene)
    lens.p1 = {'x': 100, 'y': 200}
    lens.p2 = {'x': 100, 'y': 400}
    lens.focal_length = 100

    # Create screen/blocker at x=300 to catch the collimated beam
    screen = Blocker(scene)
    screen.p1 = {'x': 300, 'y': 100}
    screen.p2 = {'x': 300, 'y': 500}

    # Add objects to scene
    scene.add_object(source)
    scene.add_object(lens)
    scene.add_object(screen)

    print(f"\nScene setup:")
    print(f"  Point source: position=({source.x}, {source.y})")
    print(f"  Lens: x={lens.p1['x']}, y=[{lens.p1['y']}, {lens.p2['y']}], f={lens.focal_length}")
    print(f"  Screen: x={screen.p1['x']}, y=[{screen.p1['y']}, {screen.p2['y']}]")
    print(f"  Ray density: {scene.ray_density} radians")

    # Run simulation
    print("\nRunning simulation...")
    simulator = Simulator(scene, max_rays=1000)
    ray_segments = simulator.run()

    print(f"  Processed {simulator.processed_ray_count} ray segments")
    print(f"  Total segments stored: {len(ray_segments)}")

    if scene.warning:
        print(f"  Warning: {scene.warning}")
    if scene.error:
        print(f"  Error: {scene.error}")

    # Create SVG visualization
    print("\nCreating SVG visualization...")

    # Set up viewport to show the entire scene
    renderer = SVGRenderer(width=800, height=600, viewbox=(-50, 100, 400, 400))

    # Draw optical elements
    renderer.draw_point({'x': source.x, 'y': source.y}, color='orange', radius=5, label='Source')
    renderer.draw_lens(
        lens.p1,
        lens.p2,
        lens.focal_length,
        color='blue',
        label=f'Lens (f={lens.focal_length})'
    )
    renderer.draw_line_segment(screen.p1, screen.p2, color='black', stroke_width=3, label='Screen')

    # Draw rays
    for ray in ray_segments:
        # Color rays by brightness for visibility
        opacity = min(ray.total_brightness, 1.0)
        renderer.draw_ray_segment(ray, color='red', opacity=opacity, stroke_width=1,extend_to_edge=False)

    # Save outputs to the same directory as this script
    import csv
    import json
    import math

    output_dir = os.path.dirname(__file__)

    # Save SVG
    svg_file = os.path.join(output_dir, 'output.svg')
    renderer.save(svg_file)
    print(f"\nSVG saved to: {svg_file}")

    # Export ray data to CSV
    csv_file = os.path.join(output_dir, 'rays.csv')
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ray_index', 'p1_x', 'p1_y', 'p2_x', 'p2_y', 'brightness_s', 'brightness_p', 'brightness_total', 'wavelength', 'gap', 'length'])
        for i, ray in enumerate(ray_segments):
            dx = ray.p2['x'] - ray.p1['x']
            dy = ray.p2['y'] - ray.p1['y']
            length = math.sqrt(dx*dx + dy*dy)
            writer.writerow([
                i,
                f"{ray.p1['x']:.4f}",
                f"{ray.p1['y']:.4f}",
                f"{ray.p2['x']:.4f}",
                f"{ray.p2['y']:.4f}",
                f"{ray.brightness_s:.6f}",
                f"{ray.brightness_p:.6f}",
                f"{ray.total_brightness:.6f}",
                ray.wavelength if ray.wavelength else '',
                ray.gap,
                f"{length:.4f}"
            ])
    print(f"CSV data exported to: {csv_file}")

    # Export ray data to JSON
    json_file = os.path.join(output_dir, 'rays.json')
    rays_data = {
        'scene': {
            'source': {'x': source.x, 'y': source.y, 'brightness': source.brightness},
            'lens': {
                'p1': lens.p1,
                'p2': lens.p2,
                'focal_length': lens.focal_length
            },
            'screen': {
                'p1': screen.p1,
                'p2': screen.p2
            },
            'ray_density': scene.ray_density
        },
        'simulation': {
            'total_rays_processed': simulator.processed_ray_count,
            'total_segments': len(ray_segments),
            'warning': scene.warning,
            'error': scene.error
        },
        'rays': []
    }

    for i, ray in enumerate(ray_segments):
        dx = ray.p2['x'] - ray.p1['x']
        dy = ray.p2['y'] - ray.p1['y']
        length = math.sqrt(dx*dx + dy*dy)

        rays_data['rays'].append({
            'index': i,
            'p1': {'x': ray.p1['x'], 'y': ray.p1['y']},
            'p2': {'x': ray.p2['x'], 'y': ray.p2['y']},
            'brightness': {
                's': ray.brightness_s,
                'p': ray.brightness_p,
                'total': ray.total_brightness
            },
            'wavelength': ray.wavelength,
            'gap': ray.gap,
            'length': length
        })

    with open(json_file, 'w') as f:
        json.dump(rays_data, f, indent=2)
    print(f"JSON data exported to: {json_file}")
    print("\nExpected result:")
    print("  - Rays diverge from the source in a semicircle")
    print("  - After passing through the lens, rays become parallel")
    print("  - All rays hit the screen at approximately y=300 (source height)")
    print("\nThis demonstrates collimation: a point source at the focal")
    print("point of a lens produces a parallel beam of light.")


if __name__ == '__main__':
    main()
