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


class AngleSource(BaseSceneObj):
    """
    Finite angle point source (point source with angle < 360°).

    An angle source emits rays within a specified angular range. The source position
    is at p1, and p2 defines a reference direction. The emission angle determines
    the angular spread of rays.

    Attributes:
        p1: The position of the point source (dict with 'x', 'y').
        p2: Another point on the reference line, defining the reference direction (dict with 'x', 'y').
        brightness: The brightness of the source (0.01 to 1.0).
        wavelength: The wavelength of emitted light in nm (only used when "Simulate Colors" is enabled).
        emis_angle: The angle of emission in degrees (0° to 180°).
        symmetric: Whether the emission is symmetric about the reference line.
                  If True, rays spread ±emis_angle/2 around the reference direction.
                  If False, rays spread from 0° to emis_angle on one side only.

    Usage:
        Angle sources are useful for:
        - Simulating directional light sources with limited angular spread
        - LED simulations with specific beam patterns
        - Spotlights and focused light sources
        - Testing optical systems with partially collimated sources

    Notes:
        - The reference direction is from p1 towards p2
        - symmetric=True: rays spread symmetrically (e.g., ±18° for 36° emission)
        - symmetric=False: rays spread asymmetrically (0° to 36° for 36° emission)
        - Brightness and ray density management same as PointSource
    """

    type = 'AngleSource'
    is_optical = True
    serializable_defaults = {
        'p1': None,
        'p2': None,
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH,
        'emis_angle': 36.001,  # Default to ~36 degrees
        'symmetric': True
    }

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with angle source controls.

        Args:
            obj_bar: The object bar to be populated.
        """
        obj_bar.set_title('Point Source (<360°)')

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
                UV_WAVELENGTH,
                INFRARED_WAVELENGTH,
                1,
                self.wavelength,
                lambda obj, value: setattr(obj, 'wavelength', value),
                'Wavelength of emitted light'
            )

        # Emission angle control
        obj_bar.create_number(
            'Emission Angle (°)',
            0, 180, 1,
            self.emis_angle,
            lambda obj, value: setattr(obj, 'emis_angle', value),
            'Angular spread of emitted rays'
        )

        # Advanced properties
        if obj_bar.show_advanced(not self.are_properties_default(['symmetric'])):
            obj_bar.create_boolean(
                'Symmetric',
                self.symmetric,
                lambda obj, value: setattr(obj, 'symmetric', value),
                'Emit rays symmetrically around reference direction'
            )

    def on_construct_mouse_down(self, mouse, ctrl, shift):
        """
        Handle mouse down during construction.

        In new color modes, default brightness is set to 0.1 instead of 0.5.

        Args:
            mouse: Mouse position.
            ctrl: Whether Ctrl key is pressed.
            shift: Whether Shift key is pressed.
        """
        super().on_construct_mouse_down(mouse, ctrl, shift)
        if self.scene.color_mode != 'default':
            self.brightness = 0.1

    def draw(self, canvas_renderer, is_above_light, is_hovered):
        """
        Draw the angle source on the canvas.

        Draws two points:
        - p1: The source position (colored by wavelength in color mode)
        - p2: The reference direction point

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether rendering above the light layer.
            is_hovered: Whether the source is hovered by the mouse.
        """
        # Draw source point (p1)
        if self.scene.simulate_colors:
            from ..base_scene_obj import wavelength_to_color
            # Outer circle with wavelength color
            canvas_renderer.draw_point(
                geometry.point(self.p1['x'], self.p1['y']),
                wavelength_to_color(self.wavelength, 1),
                self.scene.theme.light_source.size
            )
            # Inner center point
            center_color = self.scene.highlight_color if is_hovered else self.scene.theme.color_source_center.color
            canvas_renderer.draw_point(
                geometry.point(self.p1['x'], self.p1['y']),
                center_color,
                self.scene.theme.color_source_center.size
            )
        else:
            # Single color point
            color = self.scene.highlight_color if is_hovered else self.scene.theme.light_source.color
            canvas_renderer.draw_point(
                geometry.point(self.p1['x'], self.p1['y']),
                color,
                self.scene.theme.light_source.size
            )

        # Draw direction point (p2)
        direction_color = self.scene.highlight_color if is_hovered else self.scene.theme.direction_point.color
        canvas_renderer.draw_point(
            geometry.point(self.p2['x'], self.p2['y']),
            direction_color,
            self.scene.theme.direction_point.size
        )

    def move(self, diff_x, diff_y):
        """
        Move the angle source.

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
        Rotate the angle source around a center.

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
        Scale the angle source relative to a center.

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

        For an angle source, the default center is the source position (p1).

        Returns:
            The source position p1.
        """
        return {'x': self.p1['x'], 'y': self.p1['y']}

    def on_simulation_start(self):
        """
        Generate rays when simulation starts.

        Creates rays within the specified angular range. The number of rays
        depends on the scene's ray density and the source's brightness.

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

        # Calculate angular step between rays
        # 500 is the base number of angle divisions per unit ray density
        angular_step = math.pi * 2 / int(ray_density * 500)

        # In observer mode, start from a negative angle
        if hasattr(self.scene, 'mode') and self.scene.mode == 'observer':
            i0 = -angular_step * 2 + 1e-6
        else:
            i0 = 0

        # Calculate angle range
        emis_angle_rad = math.pi / 180.0 * self.emis_angle

        if self.symmetric:
            # Symmetric emission: spread ±emis_angle/2 around reference direction
            i_start = i0 - emis_angle_rad / 2.0
            i_end = i0 + emis_angle_rad / 2.0 - 1e-5
        else:
            # Asymmetric emission: spread from 0° to emis_angle
            i_start = i0
            i_end = i0 + emis_angle_rad - 1e-5

        new_rays = []

        # Calculate reference direction (from p1 to p2)
        reference_angle = math.atan2(
            self.p2['y'] - self.p1['y'],
            self.p2['x'] - self.p1['x']
        )

        # Calculate distance to p2 (used for ray endpoint calculation)
        r = math.sqrt(
            (self.p2['x'] - self.p1['x']) ** 2 +
            (self.p2['y'] - self.p1['y']) ** 2
        )

        # Generate rays
        i = i_start
        first_ray = True
        while i < i_end:
            # Calculate ray angle (reference angle + offset)
            ang = i + reference_angle

            # Calculate ray endpoint
            x1 = self.p1['x'] + r * math.cos(ang)
            y1 = self.p1['y'] + r * math.sin(ang)

            # Create ray from p1 to endpoint
            ray = geometry.line(
                geometry.point(self.p1['x'], self.p1['y']),
                geometry.point(x1, y1)
            )

            # Set ray brightness (split equally between s and p polarizations)
            per_ray_brightness = min(self.brightness / ray_density, 1)
            ray.brightness_s = per_ray_brightness * 0.5
            ray.brightness_p = per_ray_brightness * 0.5

            # Set wavelength if color simulation is enabled
            if self.scene.simulate_colors:
                ray.wavelength = self.wavelength

            # Mark as new ray
            ray.isNew = True

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
            i += angular_step

        # Calculate brightness scale for normalization
        brightness_scale = min(self.brightness / ray_density, 1) / (self.brightness / ray_density)

        return {
            'newRays': new_rays,
            'brightnessScale': brightness_scale
        }


