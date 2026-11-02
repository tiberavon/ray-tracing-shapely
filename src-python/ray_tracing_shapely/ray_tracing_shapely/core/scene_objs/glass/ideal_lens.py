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
    from ray_tracing_shapely.core.scene_objs.line_obj_mixin import LineObjMixin
    from ray_tracing_shapely.core import geometry
else:
    from ..base_scene_obj import BaseSceneObj
    from ..line_obj_mixin import LineObjMixin
    from ... import geometry


class IdealLens(LineObjMixin, BaseSceneObj):
    """
    Ideal thin lens using ray tracing formulas.

    An ideal lens is a line segment that refracts rays according to the thin lens
    approximation. It uses geometric ray tracing based on focal points rather than
    Snell's law, making it computationally efficient and avoiding chromatic aberration.

    Attributes:
        p1: The first endpoint of the line segment.
        p2: The second endpoint of the line segment.
        focalLength: The focal length of the lens (positive = converging, negative = diverging).

    Usage:
        Ideal lenses are useful for:
        - Modeling thin lenses without chromatic aberration
        - Creating collimated beams from point sources (place source at focal point)
        - Fast optical system design and testing
        - Educational demonstrations of lens behavior

    Notes:
        - Positive focal length = converging (convex) lens
        - Negative focal length = diverging (concave) lens
        - The lens uses geometric ray tracing rules:
          * Ray through center continues straight
          * Ray parallel to axis passes through far focal point
          * Ray through near focal point exits parallel to axis
        - Does not model chromatic aberration or spherical aberration
    """

    type = 'IdealLens'
    is_optical = True
    serializable_defaults = {
        'p1': None,
        'p2': None,
        'focalLength': 100
    }

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with ideal lens controls.

        Args:
            obj_bar: The object bar to populate.
        """
        obj_bar.set_title('Ideal Lens')

        # Focal length control
        obj_bar.create_number(
            'Focal Length',
            -1000 * self.scene.length_scale, 1000 * self.scene.length_scale, 1 * self.scene.length_scale,
            self.focalLength,
            lambda obj, value: setattr(obj, 'focalLength', value),
            'Focal length of the lens. Positive = converging, negative = diverging.'
        )

    def draw(self, canvas_renderer, is_above_light, is_hovered):
        """
        Draw the ideal lens on the canvas.

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether rendering above the light layer.
            is_hovered: Whether the lens is hovered by the mouse.
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

        # Calculate parallel and perpendicular unit vectors
        length = math.sqrt((p2_x - p1_x) ** 2 + (p2_y - p1_y) ** 2)
        par_x = (p2_x - p1_x) / length
        par_y = (p2_y - p1_y) / length
        per_x = par_y
        per_y = -par_x

        arrow_size_per = self.scene.theme.ideal_curve_arrow.size / 2 * ls
        arrow_size_par = self.scene.theme.ideal_curve_arrow.size / 2 * ls
        center_size = self.scene.theme.ideal_curve_arrow.size / 5 * ls

        # Draw the line segment
        if is_hovered:
            stroke_color = self.scene.highlight_color_css
        else:
            # Blend glass color with background color
            glass_r = (self.scene.theme.glass.color[0] + self.scene.theme.background.color[0]) / 2
            glass_g = (self.scene.theme.glass.color[1] + self.scene.theme.background.color[1]) / 2
            glass_b = (self.scene.theme.glass.color[2] + self.scene.theme.background.color[2]) / 2
            stroke_color = canvas_renderer.rgba_to_css_color([glass_r, glass_g, glass_b, 1])

        ctx.strokeStyle = stroke_color
        # Alpha depends on focal length (weaker appearance for strong lenses)
        ctx.globalAlpha = 1 / ((abs(self.focalLength / self.scene.length_scale) / 100) + 1)
        ctx.lineWidth = self.scene.theme.ideal_curve_arrow.size / 5 * 2 * ls
        ctx.beginPath()
        ctx.moveTo(p1_x, p1_y)
        ctx.lineTo(p2_x, p2_y)
        ctx.stroke()
        ctx.lineWidth = 1 * ls

        ctx.globalAlpha = 1
        ctx.fillStyle = canvas_renderer.rgba_to_css_color(self.scene.theme.ideal_curve_arrow.color)

        # Draw the center point of the lens
        center = geometry.segment_midpoint(self)
        center_x = center['x'] if isinstance(center, dict) else center.x
        center_y = center['y'] if isinstance(center, dict) else center.y

        ctx.strokeStyle = canvas_renderer.rgba_to_css_color(self.scene.theme.ideal_curve_center.color)
        ctx.beginPath()
        ctx.moveTo(center_x - per_x * center_size, center_y - per_y * center_size)
        ctx.lineTo(center_x + per_x * center_size, center_y + per_y * center_size)
        ctx.stroke()

        # Draw arrows indicating lens type
        if self.focalLength > 0:
            # Converging lens - arrows pointing outward
            # Arrow at p1
            ctx.beginPath()
            ctx.moveTo(p1_x - par_x * arrow_size_par, p1_y - par_y * arrow_size_par)
            ctx.lineTo(p1_x + par_x * arrow_size_par + per_x * arrow_size_per,
                      p1_y + par_y * arrow_size_par + per_y * arrow_size_per)
            ctx.lineTo(p1_x + par_x * arrow_size_par - per_x * arrow_size_per,
                      p1_y + par_y * arrow_size_par - per_y * arrow_size_per)
            ctx.fill()

            # Arrow at p2
            ctx.beginPath()
            ctx.moveTo(p2_x + par_x * arrow_size_par, p2_y + par_y * arrow_size_par)
            ctx.lineTo(p2_x - par_x * arrow_size_par + per_x * arrow_size_per,
                      p2_y - par_y * arrow_size_par + per_y * arrow_size_per)
            ctx.lineTo(p2_x - par_x * arrow_size_par - per_x * arrow_size_per,
                      p2_y - par_y * arrow_size_par - per_y * arrow_size_per)
            ctx.fill()

        elif self.focalLength < 0:
            # Diverging lens - arrows pointing inward
            # Arrow at p1
            ctx.beginPath()
            ctx.moveTo(p1_x + par_x * arrow_size_par, p1_y + par_y * arrow_size_par)
            ctx.lineTo(p1_x - par_x * arrow_size_par + per_x * arrow_size_per,
                      p1_y - par_y * arrow_size_par + per_y * arrow_size_per)
            ctx.lineTo(p1_x - par_x * arrow_size_par - per_x * arrow_size_per,
                      p1_y - par_y * arrow_size_par - per_y * arrow_size_per)
            ctx.fill()

            # Arrow at p2
            ctx.beginPath()
            ctx.moveTo(p2_x - par_x * arrow_size_par, p2_y - par_y * arrow_size_par)
            ctx.lineTo(p2_x + par_x * arrow_size_par + per_x * arrow_size_per,
                      p2_y + par_y * arrow_size_par + per_y * arrow_size_per)
            ctx.lineTo(p2_x + par_x * arrow_size_par - per_x * arrow_size_per,
                      p2_y + par_y * arrow_size_par - per_y * arrow_size_per)
            ctx.fill()

        # Show focal points when hovered
        if is_hovered:
            ctx.fillStyle = 'rgb(255,0,255)'
            ctx.fillRect(center_x + self.focalLength * per_x - 1.5 * ls,
                        center_y + self.focalLength * per_y - 1.5 * ls, 3 * ls, 3 * ls)
            ctx.fillRect(center_x - self.focalLength * per_x - 1.5 * ls,
                        center_y - self.focalLength * per_y - 1.5 * ls, 3 * ls, 3 * ls)

    def scale(self, scale_factor, center=None):
        """
        Scale the lens position and focal length.

        Args:
            scale_factor: The scale factor.
            center: Center of scaling (defaults to the lens itself).

        Returns:
            True to indicate the scaling was successful.
        """
        # Scale the position using parent method
        super().scale(scale_factor, center)
        # Also scale the focal length
        self.focalLength *= scale_factor
        return True

    def check_ray_intersects(self, ray):
        """
        Check if a ray intersects the lens.

        Args:
            ray: The ray to check.

        Returns:
            The intersection point if the ray intersects, None otherwise.
        """
        return self.check_ray_intersects_shape(ray)

    def on_ray_incident(self, ray, ray_index, incident_point, surface_merging_objs=None, verbose=0):
        """
        Handle ray incidence on the ideal lens.

        This implements the thin lens approximation using geometric ray tracing:
        - Find the line parallel to the lens through the near 2F point
        - Find where the incoming ray would intersect this line
        - Draw a line from the lens center through this intersection
        - Find where this line intersects the far 2F parallel line
        - This gives the outgoing ray direction

        Args:
            ray: The incident ray.
            ray_index: Index of the ray in the ray array.
            incident_point: The point where the ray hits the lens.
            surface_merging_objs: List of glass objects to merge with (unused for ideal lens).
            verbose: Verbosity level (default: 0)
                    0 = silent (no debug output)
                    1 = verbose (show ray processing info)
                    2 = very verbose/debug (show detailed calculations)

        Returns:
            None (modifies the ray in place).
        """
        if verbose >= 1:
            print(f"\n=== IDEAL LENS on_ray_incident CALLED ===")
            inc_x = incident_point['x'] if isinstance(incident_point, dict) else incident_point.x
            inc_y = incident_point['y'] if isinstance(incident_point, dict) else incident_point.y
            print(f"  Incident point: ({inc_x:.4f}, {inc_y:.4f})")
            print(f"  Focal length: {self.focalLength:.4f}")
            print(f"  Lens type: {'Converging' if self.focalLength > 0 else 'Diverging'}")

        # Extract coordinates handling both dict and Point objects
        if isinstance(self.p1, dict):
            p1_x, p1_y = self.p1['x'], self.p1['y']
            p2_x, p2_y = self.p2['x'], self.p2['y']
        else:
            p1_x, p1_y = self.p1.x, self.p1.y
            p2_x, p2_y = self.p2.x, self.p2.y

        # Calculate lens properties
        lens_length = math.sqrt((p2_x - p1_x) ** 2 + (p2_y - p1_y) ** 2)
        main_line_unitvector_x = (-p1_y + p2_y) / lens_length
        main_line_unitvector_y = (p1_x - p2_x) / lens_length

        # Calculate midpoint
        mid_x = (p1_x + p2_x) / 2
        mid_y = (p1_y + p2_y) / 2
        mid_point = geometry.point(mid_x, mid_y)

        # Calculate points at two focal lengths (2F) on each side
        twoF_point_1 = geometry.point(
            mid_x + main_line_unitvector_x * 2 * self.focalLength,
            mid_y + main_line_unitvector_y * 2 * self.focalLength
        )
        twoF_point_2 = geometry.point(
            mid_x - main_line_unitvector_x * 2 * self.focalLength,
            mid_y - main_line_unitvector_y * 2 * self.focalLength
        )

        # Convert ray points to Point objects for geometry calculations
        ray_p1_point = geometry.point(ray.p1['x'], ray.p1['y']) if isinstance(ray.p1, dict) else ray.p1
        ray_p2_point = geometry.point(ray.p2['x'], ray.p2['y']) if isinstance(ray.p2, dict) else ray.p2
        ray_line = geometry.line(ray_p1_point, ray_p2_point)

        # Determine which 2F point is on the near side (same side as ray origin)
        dist_sq_1 = geometry.distance_squared(ray_p1_point, twoF_point_1)
        dist_sq_2 = geometry.distance_squared(ray_p1_point, twoF_point_2)

        # Create a Line object for the lens for use with parallel_line_through_point
        lens_line = geometry.line(geometry.point(p1_x, p1_y), geometry.point(p2_x, p2_y))

        if dist_sq_1 < dist_sq_2:
            twoF_line_near = geometry.parallel_line_through_point(lens_line, twoF_point_1)
            twoF_line_far = geometry.parallel_line_through_point(lens_line, twoF_point_2)
        else:
            twoF_line_near = geometry.parallel_line_through_point(lens_line, twoF_point_2)
            twoF_line_far = geometry.parallel_line_through_point(lens_line, twoF_point_1)

        if self.focalLength > 0:
            # Converging lens
            # Find where the incoming ray intersects the near 2F line
            intersection_near = geometry.lines_intersection(twoF_line_near, ray_line)
            # Draw line from lens center through this intersection
            center_line = geometry.line(mid_point, intersection_near)
            # Find where this line intersects the far 2F line
            intersection_far = geometry.lines_intersection(twoF_line_far, center_line)
            # Set the outgoing ray (convert Point to dict if needed)
            if isinstance(ray.p2, dict):
                ray.p2['x'] = intersection_far.x
                ray.p2['y'] = intersection_far.y
                ray.p1['x'] = incident_point['x'] if isinstance(incident_point, dict) else incident_point.x
                ray.p1['y'] = incident_point['y'] if isinstance(incident_point, dict) else incident_point.y
            else:
                ray.p2 = intersection_far
                ray.p1 = incident_point
        else:
            # Diverging lens
            # More complex: trace virtual ray through far focal point
            intersection_far_virtual = geometry.lines_intersection(twoF_line_far, ray_line)
            center_line_virtual = geometry.line(mid_point, intersection_far_virtual)
            intersection_near = geometry.lines_intersection(twoF_line_near, center_line_virtual)
            incident_line = geometry.line(incident_point, intersection_near)
            intersection_far = geometry.lines_intersection(twoF_line_far, incident_line)
            # Set the outgoing ray (convert Point to dict if needed)
            if isinstance(ray.p2, dict):
                ray.p2['x'] = intersection_far.x
                ray.p2['y'] = intersection_far.y
                ray.p1['x'] = incident_point['x'] if isinstance(incident_point, dict) else incident_point.x
                ray.p1['y'] = incident_point['y'] if isinstance(incident_point, dict) else incident_point.y
            else:
                ray.p2 = intersection_far
                ray.p1 = incident_point


