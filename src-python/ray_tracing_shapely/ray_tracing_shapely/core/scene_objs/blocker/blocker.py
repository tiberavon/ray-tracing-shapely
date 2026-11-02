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

from typing import Dict, Any, Optional

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_filter import BaseFilter
    from ray_tracing_shapely.core.scene_objs.line_obj_mixin import LineObjMixin
    from ray_tracing_shapely.core.scene_objs.base_scene_obj import BaseSceneObj
    from ray_tracing_shapely.core.constants import GREEN_WAVELENGTH
    from ray_tracing_shapely.core import geometry
else:
    from ..base_filter import BaseFilter
    from ..line_obj_mixin import LineObjMixin
    from ..base_scene_obj import BaseSceneObj
    from ...constants import GREEN_WAVELENGTH
    from ... import geometry


class Blocker(LineObjMixin, BaseFilter):
    """
    Line blocker / absorbing filter.

    A blocker is a line segment that absorbs any ray that intersects it.
    It can optionally act as a wavelength-selective filter (dichroic blocker).

    Attributes:
        p1: The first endpoint of the line segment.
        p2: The second endpoint of the line segment.
        filter: Whether wavelength filtering is enabled.
        invert: If True, blocks rays outside the bandwidth. If False, blocks rays inside.
        wavelength: Target wavelength for filtering (nm).
        bandwidth: Wavelength bandwidth for filtering (nm).

    Usage:
        A blocker is useful as:
        - Absorbing screen to visualize beam patterns
        - Aperture stop (use two blockers to create an opening)
        - Wavelength-selective absorber (with filter enabled)

    Notes:
        - The blocker absorbs rays by returning {'isAbsorbed': True}
        - When used with glass objects, it merges at the surface (merges_with_glass = True)
        - Can act as a dichroic filter to block specific wavelengths
    """

    type = 'Blocker'
    is_optical = True
    merges_with_glass = True
    serializable_defaults = {
        'p1': None,
        'p2': None,
        'filter': False,
        'invert': False,
        'wavelength': GREEN_WAVELENGTH,
        'bandwidth': 10
    }

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with blocker controls.

        Args:
            obj_bar: The object bar to populate.
        """
        obj_bar.set_title('Line Blocker')
        # Call parent's populate_obj_bar to add filter controls
        super().populate_obj_bar(obj_bar)

    def draw(self, canvas_renderer, is_above_light, is_hovered):
        """
        Draw the blocker on the canvas.

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether rendering above the light layer.
            is_hovered: Whether the blocker is hovered by the mouse.
        """
        ctx = canvas_renderer.ctx
        ls = canvas_renderer.length_scale

        # Handle degenerate case (both endpoints at same location)
        if hasattr(self.p1, 'x'):
            p1_x, p1_y = self.p1.x, self.p1.y
            p2_x, p2_y = self.p2.x, self.p2.y
        else:
            p1_x, p1_y = self.p1['x'], self.p1['y']
            p2_x, p2_y = self.p2['x'], self.p2['y']

        if p1_x == p2_x and p1_y == p2_y:
            ctx.fillStyle = 'rgb(128,128,128)'
            ctx.fillRect(p1_x - 1.5 * ls, p1_y - 1.5 * ls, 3 * ls, 3 * ls)
            return

        # Determine stroke color
        if is_hovered:
            stroke_color = self.scene.highlight_color_css
        elif self.scene.simulate_colors and hasattr(self, 'wavelength') and self.wavelength and self.filter:
            # Show wavelength color for dichroic filters
            from ..base_scene_obj import wavelength_to_color
            color_array = wavelength_to_color(self.wavelength, 1)
            stroke_color = canvas_renderer.rgba_to_css_color(color_array)
        else:
            stroke_color = canvas_renderer.rgba_to_css_color(self.scene.theme.blocker.color)

        # Draw the line
        ctx.strokeStyle = stroke_color
        ctx.lineWidth = self.scene.theme.blocker.width * ls
        ctx.lineCap = 'butt'
        ctx.beginPath()
        ctx.moveTo(p1_x, p1_y)
        ctx.lineTo(p2_x, p2_y)
        ctx.stroke()
        ctx.lineWidth = 1 * ls

    def check_ray_intersects(self, ray):
        """
        Check if a ray intersects the blocker.

        Args:
            ray: The ray to check.

        Returns:
            The intersection point if the ray intersects and passes the filter,
            None otherwise.
        """
        # First check wavelength filter
        if self.check_ray_intersect_filter(ray):
            # Then check geometric intersection
            return self.check_ray_intersects_shape(ray)
        else:
            return None

    def on_ray_incident(self, ray, ray_index, incident_point, surface_merging_objs=None, verbose=0):
        """
        Handle ray incidence on the blocker.

        The blocker simply absorbs the ray.

        Args:
            ray: The incident ray.
            ray_index: Index of the ray in the ray array.
            incident_point: The point where the ray hits the blocker.
            surface_merging_objs: List of glass objects to merge with (unused for blocker).
            verbose: Verbosity level (default: 0)
                    0 = silent (no debug output)
                    1 = verbose (show ray processing info)
                    2 = very verbose/debug (show detailed calculations)

        Returns:
            Dict with 'isAbsorbed': True to indicate the ray is absorbed.
        """
        if verbose >= 1:
            print(f"\n=== BLOCKER on_ray_incident CALLED ===")
            inc_x = incident_point['x'] if isinstance(incident_point, dict) else incident_point.x
            inc_y = incident_point['y'] if isinstance(incident_point, dict) else incident_point.y
            print(f"  Incident point: ({inc_x:.4f}, {inc_y:.4f})")
            print(f"  Ray absorbed by blocker")

        return {
            'isAbsorbed': True
        }


# Example usage and testing
if __name__ == "__main__":
    print("Testing Blocker class...\n")

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.simulate_colors = False
            self.highlight_color_css = 'rgb(255,0,255)'

            # Mock theme
            class MockTheme:
                class MockBlocker:
                    color = [0.5, 0.5, 0.5, 1.0]
                    width = 2
                blocker = MockBlocker()

            self.theme = MockTheme()

    # Mock ray
    class MockRay:
        def __init__(self, wavelength=GREEN_WAVELENGTH):
            self.p1 = {'x': 0, 'y': 0}
            self.p2 = {'x': 10, 'y': 0}
            self.wavelength = wavelength
            self.brightness_s = 1.0
            self.brightness_p = 1.0

    # Test 1: Basic blocker
    print("Test 1: Basic blocker (no filter)")
    scene = MockScene()
    blocker = Blocker(scene, {
        'p1': {'x': 5, 'y': -5},
        'p2': {'x': 5, 'y': 5},
        'filter': False
    })

    print(f"  Blocker position: ({blocker.p1['x']}, {blocker.p1['y']}) to ({blocker.p2['x']}, {blocker.p2['y']})")
    print(f"  Filter enabled: {blocker.filter}")

    # Test ray intersection
    ray = MockRay()
    intersection = blocker.check_ray_intersects(ray)
    print(f"  Ray intersects: {intersection is not None}")

    if intersection:
        if hasattr(intersection, 'x'):
            print(f"  Intersection point: ({intersection.x:.2f}, {intersection.y:.2f})")
        else:
            print(f"  Intersection point: ({intersection['x']:.2f}, {intersection['y']:.2f})")

        # Test ray absorption
        result = blocker.on_ray_incident(ray, 0, intersection)
        print(f"  Ray absorbed: {result.get('isAbsorbed', False)}")

    # Test 2: Blocker with wavelength filter
    print("\nTest 2: Wavelength-selective blocker (green only)")
    scene.simulate_colors = True
    blocker_filter = Blocker(scene, {
        'p1': {'x': 5, 'y': -5},
        'p2': {'x': 5, 'y': 5},
        'filter': True,
        'wavelength': 532,  # Green
        'bandwidth': 20,
        'invert': False
    })

    print(f"  Filter enabled: {blocker_filter.filter}")
    print(f"  Target wavelength: {blocker_filter.wavelength} nm")
    print(f"  Bandwidth: {blocker_filter.bandwidth} nm")

    # Test with green ray (should be blocked)
    ray_green = MockRay(wavelength=532)
    intersection_green = blocker_filter.check_ray_intersects(ray_green)
    print(f"  Green ray (532 nm) intersects: {intersection_green is not None}")

    # Test with red ray (should pass through)
    ray_red = MockRay(wavelength=650)
    intersection_red = blocker_filter.check_ray_intersects(ray_red)
    print(f"  Red ray (650 nm) intersects: {intersection_red is not None}")

    # Test 3: Inverted filter (blocks everything except green)
    print("\nTest 3: Inverted filter (blocks all except green)")
    blocker_inverted = Blocker(scene, {
        'p1': {'x': 5, 'y': -5},
        'p2': {'x': 5, 'y': 5},
        'filter': True,
        'wavelength': 532,
        'bandwidth': 20,
        'invert': True
    })

    print(f"  Inverted filter: {blocker_inverted.invert}")

    # Test with green ray (should pass through)
    ray_green2 = MockRay(wavelength=532)
    intersection_green2 = blocker_inverted.check_ray_intersects(ray_green2)
    print(f"  Green ray (532 nm) intersects: {intersection_green2 is not None}")

    # Test with red ray (should be blocked)
    ray_red2 = MockRay(wavelength=650)
    intersection_red2 = blocker_inverted.check_ray_intersects(ray_red2)
    print(f"  Red ray (650 nm) intersects: {intersection_red2 is not None}")

    # Test 4: Ray that doesn't intersect
    print("\nTest 4: Ray that misses the blocker")
    ray_miss = MockRay()
    ray_miss.p1 = {'x': 0, 'y': 10}
    ray_miss.p2 = {'x': 10, 'y': 10}
    intersection_miss = blocker.check_ray_intersects(ray_miss)
    print(f"  Ray intersects: {intersection_miss is not None}")

    print("\nBlocker test completed successfully!")
