"""
Python-specific module: test glass geometry
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

Test script for glass geometry analysis using the coupled prisms setup.

This demonstrates how to use analyze_scene_geometry to find:
- Interfaces between adjacent glasses
- Boundary properties (area, centroid)
- Interface properties (length, center, normal)
"""

import sys
import os

# Add the src_python directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs import Glass
from ray_tracing_shapely.analysis import analyze_scene_geometry


def test_coupled_prisms_geometry():
    """Test geometry analysis with the coupled prisms setup."""
    print("=" * 60)
    print("Testing Glass Geometry Analysis with Coupled Prisms")
    print("=" * 60)

    # Refractive indices
    prisms_ref_index = 1.7
    medium_ref_index = 1.5

    # Create scene
    scene = Scene()
    scene.ray_density = 0.1
    scene.color_mode = 'linear'
    scene.mode = 'rays'

    # Create measuring prism (bottom)
    meas_prism = Glass(scene)
    meas_prism.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 188, 'y': 104, 'arc': False}
    ]
    meas_prism.not_done = False
    meas_prism.refIndex = prisms_ref_index

    # Create medium in between prisms
    medium = Glass(scene)
    medium.path = [
        {'x': 167, 'y': 61, 'arc': False},
        {'x': 274, 'y': 61, 'arc': False},
        {'x': 274, 'y': 55, 'arc': False},
        {'x': 167, 'y': 55, 'arc': False}
    ]
    medium.not_done = False
    medium.refIndex = medium_ref_index

    # Create illumination prism (top)
    ill_prism = Glass(scene)
    ill_prism.path = [
        {'x': 167, 'y': 55, 'arc': False},
        {'x': 274, 'y': 55, 'arc': False},
        {'x': 253, 'y': 13, 'arc': False}
    ]
    ill_prism.not_done = False
    ill_prism.refIndex = prisms_ref_index

    # Add objects to scene
    scene.add_object(meas_prism)
    scene.add_object(medium)
    scene.add_object(ill_prism)

    print(f"\nScene setup:")
    print(f"  - Measuring prism (n={prisms_ref_index})")
    print(f"  - Medium layer (n={medium_ref_index})")
    print(f"  - Illumination prism (n={prisms_ref_index})")

    # Analyze geometry
    print("\n" + "-" * 60)
    print("Running geometry analysis...")
    print("-" * 60)

    analysis = analyze_scene_geometry(scene)

    print(f"\nAnalysis result: {analysis}")

    # Report on boundaries
    print("\n" + "=" * 60)
    print("GLASS BOUNDARIES")
    print("=" * 60)

    for i, boundary in enumerate(analysis.boundaries):
        print(f"\nBoundary {i + 1}:")
        print(f"  Refractive index: {boundary.n:.3f}")
        print(f"  Area: {boundary.area:.2f} sq units")
        print(f"  Perimeter: {boundary.perimeter:.2f} units")
        print(f"  Centroid: ({boundary.centroid.x:.2f}, {boundary.centroid.y:.2f})")
        print(f"  Bounds: {boundary.bounds}")

    # Report on interfaces
    print("\n" + "=" * 60)
    print("GLASS INTERFACES (shared edges)")
    print("=" * 60)

    for i, interface in enumerate(analysis.interfaces):
        print(f"\nInterface {i + 1}:")
        print(f"  Between n={interface.n1:.3f} and n={interface.n2:.3f}")
        print(f"  Length: {interface.length:.2f} units")
        print(f"  Center: ({interface.center.x:.2f}, {interface.center.y:.2f})")
        normal = interface.normal_at(0.5)
        print(f"  Normal (at center): ({normal[0]:.4f}, {normal[1]:.4f})")
        print(f"  Start point: ({interface.start_point.x:.2f}, {interface.start_point.y:.2f})")
        print(f"  End point: ({interface.end_point.x:.2f}, {interface.end_point.y:.2f})")

    # Report on exterior edges
    print("\n" + "=" * 60)
    print("EXTERIOR EDGES (exposed to air)")
    print("=" * 60)

    print(f"\nTotal exterior edges: {len(analysis.exterior_edges)}")
    print(f"Total exterior length: {analysis.total_exterior_length:.2f} units")

    for i, edge in enumerate(analysis.exterior_edges):
        print(f"\nExterior edge {i + 1}:")
        print(f"  Length: {edge.length:.2f} units")
        center = edge.interpolate(0.5, normalized=True)
        print(f"  Center: ({center.x:.2f}, {center.y:.2f})")

    # Test specific interface lookup
    print("\n" + "=" * 60)
    print("SPECIFIC INTERFACE LOOKUP")
    print("=" * 60)

    # Find interface between meas_prism and medium
    meas_medium = analysis.get_interface_between(meas_prism, medium)
    if meas_medium:
        print(f"\nMeasuring prism - Medium interface:")
        print(f"  Length: {meas_medium.length:.2f}")
        print(f"  This is where light passes from prism (n={meas_medium.n1:.2f}) to medium (n={meas_medium.n2:.2f})")
    else:
        print("\nNo interface found between measuring prism and medium")

    # Find interface between medium and ill_prism
    medium_ill = analysis.get_interface_between(medium, ill_prism)
    if medium_ill:
        print(f"\nMedium - Illumination prism interface:")
        print(f"  Length: {medium_ill.length:.2f}")
        print(f"  This is where light passes from medium (n={medium_ill.n1:.2f}) to prism (n={medium_ill.n2:.2f})")
    else:
        print("\nNo interface found between medium and illumination prism")

    # Get all interfaces for the medium
    print(f"\nAll interfaces involving the medium layer:")
    medium_interfaces = analysis.get_interfaces_for(medium)
    for interface in medium_interfaces:
        other_n = interface.n1 if interface.glass2 is medium else interface.n2
        print(f"  Interface with n={other_n:.2f}, length={interface.length:.2f}")

    print("\n" + "=" * 60)
    print("TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)

    return analysis


if __name__ == '__main__':
    test_coupled_prisms_geometry()
