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

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_scene_obj import BaseSceneObj
    from ray_tracing_shapely.core.constants import GREEN_WAVELENGTH, UV_WAVELENGTH, INFRARED_WAVELENGTH
    from ray_tracing_shapely.core import geometry
else:
    from ..base_scene_obj import BaseSceneObj
    from ...constants import GREEN_WAVELENGTH, UV_WAVELENGTH, INFRARED_WAVELENGTH
    from ... import geometry


class Beam(BaseSceneObj):
    """
    A parallel or divergent beam of light.

    A beam is defined by a line segment perpendicular to the beam direction.
    Rays are emitted from points along this segment, optionally with divergence.

    Attributes:
        p1: The first endpoint of the segment perpendicular to the beam (dict with 'x', 'y').
        p2: The second endpoint of the segment perpendicular to the beam (dict with 'x', 'y').
        brightness: The brightness of the beam (ray density).
        wavelength: The wavelength of the beam in nm (only used when "Simulate Colors" is enabled).
        emis_angle: The angle of divergence in degrees (0 = parallel beam).
        lambert: Whether the beam is Lambertian (cosine intensity distribution).
        random: Whether the beam uses random ray positioning.
        random_numbers: Random numbers used for random beam (cached for consistency).

    Usage:
        Beams are useful for:
        - Simulating collimated light (laser beams, sunlight, etc.)
        - Testing optical systems with parallel light
        - Creating divergent beams with emis_angle > 0
        - Lambertian sources (cosine distribution) with lambert=True

    Notes:
        - Beam direction is perpendicular to the line segment (p1, p2)
        - emis_angle controls beam divergence (0° = parallel, 180° = full hemisphere)
        - lambert mode applies cosine weighting to ray brightness (useful for LED simulations)
        - random mode distributes rays randomly instead of uniformly
        - In images/observer mode, divergent/random beams may cause detection issues
    """

    type = 'Beam'
    is_optical = True
    serializable_defaults = {
        'p1': None,
        'p2': None,
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH,
        'emis_angle': 0.0,
        'lambert': False,
        'random': False
    }

    def __init__(self, scene, json_obj=None):
        """
        Initialize the beam.

        Args:
            scene: The scene this beam belongs to.
            json_obj: Optional JSON object with beam properties.
        """
        super().__init__(scene, json_obj)

        # Initialize random numbers array (will be populated lazily)
        if not hasattr(self, 'random_numbers'):
            self.random_numbers = []

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with beam controls.

        Args:
            obj_bar: The object bar to populate.
        """
        obj_bar.set_title('Beam')

        # Brightness control
        if self.scene.color_mode != 'default':
            brightness_info = 'In new color modes, brightness affects the number of rays emitted'
        else:
            brightness_info = 'Controls ray density. Higher values emit more rays.'

        obj_bar.create_number(
            'Brightness',
            0.01 / self.scene.length_scale,
            1 / self.scene.length_scale,
            0.01 / self.scene.length_scale,
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

        # Advanced properties
        if obj_bar.show_advanced(not self.are_properties_default(['emis_angle', 'lambert', 'random'])):
            obj_bar.create_number(
                'Emission Angle (°)',
                0, 180, 1,
                self.emis_angle,
                lambda obj, value: setattr(obj, 'emis_angle', value),
                'Angle of beam divergence (0° = parallel beam)'
            )

            obj_bar.create_boolean(
                'Lambert',
                self.lambert,
                lambda obj, value: setattr(obj, 'lambert', value),
                'Apply Lambertian (cosine) intensity distribution'
            )

            obj_bar.create_boolean(
                'Random',
                self.random,
                lambda obj, value: setattr(obj, 'random', value),
                'Use random ray positioning'
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
        Draw the beam on the canvas.

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether rendering above the light layer.
            is_hovered: Whether the beam is hovered by the mouse.
        """
        # Handle degenerate case (both endpoints at same location)
        if self.p1['x'] == self.p2['x'] and self.p1['y'] == self.p2['y']:
            canvas_renderer.draw_rect(
                self.p1['x'] - 1.5 * canvas_renderer.length_scale,
                self.p1['y'] - 1.5 * canvas_renderer.length_scale,
                3 * canvas_renderer.length_scale,
                3 * canvas_renderer.length_scale,
                [128, 128, 128, 255]
            )
            return

        # Calculate angle perpendicular to the beam direction
        angle_l = math.atan2(
            self.p1['x'] - self.p2['x'],
            self.p1['y'] - self.p2['y']
        ) - math.pi / 2

        # Draw main beam line (with wavelength color or default)
        if self.scene.simulate_colors:
            from ..base_scene_obj import wavelength_to_color
            color_array = wavelength_to_color(self.wavelength, 1)
        else:
            color_array = self.scene.theme.light_source.color

        stroke_color = self.scene.highlight_color if is_hovered else color_array
        line_width = self.scene.theme.light_source.size * 4 / 5 * canvas_renderer.length_scale

        # Offset the beam line slightly perpendicular to the segment
        offset = self.scene.theme.light_source.size * 2 / 5 * canvas_renderer.length_scale
        x1_offset = self.p1['x'] + math.sin(angle_l) * offset
        y1_offset = self.p1['y'] + math.cos(angle_l) * offset
        x2_offset = self.p2['x'] + math.sin(angle_l) * offset
        y2_offset = self.p2['y'] + math.cos(angle_l) * offset

        canvas_renderer.draw_line(
            geometry.point(x1_offset, y1_offset),
            geometry.point(x2_offset, y2_offset),
            stroke_color,
            line_width
        )

        # Draw beam shield (perpendicular line showing beam width)
        shield_color = self.scene.theme.beam_shield.color
        shield_width = self.scene.theme.beam_shield.width * canvas_renderer.length_scale

        canvas_renderer.draw_line(
            geometry.point(self.p1['x'], self.p1['y']),
            geometry.point(self.p2['x'], self.p2['y']),
            shield_color,
            shield_width
        )

    def move(self, diff_x, diff_y):
        """
        Move the beam.

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
        Rotate the beam around a center.

        Args:
            angle: Rotation angle in radians.
            center: Center of rotation (defaults to beam center).

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
        Scale the beam relative to a center.

        Also adjusts brightness to maintain total light output.

        Args:
            scale_factor: The scale factor.
            center: Center of scaling (defaults to beam center).

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

        # Adjust brightness (inversely proportional to scale)
        # This maintains the same total light output as the beam length changes
        self.brightness /= scale_factor

        return True

    def get_default_center(self):
        """
        Get the default center for rotation/scaling.

        Returns:
            The midpoint of the beam segment.
        """
        return {
            'x': (self.p1['x'] + self.p2['x']) / 2,
            'y': (self.p1['y'] + self.p2['y']) / 2
        }

    def on_simulation_start(self):
        """
        Generate rays when simulation starts.

        This method creates rays along the beam segment, optionally with divergence.
        The number of rays depends on the scene's ray density, beam length, and
        emission angle.

        Returns:
            Dict containing:
                - newRays: List of newly created rays
                - brightnessScale: Scale factor for brightness normalization
                - warning: Optional warning message (for image detection mode with divergence)

        Raises:
            ValueError: If emis_angle is negative. C-BEAM-01
                (dev_doc/architecture/contracts/C-BEAM-01.md): emis_angle is
                a full divergence angle and must be non-negative. Left
                unguarded, a negative value drives num_angled_rays negative
                below, silently flipping the sign of every emitted ray's
                brightness -- this was previously this contract's one
                confirmed-live, still-open defect.
        """
        if self.emis_angle < 0:
            raise ValueError(
                f"Beam.emis_angle must be non-negative (it is a full "
                f"divergence angle in degrees, not a signed rotation), got "
                f"{self.emis_angle}. See C-BEAM-01."
            )

        # Check for image detection warning
        if (hasattr(self.scene, 'mode') and
            (self.scene.mode == 'images' or self.scene.mode == 'observer') and
            (self.emis_angle > 0 or self.random)):
            self.warning = 'Beam with divergence or randomness may cause issues in image detection mode'
        else:
            self.warning = None

        ray_density = self.scene.ray_density

        # Adjust ray density to keep brightness <= 1 in new color modes
        while True:
            # Calculate number of rays along the beam
            segment_length = geometry.segment_length(
                geometry.line(
                    geometry.point(self.p1['x'], self.p1['y']),
                    geometry.point(self.p2['x'], self.p2['y'])
                )
            )
            n = segment_length * ray_density / self.scene.length_scale

            # Calculate ray positions along the beam
            step_x = (self.p2['x'] - self.p1['x']) / n
            step_y = (self.p2['y'] - self.p1['y']) / n

            # Calculate angular spacing for divergent rays
            s = math.pi * 2 / int(ray_density * 500)

            # Calculate normal direction (perpendicular to beam segment)
            normal = math.atan2(step_x, step_y) + math.pi / 2.0

            # Calculate number of angled rays
            half_angle = self.emis_angle / 180.0 * math.pi * 0.5
            num_angled_rays = 1.0 + math.floor(half_angle / s) * 2.0
            ray_brightness = 1.0 / num_angled_rays

            # Calculate expected brightness per ray
            expect_brightness = (self.brightness * self.scene.length_scale /
                               ray_density * ray_brightness)

            # In new color modes, increase ray density if brightness would exceed 1
            if self.scene.color_mode != 'default' and expect_brightness > 1:
                ray_density += 1 / 500
            else:
                break

        # Initialize random numbers if needed
        self.init_random()

        new_rays = []

        if not self.random:
            # Deterministic ray placement
            # Use max(1, ...) to ensure at least 1 ray is generated
            num_positions = max(1, int(n))
            for i in range(num_positions):
                i_pos = i + 0.5  # Center ray within segment
                x = self.p1['x'] + i_pos * step_x
                y = self.p1['y'] + i_pos * step_y

                # Create central ray
                new_rays.append(
                    self.new_ray(x, y, normal, 0.0, i == 0, ray_brightness, ray_density)
                )

                # Create angled rays if divergence > 0
                angle = s
                while angle < half_angle:
                    new_rays.append(
                        self.new_ray(x, y, normal, angle, i == 0, ray_brightness, ray_density)
                    )
                    new_rays.append(
                        self.new_ray(x, y, normal, -angle, i == 0, ray_brightness, ray_density)
                    )
                    angle += s
        else:
            # Random ray placement
            size_x = self.p2['x'] - self.p1['x']
            size_y = self.p2['y'] - self.p1['y']

            # Use max(1, ...) to ensure at least 1 ray is generated
            num_random_rays = max(1, int(n * num_angled_rays))
            for i in range(num_random_rays):
                position = self.get_random(i * 2)
                angle = self.get_random(i * 2 + 1)

                new_rays.append(
                    self.new_ray(
                        self.p1['x'] + position * size_x,
                        self.p1['y'] + position * size_y,
                        normal,
                        (angle * 2 - 1) * half_angle,
                        i == 0,
                        ray_brightness,
                        ray_density
                    )
                )

        # Calculate brightness scale
        actual_brightness = min(
            self.brightness * self.scene.length_scale / ray_density * ray_brightness,
            1
        )
        requested_brightness = self.brightness * self.scene.length_scale / ray_density * ray_brightness
        brightness_scale = actual_brightness / requested_brightness if requested_brightness > 0 else 1.0

        return {
            'newRays': new_rays,
            'brightnessScale': brightness_scale
        }

    def init_random(self):
        """Initialize random number array for random beam mode."""
        if not hasattr(self, 'random_numbers') or self.random_numbers is None:
            self.random_numbers = []
        if not self.random:
            self.clear_random()

    def clear_random(self):
        """Clear the random number cache."""
        self.random_numbers = []

    def get_random(self, i):
        """
        Get a random number by index (cached for consistency).

        Args:
            i: Index of the random number.

        Returns:
            A random number in [0, 1).
        """
        # Extend array if needed
        while len(self.random_numbers) <= i:
            self.random_numbers.append(self.scene.rng())
        return self.random_numbers[i]

    def new_ray(self, x, y, normal, angle, gap, brightness_factor=1.0, ray_density=None):
        """
        Create a new ray for this beam.

        Args:
            x: X position of ray origin.
            y: Y position of ray origin.
            normal: Normal direction (perpendicular to beam).
            angle: Angle offset from normal (for divergence).
            gap: Whether this is a gap ray (for image detection).
            brightness_factor: Brightness multiplier (for angled rays).
            ray_density: Ray density to use for brightness calculation.

        Returns:
            A ray geometry object with brightness and wavelength properties.
        """
        if ray_density is None:
            ray_density = self.scene.ray_density

        # Create ray in the direction (normal + angle)
        ray_angle = normal + angle
        ray = geometry.line(
            geometry.point(x, y),
            geometry.point(x + math.sin(ray_angle), y + math.cos(ray_angle))
        )

        # Calculate ray brightness (split between s and p polarizations)
        per_ray_brightness = min(
            self.brightness * self.scene.length_scale / ray_density * brightness_factor,
            1
        )
        ray.brightness_s = per_ray_brightness * 0.5
        ray.brightness_p = per_ray_brightness * 0.5

        # Apply Lambert (cosine) weighting if enabled
        if self.lambert:
            lambert_factor = math.cos(angle)
            ray.brightness_s *= lambert_factor
            ray.brightness_p *= lambert_factor

        # Mark as new ray
        ray.isNew = True

        # Set wavelength if color simulation is enabled
        if self.scene.simulate_colors:
            ray.wavelength = self.wavelength

        # Mark gap ray (for image detection)
        ray.gap = gap

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Source Tracking
        # =====================================================================
        # Tag rays with source UUID and name for correlation in results
        # =====================================================================
        ray.source_uuid = self.uuid
        ray.source_label = self.name  # Use source's name as the ray label

        return ray


# Example usage and testing
if __name__ == "__main__":
    print("Testing Beam class...\n")

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.simulate_colors = False
            self.color_mode = 'default'
            self.ray_density = 0.1
            self.length_scale = 1.0
            self.mode = 'rays'
            self._rng_counter = 0

            # Mock theme
            class MockTheme:
                class MockLightSource:
                    color = [1.0, 1.0, 0.5, 1.0]
                    size = 3

                class MockBeamShield:
                    color = [0.5, 0.5, 0.5, 1.0]
                    width = 1

                light_source = MockLightSource()
                beam_shield = MockBeamShield()

            self.theme = MockTheme()
            self.highlight_color = [1.0, 0.0, 1.0, 1.0]

        def rng(self):
            """Simple random number generator for testing."""
            self._rng_counter += 1
            return (self._rng_counter * 137.5) % 1.0

    # Test 1: Parallel beam (no divergence)
    print("Test 1: Parallel beam (emis_angle = 0°)")
    scene = MockScene()
    beam = Beam(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 50, 'y': 0},
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH,
        'emis_angle': 0.0,
        'lambert': False,
        'random': False
    })

    print(f"  Beam segment: ({beam.p1['x']}, {beam.p1['y']}) to ({beam.p2['x']}, {beam.p2['y']})")
    print(f"  Brightness: {beam.brightness}")
    print(f"  Emission angle: {beam.emis_angle}°")

    result = beam.on_simulation_start()
    print(f"  Rays generated: {len(result['newRays'])}")
    print(f"  Brightness scale: {result['brightnessScale']:.4f}")

    if len(result['newRays']) > 0:
        ray = result['newRays'][0]
        total_brightness = ray.brightness_s + ray.brightness_p
        print(f"  First ray brightness: {total_brightness:.4f} (s={ray.brightness_s:.4f}, p={ray.brightness_p:.4f})")

    # Test 2: Divergent beam
    print("\nTest 2: Divergent beam (emis_angle = 30°)")
    beam_div = Beam(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH,
        'emis_angle': 30.0,
        'lambert': False,
        'random': False
    })

    print(f"  Beam segment: ({beam_div.p1['x']}, {beam_div.p1['y']}) to ({beam_div.p2['x']}, {beam_div.p2['y']})")
    print(f"  Emission angle: {beam_div.emis_angle}°")

    result_div = beam_div.on_simulation_start()
    print(f"  Rays generated: {len(result_div['newRays'])}")
    print(f"  Brightness scale: {result_div['brightnessScale']:.4f}")
    print("  ==> More rays due to divergence (central ray + angled rays)")

    # Test 3: Lambertian beam
    print("\nTest 3: Lambertian beam (lambert = True)")
    beam_lambert = Beam(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH,
        'emis_angle': 30.0,
        'lambert': True,
        'random': False
    })

    print(f"  Lambert mode: {beam_lambert.lambert}")
    print(f"  Emission angle: {beam_lambert.emis_angle}°")

    result_lambert = beam_lambert.on_simulation_start()
    print(f"  Rays generated: {len(result_lambert['newRays'])}")

    if len(result_lambert['newRays']) >= 3:
        # Check that angled rays have lower brightness (cosine weighting)
        ray_central = result_lambert['newRays'][0]
        ray_angled = result_lambert['newRays'][1]
        print(f"  Central ray brightness: {ray_central.brightness_s + ray_central.brightness_p:.4f}")
        print(f"  Angled ray brightness: {ray_angled.brightness_s + ray_angled.brightness_p:.4f}")
        print("  ==> Angled rays are dimmer due to Lambert (cosine) weighting")

    # Test 4: Random beam
    print("\nTest 4: Random beam (random = True)")
    beam_random = Beam(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5,
        'wavelength': GREEN_WAVELENGTH,
        'emis_angle': 20.0,
        'lambert': False,
        'random': True
    })

    print(f"  Random mode: {beam_random.random}")
    print(f"  Emission angle: {beam_random.emis_angle}°")

    result_random = beam_random.on_simulation_start()
    print(f"  Rays generated: {len(result_random['newRays'])}")
    print(f"  Random numbers cached: {len(beam_random.random_numbers)}")
    print("  ==> Rays placed randomly instead of uniformly")

    # Test 5: Color simulation
    print("\nTest 5: Beam with color simulation (red light)")
    scene.simulate_colors = True
    beam_color = Beam(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 5, 'y': 0},
        'brightness': 0.3,
        'wavelength': 650,  # Red
        'emis_angle': 0.0,
        'lambert': False,
        'random': False
    })

    print(f"  Wavelength: {beam_color.wavelength} nm (red)")

    result_color = beam_color.on_simulation_start()
    print(f"  Rays generated: {len(result_color['newRays'])}")

    if len(result_color['newRays']) > 0:
        ray = result_color['newRays'][0]
        print(f"  Ray wavelength: {ray.wavelength} nm")

    # Test 6: Transformations
    print("\nTest 6: Transformations")
    beam_test = Beam(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5
    })

    print(f"  Initial: p1=({beam_test.p1['x']}, {beam_test.p1['y']}), p2=({beam_test.p2['x']}, {beam_test.p2['y']})")

    # Move
    beam_test.move(5, 3)
    print(f"  After move(5, 3): p1=({beam_test.p1['x']}, {beam_test.p1['y']}), p2=({beam_test.p2['x']}, {beam_test.p2['y']})")

    # Rotate
    beam_test.p1 = {'x': 0, 'y': 0}
    beam_test.p2 = {'x': 10, 'y': 0}
    beam_test.rotate(math.pi / 2, {'x': 5, 'y': 0})
    print(f"  After rotate(90° around (5,0)): p1=({beam_test.p1['x']:.2f}, {beam_test.p1['y']:.2f}), p2=({beam_test.p2['x']:.2f}, {beam_test.p2['y']:.2f})")

    # Scale
    beam_test.p1 = {'x': 0, 'y': 0}
    beam_test.p2 = {'x': 10, 'y': 0}
    initial_brightness = beam_test.brightness
    beam_test.scale(2.0, {'x': 5, 'y': 0})
    print(f"  After scale(2.0 from (5,0)): p1=({beam_test.p1['x']:.2f}, {beam_test.p1['y']:.2f}), p2=({beam_test.p2['x']:.2f}, {beam_test.p2['y']:.2f})")
    print(f"  Brightness: {initial_brightness:.2f} -> {beam_test.brightness:.2f} (divided by scale factor)")

    # Test 7: Warning in image detection mode
    print("\nTest 7: Warning in image detection mode")
    scene.mode = 'images'
    beam_warning = Beam(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 10, 'y': 0},
        'brightness': 0.5,
        'emis_angle': 20.0
    })

    result_warning = beam_warning.on_simulation_start()
    if beam_warning.warning:
        print(f"  Warning: {beam_warning.warning}")
    else:
        print("  No warning")

    print("\nBeam test completed successfully!")
