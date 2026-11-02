"""
Python-specific module: test grazing incidence
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

===============================================================================
GRAZING INCIDENCE DETECTION - Feature Verification Test
===============================================================================

This script tests the Python-specific grazing incidence detection feature.

WHAT IS GRAZING INCIDENCE?
--------------------------
Grazing incidence occurs when light strikes a surface at an angle very close
to the critical angle (the angle at which Total Internal Reflection begins).
At these angles, polarization effects become extreme:

- S-polarized light (electric field perpendicular to plane of incidence) is
  mostly reflected
- P-polarized light (electric field in plane of incidence) is mostly transmitted

This effect is exploited in instruments like the Abbe refractometer, where
the boundary between light and dark regions occurs at the critical angle.

WHY TRACK GRAZING INCIDENCE?
----------------------------
Unlike TIR (where no light is transmitted), grazing incidence still transmits
some light, but with extreme polarization. Tracking these rays is useful for:

1. Abbe refractometer simulations - identifying the critical angle boundary
2. Polarization analysis - understanding extreme s/p ratios
3. Optical system design - identifying rays with unusual behavior
4. Debugging simulations - finding rays near the edge of TIR

THREE INDEPENDENT DETECTION CRITERIA
------------------------------------
The feature uses three independent criteria to detect grazing incidence:

1. ANGLE CRITERION (grazing_angle_threshold)
   - Triggers when incidence angle >= threshold (default 85 degrees)
   - Directly measures proximity to critical angle
   - Most intuitive criterion

2. POLARIZATION RATIO CRITERION (grazing_polarization_ratio_threshold)
   - Triggers when T_p / T_s >= threshold (default 10.0)
   - Detects extreme polarization effects
   - T_p = transmission coefficient for p-polarization
   - T_s = transmission coefficient for s-polarization

3. TRANSMISSION RATIO CRITERION (grazing_transmission_threshold)
   - Triggers when T_ratio < threshold (default 0.1)
   - T_ratio = (brightness_s * T_s + brightness_p * T_p) / total_incident
   - Detects when very little light is transmitted overall

RAY ATTRIBUTES
--------------
Each ray segment has 6 grazing-related boolean attributes:

For each criterion (angle, polar, transm):
- is_grazing_result__<criterion>: True if this segment was PRODUCED by grazing
- caused_grazing__<criterion>: True if this segment's endpoint CAUSED grazing

The "caused" flag is on the INCIDENT ray segment (before refraction).
The "is_result" flag is on the REFRACTED ray segment (after refraction).

SCENE CONFIGURATION
-------------------
Thresholds are configured on the Scene object:
- scene.grazing_angle_threshold = 85.0  # degrees
- scene.grazing_polarization_ratio_threshold = 10.0  # ratio
- scene.grazing_transmission_threshold = 0.1  # fraction

ANALYSIS FUNCTIONS
------------------
The analysis module provides:
- filter_grazing_rays(segments, grazing_only=True, criterion=None)
- get_ray_statistics(segments) - includes grazing_rays_* counts
- save_rays_csv() - exports grazing flags to CSV

===============================================================================
"""

import sys
import math
from pathlib import Path

# Add the src-python directory to the path for imports
src_python = Path(__file__).parent.parent.parent
sys.path.insert(0, str(src_python))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.ray import Ray
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.analysis import filter_grazing_rays, get_ray_statistics


