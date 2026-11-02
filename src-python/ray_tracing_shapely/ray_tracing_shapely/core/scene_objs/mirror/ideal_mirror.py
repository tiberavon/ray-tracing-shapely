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

from typing import Dict, Any, Optional, Union, TYPE_CHECKING
import math

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_filter import BaseFilter
    from ray_tracing_shapely.core.scene_objs.line_obj_mixin import LineObjMixin
    from ray_tracing_shapely.core.geometry import geometry
    from ray_tracing_shapely.core.constants import GREEN_WAVELENGTH
else:
    from ..base_filter import BaseFilter
    from ..line_obj_mixin import LineObjMixin
    from ...geometry import geometry
    from ...constants import GREEN_WAVELENGTH

if TYPE_CHECKING:
    from ...scene import Scene
    from ...ray import Ray
    from ...geometry import Point


class IdealMirror(LineObjMixin, BaseFilter):
    """
    Ideal curved mirror that follows the mirror equation exactly.

    This mirror uses the thin lens equation (1/f = 1/do + 1/di) and mirrors
    the result to create perfect focusing behavior regardless of incident angle.
    Unlike real curved mirrors, this doesn't have a specific shape - it
    implements the ideal mathematical behavior.

    Tools -> Mirror -> Ideal curved mirror

    Attributes:
        p1 (dict): The first endpoint of the mirror line segment
        p2 (dict): The second endpoint of the mirror line segment
        focalLength (float): The focal length. The Cartesian sign convention
                            is not used internally. But if the Cartesian sign
                            convention is enabled (as a preference setting),
                            the focal length changes sign in the UI.
        filter (bool): Whether wavelength filtering is enabled
        invert (bool): Whether to invert the filter behavior
        wavelength (float): Target wavelength for dichroic filtering (nm)
        bandwidth (float): Bandwidth of the wavelength filter (nm)
    """

    type = 'IdealMirror'
    is_optical = True
    merges_with_glass = True

    serializable_defaults = {
        'p1': None,
        'p2': None,
        'focalLength': 100,
        'filter': False,
        'invert': False,
        'wavelength': GREEN_WAVELENGTH,
        'bandwidth': 10
    }

    def __init__(self, scene: 'Scene', json_obj: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize an ideal mirror.

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
        # Set title (in JS: i18next.t('main:tools.IdealMirror.title'))
        obj_bar.set_title("Ideal curved mirror")

        # Check for Cartesian sign convention preference
        # In JS this uses localStorage, in Python we'd use config/preferences
        cartesian_sign: bool = False
        # TODO: Implement preference storage
        # if hasattr(self.scene, 'preferences'):
        #     cartesian_sign = self.scene.preferences.get('rayOpticsCartesianSign', False)

        # Create focal length control
        # The sign is flipped in the UI if Cartesian convention is enabled
        obj_bar.create_number(
            "Focal length",  # i18next.t('simulator:sceneObjs.common.focalLength')
            -1000 * self.scene.length_scale,
            1000 * self.scene.length_scale,
            1 * self.scene.length_scale,
            self.focalLength * (-1 if cartesian_sign else 1),
            lambda obj, value: setattr(obj, 'focalLength', value * (-1 if cartesian_sign else 1)),
            "Length unit info"  # i18next.t('simulator:sceneObjs.common.lengthUnitInfo')
        )

        # Advanced option to toggle Cartesian sign convention
        if obj_bar.show_advanced(cartesian_sign):
            obj_bar.create_boolean(
                "Cartesian sign convention",  # i18next.t('simulator:sceneObjs.IdealMirror.cartesianSign')
                cartesian_sign,
                lambda obj, value: self._set_cartesian_sign(value),
                None,
                True
            )

        # Call parent's populate_obj_bar to add filter controls
        super().populate_obj_bar(obj_bar)
        return True

    def _set_cartesian_sign(self, value: bool) -> None:
        """
        Set the Cartesian sign convention preference.

        Args:
            value: True to enable Cartesian sign convention

        Returns:
            None
        """
        # TODO: Implement preference storage
        # if hasattr(self.scene, 'preferences'):
        #     self.scene.preferences['rayOpticsCartesianSign'] = value
        pass

    def draw(self, canvas_renderer: Any, is_above_light: bool, is_hovered: bool) -> bool:
        """
        Draw the ideal mirror on the canvas.

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

        # Calculate line segment length and unit vectors
        dx: float = self.p2['x'] - self.p1['x']
        dy: float = self.p2['y'] - self.p1['y']
        length: float = math.sqrt(dx * dx + dy * dy)

        # Unit vector parallel to mirror
        par_x: float = dx / length
        par_y: float = dy / length

        # Unit vector perpendicular to mirror
        per_x: float = par_y
        per_y: float = -par_x

        # Calculate arrow and center marker sizes
        arrow_size_per: float = self.scene.theme.ideal_curve_arrow['size'] / 2 * ls
        arrow_size_par: float = self.scene.theme.ideal_curve_arrow['size'] / 2 * ls
        center_size: float = max(1, self.scene.theme.mirror['width'] / 2) * ls

        # Draw the main line segment
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

        ctx.lineWidth = self.scene.theme.mirror['width'] * ls
        ctx.globalAlpha = 1
        ctx.beginPath()
        ctx.moveTo(self.p1['x'], self.p1['y'])
        ctx.lineTo(self.p2['x'], self.p2['y'])
        ctx.stroke()

        # Draw the center point marker
        mid_x: float = (self.p1['x'] + self.p2['x']) / 2
        mid_y: float = (self.p1['y'] + self.p2['y']) / 2

        ctx.strokeStyle = canvas_renderer.rgba_to_css_color(
            self.scene.theme.ideal_curve_center['color']
        )
        ctx.lineWidth = self.scene.theme.ideal_curve_center['size'] * ls
        ctx.beginPath()
        ctx.moveTo(mid_x - per_x * center_size, mid_y - per_y * center_size)
        ctx.lineTo(mid_x + per_x * center_size, mid_y + per_y * center_size)
        ctx.stroke()

        # Draw direction arrows
        ctx.fillStyle = canvas_renderer.rgba_to_css_color(
            self.scene.theme.ideal_curve_arrow['color']
        )

        if self.focalLength < 0:
            # Diverging mirror (negative focal length) - arrows point outward
            self._draw_arrow_outward(
                ctx, self.p1['x'], self.p1['y'],
                par_x, par_y, per_x, per_y,
                arrow_size_par, arrow_size_per
            )
            self._draw_arrow_outward(
                ctx, self.p2['x'], self.p2['y'],
                -par_x, -par_y, per_x, per_y,
                arrow_size_par, arrow_size_per
            )

        if self.focalLength > 0:
            # Converging mirror (positive focal length) - arrows point inward
            self._draw_arrow_inward(
                ctx, self.p1['x'], self.p1['y'],
                par_x, par_y, per_x, per_y,
                arrow_size_par, arrow_size_per
            )
            self._draw_arrow_inward(
                ctx, self.p2['x'], self.p2['y'],
                -par_x, -par_y, per_x, per_y,
                arrow_size_par, arrow_size_per
            )

        return True

    def _draw_arrow_outward(
        self, ctx: Any,
        x: float, y: float,
        par_x: float, par_y: float,
        per_x: float, per_y: float,
        size_par: float, size_per: float
    ) -> None:
        """
        Draw an outward-pointing arrow (for diverging mirrors).

        Args:
            ctx: Canvas rendering context
            x, y: Arrow base position
            par_x, par_y: Parallel unit vector
            per_x, per_y: Perpendicular unit vector
            size_par, size_per: Arrow size in parallel and perpendicular directions
        """
        ctx.beginPath()
        ctx.moveTo(x - par_x * size_par, y - par_y * size_par)
        ctx.lineTo(
            x + par_x * size_par + per_x * size_per,
            y + par_y * size_par + per_y * size_per
        )
        ctx.lineTo(
            x + par_x * size_par - per_x * size_per,
            y + par_y * size_par - per_y * size_per
        )
        ctx.fill()

    def _draw_arrow_inward(
        self, ctx: Any,
        x: float, y: float,
        par_x: float, par_y: float,
        per_x: float, per_y: float,
        size_par: float, size_per: float
    ) -> None:
        """
        Draw an inward-pointing arrow (for converging mirrors).

        Args:
            ctx: Canvas rendering context
            x, y: Arrow base position
            par_x, par_y: Parallel unit vector
            per_x, per_y: Perpendicular unit vector
            size_par, size_per: Arrow size in parallel and perpendicular directions
        """
        ctx.beginPath()
        ctx.moveTo(x + par_x * size_par, y + par_y * size_par)
        ctx.lineTo(
            x - par_x * size_par + per_x * size_per,
            y - par_y * size_par + per_y * size_per
        )
        ctx.lineTo(
            x - par_x * size_par - per_x * size_per,
            y - par_y * size_par - per_y * size_per
        )
        ctx.fill()

    def scale(self, scale: float, center: Optional['Point'] = None) -> bool:
        """
        Scale the mirror by the given factor.

        Args:
            scale: The scaling factor
            center: The center point for scaling

        Returns:
            True when complete
        """
        # Scale the line endpoints
        super().scale(scale, center)

        # Scale the focal length
        self.focalLength *= scale

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
        Handle a ray incident on the ideal mirror.

        This implements the ideal mirror equation by:
        1. Calculating the mirror's optical axis (perpendicular to the surface)
        2. Finding points at 2F (two focal lengths) on both sides
        3. Using ray construction similar to thin lens equation
        4. Mirroring the result to get reflection instead of transmission

        Args:
            ray: The incident ray
            ray_index: Index of the ray in the simulation
            incident_point: The point where the ray hits the mirror
            surface_merging_objs: List of objects for surface merging (unused for mirrors)
            verbose: Verbosity level for debugging

        Returns:
            None (modifies ray in place)
        """
        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Surface Hit Records (Step B, opt-in)
        # =====================================================================
        # Record hit geometry BEFORE ray.p1/p2 are overwritten below. The mirror
        # normal is perpendicular to its surface direction (p2 - p1); the angle of
        # incidence is measured from that normal using the ORIGINAL incident
        # direction (incident_point - ray.p1). CONTRIBUTING.md acos clamp applies.
        if getattr(ray, 'record_surface_hits', False):
            mx: float = self.p2['x'] - self.p1['x']
            my: float = self.p2['y'] - self.p1['y']
            di_x: float = incident_point['x'] - ray.p1['x']
            di_y: float = incident_point['y'] - ray.p1['y']
            m_len: float = math.hypot(mx, my)
            di_len: float = math.hypot(di_x, di_y)
            if m_len > 0 and di_len > 0:
                nx: float = -my / m_len
                ny: float = mx / m_len
                cos_inc: float = abs((di_x * nx + di_y * ny) / di_len)
                ray.hit_surface_uuid = self._uuid
                ray.hit_point = {'x': incident_point['x'], 'y': incident_point['y']}
                ray.hit_normal = {'x': nx, 'y': ny}
                ray.incident_angle = math.acos(max(-1.0, min(1.0, cos_inc)))

        # Calculate mirror geometry
        # Convert dict points to Point objects for geometry calculations
        p1_point = geometry.point(self.p1['x'], self.p1['y'])
        p2_point = geometry.point(self.p2['x'], self.p2['y'])
        mirror_line = geometry.line(p1_point, p2_point)

        mirror_length: float = geometry.segment_length(mirror_line)
        mid_point_obj = geometry.segment_midpoint(mirror_line)
        mid_point: Dict[str, float] = {'x': mid_point_obj.x, 'y': mid_point_obj.y}

        # Unit vector perpendicular to mirror (the optical axis direction)
        main_line_unitvector_x: float = (-self.p1['y'] + self.p2['y']) / mirror_length
        main_line_unitvector_y: float = (self.p1['x'] - self.p2['x']) / mirror_length

        # Points at 2F on both sides of the mirror (these are Point objects)
        twoF_point_1 = geometry.point(
            mid_point['x'] + main_line_unitvector_x * 2 * self.focalLength,
            mid_point['y'] + main_line_unitvector_y * 2 * self.focalLength
        )
        twoF_point_2 = geometry.point(
            mid_point['x'] - main_line_unitvector_x * 2 * self.focalLength,
            mid_point['y'] - main_line_unitvector_y * 2 * self.focalLength
        )

        # Determine which 2F point is on the same side as the incident ray
        ray_p1_pt = geometry.point(ray.p1['x'], ray.p1['y'])

        dist_1: float = geometry.distance_squared(ray_p1_pt, twoF_point_1)
        dist_2: float = geometry.distance_squared(ray_p1_pt, twoF_point_2)

        if dist_1 < dist_2:
            # Point 1 is on the same side as the incident ray
            twoF_line_near = geometry.parallel_line_through_point(mirror_line, twoF_point_1)
            twoF_line_far = geometry.parallel_line_through_point(mirror_line, twoF_point_2)
        else:
            # Point 2 is on the same side as the incident ray
            twoF_line_near = geometry.parallel_line_through_point(mirror_line, twoF_point_2)
            twoF_line_far = geometry.parallel_line_through_point(mirror_line, twoF_point_1)

        # Apply ideal lens equation (ray construction method)
        # Convert ray to Line object
        ray_p1 = geometry.point(ray.p1['x'], ray.p1['y'])
        ray_p2 = geometry.point(ray.p2['x'], ray.p2['y'])
        ray_line = geometry.line(ray_p1, ray_p2)

        if self.focalLength > 0:
            # Converging mirror
            # Ray path: from incident point through near 2F, then from center through that intersection
            intersection_near_obj = geometry.lines_intersection(twoF_line_near, ray_line)
            mid_point_pt = geometry.point(mid_point['x'], mid_point['y'])
            center_line = geometry.line(mid_point_pt, intersection_near_obj)
            new_p2_obj = geometry.lines_intersection(twoF_line_far, center_line)

            ray.p2 = {'x': new_p2_obj.x, 'y': new_p2_obj.y}
            ray.p1 = {'x': incident_point['x'], 'y': incident_point['y']}
        else:
            # Diverging mirror
            # More complex construction for negative focal length
            intersection_far_obj = geometry.lines_intersection(twoF_line_far, ray_line)
            mid_point_pt = geometry.point(mid_point['x'], mid_point['y'])
            mid_to_far_line = geometry.line(mid_point_pt, intersection_far_obj)
            intersection_near_virtual_obj = geometry.lines_intersection(
                twoF_line_near,
                mid_to_far_line
            )
            incident_point_pt = geometry.point(incident_point['x'], incident_point['y'])
            incident_to_near_line = geometry.line(
                incident_point_pt,
                intersection_near_virtual_obj
            )
            new_p2_obj = geometry.lines_intersection(
                twoF_line_far,
                incident_to_near_line
            )

            ray.p2 = {'x': new_p2_obj.x, 'y': new_p2_obj.y}
            ray.p1 = {'x': incident_point['x'], 'y': incident_point['y']}

        # The above calculation is for an ideal lens - now mirror it for reflection
        # Swap p1 and p2, then reflect across the mirror surface
        ray.p1['x'] = 2 * ray.p1['x'] - ray.p2['x']
        ray.p1['y'] = 2 * ray.p1['y'] - ray.p2['y']

        # Calculate reflection across mirror surface
        # Vector from incident point to new p1
        rx: float = ray.p1['x'] - incident_point['x']
        ry: float = ray.p1['y'] - incident_point['y']

        # Mirror surface direction vector
        mx: float = self.p2['x'] - self.p1['x']
        my: float = self.p2['y'] - self.p1['y']

        # Reflect the vector across the mirror surface
        # Formula: r' = r - 2(r·n)n where n is the surface normal
        # For a line, we can use: r'_x = r_x(m_y² - m_x²) - 2*r_y*m_x*m_y
        #                        r'_y = r_y(m_x² - m_y²) - 2*r_x*m_x*m_y
        ray.p1 = {'x': incident_point['x'], 'y': incident_point['y']}
        ray.p2 = {
            'x': incident_point['x'] + rx * (my * my - mx * mx) - 2 * ry * mx * my,
            'y': incident_point['y'] + ry * (mx * mx - my * my) - 2 * rx * mx * my
        }

        return None


# Example usage and testing
if __name__ == "__main__":
    print("Testing IdealMirror class...\n")

    # Mock classes for testing
    class MockScene:
        def __init__(self):
            self.objs = []
            self.length_scale = 1.0
            self.simulate_colors = False
            self.highlight_color_css = '#ff0000'
            self.theme = {
                'mirror': {'width': 2, 'color': [168, 168, 168, 255]},
                'ideal_curve_arrow': {'size': 10, 'color': [0, 0, 0, 255]},
                'ideal_curve_center': {'size': 2, 'color': [255, 0, 0, 255]}
            }

    class MockRay:
        def __init__(self, p1, p2, wavelength=None):
            self.p1 = p1
            self.p2 = p2
            self.wavelength = wavelength
            self.brightness_s = 1.0
            self.brightness_p = 0.0

    scene = MockScene()

    # Test 1: Create a basic ideal mirror
    print("Test 1: Basic ideal mirror creation")
    mirror1 = IdealMirror(scene, {
        'p1': {'x': 100, 'y': 100},
        'p2': {'x': 100, 'y': 200},
        'focalLength': 50
    })
    print(f"  Type: {mirror1.type}")
    print(f"  Focal length: {mirror1.focalLength}")
    print(f"  p1: {mirror1.p1}")
    print(f"  p2: {mirror1.p2}")
    print(f"  Is optical: {mirror1.is_optical}")
    print(f"  Merges with glass: {mirror1.merges_with_glass}")

    # Test 2: Converging mirror (positive focal length)
    print("\nTest 2: Converging mirror (f=50)")
    mirror2 = IdealMirror(scene, {
        'p1': {'x': 200, 'y': 150},
        'p2': {'x': 200, 'y': 250},
        'focalLength': 50,
        'filter': False
    })
    print(f"  Focal length: {mirror2.focalLength}")
    print(f"  Filter enabled: {mirror2.filter}")

    # Test horizontal ray hitting vertical mirror
    ray = MockRay({'x': 150, 'y': 200}, {'x': 250, 'y': 200})
    incident_point = {'x': 200, 'y': 200}

    print(f"  Incident ray: ({ray.p1['x']}, {ray.p1['y']}) -> ({ray.p2['x']}, {ray.p2['y']})")
    mirror2.on_ray_incident(ray, 0, incident_point)
    print(f"  Reflected ray: ({ray.p1['x']:.2f}, {ray.p1['y']:.2f}) -> ({ray.p2['x']:.2f}, {ray.p2['y']:.2f})")

    # Test 3: Diverging mirror (negative focal length)
    print("\nTest 3: Diverging mirror (f=-50)")
    mirror3 = IdealMirror(scene, {
        'p1': {'x': 200, 'y': 150},
        'p2': {'x': 200, 'y': 250},
        'focalLength': -50,
        'filter': False
    })
    print(f"  Focal length: {mirror3.focalLength}")

    ray2 = MockRay({'x': 150, 'y': 200}, {'x': 250, 'y': 200})
    incident_point2 = {'x': 200, 'y': 200}

    print(f"  Incident ray: ({ray2.p1['x']}, {ray2.p1['y']}) -> ({ray2.p2['x']}, {ray2.p2['y']})")
    mirror3.on_ray_incident(ray2, 0, incident_point2)
    print(f"  Reflected ray: ({ray2.p1['x']:.2f}, {ray2.p1['y']:.2f}) -> ({ray2.p2['x']:.2f}, {ray2.p2['y']:.2f})")

    # Test 4: Scaling
    print("\nTest 4: Scaling mirror")
    mirror4 = IdealMirror(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 100, 'y': 0},
        'focalLength': 50
    })
    print(f"  Before scaling: p1={mirror4.p1}, p2={mirror4.p2}, f={mirror4.focalLength}")

    center = geometry.point(0, 0)
    mirror4.scale(2.0, center)
    print(f"  After 2x scaling: p1={mirror4.p1}, p2={mirror4.p2}, f={mirror4.focalLength}")

    # Test 5: Wavelength filter
    print("\nTest 5: Wavelength filtering")
    mirror5 = IdealMirror(scene, {
        'p1': {'x': 100, 'y': 100},
        'p2': {'x': 100, 'y': 200},
        'focalLength': 50,
        'filter': True,
        'wavelength': 532,  # Green
        'bandwidth': 10
    })
    scene.simulate_colors = True

    ray_green = MockRay({'x': 50, 'y': 150}, {'x': 150, 'y': 150}, wavelength=532)
    ray_red = MockRay({'x': 50, 'y': 150}, {'x': 150, 'y': 150}, wavelength=650)

    print(f"  Filter: wavelength={mirror5.wavelength}nm, bandwidth=±{mirror5.bandwidth}nm")
    print(f"  Green ray (532nm): {mirror5.check_ray_intersect_filter(ray_green)}")
    print(f"  Red ray (650nm): {mirror5.check_ray_intersect_filter(ray_red)}")

    # Test 6: Serialization
    print("\nTest 6: Serialization")
    mirror6 = IdealMirror(scene, {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 100, 'y': 100},
        'focalLength': 75,
        'filter': True,
        'wavelength': 650
    })
    serialized = mirror6.serialize()
    print(f"  Serialized: {serialized}")

    print("\nIdealMirror test completed successfully!")
