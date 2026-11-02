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

Copyright 2025 The Ray Optics Simulation authors and contributors

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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from geometry import geometry
from equation import evaluate_latex
from typing import Optional, Dict, Any, List
import math


class ParamCurveObjMixin:
    """
    Mixin for scene objects that are defined by parametric curve equations.

    This mixin provides functionality for objects defined by parametric equations
    x(t) and y(t) over ranges of the parameter t. It supports multiple pieces
    (piecewise parametric curves).

    Expected attributes in the class using this mixin:
    - origin: Dict with 'x' and 'y' keys for the curve origin
    - pieces: List of dicts, each with 'eqnX', 'eqnY', 'tMin', 'tMax', 'tStep'
    - scene: Reference to the scene object
    - path: Optional cached list of points on the curve
    - error: Optional error message string
    - intersect_tol: Tolerance for intersection detection (optional, defaults to appropriate value)
    
    features:

    - LaTeX equation support - We built a full LaTeX parser with evaluate_latex() that handles fractions, trig functions, powers, etc. 
    - Piecewise curves - Supporting multiple pieces with different equations is powerful
    - Inside/outside testing - The crossing number algorithm with boundary detection is well-implemented
    - Ray intersections - The normal vector calculation with smoothing at segment joints is sophisticated
    
    design choices:

    - Caching path points (only regenerating when needed)
    - Error handling throughout with informative messages
    - The sech custom function for GRIN lens support
    
    """

    def __init__(self, scene, json_obj: Optional[Dict[str, Any]] = None):
        """
        Initialize the parametric curve object.

        Args:
            scene: The scene object
            json_obj: Optional JSON object for deserialization
        """
        super().__init__(scene, json_obj)

        # Check for unknown keys in pieces
        known_keys = ['eqnX', 'eqnY', 'tMin', 'tMax', 'tStep']
        for i, piece in enumerate(self.pieces):
            for key in piece.keys():
                if key not in known_keys:
                    # Store error in scene to prevent further errors from replacing it
                    self.scene.error = f"Unknown key 'pieces[{i}].{key}' in object type '{self.type}'"

    def move(self, diff_x: float, diff_y: float) -> bool:
        """
        Move the parametric curve by a given offset.

        Args:
            diff_x: X offset
            diff_y: Y offset

        Returns:
            True if the object was moved successfully
        """
        self.origin['x'] = self.origin['x'] + diff_x
        self.origin['y'] = self.origin['y'] + diff_y

        # Invalidate path after moving
        if hasattr(self, 'path'):
            delattr(self, 'path')

        return True

    def rotate(self, angle: float, center=None) -> bool:
        """
        Rotate the parametric curve around a center point.

        Args:
            angle: Rotation angle in radians
            center: Center of rotation (Point object). If None, uses origin.

        Returns:
            False (indicates that the object bar needs to be updated)
        """
        # Use origin as default rotation center if none is provided
        if center is None:
            rotation_center = geometry.point(self.origin['x'], self.origin['y'])
        else:
            rotation_center = center

        # Calculate difference from rotation center for origin
        diff_x = self.origin['x'] - rotation_center.x
        diff_y = self.origin['y'] - rotation_center.y

        # Apply rotation matrix to origin
        self.origin['x'] = rotation_center.x + diff_x * math.cos(angle) - diff_y * math.sin(angle)
        self.origin['y'] = rotation_center.y + diff_x * math.sin(angle) + diff_y * math.cos(angle)

        # Invalidate path after rotating
        if hasattr(self, 'path'):
            delattr(self, 'path')

        return False

    def scale(self, scale_factor: float, center=None) -> bool:
        """
        Scale the parametric curve around a center point.

        Args:
            scale_factor: Scaling factor
            center: Center of scaling (Point object). If None, uses origin.

        Returns:
            False (indicates that the object bar needs to be updated)
        """
        # Use origin as default scaling center if none is provided
        if center is None:
            scaling_center = geometry.point(self.origin['x'], self.origin['y'])
        else:
            scaling_center = center

        # Calculate difference from scaling center for origin
        diff_x = self.origin['x'] - scaling_center.x
        diff_y = self.origin['y'] - scaling_center.y

        # Apply scaling to origin
        self.origin['x'] = scaling_center.x + diff_x * scale_factor
        self.origin['y'] = scaling_center.y + diff_y * scale_factor

        # Invalidate path after scaling
        if hasattr(self, 'path'):
            delattr(self, 'path')

        return False

    def get_default_center(self):
        """
        Get the default center of rotation or scaling.

        Returns:
            Point object representing the origin of the curve.
        """
        return geometry.point(self.origin['x'], self.origin['y'])

    def on_construct_mouse_down(self, mouse, ctrl: bool, shift: bool):
        """
        Mouse down event when the object is being constructed by the user.

        Args:
            mouse: The mouse object
            ctrl: Whether the control key is pressed
            shift: Whether the shift key is pressed
        """
        mouse_pos = mouse.get_pos_snapped_to_grid()
        self.origin['x'] = mouse_pos['x']
        self.origin['y'] = mouse_pos['y']

        # Invalidate path during construction
        if hasattr(self, 'path'):
            delattr(self, 'path')

    def on_construct_mouse_move(self, mouse, ctrl: bool, shift: bool):
        """
        Mouse move event when the object is being constructed by the user.

        Args:
            mouse: The mouse object
            ctrl: Whether the control key is pressed
            shift: Whether the shift key is pressed
        """
        # No movement during construction for point-based objects
        # Invalidate path during construction
        if hasattr(self, 'path'):
            delattr(self, 'path')

    def on_construct_mouse_up(self, mouse, ctrl: bool, shift: bool) -> Dict[str, Any]:
        """
        Mouse up event when the object is being constructed by the user.

        Args:
            mouse: The mouse object
            ctrl: Whether the control key is pressed
            shift: Whether the shift key is pressed

        Returns:
            Dict with 'is_done' key indicating construction is complete
        """
        # Invalidate path after construction
        if hasattr(self, 'path'):
            delattr(self, 'path')

        return {'is_done': True}

    def init_path(self) -> bool:
        """
        Initialize the path points based on the parametric curve pieces.

        This method generates points for each piece from tMin to tMax with the given step.

        Returns:
            True if the initialization was successful, False otherwise
        """
        fns = []
        try:
            # Compile all the equations
            for i, piece in enumerate(self.pieces):
                fns.append({
                    'fn_x': evaluate_latex(piece['eqnX']),
                    'fn_y': evaluate_latex(piece['eqnY'])
                })
        except Exception as e:
            if hasattr(self, 'path'):
                delattr(self, 'path')
            self.error = str(e)
            return False

        self.path = []

        # Generate points for each piece
        for piece_index, piece in enumerate(self.pieces):
            fn = fns[piece_index]

            t_min = piece['tMin']
            t_max = piece['tMax']
            t_step = piece['tStep']

            if not (t_step > 0):
                if hasattr(self, 'path'):
                    delattr(self, 'path')
                self.error = f"Invalid step size: {t_step}"
                return False

            if not (t_min < t_max):
                if hasattr(self, 'path'):
                    delattr(self, 'path')
                self.error = f"Invalid range: tMin={t_min}, tMax={t_max}"
                return False

            # Always sample t=tMin
            try:
                x = fn['fn_x'](t=t_min)
                y = fn['fn_y'](t=t_min)

                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError(f"Non-finite coordinates at t={t_min}: x={x}, y={y}")

                self.path.append({
                    'x': self.origin['x'] + x,
                    'y': self.origin['y'] + y,
                    'piece_index': piece_index,
                    't': t_min
                })
            except Exception as e:
                if hasattr(self, 'path'):
                    delattr(self, 'path')
                self.error = f"Error in piece {piece_index + 1} at t={t_min}: {str(e)}"
                return False

            # Sample intermediate points
            t = t_min + t_step
            while t < t_max:
                try:
                    x = fn['fn_x'](t=t)
                    y = fn['fn_y'](t=t)

                    if not (math.isfinite(x) and math.isfinite(y)):
                        raise ValueError(f"Non-finite coordinates at t={t}: x={x}, y={y}")

                    self.path.append({
                        'x': self.origin['x'] + x,
                        'y': self.origin['y'] + y,
                        'piece_index': piece_index,
                        't': t
                    })
                except Exception as e:
                    if hasattr(self, 'path'):
                        delattr(self, 'path')
                    self.error = f"Error in piece {piece_index + 1} at t={t}: {str(e)}"
                    return False

                t += t_step

            # Always sample t=tMax (unless it's the same as tMin)
            if t_max > t_min:
                try:
                    x = fn['fn_x'](t=t_max)
                    y = fn['fn_y'](t=t_max)

                    if not (math.isfinite(x) and math.isfinite(y)):
                        raise ValueError(f"Non-finite coordinates at t={t_max}: x={x}, y={y}")

                    self.path.append({
                        'x': self.origin['x'] + x,
                        'y': self.origin['y'] + y,
                        'piece_index': piece_index,
                        't': t_max
                    })
                except Exception as e:
                    if hasattr(self, 'path'):
                        delattr(self, 'path')
                    self.error = f"Error in piece {piece_index + 1} at t={t_max}: {str(e)}"
                    return False

        self.error = None
        return True

    def is_closed(self) -> bool:
        """
        Check if the parametric curve is closed.

        A curve is closed if the first point matches the last point within
        floating point error tolerance.

        Returns:
            True if the curve is closed, False otherwise
        """
        # Initialize path if needed
        if not hasattr(self, 'path'):
            if not self.init_path():
                return False

        if len(self.path) < 2:
            return False

        first_point = self.path[0]
        last_point = self.path[-1]

        # Check if first and last points are within floating point error
        tolerance = 1e-10
        dx = abs(first_point['x'] - last_point['x'])
        dy = abs(first_point['y'] - last_point['y'])

        return dx < tolerance and dy < tolerance

    def is_positively_oriented(self) -> bool:
        """
        Check if the parametric curve is positively oriented (clockwise in CG coords).

        Uses the shoelace formula to calculate signed area.

        Returns:
            True if the curve is positively oriented, False otherwise
        """
        # Initialize path if needed
        if not hasattr(self, 'path'):
            if not self.init_path():
                return False

        if len(self.path) < 3:
            return False

        # Calculate signed area using the shoelace formula
        signed_area = 0

        for i in range(len(self.path) - 1):
            p1 = self.path[i]
            p2 = self.path[i + 1]
            signed_area += (p1['x'] - p2['x']) * (p1['y'] + p2['y'])

        return signed_area > 0

    def is_outside(self, point) -> bool:
        """
        Check if a point is outside the parametric curve.

        Uses the crossing number algorithm.

        Args:
            point: Point object to test

        Returns:
            True if the point is outside the curve, False otherwise
        """
        # Initialize path if needed
        if not hasattr(self, 'path'):
            if not self.init_path():
                return False

        return not self.is_on_boundary(point) and self.count_intersections(point) % 2 == 0

    def is_inside(self, point) -> bool:
        """
        Check if a point is inside the parametric curve.

        Uses the crossing number algorithm.

        Args:
            point: Point object to test

        Returns:
            True if the point is inside the curve, False otherwise
        """
        # Initialize path if needed
        if not hasattr(self, 'path'):
            if not self.init_path():
                return False

        return not self.is_on_boundary(point) and self.count_intersections(point) % 2 == 1

    def is_on_boundary(self, point) -> bool:
        """
        Check if a point is on the boundary of the parametric curve.

        Uses distance-based approach for robustness.

        Args:
            point: Point object to test

        Returns:
            True if the point is on the boundary, False otherwise
        """
        # Initialize path if needed
        if not hasattr(self, 'path'):
            if not self.init_path():
                return False

        if len(self.path) < 2:
            return False

        # Get intersection tolerance (default to a reasonable value if not set)
        intersect_tol = getattr(self, 'intersect_tol', 1e-2)

        # Check distance to each segment
        for i in range(len(self.path) - 1):
            p1 = geometry.point(self.path[i]['x'], self.path[i]['y'])
            p2 = geometry.point(self.path[i + 1]['x'], self.path[i + 1]['y'])

            # Skip degenerate segments
            seg_length_sq = geometry.distance_squared(p1, p2)
            if seg_length_sq < 1e-20:
                continue

            # Calculate distance from point to line segment
            seg = geometry.line(p1, p2)
            dist_to_seg = self.distance_point_to_segment(point, seg)

            if dist_to_seg <= intersect_tol:
                return True

        return False

    def distance_point_to_segment(self, point, segment) -> float:
        """
        Calculate distance from a point to a line segment.

        Args:
            point: Point object
            segment: Line segment (Line object with p1 and p2)

        Returns:
            Distance from point to segment
        """
        p1 = segment.p1
        p2 = segment.p2

        dx = p2.x - p1.x
        dy = p2.y - p1.y
        length_sq = dx * dx + dy * dy

        if length_sq < 1e-20:
            # Degenerate segment - return distance to point
            return geometry.distance(point, p1)

        # Calculate parameter t for closest point on line
        t = ((point.x - p1.x) * dx + (point.y - p1.y) * dy) / length_sq

        # Clamp t to [0,1] to stay within segment
        t = max(0, min(1, t))

        # Calculate closest point on segment
        closest_x = p1.x + t * dx
        closest_y = p1.y + t * dy

        # Return distance to closest point
        return geometry.distance(point, geometry.point(closest_x, closest_y))

    def count_intersections(self, point) -> int:
        """
        Count intersections between a horizontal ray from the point and the curve.

        Uses crossing number algorithm that handles dense/repeated points.

        Args:
            point: Point object from which to cast the horizontal ray

        Returns:
            Number of intersections with the curve boundary
        """
        # Initialize path if needed
        if not hasattr(self, 'path'):
            if not self.init_path():
                return 0

        if len(self.path) < 2:
            return 0

        cnt = 0
        ray_y = point.y
        ray_start_x = point.x

        for i in range(len(self.path) - 1):
            p1_dict = self.path[i]
            p2_dict = self.path[i + 1]

            p1 = geometry.point(p1_dict['x'], p1_dict['y'])
            p2 = geometry.point(p2_dict['x'], p2_dict['y'])

            # Skip degenerate segments
            if geometry.distance_squared(p1, p2) < 1e-20:
                continue

            # Ensure p1.y <= p2.y for consistent crossing detection
            if p1.y > p2.y:
                p1, p2 = p2, p1

            # Check if ray intersects this segment's y range
            if ray_y > p2.y or ray_y <= p1.y:
                continue

            # Calculate x intersection point
            if abs(p2.y - p1.y) < 1e-10:
                # Nearly horizontal segment - skip to avoid numerical issues
                continue
            else:
                # Calculate intersection x-coordinate
                t = (ray_y - p1.y) / (p2.y - p1.y)
                intersect_x = p1.x + t * (p2.x - p1.x)

            # Check if intersection is to the right of the point
            if intersect_x > ray_start_x:
                cnt += 1

        return cnt

    def get_ray_intersections(self, ray) -> List[Dict[str, Any]]:
        """
        Get all ray intersections with the parametric curve.

        Returns an array of intersection data with normal vectors and incident types
        consistent with CustomArcSurface conventions for counterclockwise arcs.

        Args:
            ray: The ray to check intersections with

        Returns:
            List of intersection dicts with properties:
            - s_point: intersection point (Point object)
            - normal: Dict with 'x' and 'y' keys for normal vector
            - incident_type: 1 (inside to outside), -1 (outside to inside), or NaN
            - incident_piece: piece index (0-based)
            - incident_pos: parameter t value of the intersection
        """
        intersections = []

        # Initialize path if needed
        if not hasattr(self, 'path'):
            if not self.init_path():
                return intersections

        if len(self.path) < 2:
            return intersections

        # Check each segment in the path
        for i in range(len(self.path) - 1):
            p1_dict = self.path[i]
            p2_dict = self.path[i + 1]

            p1 = geometry.point(p1_dict['x'], p1_dict['y'])
            p2 = geometry.point(p2_dict['x'], p2_dict['y'])

            # Check for ray intersection with this segment
            ray_p1 = geometry.point(ray['p1']['x'], ray['p1']['y'])
            ray_p2 = geometry.point(ray['p2']['x'], ray['p2']['y'])

            rp_temp = geometry.lines_intersection(
                geometry.line(ray_p1, ray_p2),
                geometry.line(p1, p2)
            )

            if (geometry.intersection_is_on_segment(rp_temp, geometry.line(p1, p2)) and
                geometry.intersection_is_on_ray(rp_temp, ray) and
                geometry.distance_squared(ray_p1, rp_temp) > 1e-10):

                # Linear interpolation to find exact t value within the segment
                segment_length = geometry.distance(p1, p2)
                intersection_dist = geometry.distance(p1, rp_temp)
                segment_ratio = intersection_dist / segment_length if segment_length > 1e-10 else 0
                incident_pos = p1_dict['t'] + (p2_dict['t'] - p1_dict['t']) * segment_ratio

                # Calculate tangent vector (direction of parametric curve)
                tangent_x = p2.x - p1.x
                tangent_y = p2.y - p1.y
                tangent_length = math.sqrt(tangent_x * tangent_x + tangent_y * tangent_y)

                if tangent_length > 1e-10:
                    # Normalize tangent
                    tangent_norm_x = tangent_x / tangent_length
                    tangent_norm_y = tangent_y / tangent_length

                    # Calculate incident type using cross product
                    rcrosst = ((ray_p2.x - ray_p1.x) * tangent_norm_y -
                              (ray_p2.y - ray_p1.y) * tangent_norm_x)

                    if rcrosst > 1e-10:
                        incident_type = 1  # From inside to outside
                    elif rcrosst < -1e-10:
                        incident_type = -1  # From outside to inside
                    else:
                        incident_type = float('nan')  # Parallel/tangent

                    # Calculate basic normal for this segment
                    rdots = ((ray_p2.x - ray_p1.x) * tangent_norm_x +
                            (ray_p2.y - ray_p1.y) * tangent_norm_y)

                    normal_x = rdots * tangent_norm_x - (ray_p2.x - ray_p1.x)
                    normal_y = rdots * tangent_norm_y - (ray_p2.y - ray_p1.y)

                    # Smooth out the normal vector for better image detection
                    # Calculate fraction along the segment
                    if abs(tangent_x) > abs(tangent_y):
                        frac = (rp_temp.x - p1.x) / tangent_x
                    else:
                        frac = (rp_temp.y - p1.y) / tangent_y

                    normal_x_final = normal_x
                    normal_y_final = normal_y

                    # Apply smoothing if not at the endpoints and we have adjacent segments
                    if (i > 0 and frac < 0.5) or (i < len(self.path) - 2 and frac >= 0.5):
                        seg_a = None
                        if frac < 0.5 and i > 0:
                            seg_a_p1 = geometry.point(self.path[i - 1]['x'], self.path[i - 1]['y'])
                            seg_a_p2 = geometry.point(self.path[i]['x'], self.path[i]['y'])
                            seg_a = geometry.line(seg_a_p1, seg_a_p2)
                        elif frac >= 0.5 and i < len(self.path) - 2:
                            seg_a_p1 = geometry.point(self.path[i + 1]['x'], self.path[i + 1]['y'])
                            seg_a_p2 = geometry.point(self.path[i + 2]['x'], self.path[i + 2]['y'])
                            seg_a = geometry.line(seg_a_p1, seg_a_p2)

                        if seg_a:
                            tangent_a_x = seg_a.p2.x - seg_a.p1.x
                            tangent_a_y = seg_a.p2.y - seg_a.p1.y
                            tangent_a_length = math.sqrt(tangent_a_x * tangent_a_x +
                                                        tangent_a_y * tangent_a_y)

                            # Apply smoothing only if adjacent segments have comparable lengths
                            if (tangent_a_length / tangent_length < 10 and
                                tangent_length / tangent_a_length < 10):
                                tangent_a_norm_x = tangent_a_x / tangent_a_length
                                tangent_a_norm_y = tangent_a_y / tangent_a_length

                                rdots_a = ((ray_p2.x - ray_p1.x) * tangent_a_norm_x +
                                          (ray_p2.y - ray_p1.y) * tangent_a_norm_y)

                                normal_x_a = rdots_a * tangent_a_norm_x - (ray_p2.x - ray_p1.x)
                                normal_y_a = rdots_a * tangent_a_norm_y - (ray_p2.y - ray_p1.y)

                                # Blend the normals
                                if frac < 0.5:
                                    normal_x_final = normal_x * (0.5 + frac) + normal_x_a * (0.5 - frac)
                                    normal_y_final = normal_y * (0.5 + frac) + normal_y_a * (0.5 - frac)
                                else:
                                    normal_x_final = normal_x_a * (frac - 0.5) + normal_x * (1.5 - frac)
                                    normal_y_final = normal_y_a * (frac - 0.5) + normal_y * (1.5 - frac)

                    normal_len = math.sqrt(normal_x_final * normal_x_final +
                                          normal_y_final * normal_y_final)
                    normal = {
                        'x': normal_x_final / normal_len,
                        'y': normal_y_final / normal_len
                    }
                else:
                    # Tangent length too small - degenerate segment
                    incident_type = float('nan')
                    normal = {
                        'x': float('nan'),
                        'y': float('nan')
                    }

                intersections.append({
                    's_point': geometry.point(rp_temp.x, rp_temp.y),
                    'normal': normal,
                    'incident_type': incident_type,
                    'incident_piece': p1_dict['piece_index'],
                    'incident_pos': incident_pos
                })

        return intersections