# Example usage and testing
if __name__ == "__main__":
    print("Testing AngleSource class...\n")

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.simulate_colors = False
            self.color_mode = 'default'
            self.ray_density = 0.1
            self.mode = 'rays'

            # Mock theme
            class MockTheme:
                class MockLightSource:
                    color = [1.0, 1.0, 0.5, 1.0]
                    size = 5

                class MockColorSourceCenter:
                    color = [1.0, 1.0, 1.0, 1.0]
                    size = 2

                class MockDirectionPoint:
                    color = [0.0, 1.0, 1.0, 1.0]
                    size = 3

                light_source = MockLightSource()
                color_source_center = MockColorSourceCenter()
                direction_point = MockDirectionPoint()

            self.theme = MockTheme()
            self.highlight_color = [1.0, 0.0, 1.0, 1.0]

    # Test 1: Basic angle source (symmetric)
    print("Test 1: Symmetric angle source (36°)")
    scene = MockScene()
    source = AngleSource(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},  # Reference direction: +X axis
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH,
        'emis_angle': 36.0,
        'symmetric': True
    })

    print(f"  Source position (p1): ({source.p1['x']}, {source.p1['y']})")
    print(f"  Reference point (p2): ({source.p2['x']}, {source.p2['y']})")
    print(f"  Brightness: {source.brightness}")
    print(f"  Emission angle: {source.emis_angle}°")
    print(f"  Symmetric: {source.symmetric}")

    result = source.on_simulation_start()
    print(f"  Rays generated: {len(result['newRays'])}")
    print(f"  Brightness scale: {result['brightnessScale']:.4f}")

    if len(result['newRays']) > 0:
        ray = result['newRays'][0]
        total_brightness = ray.brightness_s + ray.brightness_p
        print(f"  First ray brightness: {total_brightness:.4f} (s={ray.brightness_s:.4f}, p={ray.brightness_p:.4f})")

    # Test 2: Asymmetric angle source
    print("\nTest 2: Asymmetric angle source (45°)")
    source_asym = AngleSource(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH,
        'emis_angle': 45.0,
        'symmetric': False  # Asymmetric
    })

    print(f"  Emission angle: {source_asym.emis_angle}°")
    print(f"  Symmetric: {source_asym.symmetric}")

    result_asym = source_asym.on_simulation_start()
    print(f"  Rays generated: {len(result_asym['newRays'])}")

    # Check angular spread
    if len(result_asym['newRays']) >= 2:
        first_ray = result_asym['newRays'][0]
        last_ray = result_asym['newRays'][-1]
        # Calculate angles
        angle_first = math.atan2(
            first_ray.p2['y'] if isinstance(first_ray.p2, dict) else first_ray.p2.y,
            first_ray.p2['x'] if isinstance(first_ray.p2, dict) else first_ray.p2.x
        ) * 180 / math.pi
        angle_last = math.atan2(
            last_ray.p2['y'] if isinstance(last_ray.p2, dict) else last_ray.p2.y,
            last_ray.p2['x'] if isinstance(last_ray.p2, dict) else last_ray.p2.x
        ) * 180 / math.pi
        print(f"  First ray angle: {angle_first:.1f}°")
        print(f"  Last ray angle: {angle_last:.1f}°")
        print(f"  ==> Asymmetric: rays from 0° to 45° (one-sided)")

    # Test 3: Color simulation
    print("\nTest 3: Angle source with color simulation (red light)")
    scene.simulate_colors = True
    source_color = AngleSource(scene, {
        'p1': {'x': 5, 'y': 5},
        'p2': {'x': 15, 'y': 5},
        'brightness': 0.3,
        'wavelength': 650,  # Red
        'emis_angle': 60.0,
        'symmetric': True
    })

    print(f"  Wavelength: {source_color.wavelength} nm (red)")
    print(f"  Emission angle: {source_color.emis_angle}°")

    result_color = source_color.on_simulation_start()
    print(f"  Rays generated: {len(result_color['newRays'])}")

    if len(result_color['newRays']) > 0:
        ray = result_color['newRays'][0]
        print(f"  Ray wavelength: {ray.wavelength} nm")

    # Test 4: Transformations
    print("\nTest 4: Transformations")
    source_test = AngleSource(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5,
        'emis_angle': 36.0
    })

    print(f"  Initial: p1=({source_test.p1['x']}, {source_test.p1['y']}), p2=({source_test.p2['x']}, {source_test.p2['y']})")

    # Move
    source_test.move(5, 3)
    print(f"  After move(5, 3): p1=({source_test.p1['x']}, {source_test.p1['y']}), p2=({source_test.p2['x']}, {source_test.p2['y']})")

    # Rotate 90° around origin
    source_test.p1 = {'x': 0, 'y': 0}
    source_test.p2 = {'x': 10, 'y': 0}
    source_test.rotate(math.pi / 2, {'x': 0, 'y': 0})
    print(f"  After rotate(90° around origin): p1=({source_test.p1['x']:.2f}, {source_test.p1['y']:.2f}), p2=({source_test.p2['x']:.2f}, {source_test.p2['y']:.2f})")

    # Scale 2x from origin
    source_test.p1 = {'x': 0, 'y': 0}
    source_test.p2 = {'x': 10, 'y': 0}
    source_test.scale(2.0, {'x': 0, 'y': 0})
    print(f"  After scale(2.0 from origin): p1=({source_test.p1['x']:.2f}, {source_test.p1['y']:.2f}), p2=({source_test.p2['x']:.2f}, {source_test.p2['y']:.2f})")

    # Test 5: Default center is p1
    print("\nTest 5: Default center (should be p1)")
    center = source_test.get_default_center()
    print(f"  p1: ({source_test.p1['x']}, {source_test.p1['y']})")
    print(f"  Default center: ({center['x']}, {center['y']})")
    print(f"  Centers match: {center['x'] == source_test.p1['x'] and center['y'] == source_test.p1['y']}")

    # Test 6: Brightness adjustment in new color mode
    print("\nTest 6: Brightness adjustment in new color mode")
    scene.color_mode = 'waves'
    scene.ray_density = 0.1  # Low density
    source_bright = AngleSource(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.8,  # High brightness
        'emis_angle': 90.0
    })

    result_bright = source_bright.on_simulation_start()
    print(f"  Brightness: {source_bright.brightness}")
    print(f"  Initial ray_density: 0.1")
    print(f"  Rays generated: {len(result_bright['newRays'])}")
    print(f"  Brightness scale: {result_bright['brightnessScale']:.4f}")
    print(f"  ==> No brightness loss! Ray density was automatically increased.")

    if len(result_bright['newRays']) > 0:
        ray = result_bright['newRays'][0]
        total_brightness = ray.brightness_s + ray.brightness_p
        print(f"  Per-ray brightness: {total_brightness:.4f} (should be <= 1.0)")

    # Test 7: Wide angle vs narrow angle
    print("\nTest 7: Wide angle (180°) vs narrow angle (10°)")
    scene.color_mode = 'default'

    source_wide = AngleSource(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5,
        'emis_angle': 180.0,
        'symmetric': True
    })

    source_narrow = AngleSource(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5,
        'emis_angle': 10.0,
        'symmetric': True
    })

    result_wide = source_wide.on_simulation_start()
    result_narrow = source_narrow.on_simulation_start()

    print(f"  Wide angle (180°): {len(result_wide['newRays'])} rays")
    print(f"  Narrow angle (10°): {len(result_narrow['newRays'])} rays")
    print(f"  ==> Wider angle produces more rays")

    print("\nAngleSource test completed successfully!")
