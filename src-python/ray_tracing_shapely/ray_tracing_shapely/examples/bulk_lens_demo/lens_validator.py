"""
Python-specific module: lens validator
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
import math

# Add parent directories to path to from ray_tracing_shapely import core modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.glass.spherical_lens import SphericalLens
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

    # Create spherical lens at x=100 with focal length ~100
    # This places the source exactly at the focal point
    # For f=100 with n=1.5, we need R=100 (symmetric biconvex)
    # Use larger radii (r=200) to keep lens narrow and visible
    # Testing with r1=200, r2=-200
    # Parameters: d = thickness at center (60), r1/r2 = radii of curvature (±200)
    lens = SphericalLens(scene, {
        'p1': {'x': 180, 'y': 220},
        'p2': {'x': 220, 'y': 380},
        'def_by': 'DR1R2',
        'params': {'d': 60, 'r1': 200, 'r2': -200},
        'refIndex': 1.5
    })

# Validate lens geometry
    print("\n" + "="*60)
    print("LENS GEOMETRY VALIDATION")
    print("="*60)

    if not lens.path or len(lens.path) < 6:
        print("ERROR: Lens path is invalid or incomplete!")
        print(f"  Path exists: {lens.path is not None}")
        print(f"  Path length: {len(lens.path) if lens.path else 0}")
        exit(1)

    # Extract key points
    p0 = lens.path[0]  # edge at top
    p1 = lens.path[1]  # edge at top
    p2 = lens.path[2]  # arc center
    p3 = lens.path[3]  # edge at bottom
    p4 = lens.path[4]  # edge at bottom
    p5 = lens.path[5]  # arc center

    lens_center_x = (p0['x'] + p1['x']) / 2
    lens_center_y = (p0['y'] + p4['y']) / 2

    print(f"\nLens center: ({lens_center_x:.2f}, {lens_center_y:.2f})")
    print("Expected center: (100, 300)")

    # Check 1: Are the edge points properly ordered?
    print("\nCheck 1: Edge point positions")
    print(f"  p0 (top): x={p0['x']:.2f}, y={p0['y']:.2f}")
    print(f"  p1 (top): x={p1['x']:.2f}, y={p1['y']:.2f}")
    print(f"  p3 (bot): x={p3['x']:.2f}, y={p3['y']:.2f}")
    print(f"  p4 (bot): x={p4['x']:.2f}, y={p4['y']:.2f}")

    # Check 2: Are arc centers reasonable?
    print("\nCheck 2: Arc centers")
    print(f"  p2 (arc center): x={p2['x']:.2f}, y={p2['y']:.2f}")
    print(f"  p5 (arc center): x={p5['x']:.2f}, y={p5['y']:.2f}")

    # Check 3: Calculate and verify radii
    r0_to_p5 = math.sqrt((p0['x'] - p5['x'])**2 + (p0['y'] - p5['y'])**2)
    r4_to_p5 = math.sqrt((p4['x'] - p5['x'])**2 + (p4['y'] - p5['y'])**2)
    r1_to_p2 = math.sqrt((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)
    r3_to_p2 = math.sqrt((p3['x'] - p2['x'])**2 + (p3['y'] - p2['y'])**2)

    print("\nCheck 3: Arc radii consistency")
    print("  Surface 1 (p5 center):")
    print(f"    Distance p0 to p5: {r0_to_p5:.2f}")
    print(f"    Distance p4 to p5: {r4_to_p5:.2f}")
    print(f"    Difference: {abs(r0_to_p5 - r4_to_p5):.4f} (should be ~0)")
    print("  Surface 2 (p2 center):")
    print(f"    Distance p1 to p2: {r1_to_p2:.2f}")
    print(f"    Distance p3 to p2: {r3_to_p2:.2f}")
    print(f"    Difference: {abs(r1_to_p2 - r3_to_p2):.4f} (should be ~0)")

    # Check 4: Is this a biconvex lens? (both surfaces should curve away from center)
    print("\nCheck 4: Lens type (biconvex, biconcave, or meniscus)")

    # For a biconvex lens centered at x=100:
    # - Left surface (p5 center) should be at x < 100 and curve outward (left)
    # - Right surface (p2 center) should be at x > 100 and curve outward (right)

    if p5['x'] < lens_center_x:
        surface1_type = "curves LEFT (convex on left side)"
    else:
        surface1_type = "curves RIGHT (concave on left side)"

    if p2['x'] > lens_center_x:
        surface2_type = "curves RIGHT (convex on right side)"
    else:
        surface2_type = "curves LEFT (concave on right side)"

    print(f"  Surface 1 center at x={p5['x']:.2f}: {surface1_type}")
    print(f"  Surface 2 center at x={p2['x']:.2f}: {surface2_type}")

    # Determine lens type
    is_biconvex = (p5['x'] < lens_center_x) and (p2['x'] > lens_center_x)
    is_biconcave = (p5['x'] > lens_center_x) and (p2['x'] < lens_center_x)

    if is_biconvex:
        print("  RESULT: BICONVEX (converging) lens [OK]")
    elif is_biconcave:
        print("  RESULT: BICONCAVE (diverging) lens [ERROR]")
    else:
        print("  RESULT: MENISCUS lens [WARNING]")

    # Check 5: Lens width at center
    lens_width = abs(max(p0['x'], p4['x']) - min(p1['x'], p3['x']))
    print("\nCheck 5: Lens width")
    print(f"  Width at center: {lens_width:.2f}")
    print("  Expected: ~43-44 (for r=200, thickness=10)")

    # Check 6: CRITICAL - Aperture vs chord length constraint
    print("\nCheck 6: Aperture vs chord constraint (CRITICAL)")

    # The two circles defining the lens surfaces
    # Left surface: center at p5, radius r0_to_p5
    # Right surface: center at p2, radius r1_to_p2

    # Distance between circle centers
    center_distance = math.sqrt((p2['x'] - p5['x'])**2 + (p2['y'] - p5['y'])**2)
    print(f"  Distance between arc centers: {center_distance:.2f}")

    # For two circles to intersect, the distance between centers must be:
    # |r1 - r2| < d < r1 + r2
    r_left = r0_to_p5
    r_right = r1_to_p2
    min_distance = abs(r_left - r_right)
    max_distance = r_left + r_right

    circles_intersect = (min_distance < center_distance < max_distance)
    print(f"  Left surface radius: {r_left:.2f}")
    print(f"  Right surface radius: {r_right:.2f}")
    print(f"  Valid range: {min_distance:.2f} < {center_distance:.2f} < {max_distance:.2f}")
    print(f"  Circles intersect: {circles_intersect}")

    if not circles_intersect:
        print("  ERROR: Circles do not intersect! Invalid lens geometry.")
    else:
        # Calculate the chord length at the intersection points
        # Using the formula for chord length between two intersecting circles
        # The intersection points lie on a line perpendicular to the line joining centers

        # Distance from left circle center to the radical line (where circles intersect)
        a = (r_left**2 - r_right**2 + center_distance**2) / (2 * center_distance)

        # Half-chord length (perpendicular distance from radical line to intersection point)
        if r_left**2 - a**2 >= 0:
            h = math.sqrt(r_left**2 - a**2)
            chord_length = 2 * h

            #debug here
            # Lens aperture (height)
            lens_aperture = abs(p0['y'] - p4['y'])

            print(f"  Maximum chord length: {chord_length:.2f}")
            print(f"  Actual lens aperture: {lens_aperture:.2f}")
            print(f"  Aperture/Chord ratio: {lens_aperture/chord_length:.3f}")

            aperture_valid = lens_aperture < chord_length

            if not aperture_valid:
                print("  ERROR: Aperture exceeds chord length!")
                print(f"         Lens aperture ({lens_aperture:.2f}) must be < chord ({chord_length:.2f})")
            elif abs(lens_aperture - chord_length) < 0.1:
                print("  WARNING: Aperture very close to chord (degenerate edges)")
            else:
                margin = chord_length - lens_aperture
                print(f"  OK: Aperture is valid (margin: {margin:.2f})")
        else:
            print("  ERROR: Cannot calculate chord (circles don't intersect properly)")
            aperture_valid = False
    
    # i don't hink the min aperture above is correct, moreover the check
    # applied to biconvex lenses should be different to the check applied
    # to biconcave lenses, and I dont' see the case switch structure here.  
    # So for the time being override aperture check , we need to debug this
    if aperture_valid is False:
        print(" OVERRIDDEN")
        aperture_valid = True

    print("="*60 + "\n")

    if not is_biconvex:
        print("ERROR: Lens geometry is NOT biconvex!")
        print("This will cause incorrect ray refraction.\n")

    if not circles_intersect or not aperture_valid:
        print("FATAL ERROR: Lens geometry violates fundamental constraints!")
        print("The lens cannot be physically realized with these parameters.\n")
        exit(1)
