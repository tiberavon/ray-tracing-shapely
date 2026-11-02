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

import math
from typing import Dict, Any, Optional

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_scene_obj import BaseSceneObj
    from ray_tracing_shapely.core.constants import GREEN_WAVELENGTH, UV_WAVELENGTH, INFRARED_WAVELENGTH
    from ray_tracing_shapely.core import geometry
else:
    from ..base_scene_obj import BaseSceneObj
    from ...constants import GREEN_WAVELENGTH, UV_WAVELENGTH, INFRARED_WAVELENGTH
    from ... import geometry


class SingleRay(BaseSceneObj):
    """
    A single ray of light.

    A single ray is defined by two points: a starting point (p1) and a direction
    point (p2). The ray originates from p1 and passes through p2, continuing
    infinitely in that direction.

    Attributes:
        p1: The start point of the ray (dict with 'x', 'y').
        p2: Another point on the ray, defining the direction (dict with 'x', 'y').
        brightness: The brightness of the ray (0.01 to 1.0).
        wavelength: The wavelength of the ray in nm (only used when "Simulate Colors" is enabled).

    Usage:
        Single rays are useful for:
        - Testing specific ray paths through optical systems
        - Debugging optical configurations
        - Educational demonstrations of ray behavior
        - Creating specific ray trajectories

    Notes:
        - Unlike beams or point sources, a single ray emits exactly one ray
        - The ray starts at p1 and travels through p2
        - Brightness is not affected by ray density (only one ray)
        - In color simulation mode, the ray's wavelength determines its color
    """

    type = 'SingleRay'
    is_optical = True
    serializable_defaults = {
        'p1': None,
        'p2': None,
        'brightness': 1.0,
        'wavelength': GREEN_WAVELENGTH
    }

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with single ray controls.

        Args:
            obj_bar: The object bar to populate.
        """
        obj_bar.set_title('Single Ray')

        # Brightness control
        obj_bar.create_number(
            'Brightness',
            0.01, 1.0, 0.01,
            self.brightness,
            lambda obj, value: setattr(obj, 'brightness', value),
            'Brightness of the single ray'
        )

        # Wavelength control (only in color simulation mode)
        if self.scene.simulate_colors:
            obj_bar.create_number(
                'Wavelength (nm)',
                UV_WAVELENGTH,
                INFRARED_WAVELENGTH,
                1,
                self.wavelength,
                lambda obj, value: setattr(obj, 'wavelength', value),
                'Wavelength of emitted light'
            )

    def draw(self, canvas_renderer, is_above_light, is_hovered):
        """
        Draw the single ray on the canvas.

        Draws two points:
        - p1: The source point (colored by wavelength in color mode)
        - p2: The direction point (shows ray direction)

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether rendering above the light layer.
            is_hovered: Whether the ray is hovered by the mouse.
        """
        # Get colors from theme
        source_color = self.scene.theme.source_point.color
        direction_color = self.scene.theme.direction_point.color

        # In color simulation mode, use wavelength color for source point
        if self.scene.simulate_colors:
            from ..base_scene_obj import wavelength_to_color
            source_color = wavelength_to_color(self.wavelength, 1)

        # Override with highlight color if hovered
        if is_hovered:
            source_color = self.scene.highlight_color
            direction_color = self.scene.highlight_color

        # Draw source point (p1)
        canvas_renderer.draw_point(
            geometry.point(self.p1['x'], self.p1['y']),
            source_color,
            self.scene.theme.source_point.size
        )

        # Draw direction point (p2)
        canvas_renderer.draw_point(
            geometry.point(self.p2['x'], self.p2['y']),
            direction_color,
            self.scene.theme.direction_point.size
        )

    def move(self, diff_x, diff_y):
        """
        Move the single ray.

        Args:
            diff_x: X displacement.
            diff_y: Y displacement.

        Returns:
            True to indicate the move was successful.
        """
        self.p1['x'] += diff_x
        self.p1['y'] += diff_y
        self.p2['x'] += diff_x
        self.p2['y'] += diff_y
        return True

    def rotate(self, angle, center=None):
        """
        Rotate the single ray around a center.

        Args:
            angle: Rotation angle in radians.
            center: Center of rotation (defaults to p1).

        Returns:
            True to indicate the rotation was successful.
        """
        if center is None:
            center = self.get_default_center()

        # Rotate p1
        dx1 = self.p1['x'] - center['x']
        dy1 = self.p1['y'] - center['y']
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        self.p1['x'] = center['x'] + dx1 * cos_a - dy1 * sin_a
        self.p1['y'] = center['y'] + dx1 * sin_a + dy1 * cos_a

        # Rotate p2
        dx2 = self.p2['x'] - center['x']
        dy2 = self.p2['y'] - center['y']
        self.p2['x'] = center['x'] + dx2 * cos_a - dy2 * sin_a
        self.p2['y'] = center['y'] + dx2 * sin_a + dy2 * cos_a

        return True

    def scale(self, scale_factor, center=None):
        """
        Scale the single ray relative to a center.

        Args:
            scale_factor: The scale factor.
            center: Center of scaling (defaults to p1).

        Returns:
            True to indicate the scaling was successful.
        """
        if center is None:
            center = self.get_default_center()

        # Scale positions
        self.p1['x'] = center['x'] + (self.p1['x'] - center['x']) * scale_factor
        self.p1['y'] = center['y'] + (self.p1['y'] - center['y']) * scale_factor
        self.p2['x'] = center['x'] + (self.p2['x'] - center['x']) * scale_factor
        self.p2['y'] = center['y'] + (self.p2['y'] - center['y']) * scale_factor

        return True

    def get_default_center(self):
        """
        Get the default center for rotation/scaling.

        For a single ray, the default center is the source point (p1).

        Returns:
            The source point p1.
        """
        return {'x': self.p1['x'], 'y': self.p1['y']}

    def on_simulation_start(self):
        """
        Generate the ray when simulation starts.

        A single ray always generates exactly one ray from p1 through p2.

        Returns:
            Dict containing:
                - newRays: List containing the single ray
        """
        # Create ray from p1 through p2
        ray = geometry.line(
            geometry.point(self.p1['x'], self.p1['y']),
            geometry.point(self.p2['x'], self.p2['y'])
        )

        # Set ray brightness (split equally between s and p polarizations)
        ray.brightness_s = 0.5 * self.brightness
        ray.brightness_p = 0.5 * self.brightness

        # Set wavelength if color simulation is enabled
        if self.scene.simulate_colors:
            ray.wavelength = self.wavelength

        # Mark as gap ray (for image detection)
        ray.gap = True

        # Mark as new ray
        ray.isNew = True

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Source Tracking
        # =====================================================================
        # Tag the ray with the source's UUID and name for correlation in results
        # =====================================================================
        ray.source_uuid = self.uuid
        ray.source_label = self.name  # Use source's name as the ray label

        return {
            'newRays': [ray]
        }


# Example usage and testing
if __name__ == "__main__":
    print("Testing SingleRay class...\n")

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.simulate_colors = False

            # Mock theme
            class MockTheme:
                class MockSourcePoint:
                    color = [1.0, 1.0, 0.0, 1.0]  # Yellow
                    size = 5

                class MockDirectionPoint:
                    color = [0.0, 1.0, 1.0, 1.0]  # Cyan
                    size = 3

                source_point = MockSourcePoint()
                direction_point = MockDirectionPoint()

            self.theme = MockTheme()
            self.highlight_color = [1.0, 0.0, 1.0, 1.0]  # Magenta

    # Test 1: Basic single ray
    print("Test 1: Basic single ray (no color simulation)")
    scene = MockScene()
    ray = SingleRay(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 5},
        'brightness': 1.0,
        'wavelength': GREEN_WAVELENGTH
    })

    print(f"  Start point (p1): ({ray.p1['x']}, {ray.p1['y']})")
    print(f"  Direction point (p2): ({ray.p2['x']}, {ray.p2['y']})")
    print(f"  Brightness: {ray.brightness}")
    print(f"  Wavelength: {ray.wavelength} nm")

    # Generate ray
    result = ray.on_simulation_start()
    print(f"  Rays generated: {len(result['newRays'])}")

    # Check ray properties
    generated_ray = result['newRays'][0]
    print(f"  Ray brightness: {generated_ray.brightness_s + generated_ray.brightness_p:.2f}")
    print(f"    (s={generated_ray.brightness_s:.2f}, p={generated_ray.brightness_p:.2f})")
    print(f"  Ray is new: {generated_ray.isNew}")
    print(f"  Ray has gap: {generated_ray.gap}")

    # Test 2: Single ray with color simulation
    print("\nTest 2: Single ray with color simulation (red light)")
    scene.simulate_colors = True
    ray_red = SingleRay(scene, {
        'p1': {'x': 5, 'y': 5},
        'p2': {'x': 15, 'y': 10},
        'brightness': 0.5,
        'wavelength': 650  # Red
    })

    print(f"  Start point: ({ray_red.p1['x']}, {ray_red.p1['y']})")
    print(f"  Direction point: ({ray_red.p2['x']}, {ray_red.p2['y']})")
    print(f"  Brightness: {ray_red.brightness}")
    print(f"  Wavelength: {ray_red.wavelength} nm (red)")

    result_red = ray_red.on_simulation_start()
    print(f"  Rays generated: {len(result_red['newRays'])}")

    # Check wavelength is set
    if len(result_red['newRays']) > 0:
        generated_ray_red = result_red['newRays'][0]
        print(f"  Ray wavelength: {generated_ray_red.wavelength} nm")
        print(f"  Ray brightness: {generated_ray_red.brightness_s + generated_ray_red.brightness_p:.2f}")

    # Test 3: Transformations
    print("\nTest 3: Transformations")
    ray_test = SingleRay(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 1.0
    })

    print(f"  Initial: p1=({ray_test.p1['x']}, {ray_test.p1['y']}), p2=({ray_test.p2['x']}, {ray_test.p2['y']})")

    # Move
    ray_test.move(5, 3)
    print(f"  After move(5, 3): p1=({ray_test.p1['x']}, {ray_test.p1['y']}), p2=({ray_test.p2['x']}, {ray_test.p2['y']})")

    # Rotate 90° around origin
    ray_test.p1 = {'x': 0, 'y': 0}
    ray_test.p2 = {'x': 10, 'y': 0}
    ray_test.rotate(math.pi / 2, {'x': 0, 'y': 0})
    print(f"  After rotate(90° around origin): p1=({ray_test.p1['x']:.2f}, {ray_test.p1['y']:.2f}), p2=({ray_test.p2['x']:.2f}, {ray_test.p2['y']:.2f})")

    # Scale 2x from origin
    ray_test.p1 = {'x': 0, 'y': 0}
    ray_test.p2 = {'x': 10, 'y': 0}
    ray_test.scale(2.0, {'x': 0, 'y': 0})
    print(f"  After scale(2.0 from origin): p1=({ray_test.p1['x']:.2f}, {ray_test.p1['y']:.2f}), p2=({ray_test.p2['x']:.2f}, {ray_test.p2['y']:.2f})")

    # Test 4: Default center is p1
    print("\nTest 4: Default center (should be p1)")
    ray_center = SingleRay(scene, {
        'p1': {'x': 3, 'y': 7},
        'p2': {'x': 10, 'y': 15},
        'brightness': 1.0
    })

    center = ray_center.get_default_center()
    print(f"  p1: ({ray_center.p1['x']}, {ray_center.p1['y']})")
    print(f"  Default center: ({center['x']}, {center['y']})")
    print(f"  Centers match: {center['x'] == ray_center.p1['x'] and center['y'] == ray_center.p1['y']}")

    # Test 5: Rotation around default center (p1)
    print("\nTest 5: Rotation around default center (p1)")
    ray_rot = SingleRay(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 1.0
    })

    print(f"  Before rotation: p1=({ray_rot.p1['x']}, {ray_rot.p1['y']}), p2=({ray_rot.p2['x']}, {ray_rot.p2['y']})")
    ray_rot.rotate(math.pi / 2)  # 90° rotation, no center specified (uses p1)
    print(f"  After 90° rotation: p1=({ray_rot.p1['x']:.2f}, {ray_rot.p1['y']:.2f}), p2=({ray_rot.p2['x']:.2f}, {ray_rot.p2['y']:.2f})")
    print(f"  p1 stayed at origin: {abs(ray_rot.p1['x']) < 0.01 and abs(ray_rot.p1['y']) < 0.01}")
    print(f"  p2 rotated to y-axis: {abs(ray_rot.p2['x']) < 0.01 and abs(ray_rot.p2['y'] - 10) < 0.01}")

    # Test 6: Different brightness values
    print("\nTest 6: Different brightness values")
    for brightness_val in [0.01, 0.5, 1.0]:
        ray_bright = SingleRay(scene, {
            'p1': {'x': 0, 'y': 0},
            'p2': {'x': 10, 'y': 0},
            'brightness': brightness_val
        })
        result_bright = ray_bright.on_simulation_start()
        generated = result_bright['newRays'][0]
        total_brightness = generated.brightness_s + generated.brightness_p
        print(f"  Brightness {brightness_val:.2f} -> Ray brightness: {total_brightness:.2f}")

    print("\nSingleRay test completed successfully!")