def test_grazing_angle_criterion():
    """Test the angle criterion for grazing incidence detection."""
    print("=" * 70)
    print("TEST 1: Angle Criterion")
    print("=" * 70)
    print()

    # Create scene with angle threshold of 85 degrees
    scene = Scene()
    scene.grazing_angle_threshold = 85.0
    scene.grazing_polarization_ratio_threshold = 100.0  # High to avoid triggering
    scene.grazing_transmission_threshold = 0.001  # Low to avoid triggering

    # Create a rectangular glass slab (horizontal)
    glass = Glass(scene, {
        'path': [
            {'x': -1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': -100, 'arc': False},
            {'x': -1000, 'y': -100, 'arc': False}
        ],
        'refIndex': 1.5
    })
    scene.add_object(glass)

    # Calculate critical angle for n=1.5
    critical_angle = math.degrees(math.asin(1 / 1.5))
    print(f"Glass refractive index: n = {glass.refIndex}")
    print(f"Critical angle (for TIR from inside): {critical_angle:.1f} degrees")
    print(f"Grazing angle threshold: {scene.grazing_angle_threshold} degrees")
    print()

    # Test with a ray at exactly 85 degrees (should trigger)
    angle_deg = 85.0
    angle_rad = math.radians(angle_deg)

    ray = Ray(
        p1={'x': -500, 'y': 100},
        p2={'x': -500 + math.sin(angle_rad), 'y': 100 - math.cos(angle_rad)},
        brightness_s=0.5,
        brightness_p=0.5
    )

    simulator = Simulator(scene, max_rays=10)  # Limit rays for this test
    simulator.add_ray(ray)
    segments = simulator.run()

    # Find segments with grazing flags
    caused = [i for i, s in enumerate(segments) if s.caused_grazing__angle]
    is_result = [i for i, s in enumerate(segments) if s.is_grazing_result__angle]

    print(f"Ray incident at {angle_deg} degrees from normal")
    print(f"Total segments: {len(segments)}")
    print(f"Segments that caused_grazing__angle: {caused}")
    print(f"Segments that is_grazing_result__angle: {is_result}")
    print()

    # Verify the flags are set correctly
    if len(caused) == 1 and len(is_result) == 1:
        # The incident segment should end where the result segment begins
        incident = segments[caused[0]]
        result = segments[is_result[0]]
        print(f"Incident segment: p1=({incident.p1['x']:.2f}, {incident.p1['y']:.2f}) -> "
              f"p2=({incident.p2['x']:.2f}, {incident.p2['y']:.2f})")
        print(f"Result segment:   p1=({result.p1['x']:.2f}, {result.p1['y']:.2f}) -> "
              f"p2=({result.p2['x']:.2f}, {result.p2['y']:.2f})")

        # Check that they share the refraction point
        dx = incident.p2['x'] - result.p1['x']
        dy = incident.p2['y'] - result.p1['y']
        distance = math.sqrt(dx * dx + dy * dy)
        print(f"Refraction point match: distance = {distance:.6f}")

        if distance < 1e-6:
            print("\n[PASS] Angle criterion test passed!")
            return True
        else:
            print("\n[FAIL] Refraction points don't match!")
            return False
    else:
        print(f"\n[FAIL] Expected 1 caused and 1 result segment, got {len(caused)} and {len(is_result)}")
        return False


def test_below_threshold():
    """Test that rays below the threshold are NOT flagged."""
    print()
    print("=" * 70)
    print("TEST 2: Below Threshold (No Grazing)")
    print("=" * 70)
    print()

    scene = Scene()
    scene.grazing_angle_threshold = 85.0

    glass = Glass(scene, {
        'path': [
            {'x': -1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': -100, 'arc': False},
            {'x': -1000, 'y': -100, 'arc': False}
        ],
        'refIndex': 1.5
    })
    scene.add_object(glass)

    # Test with a ray at 45 degrees (should NOT trigger)
    angle_deg = 45.0
    angle_rad = math.radians(angle_deg)

    ray = Ray(
        p1={'x': 0, 'y': 100},
        p2={'x': math.sin(angle_rad), 'y': 100 - math.cos(angle_rad)},
        brightness_s=0.5,
        brightness_p=0.5
    )

    simulator = Simulator(scene, max_rays=10)
    simulator.add_ray(ray)
    segments = simulator.run()

    # Check that no grazing flags are set
    grazing_any = filter_grazing_rays(segments, grazing_only=True)

    print(f"Ray incident at {angle_deg} degrees from normal")
    print(f"Total segments: {len(segments)}")
    print(f"Grazing rays found: {len(grazing_any)}")

    if len(grazing_any) == 0:
        print("\n[PASS] Below-threshold test passed (no false positives)!")
        return True
    else:
        print("\n[FAIL] Found grazing rays when none should exist!")
        return False


def test_filter_functions():
    """Test the filter_grazing_rays function with different criteria."""
    print()
    print("=" * 70)
    print("TEST 3: Filter Functions")
    print("=" * 70)
    print()

    scene = Scene()
    scene.grazing_angle_threshold = 85.0
    scene.grazing_polarization_ratio_threshold = 10.0
    scene.grazing_transmission_threshold = 0.1

    glass = Glass(scene, {
        'path': [
            {'x': -1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': -100, 'arc': False},
            {'x': -1000, 'y': -100, 'arc': False}
        ],
        'refIndex': 1.5
    })
    scene.add_object(glass)

    # Create a ray at 85 degrees
    angle_rad = math.radians(85.0)
    ray = Ray(
        p1={'x': -500, 'y': 100},
        p2={'x': -500 + math.sin(angle_rad), 'y': 100 - math.cos(angle_rad)},
        brightness_s=0.5,
        brightness_p=0.5
    )

    simulator = Simulator(scene, max_rays=100)
    simulator.add_ray(ray)
    segments = simulator.run()

    # Test different filter criteria
    grazing_any = filter_grazing_rays(segments, grazing_only=True)
    grazing_angle = filter_grazing_rays(segments, grazing_only=True, criterion='angle')
    grazing_polar = filter_grazing_rays(segments, grazing_only=True, criterion='polar')
    grazing_transm = filter_grazing_rays(segments, grazing_only=True, criterion='transm')
    non_grazing = filter_grazing_rays(segments, grazing_only=False)

    print(f"Total segments: {len(segments)}")
    print(f"Grazing rays (any criterion): {len(grazing_any)}")
    print(f"Grazing rays (angle only): {len(grazing_angle)}")
    print(f"Grazing rays (polar only): {len(grazing_polar)}")
    print(f"Grazing rays (transm only): {len(grazing_transm)}")
    print(f"Non-grazing rays: {len(non_grazing)}")

    # Verify consistency
    total_check = len(grazing_any) + len(non_grazing)
    print(f"\nConsistency check: grazing + non-grazing = {total_check} (should be {len(segments)})")

    if total_check == len(segments) and len(grazing_angle) > 0:
        print("\n[PASS] Filter functions test passed!")
        return True
    else:
        print("\n[FAIL] Filter functions test failed!")
        return False


def test_statistics():
    """Test the get_ray_statistics function for grazing counts."""
    print()
    print("=" * 70)
    print("TEST 4: Statistics Function")
    print("=" * 70)
    print()

    scene = Scene()
    scene.grazing_angle_threshold = 85.0

    glass = Glass(scene, {
        'path': [
            {'x': -1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': 0, 'arc': False},
            {'x': 1000, 'y': -100, 'arc': False},
            {'x': -1000, 'y': -100, 'arc': False}
        ],
        'refIndex': 1.5
    })
    scene.add_object(glass)

    # Create a ray at 85 degrees
    angle_rad = math.radians(85.0)
    ray = Ray(
        p1={'x': -500, 'y': 100},
        p2={'x': -500 + math.sin(angle_rad), 'y': 100 - math.cos(angle_rad)},
        brightness_s=0.5,
        brightness_p=0.5
    )

    simulator = Simulator(scene, max_rays=100)
    simulator.add_ray(ray)
    segments = simulator.run()

    stats = get_ray_statistics(segments)

    print(f"Statistics from get_ray_statistics():")
    print(f"  total_rays: {stats['total_rays']}")
    print(f"  tir_rays: {stats['tir_rays']}")
    print(f"  grazing_rays_angle: {stats['grazing_rays_angle']}")
    print(f"  grazing_rays_polar: {stats['grazing_rays_polar']}")
    print(f"  grazing_rays_transm: {stats['grazing_rays_transm']}")
    print(f"  grazing_rays_any: {stats['grazing_rays_any']}")

    if stats['grazing_rays_angle'] > 0 and stats['total_rays'] > 0:
        print("\n[PASS] Statistics test passed!")
        return True
    else:
        print("\n[FAIL] Statistics test failed!")
        return False


def test_ray_attributes():
    """Test that Ray class has all grazing attributes."""
    print()
    print("=" * 70)
    print("TEST 5: Ray Attributes")
    print("=" * 70)
    print()

    ray = Ray(
        p1={'x': 0, 'y': 0},
        p2={'x': 1, 'y': 0},
        brightness_s=0.5,
        brightness_p=0.5
    )

    # Check all grazing attributes exist
    attributes = [
        'is_grazing_result__angle',
        'caused_grazing__angle',
        'is_grazing_result__polar',
        'caused_grazing__polar',
        'is_grazing_result__transm',
        'caused_grazing__transm',
    ]

    print("Checking Ray attributes:")
    all_exist = True
    for attr in attributes:
        exists = hasattr(ray, attr)
        value = getattr(ray, attr, 'MISSING')
        status = "[OK]" if exists else "[MISSING]"
        print(f"  {status} {attr} = {value}")
        if not exists:
            all_exist = False

    # Test Ray.copy() preserves is_result flags
    ray.is_grazing_result__angle = True
    ray.is_grazing_result__polar = True
    ray.is_grazing_result__transm = True
    ray.caused_grazing__angle = True  # Should NOT be copied

    copied = ray.copy()

    print("\nAfter copy():")
    print(f"  Original is_grazing_result__angle: {ray.is_grazing_result__angle}")
    print(f"  Copied is_grazing_result__angle: {copied.is_grazing_result__angle}")
    print(f"  Original caused_grazing__angle: {ray.caused_grazing__angle}")
    print(f"  Copied caused_grazing__angle: {copied.caused_grazing__angle} (should be False)")

    copy_correct = (
        copied.is_grazing_result__angle == True and
        copied.caused_grazing__angle == False  # Position-specific, should not copy
    )

    if all_exist and copy_correct:
        print("\n[PASS] Ray attributes test passed!")
        return True
    else:
        print("\n[FAIL] Ray attributes test failed!")
        return False


def test_scene_thresholds():
    """Test that Scene class has configurable grazing thresholds."""
    print()
    print("=" * 70)
    print("TEST 6: Scene Threshold Configuration")
    print("=" * 70)
    print()

    scene = Scene()

    # Check default values
    print("Default threshold values:")
    print(f"  grazing_angle_threshold: {scene.grazing_angle_threshold} degrees")
    print(f"  grazing_polarization_ratio_threshold: {scene.grazing_polarization_ratio_threshold}")
    print(f"  grazing_transmission_threshold: {scene.grazing_transmission_threshold}")

    # Test custom values
    scene.grazing_angle_threshold = 80.0
    scene.grazing_polarization_ratio_threshold = 5.0
    scene.grazing_transmission_threshold = 0.2

    print("\nAfter custom configuration:")
    print(f"  grazing_angle_threshold: {scene.grazing_angle_threshold} degrees")
    print(f"  grazing_polarization_ratio_threshold: {scene.grazing_polarization_ratio_threshold}")
    print(f"  grazing_transmission_threshold: {scene.grazing_transmission_threshold}")

    if (scene.grazing_angle_threshold == 80.0 and
        scene.grazing_polarization_ratio_threshold == 5.0 and
        scene.grazing_transmission_threshold == 0.2):
        print("\n[PASS] Scene thresholds test passed!")
        return True
    else:
        print("\n[FAIL] Scene thresholds test failed!")
        return False


def main():
    """Run all grazing incidence detection tests."""
    print()
    print("=" * 70)
    print("GRAZING INCIDENCE DETECTION - Feature Verification")
    print("=" * 70)
    print()
    print("This test suite verifies the Python-specific grazing incidence")
    print("detection feature. See the module docstring for feature details.")
    print()

    results = []

    results.append(("Angle Criterion", test_grazing_angle_criterion()))
    results.append(("Below Threshold", test_below_threshold()))
    results.append(("Filter Functions", test_filter_functions()))
    results.append(("Statistics Function", test_statistics()))
    results.append(("Ray Attributes", test_ray_attributes()))
    results.append(("Scene Thresholds", test_scene_thresholds()))

    # Summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print()

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}")

    print()
    print(f"Results: {passed}/{total} tests passed")
    print()

    if passed == total:
        print("=" * 70)
        print("ALL TESTS PASSED - Grazing incidence detection is working correctly!")
        print("=" * 70)
        return 0
    else:
        print("=" * 70)
        print("SOME TESTS FAILED - Please review the output above")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
