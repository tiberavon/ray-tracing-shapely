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
    from ray_tracing_shapely.core.constants import GREEN_WAVELENGTH
    from ray_tracing_shapely.core import geometry
else:
    from ..base_scene_obj import BaseSceneObj
    from ...constants import GREEN_WAVELENGTH
    from ... import geometry


class PointSource(BaseSceneObj):
    """
    360-degree point source.

    A point source emits rays uniformly in all directions (360°). The number
    of rays is determined by the scene's ray density setting.

    Attributes:
        x: The x-coordinate of the point source.
        y: The y-coordinate of the point source.
        brightness: The brightness of the source (0.01 to 1.0).
        wavelength: The wavelength of emitted light in nm (only used when
                   "Simulate Colors" is enabled).

    Usage:
        Point sources are useful for:
        - Testing optical systems with diverging light
        - Simulating point-like light sources (LEDs, stars, etc.)
        - Placing at focal points to create collimated beams

    Notes:
        - Brightness represents ray density in default mode
        - In new color modes, brightness is always scaled to 1 for consistent
          detector readings
        - Ray density is automatically adjusted to maintain brightness scale
    """

    type = 'PointSource'
    is_optical = True
    serializable_defaults = {
        'x': None,
        'y': None,
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH
    }

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with point source controls.

        Args:
            obj_bar: The object bar to populate.
        """
        obj_bar.set_title('Point Source (360°)')

        # Brightness control
        if self.scene.color_mode != 'default':
            brightness_info = 'In new color modes, brightness affects the number of rays emitted'
        else:
            brightness_info = 'Controls ray density. Higher values emit more rays per direction.'

        obj_bar.create_number(
            'Brightness',
            0.01, 1, 0.01,
            self.brightness,
            lambda obj, value: setattr(obj, 'brightness', value),
            brightness_info
        )

        # Wavelength control (only in color simulation mode)
        if self.scene.simulate_colors:
            obj_bar.create_number(
                'Wavelength (nm)',
                380, 700, 1,  # UV to IR range
                self.wavelength,
                lambda obj, value: setattr(obj, 'wavelength', value),
                'Wavelength of emitted light'
            )

    def draw(self, canvas_renderer, is_above_light, is_hovered):
        """
        Draw the point source on the canvas.

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether rendering above the light layer.
            is_hovered: Whether the source is hovered by the mouse.
        """
        # Draw outer circle (wavelength color or default)
        if self.scene.simulate_colors:
            from ..base_scene_obj import wavelength_to_color
            color = wavelength_to_color(self.wavelength, 1)
            canvas_renderer.draw_point(
                geometry.point(self.x, self.y),
                color,
                self.scene.theme.light_source.size
            )
            # Draw inner center point
            center_color = self.scene.highlight_color if is_hovered else self.scene.theme.color_source_center.color
            canvas_renderer.draw_point(
                geometry.point(self.x, self.y),
                center_color,
                self.scene.theme.color_source_center.size
            )
        else:
            # Default single color
            color = self.scene.highlight_color if is_hovered else self.scene.theme.light_source.color
            canvas_renderer.draw_point(
                geometry.point(self.x, self.y),
                color,
                self.scene.theme.light_source.size
            )

    def move(self, diff_x, diff_y):
        """
        Move the point source.

        Args:
            diff_x: X displacement.
            diff_y: Y displacement.

        Returns:
            True to indicate the move was successful.
        """
        self.x += diff_x
        self.y += diff_y
        return True

    def rotate(self, angle, center=None):
        """
        Rotate the point source around a center.

        Args:
            angle: Rotation angle in radians.
            center: Center of rotation (defaults to the point itself).

        Returns:
            True to indicate the rotation was successful.
        """
        # Use the point itself as default center if none provided
        if center is None:
            center = self.get_default_center()

        # Apply rotation
        dx = self.x - center['x'] if isinstance(center, dict) else self.x - center.x
        dy = self.y - center['y'] if isinstance(center, dict) else self.y - center.y
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        center_x = center['x'] if isinstance(center, dict) else center.x
        center_y = center['y'] if isinstance(center, dict) else center.y

        self.x = center_x + dx * cos_a - dy * sin_a
        self.y = center_y + dx * sin_a + dy * cos_a

        return True

    def scale(self, scale_factor, center=None):
        """
        Scale the point source position relative to a center.

        Args:
            scale_factor: The scale factor.
            center: Center of scaling (defaults to the point itself).

        Returns:
            True to indicate the scaling was successful.
        """
        # Use the point itself as default center if none provided
        if center is None:
            center = self.get_default_center()

        # Scale the position relative to the center
        center_x = center['x'] if isinstance(center, dict) else center.x
        center_y = center['y'] if isinstance(center, dict) else center.y

        self.x = center_x + (self.x - center_x) * scale_factor
        self.y = center_y + (self.y - center_y) * scale_factor

        return True

    def get_default_center(self):
        """
        Get the default center for rotation/scaling.

        Returns:
            A point representing the source location.
        """
        return {'x': self.x, 'y': self.y}

    def on_simulation_start(self):
        """
        Generate rays when simulation starts.

        This method creates rays emanating uniformly in all directions (360°).
        The number of rays depends on the scene's ray density and the source's
        brightness.

        Returns:
            Dict containing:
                - newRays: List of newly created rays
                - brightnessScale: Scale factor for brightness normalization
        """
        ray_density = self.scene.ray_density

        # In new color modes, adjust ray density to keep brightness <= 1
        expect_brightness = self.brightness / ray_density
        while self.scene.color_mode != 'default' and expect_brightness > 1:
            ray_density += 1 / 500
            expect_brightness = self.brightness / ray_density

        new_rays = []

        # Calculate angular step between rays
        # 500 is the base number of angle divisions per unit ray density
        angular_step = math.pi * 2 / int(ray_density * 500)

        # In observer mode, start from a negative angle
        if hasattr(self.scene, 'mode') and self.scene.mode == 'observer':
            start_angle = -angular_step * 2 + 1e-6
        else:
            start_angle = 0

        # Generate rays in all directions
        angle = start_angle
        first_ray = True

        while angle < (math.pi * 2 - 1e-5):
            # Create ray emanating from the point source
            ray = geometry.line(
                geometry.point(self.x, self.y),
                geometry.point(self.x + math.sin(angle), self.y + math.cos(angle))
            )

            # Set ray brightness (split equally between s and p polarizations)
            per_ray_brightness = min(self.brightness / ray_density, 1)
            ray.brightness_s = per_ray_brightness * 0.5
            ray.brightness_p = per_ray_brightness * 0.5

            # Mark as new ray
            ray.isNew = True

            # Set wavelength if color simulation is enabled
            if self.scene.simulate_colors:
                ray.wavelength = self.wavelength

            # Mark first ray with gap (for image detection)
            if first_ray:
                ray.gap = True
                first_ray = False

            # =====================================================================
            # PYTHON-SPECIFIC FEATURE: Source Tracking
            # =====================================================================
            # Tag rays with source UUID and name for correlation in results
            # =====================================================================
            ray.source_uuid = self.uuid
            ray.source_label = self.name  # Use source's name as the ray label

            new_rays.append(ray)
            angle += angular_step

        # Calculate brightness scale for normalization
        # This tells the renderer what fraction of requested brightness was actually achieved
        # If clamping occurred: brightness_scale < 1.0 (brightness was reduced)
        # If no clamping: brightness_scale = 1.0 (full brightness achieved)
        # Formula: actual_brightness / requested_brightness
        brightness_scale = min(self.brightness / ray_density, 1) / (self.brightness / ray_density)

        return {
            'newRays': new_rays,
            'brightnessScale': brightness_scale
        }


# Example usage and testing
if __name__ == "__main__":
    print("Testing PointSource class...\n")

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.simulate_colors = False
            self.color_mode = 'default'
            self.ray_density = 0.1  # Low density for testing
            self.mode = 'rays'

            # Mock theme
            class MockTheme:
                class MockLightSource:
                    color = [1.0, 1.0, 0.5, 1.0]
                    size = 3

                class MockColorSourceCenter:
                    color = [1.0, 1.0, 1.0, 1.0]
                    size = 1

                light_source = MockLightSource()
                color_source_center = MockColorSourceCenter()

            self.theme = MockTheme()
            self.highlight_color = [1.0, 0.0, 1.0, 1.0]

    # Test 1: Basic point source
    print("Test 1: Basic point source (no color simulation)")
    scene = MockScene()
    source = PointSource(scene, {
        'x': 0,
        'y': 0,
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH
    })

    print(f"  Position: ({source.x}, {source.y})")
    print(f"  Brightness: {source.brightness}")
    print(f"  Wavelength: {source.wavelength} nm")

    # Generate rays
    result = source.on_simulation_start()
    print(f"  Rays generated: {len(result['newRays'])}")
    print(f"  Brightness scale: {result['brightnessScale']:.4f}")

    # Check first few rays
    print("  First 3 rays:")
    for i in range(min(3, len(result['newRays']))):
        ray = result['newRays'][i]
        if hasattr(ray.p2, 'x'):
            dx = ray.p2.x - ray.p1.x
            dy = ray.p2.y - ray.p1.y
        else:
            dx = ray.p2['x'] - ray.p1['x']
            dy = ray.p2['y'] - ray.p1['y']
        angle = math.atan2(dx, dy) * 180 / math.pi
        print(f"    Ray {i}: angle={angle:.1f}°, brightness_s={ray.brightness_s:.4f}, brightness_p={ray.brightness_p:.4f}")

    # Test 2: Point source with color simulation
    print("\nTest 2: Point source with color simulation (red light)")
    scene.simulate_colors = True
    source_red = PointSource(scene, {
        'x': 5,
        'y': 5,
        'brightness': 0.3,
        'wavelength': 650  # Red
    })

    print(f"  Position: ({source_red.x}, {source_red.y})")
    print(f"  Brightness: {source_red.brightness}")
    print(f"  Wavelength: {source_red.wavelength} nm (red)")

    result_red = source_red.on_simulation_start()
    print(f"  Rays generated: {len(result_red['newRays'])}")

    # Check that wavelength is set on rays
    if len(result_red['newRays']) > 0:
        ray = result_red['newRays'][0]
        print(f"  Ray wavelength: {ray.wavelength} nm")

    # Test 3: Movement and transformations
    print("\nTest 3: Movement and transformations")
    source_test = PointSource(scene, {'x': 0, 'y': 0, 'brightness': 0.5})

    print(f"  Initial position: ({source_test.x}, {source_test.y})")

    # Move
    source_test.move(10, 5)
    print(f"  After move(10, 5): ({source_test.x}, {source_test.y})")

    # Rotate around origin
    source_test.x, source_test.y = 10, 0
    source_test.rotate(math.pi / 2, {'x': 0, 'y': 0})
    print(f"  After rotate(90° around origin): ({source_test.x:.2f}, {source_test.y:.2f})")

    # Scale from origin
    source_test.x, source_test.y = 10, 0
    source_test.scale(2.0, {'x': 0, 'y': 0})
    print(f"  After scale(2.0 from origin): ({source_test.x:.2f}, {source_test.y:.2f})")

    # Test 4: Brightness clamping in default mode (IMPORTANT)
    print("\nTest 4: Brightness clamping in default mode")
    print("  This test demonstrates an important behavior:")
    print("  Per-ray brightness is calculated as min(brightness / ray_density, 1)")
    print("  This means low ray_density can cause CLAMPING and LOSS of brightness!\n")

    scene.color_mode = 'default'
    scene.ray_density = 0.1  # Very low density
    source_clamped = PointSource(scene, {
        'x': 0,
        'y': 0,
        'brightness': 0.5
    })

    result_clamped = source_clamped.on_simulation_start()
    expected_per_ray = source_clamped.brightness / scene.ray_density
    actual_per_ray = min(expected_per_ray, 1)

    print(f"  Brightness: {source_clamped.brightness}")
    print(f"  Ray density: {scene.ray_density}")
    print(f"  Expected per-ray brightness (brightness / ray_density): {expected_per_ray:.2f}")
    print(f"  Actual per-ray brightness (min of above, 1.0): {actual_per_ray:.2f}")
    print(f"  Brightness scale (actual / expected): {result_clamped['brightnessScale']:.2f}")
    print(f"  ==> We lose {(1 - result_clamped['brightnessScale']) * 100:.0f}% of requested brightness due to clamping!")

    if len(result_clamped['newRays']) > 0:
        ray = result_clamped['newRays'][0]
        total_brightness = ray.brightness_s + ray.brightness_p
        print(f"  Actual per-ray brightness: {total_brightness:.2f} (s={ray.brightness_s:.2f}, p={ray.brightness_p:.2f})")

    # Test 5: High brightness in new color mode (auto-adjusts ray_density)
    print("\nTest 5: Brightness adjustment in new color mode")
    print("  In new color modes, ray_density is automatically increased")
    print("  to prevent clamping and preserve the requested brightness.\n")

    scene.color_mode = 'waves'
    scene.ray_density = 0.1  # Start with low density
    source_bright = PointSource(scene, {
        'x': 0,
        'y': 0,
        'brightness': 0.8
    })

    result_bright = source_bright.on_simulation_start()
    print(f"  Brightness: {source_bright.brightness}")
    print(f"  Initial ray_density: 0.1")
    print(f"  Rays generated: {len(result_bright['newRays'])}")
    print(f"  Brightness scale: {result_bright['brightnessScale']:.4f}")
    print(f"  ==> No brightness loss! The algorithm increased ray count to avoid clamping.")

    if len(result_bright['newRays']) > 0:
        ray = result_bright['newRays'][0]
        total_brightness = ray.brightness_s + ray.brightness_p
        print(f"  Per-ray brightness: {total_brightness:.4f} (should be <= 1.0)")

    # Test 6: Proper ray_density to avoid clamping
    print("\nTest 6: Using proper ray_density to avoid clamping")
    print("  To avoid clamping in default mode, ensure:")
    print("  ray_density >= brightness (so brightness / ray_density <= 1)\n")

    scene.color_mode = 'default'
    scene.ray_density = 0.5  # Set >= brightness
    source_proper = PointSource(scene, {
        'x': 0,
        'y': 0,
        'brightness': 0.5
    })

    result_proper = source_proper.on_simulation_start()
    expected_per_ray = source_proper.brightness / scene.ray_density
    actual_per_ray = min(expected_per_ray, 1)

    print(f"  Brightness: {source_proper.brightness}")
    print(f"  Ray density: {scene.ray_density}")
    print(f"  Expected per-ray brightness: {expected_per_ray:.2f}")
    print(f"  Actual per-ray brightness: {actual_per_ray:.2f}")
    print(f"  Brightness scale: {result_proper['brightnessScale']:.2f}")
    print(f"  ==> No clamping! Full brightness preserved.")

    if len(result_proper['newRays']) > 0:
        ray = result_proper['newRays'][0]
        total_brightness = ray.brightness_s + ray.brightness_p
        print(f"  Actual per-ray brightness: {total_brightness:.2f}")

    print("\nPointSource test completed successfully!")