# Example usage and testing
if __name__ == "__main__":
    # Mock scene class
    class MockScene:
        def __init__(self):
            self.error = None

    # Mock base class that the mixin would normally be combined with
    class MockBase:
        def __init__(self, scene, json_obj=None):
            pass

    # Example class using the mixin
    class TestParamCurveObj(ParamCurveObjMixin, MockBase):
        def __init__(self, scene, json_obj=None):
            self.type = 'test_param_curve'
            self.scene = scene
            self.origin = {'x': 0, 'y': 0}
            self.pieces = []
            self.intersect_tol = 0.01

            # Initialize parent (which calls mixin __init__)
            super().__init__(scene, json_obj)

    scene = MockScene()

    # Test 1: Circle parametric curve
    print("=" * 60)
    print("Test 1: Circle (x=cos(t), y=sin(t), 0 <= t <= 2π)")
    print("=" * 60)

    obj1 = TestParamCurveObj(scene)
    obj1.origin = {'x': 100, 'y': 100}
    obj1.pieces = [{
        'eqnX': r'\cos(t)',
        'eqnY': r'\sin(t)',
        'tMin': 0,
        'tMax': 2 * math.pi,
        'tStep': 0.1
    }]

    success = obj1.init_path()
    print(f"Path initialization: {'Success' if success else 'Failed'}")
    if success:
        print(f"Number of points: {len(obj1.path)}")
        print(f"First point: ({obj1.path[0]['x']:.3f}, {obj1.path[0]['y']:.3f})")
        print(f"Last point: ({obj1.path[-1]['x']:.3f}, {obj1.path[-1]['y']:.3f})")
        print(f"Is closed: {obj1.is_closed()}")
        print(f"Is positively oriented: {obj1.is_positively_oriented()}")

        # Test point inside/outside
        center = geometry.point(100, 100)
        inside = geometry.point(100.5, 100)
        outside = geometry.point(102, 100)

        print(f"Center (100, 100) - inside: {obj1.is_inside(center)}, outside: {obj1.is_outside(center)}")
        print(f"Point (100.5, 100) - inside: {obj1.is_inside(inside)}, outside: {obj1.is_outside(inside)}")
        print(f"Point (102, 100) - inside: {obj1.is_inside(outside)}, outside: {obj1.is_outside(outside)}")

    # Test 2: Parabola
    print("\n" + "=" * 60)
    print("Test 2: Parabola (x=t, y=t^2, -2 <= t <= 2)")
    print("=" * 60)

    obj2 = TestParamCurveObj(scene)
    obj2.origin = {'x': 0, 'y': 0}
    obj2.pieces = [{
        'eqnX': 't',
        'eqnY': 't^2',
        'tMin': -2,
        'tMax': 2,
        'tStep': 0.1
    }]

    success = obj2.init_path()
    print(f"Path initialization: {'Success' if success else 'Failed'}")
    if success:
        print(f"Number of points: {len(obj2.path)}")
        print(f"First point: ({obj2.path[0]['x']:.3f}, {obj2.path[0]['y']:.3f})")
        print(f"Last point: ({obj2.path[-1]['x']:.3f}, {obj2.path[-1]['y']:.3f})")
        print(f"Is closed: {obj2.is_closed()}")

    # Test 3: Piecewise curve (two semicircles)
    print("\n" + "=" * 60)
    print("Test 3: Two semicircles forming a figure-8")
    print("=" * 60)

    obj3 = TestParamCurveObj(scene)
    obj3.origin = {'x': 0, 'y': 0}
    obj3.pieces = [
        {
            'eqnX': r'\cos(t)',
            'eqnY': r'\sin(t)',
            'tMin': 0,
            'tMax': math.pi,
            'tStep': 0.1
        },
        {
            'eqnX': r'\cos(t) + 2',
            'eqnY': r'\sin(t)',
            'tMin': math.pi,
            'tMax': 2 * math.pi,
            'tStep': 0.1
        }
    ]

    success = obj3.init_path()
    print(f"Path initialization: {'Success' if success else 'Failed'}")
    if success:
        print(f"Number of points: {len(obj3.path)}")
        print(f"Piece 0 points: {sum(1 for p in obj3.path if p['piece_index'] == 0)}")
        print(f"Piece 1 points: {sum(1 for p in obj3.path if p['piece_index'] == 1)}")

    # Test 4: Test transformations (move, rotate, scale)
    print("\n" + "=" * 60)
    print("Test 4: Transformations")
    print("=" * 60)

    obj4 = TestParamCurveObj(scene)
    obj4.origin = {'x': 0, 'y': 0}
    obj4.pieces = [{
        'eqnX': 't',
        'eqnY': '0',
        'tMin': 0,
        'tMax': 1,
        'tStep': 0.1
    }]

    print(f"Original origin: ({obj4.origin['x']}, {obj4.origin['y']})")

    obj4.move(10, 20)
    print(f"After move(10, 20): ({obj4.origin['x']}, {obj4.origin['y']})")

    obj4.rotate(math.pi / 2)
    print(f"After rotate(π/2): ({obj4.origin['x']:.3f}, {obj4.origin['y']:.3f})")

    obj4.scale(2.0)
    print(f"After scale(2.0): ({obj4.origin['x']:.3f}, {obj4.origin['y']:.3f})")

    # Test 5: Error handling
    print("\n" + "=" * 60)
    print("Test 5: Error handling")
    print("=" * 60)

    # Invalid step size
    obj5a = TestParamCurveObj(scene)
    obj5a.pieces = [{
        'eqnX': 't',
        'eqnY': 't',
        'tMin': 0,
        'tMax': 1,
        'tStep': -0.1  # Invalid
    }]
    success = obj5a.init_path()
    print(f"Invalid step (-0.1): {'Success' if success else 'Failed'}")
    if not success:
        print(f"  Error: {obj5a.error}")

    # Invalid range
    obj5b = TestParamCurveObj(scene)
    obj5b.pieces = [{
        'eqnX': 't',
        'eqnY': 't',
        'tMin': 1,
        'tMax': 0,  # Invalid
        'tStep': 0.1
    }]
    success = obj5b.init_path()
    print(f"Invalid range (tMin > tMax): {'Success' if success else 'Failed'}")
    if not success:
        print(f"  Error: {obj5b.error}")

    # Invalid equation (division by zero)
    obj5c = TestParamCurveObj(scene)
    obj5c.pieces = [{
        'eqnX': r'\frac{1}{t}',
        'eqnY': '0',
        'tMin': 0,  # Will cause division by zero
        'tMax': 1,
        'tStep': 0.1
    }]
    success = obj5c.init_path()
    print(f"Division by zero at t=0: {'Success' if success else 'Failed'}")
    if not success:
        print(f"  Error: {obj5c.error[:80]}...")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