# Example usage and testing
if __name__ == "__main__":
    print("Testing IdealLens class...\n")

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.length_scale = 1.0
            self.highlight_color_css = 'rgb(255,0,255)'

            # Mock theme
            class MockTheme:
                class MockGlass:
                    color = [0.8, 0.8, 1.0, 1.0]

                class MockBackground:
                    color = [1.0, 1.0, 1.0, 1.0]

                class MockIdealCurveArrow:
                    size = 10
                    color = [0.5, 0.5, 0.5, 1.0]

                class MockIdealCurveCenter:
                    color = [0.0, 0.0, 0.0, 1.0]

                glass = MockGlass()
                background = MockBackground()
                ideal_curve_arrow = MockIdealCurveArrow()
                ideal_curve_center = MockIdealCurveCenter()

            self.theme = MockTheme()

    # Mock ray - use dict format for compatibility with LineObjMixin
    class MockRay:
        def __init__(self, p1_dict, p2_dict):
            self.p1 = p1_dict
            self.p2 = p2_dict
            self.brightness_s = 1.0
            self.brightness_p = 1.0

    # Test 1: Converging lens
    print("Test 1: Converging lens (f = 100)")
    scene = MockScene()
    lens = IdealLens(scene, {
        'p1': {'x': 200, 'y': -100},
        'p2': {'x': 200, 'y': 100},
        'focalLength': 100
    })

    print(f"  Lens position: ({lens.p1['x']}, {lens.p1['y']}) to ({lens.p2['x']}, {lens.p2['y']})")
    print(f"  Focal length: {lens.focalLength}")
    print(f"  Type: {'Converging' if lens.focalLength > 0 else 'Diverging'}")

    # Test ray parallel to axis (should pass through focal point)
    ray_parallel = MockRay({'x': 0, 'y': 50}, {'x': 300, 'y': 50})
    intersection = lens.check_ray_intersects(ray_parallel)
    print(f"  Parallel ray intersects: {intersection is not None}")

    if intersection:
        if hasattr(intersection, 'x'):
            print(f"  Intersection point: ({intersection.x:.2f}, {intersection.y:.2f})")
        else:
            print(f"  Intersection point: ({intersection['x']:.2f}, {intersection['y']:.2f})")

        # Refract the ray
        lens.on_ray_incident(ray_parallel, 0, intersection)
        p2 = ray_parallel.p2
        p2_x = p2['x'] if isinstance(p2, dict) else p2.x
        p2_y = p2['y'] if isinstance(p2, dict) else p2.y
        print(f"  Refracted ray direction: ({p2_x:.2f}, {p2_y:.2f})")

    # Test 2: Diverging lens
    print("\nTest 2: Diverging lens (f = -100)")
    lens_diverging = IdealLens(scene, {
        'p1': {'x': 200, 'y': -100},
        'p2': {'x': 200, 'y': 100},
        'focalLength': -100
    })

    print(f"  Focal length: {lens_diverging.focalLength}")
    print(f"  Type: {'Converging' if lens_diverging.focalLength > 0 else 'Diverging'}")

    # Test ray parallel to axis (should diverge)
    ray_parallel_2 = MockRay({'x': 0, 'y': 50}, {'x': 300, 'y': 50})
    intersection_2 = lens_diverging.check_ray_intersects(ray_parallel_2)
    print(f"  Parallel ray intersects: {intersection_2 is not None}")

    if intersection_2:
        lens_diverging.on_ray_incident(ray_parallel_2, 0, intersection_2)
        p2_2 = ray_parallel_2.p2
        p2_x_2 = p2_2['x'] if isinstance(p2_2, dict) else p2_2.x
        p2_y_2 = p2_2['y'] if isinstance(p2_2, dict) else p2_2.y
        print(f"  Refracted ray direction: ({p2_x_2:.2f}, {p2_y_2:.2f})")

    # Test 3: Scaling
    print("\nTest 3: Scaling")
    lens_scale = IdealLens(scene, {
        'p1': {'x': 0, 'y': -50},
        'p2': {'x': 0, 'y': 50},
        'focalLength': 100
    })

    print(f"  Initial focal length: {lens_scale.focalLength}")
    # Calculate length manually since lens has dict points
    initial_len = math.sqrt((lens_scale.p2['x'] - lens_scale.p1['x'])**2 + (lens_scale.p2['y'] - lens_scale.p1['y'])**2)
    print(f"  Initial length: {initial_len:.2f}")

    lens_scale.scale(2.0)
    print(f"  After scale(2.0) focal length: {lens_scale.focalLength}")
    scaled_len = math.sqrt((lens_scale.p2['x'] - lens_scale.p1['x'])**2 + (lens_scale.p2['y'] - lens_scale.p1['y'])**2)
    print(f"  After scale(2.0) length: {scaled_len:.2f}")

    # Test 4: Ray that misses the lens
    print("\nTest 4: Ray that misses the lens")
    ray_miss = MockRay({'x': 0, 'y': 200}, {'x': 300, 'y': 200})
    intersection_miss = lens.check_ray_intersects(ray_miss)
    print(f"  Ray intersects: {intersection_miss is not None}")

    print("\nIdealLens test completed successfully!")
