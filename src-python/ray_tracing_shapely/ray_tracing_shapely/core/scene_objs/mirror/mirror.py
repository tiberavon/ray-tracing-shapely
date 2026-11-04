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
from typing import Dict, Any, Optional, Union, TYPE_CHECKING

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_filter import BaseFilter
    from ray_tracing_shapely.core.scene_objs.line_obj_mixin import LineObjMixin
    from ray_tracing_shapely.core.constants import GREEN_WAVELENGTH
else:
    from ..base_filter import BaseFilter
    from ..line_obj_mixin import LineObjMixin
    from ...constants import GREEN_WAVELENGTH

if TYPE_CHECKING:
    from ...scene import Scene
    from ...ray import Ray
    from ...geometry import Point


class Mirror(LineObjMixin, BaseFilter):
    """
    Mirror with shape of a line segment.

    This is a simple flat (planar) mirror that reflects light according to
    the law of reflection (angle of incidence = angle of reflection).

    Tools -> Mirror -> Segment

    Attributes:
        p1 (dict): The first endpoint of the mirror line segment
        p2 (dict): The second endpoint of the mirror line segment
        filter (bool): Whether it is a dichroic mirror (wavelength-selective)
        invert (bool): If True, rays with wavelength outside the bandwidth are
                      reflected. If False, rays with wavelength inside the
                      bandwidth are reflected.
        wavelength (float): The target wavelength if dichroic is enabled (nm)
        bandwidth (float): The bandwidth if dichroic is enabled (nm)
    """

    type = 'Mirror'
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

    def __init__(self, scene: 'Scene', json_obj: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize a mirror.

        Args:
            scene: The scene containing this mirror
            json_obj: Optional JSON serialization data
        """
        super().__init__(scene, json_obj)

    def populate_obj_bar(self, obj_bar: Any) -> bool:
        """
        Populate the object properties bar in the UI.

        Args:
            obj_bar: The UI object bar to populate

        Returns:
            True when complete
        """
        # Set title (in JS: i18next.t with parentheses formatter)
        obj_bar.set_title("Mirror (Segment)")

        # Call parent's populate_obj_bar to add filter controls
        super().populate_obj_bar(obj_bar)
        return True

    def draw(self, canvas_renderer: Any, is_above_light: bool, is_hovered: bool) -> bool:
        """
        Draw the mirror on the canvas.

        Args:
            canvas_renderer: The canvas rendering context
            is_above_light: Whether this object is above the light layer
            is_hovered: Whether the mouse is hovering over this object

        Returns:
            True when complete
        """
        ctx: Any = canvas_renderer.ctx
        ls: float = canvas_renderer.length_scale

        # Handle degenerate case (both endpoints at same position)
        if self.p1['x'] == self.p2['x'] and self.p1['y'] == self.p2['y']:
            ctx.fillStyle = 'rgb(128,128,128)'
            ctx.fillRect(
                self.p1['x'] - 1.5 * ls,
                self.p1['y'] - 1.5 * ls,
                3 * ls,
                3 * ls
            )
            return True

        # Determine color based on wavelength filter and hover state
        from ...simulator import Simulator
        color_array: list = Simulator.wavelength_to_color(
            self.wavelength or GREEN_WAVELENGTH,
            1
        )

        if is_hovered:
            ctx.strokeStyle = self.scene.highlight_color_css
        elif self.scene.simulate_colors and self.wavelength and self.filter:
            ctx.strokeStyle = canvas_renderer.rgba_to_css_color(color_array)
        else:
            ctx.strokeStyle = canvas_renderer.rgba_to_css_color(
                self.scene.theme.mirror['color']
            )

        # Draw the mirror line segment
        ctx.lineWidth = self.scene.theme.mirror['width'] * ls
        ctx.beginPath()
        ctx.moveTo(self.p1['x'], self.p1['y'])
        ctx.lineTo(self.p2['x'], self.p2['y'])
        ctx.stroke()

        return True

    def check_ray_intersects(self, ray: 'Ray') -> Optional['Point']:
        """
        Check if a ray intersects this mirror.

        Args:
            ray: The ray to check for intersection

        Returns:
            The intersection point, or None if no intersection or filtered out
        """
        # First check wavelength filter
        if self.check_ray_intersect_filter(ray):
            # Then check geometric intersection with line segment
            return self.check_ray_intersects_shape(ray)
        else:
            return None

    def on_ray_incident(
        self,
        ray: 'Ray',
        ray_index: int,
        incident_point: Union['Point', Dict[str, float]],
        surface_merging_objs: Optional[list] = None,
        verbose: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Handle a ray incident on the mirror.

        This implements the law of reflection: the angle of incidence equals
        the angle of reflection. The incident ray is reflected across the
        mirror's surface normal.

        Args:
            ray: The incident ray
            ray_index: Index of the ray in the simulation
            incident_point: The point where the ray hits the mirror
            surface_merging_objs: List of objects for surface merging (unused for mirrors)
            verbose: Verbosity level for debugging

        Returns:
            None (modifies ray in place)
        """
        # Calculate incident ray direction (from p1 to incident point)
        rx: float = ray.p1['x'] - incident_point['x']
        ry: float = ray.p1['y'] - incident_point['y']

        # Calculate mirror surface direction vector
        mx: float = self.p2['x'] - self.p1['x']
        my: float = self.p2['y'] - self.p1['y']

        # Apply reflection formula
        # The reflected ray is calculated by reflecting the incident vector
        # across the mirror surface.
        # Formula: r' = r - 2(r·n)n where n is the surface normal
        # For a line segment, this simplifies to:
        #   r'_x = r_x * (m_y² - m_x²) - 2 * r_y * m_x * m_y
        #   r'_y = r_y * (m_x² - m_y²) - 2 * r_x * m_x * m_y
        # where (m_x, m_y) is the mirror direction vector

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Surface Hit Records (Step B, opt-in)
        # =====================================================================
        # Record hit geometry onto `ray` (the simulator's output_ray_geom) before
        # overwriting p1/p2. The mirror normal is perpendicular to its surface
        # direction (mx, my); the angle of incidence is measured from that normal.
        # rx, ry = p1 - incident_point (the reversed incident direction), so the
        # incident direction is (-rx, -ry). CONTRIBUTING.md acos clamp rule applies.
        if getattr(ray, 'record_surface_hits', False):
            m_len: float = math.hypot(mx, my)
            di_len: float = math.hypot(rx, ry)
            if m_len > 0 and di_len > 0:
                nx: float = -my / m_len
                ny: float = mx / m_len
                # cos(incidence) = |incident_dir . normal|
                cos_inc: float = abs((-rx * nx - ry * ny) / di_len)
                ray.hit_surface_uuid = self._uuid
                ray.hit_point = {'x': incident_point['x'], 'y': incident_point['y']}
                ray.hit_normal = {'x': nx, 'y': ny}
                ray.incident_angle = math.acos(max(-1.0, min(1.0, cos_inc)))

        # Update ray: start at incident point, direction is reflected
        ray.p1 = {'x': incident_point['x'], 'y': incident_point['y']}
        ray.p2 = {
            'x': incident_point['x'] + rx * (my * my - mx * mx) - 2 * ry * mx * my,
            'y': incident_point['y'] + ry * (mx * mx - my * my) - 2 * rx * mx * my
        }

        return None


# Example usage and testing
if __name__ == "__main__":
    print("Testing Mirror class...\n")

    # Mock classes for testing
    class MockScene:
        def __init__(self):
            self.objs = []
            self.length_scale = 1.0
            self.simulate_colors = False
            self.highlight_color_css = '#ff0000'
            self.theme = {
                'mirror': {'width': 2, 'color': [168, 168, 168, 255]}
            }

    class MockRay:
        def __init__(self, p1, p2, wavelength=None):
            self.p1 = p1
            self.p2 = p2
            self.wavelength = wavelength
            self.brightness_s = 1.0
            self.brightness_p = 0.0

    scene = MockScene()

    # Test 1: Create a basic mirror
    print("Test 1: Basic mirror creation")
    mirror1 = Mirror(scene, {
        'p1': {'x': 100, 'y': 100},
        'p2': {'x': 100, 'y': 200}
    })
    print(f"  Type: {mirror1.type}")
    print(f"  p1: {mirror1.p1}")
    print(f"  p2: {mirror1.p2}")
    print(f"  Is optical: {mirror1.is_optical}")
    print(f"  Merges with glass: {mirror1.merges_with_glass}")

    # Test 2: Horizontal ray hitting vertical mirror
    print("\nTest 2: Horizontal ray hitting vertical mirror")
    mirror2 = Mirror(scene, {
        'p1': {'x': 200, 'y': 150},
        'p2': {'x': 200, 'y': 250},
        'filter': False
    })

    ray = MockRay({'x': 150, 'y': 200}, {'x': 250, 'y': 200})
    incident_point = {'x': 200, 'y': 200}

    print(f"  Incident ray: ({ray.p1['x']}, {ray.p1['y']}) -> ({ray.p2['x']}, {ray.p2['y']})")
    mirror2.on_ray_incident(ray, 0, incident_point)
    print(f"  Reflected ray: ({ray.p1['x']:.2f}, {ray.p1['y']:.2f}) -> ({ray.p2['x']:.2f}, {ray.p2['y']:.2f})")
    print("  Expected: ray should reflect back to the left")

    # Test 3: 45-degree ray hitting vertical mirror
    print("\nTest 3: 45-degree ray hitting vertical mirror")
    mirror3 = Mirror(scene, {
        'p1': {'x': 200, 'y': 150},
        'p2': {'x': 200, 'y': 250},
        'filter': False
    })

    ray2 = MockRay({'x': 150, 'y': 150}, {'x': 250, 'y': 250})
    incident_point2 = {'x': 200, 'y': 200}

    dx = ray2.p2['x'] - ray2.p1['x']
    dy = ray2.p2['y'] - ray2.p1['y']
    import math
    angle_in = math.degrees(math.atan2(dy, dx))
    print(f"  Incident angle: {angle_in:.1f}°")
    print(f"  Incident ray: ({ray2.p1['x']}, {ray2.p1['y']}) -> ({ray2.p2['x']}, {ray2.p2['y']})")

    mirror3.on_ray_incident(ray2, 0, incident_point2)

    dx_out = ray2.p2['x'] - ray2.p1['x']
    dy_out = ray2.p2['y'] - ray2.p1['y']
    angle_out = math.degrees(math.atan2(dy_out, dx_out))
    print(f"  Reflected ray: ({ray2.p1['x']:.2f}, {ray2.p1['y']:.2f}) -> ({ray2.p2['x']:.2f}, {ray2.p2['y']:.2f})")
    print(f"  Reflected angle: {angle_out:.1f}°")

    # Test 4: Angled mirror (45 degrees)
    print("\nTest 4: Horizontal ray hitting 45° angled mirror")
    mirror4 = Mirror(scene, {
        'p1': {'x': 150, 'y': 150},
        'p2': {'x': 250, 'y': 250},  # 45-degree mirror
        'filter': False
    })

    ray3 = MockRay({'x': 150, 'y': 200}, {'x': 250, 'y': 200})
    incident_point3 = {'x': 200, 'y': 200}

    print(f"  Incident ray: ({ray3.p1['x']}, {ray3.p1['y']}) -> ({ray3.p2['x']}, {ray3.p2['y']})")
    mirror4.on_ray_incident(ray3, 0, incident_point3)
    print(f"  Reflected ray: ({ray3.p1['x']:.2f}, {ray3.p1['y']:.2f}) -> ({ray3.p2['x']:.2f}, {ray3.p2['y']:.2f})")
    print("  Expected: ray should reflect 90° (upward)")

    # Test 5: Wavelength filter (dichroic mirror)
    print("\nTest 5: Dichroic mirror (reflects green only)")
    mirror5 = Mirror(scene, {
        'p1': {'x': 100, 'y': 100},
        'p2': {'x': 100, 'y': 200},
        'filter': True,
        'wavelength': 532,  # Green
        'bandwidth': 10
    })
    scene.simulate_colors = True

    ray_green = MockRay({'x': 50, 'y': 150}, {'x': 150, 'y': 150}, wavelength=532)
    ray_red = MockRay({'x': 50, 'y': 150}, {'x': 150, 'y': 150}, wavelength=650)

    print(f"  Filter: wavelength={mirror5.wavelength}nm, bandwidth=±{mirror5.bandwidth}nm")
    print(f"  Green ray (532nm) intersects: {mirror5.check_ray_intersect_filter(ray_green)}")
    print(f"  Red ray (650nm) intersects: {mirror5.check_ray_intersect_filter(ray_red)}")

    # Test 6: Inverted filter (reflects everything except green)
    print("\nTest 6: Inverted dichroic mirror (reflects all except green)")
    mirror6 = Mirror(scene, {
        'p1': {'x': 100, 'y': 100},
        'p2': {'x': 100, 'y': 200},
        'filter': True,
        'wavelength': 532,  # Green
        'bandwidth': 10,
        'invert': True  # Inverted
    })

    print(f"  Filter: wavelength={mirror6.wavelength}nm, bandwidth=±{mirror6.bandwidth}nm, inverted=True")
    print(f"  Green ray (532nm) intersects: {mirror6.check_ray_intersect_filter(ray_green)}")
    print(f"  Red ray (650nm) intersects: {mirror6.check_ray_intersect_filter(ray_red)}")

    # Test 7: Serialization
    print("\nTest 7: Serialization")
    mirror7 = Mirror(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 100, 'y': 100},
        'filter': True,
        'wavelength': 650
    })
    serialized = mirror7.serialize()
    print(f"  Serialized: {serialized}")

    # Test 8: Verify law of reflection (angle in = angle out)
    print("\nTest 8: Verify law of reflection")
    mirror8 = Mirror(scene, {
        'p1': {'x': 200, 'y': 100},
        'p2': {'x': 200, 'y': 300}  # Vertical mirror
    })

    # Test at different angles
    test_angles = [15, 30, 45, 60, 75]
    print("  Testing various incident angles on vertical mirror:")
    for angle_deg in test_angles:
        angle_rad = math.radians(angle_deg)
        # Create ray at specified angle
        ray_len = 100
        ray_test = MockRay(
            {'x': 150, 'y': 200},
            {'x': 150 + ray_len * math.cos(angle_rad), 'y': 200 + ray_len * math.sin(angle_rad)}
        )
        incident_pt = {'x': 200, 'y': 200}

        # Calculate incident angle from horizontal
        dx_in = ray_test.p2['x'] - ray_test.p1['x']
        dy_in = ray_test.p2['y'] - ray_test.p1['y']
        angle_in_calc = math.degrees(math.atan2(dy_in, dx_in))

        mirror8.on_ray_incident(ray_test, 0, incident_pt)

        # Calculate reflected angle
        dx_out = ray_test.p2['x'] - ray_test.p1['x']
        dy_out = ray_test.p2['y'] - ray_test.p1['y']
        angle_out_calc = math.degrees(math.atan2(dy_out, dx_out))

        # For vertical mirror, reflected angle should be 180 - incident_angle
        expected_out = 180 - angle_in_calc
        error = abs(angle_out_calc - expected_out)

        print(f"    {angle_deg:2.0f}° in -> {angle_out_calc:6.2f}° out (expected {expected_out:6.2f}°, error: {error:.2e}°)")

    print("\nMirror test completed successfully!")
