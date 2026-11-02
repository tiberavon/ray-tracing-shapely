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
from typing import Optional, Dict, Any
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from geometry import geometry
from constants import MIN_RAY_SEGMENT_LENGTH_SQUARED


class CircleObjMixin:
    """
    Mixin class for scene objects that are defined by a circle.

    This mixin provides common functionality for circular objects with:
    - p1: Center of the circle
    - p2: Point on the circumference (defines the radius)

    Features:
    - Transformation methods (move, rotate, scale)
    - Construction methods for user interaction
    - Mouse interaction (dragging center, circumference point, or entire circle)
    - Ray intersection testing

    Usage:
        class MyCircleObject(CircleObjMixin, BaseSceneObj):
            serializable_defaults = {
                'p1': {'x': 0, 'y': 0},    # Center
                'p2': {'x': 50, 'y': 0}    # Point on circumference
            }

    Note: This class should be used as a mixin with BaseSceneObj or its subclasses.
          In Python's MRO (Method Resolution Order), mixins should come before the base class.
    """

    def move(self, diff_x: float, diff_y: float) -> bool:
        """
        Move the circle by the given displacement.

        Args:
            diff_x: The x-coordinate displacement.
            diff_y: The y-coordinate displacement.

        Returns:
            True, indicating the movement was successful.
        """
        # Move the center point (p1)
        self.p1['x'] = self.p1['x'] + diff_x
        self.p1['y'] = self.p1['y'] + diff_y
        # Move the circumference point (p2)
        self.p2['x'] = self.p2['x'] + diff_x
        self.p2['y'] = self.p2['y'] + diff_y

        return True

    def rotate(self, angle: float, center=None) -> bool:
        """
        Rotate the circle by the given angle.

        Args:
            angle: The angle in radians. Positive for counter-clockwise.
            center: The center of rotation (dict with 'x' and 'y' keys).
                   If None, uses the center of the circle (p1).

        Returns:
            True, indicating the rotation was successful.
        """
        # Use center of circle as default rotation center if none is provided
        rotation_center = center if center is not None else self.get_default_center()

        # Calculate differences from rotation center for both points
        diff_p1_x = self.p1['x'] - rotation_center.x
        diff_p1_y = self.p1['y'] - rotation_center.y
        diff_p2_x = self.p2['x'] - rotation_center.x
        diff_p2_y = self.p2['y'] - rotation_center.y

        # Apply rotation matrix to p1 (center of circle)
        self.p1['x'] = rotation_center.x + diff_p1_x * math.cos(angle) - diff_p1_y * math.sin(angle)
        self.p1['y'] = rotation_center.y + diff_p1_x * math.sin(angle) + diff_p1_y * math.cos(angle)

        # Apply rotation matrix to p2 (point on circumference)
        self.p2['x'] = rotation_center.x + diff_p2_x * math.cos(angle) - diff_p2_y * math.sin(angle)
        self.p2['y'] = rotation_center.y + diff_p2_x * math.sin(angle) + diff_p2_y * math.cos(angle)

        return True

    def scale(self, scale: float, center=None) -> bool:
        """
        Scale the circle by the given scale factor.

        Args:
            scale: The scale factor.
            center: The center of scaling (dict with 'x' and 'y' keys).
                   If None, uses the center of the circle (p1).

        Returns:
            True, indicating the scaling was successful.
        """
        # Use center of circle as default scaling center if none is provided
        scaling_center = center if center is not None else self.get_default_center()

        # Calculate differences from scaling center for both points
        diff_p1_x = self.p1['x'] - scaling_center.x
        diff_p1_y = self.p1['y'] - scaling_center.y
        diff_p2_x = self.p2['x'] - scaling_center.x
        diff_p2_y = self.p2['y'] - scaling_center.y

        # Apply scaling to p1 (center of circle)
        self.p1['x'] = scaling_center.x + diff_p1_x * scale
        self.p1['y'] = scaling_center.y + diff_p1_y * scale

        # Apply scaling to p2 (point on circumference)
        self.p2['x'] = scaling_center.x + diff_p2_x * scale
        self.p2['y'] = scaling_center.y + diff_p2_y * scale

        return True

    def get_default_center(self):
        """
        Get the default center of rotation or scaling.

        Returns:
            Point object representing the center of the circle (p1).
        """
        # Return the center of the circle (p1) as a Point object
        return geometry.point(self.p1['x'], self.p1['y'])

    def on_construct_mouse_down(self, mouse, ctrl: bool, shift: bool) -> Optional[Dict[str, Any]]:
        """
        Mouse down event when the object is being constructed by the user.

        Args:
            mouse: The mouse object.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.

        Returns:
            ConstructReturn dictionary, or None.
        """
        if not hasattr(self, 'construction_point') or self.construction_point is None:
            # Initialize the construction stage
            self.construction_point = mouse.get_pos_snapped_to_grid()
            self.p1 = self.construction_point
            self.p2 = self.construction_point

        if shift:
            self.p2 = mouse.get_pos_snapped_to_direction(
                self.construction_point,
                [{'x': 1, 'y': 0}, {'x': 0, 'y': 1}, {'x': 1, 'y': 1}, {'x': 1, 'y': -1}]
            )
        else:
            self.p2 = mouse.get_pos_snapped_to_grid()

        return None

    def on_construct_mouse_move(self, mouse, ctrl: bool, shift: bool) -> Optional[Dict[str, Any]]:
        """
        Mouse move event when the object is being constructed by the user.

        Args:
            mouse: The mouse object.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.

        Returns:
            ConstructReturn dictionary, or None.
        """
        if shift:
            self.p2 = mouse.get_pos_snapped_to_direction(
                self.construction_point,
                [{'x': 1, 'y': 0}, {'x': 0, 'y': 1}, {'x': 1, 'y': 1}, {'x': 1, 'y': -1}]
            )
        else:
            self.p2 = mouse.get_pos_snapped_to_grid()

        # Keep the center at construction_point (unlike LineObjMixin which has mirror mode)
        self.p1 = self.construction_point

        return None

    def on_construct_mouse_up(self, mouse, ctrl: bool, shift: bool) -> Optional[Dict[str, Any]]:
        """
        Mouse up event when the object is being constructed by the user.

        Args:
            mouse: The mouse object.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.

        Returns:
            ConstructReturn dictionary, or None.
        """
        if not mouse.snaps_on_point(self.p1):
            # Construction is done if p1 and p2 are different
            if hasattr(self, 'construction_point'):
                delattr(self, 'construction_point')
            return {'isDone': True}

        return None

    def check_mouse_over(self, mouse):
        """
        Check whether the mouse is over the circle.

        Args:
            mouse: The mouse object.

        Returns:
            Drag context dictionary if the mouse is over the object, None otherwise.
        """
        drag_context = {}

        # Convert dict points to Point objects for geometry operations
        p1_point = geometry.point(self.p1['x'], self.p1['y'])
        p2_point = geometry.point(self.p2['x'], self.p2['y'])

        # Check if mouse is on p1 (center) and closer to p1 than p2
        if (mouse.is_on_point(self.p1) and
            geometry.distance_squared(mouse.pos, p1_point) <= geometry.distance_squared(mouse.pos, p2_point)):
            drag_context['part'] = 1
            drag_context['targetPoint'] = geometry.point(self.p1['x'], self.p1['y'])
            return drag_context

        # Check if mouse is on p2 (circumference point)
        if mouse.is_on_point(self.p2):
            drag_context['part'] = 2
            drag_context['targetPoint'] = geometry.point(self.p2['x'], self.p2['y'])
            return drag_context

        # Check if mouse is on the circle circumference
        # Distance from center to mouse should equal radius (within click tolerance)
        radius = geometry.segment_length(geometry.line(p1_point, p2_point))
        distance_to_center = geometry.distance(p1_point, mouse.pos)

        if abs(distance_to_center - radius) < mouse.get_click_extent():
            mouse_pos = mouse.get_pos_snapped_to_grid()
            drag_context['part'] = 0
            drag_context['mousePos0'] = mouse_pos  # Mouse position when user starts dragging
            drag_context['mousePos1'] = mouse_pos  # Mouse position at last moment during dragging
            drag_context['snapContext'] = {}
            return drag_context

        return None

    def on_drag(self, mouse, drag_context, ctrl: bool, shift: bool) -> None:
        """
        Handle dragging of the circle or its control points.

        Args:
            mouse: The mouse object.
            drag_context: The drag context from check_mouse_over.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.
        """
        if drag_context['part'] == 1:
            # Dragging the center point
            base_point = geometry.point(
                drag_context['originalObj'].p2['x'],
                drag_context['originalObj'].p2['y']
            )

            if shift:
                # Snap to direction
                orig_obj = drag_context['originalObj']
                self.p1 = mouse.get_pos_snapped_to_direction(
                    base_point,
                    [
                        {'x': 1, 'y': 0},
                        {'x': 0, 'y': 1},
                        {'x': 1, 'y': 1},
                        {'x': 1, 'y': -1},
                        {'x': orig_obj.p2['x'] - orig_obj.p1['x'], 'y': orig_obj.p2['y'] - orig_obj.p1['y']}
                    ]
                )
            else:
                self.p1 = mouse.get_pos_snapped_to_grid()

            self.p2 = base_point.to_dict()

        elif drag_context['part'] == 2:
            # Dragging the point on the circumference
            base_point = geometry.point(
                drag_context['originalObj'].p1['x'],
                drag_context['originalObj'].p1['y']
            )

            if shift:
                # Snap to direction
                orig_obj = drag_context['originalObj']
                self.p2 = mouse.get_pos_snapped_to_direction(
                    base_point,
                    [
                        {'x': 1, 'y': 0},
                        {'x': 0, 'y': 1},
                        {'x': 1, 'y': 1},
                        {'x': 1, 'y': -1},
                        {'x': orig_obj.p2['x'] - orig_obj.p1['x'], 'y': orig_obj.p2['y'] - orig_obj.p1['y']}
                    ]
                )
            else:
                self.p2 = mouse.get_pos_snapped_to_grid()

            self.p1 = base_point.to_dict()

        elif drag_context['part'] == 0:
            # Dragging the entire circle
            if shift:
                orig_obj = drag_context['originalObj']
                mouse_pos = mouse.get_pos_snapped_to_direction(
                    drag_context['mousePos0'],
                    [
                        {'x': 1, 'y': 0},
                        {'x': 0, 'y': 1},
                        {'x': orig_obj.p2['x'] - orig_obj.p1['x'], 'y': orig_obj.p2['y'] - orig_obj.p1['y']},
                        {'x': orig_obj.p2['y'] - orig_obj.p1['y'], 'y': -(orig_obj.p2['x'] - orig_obj.p1['x'])}
                    ],
                    drag_context['snapContext']
                )
            else:
                mouse_pos = mouse.get_pos_snapped_to_grid()
                drag_context['snapContext'] = {}  # Unlock dragging direction when user releases shift

            # Calculate mouse movement difference
            mouse_diff_x = drag_context['mousePos1']['x'] - mouse_pos['x']
            mouse_diff_y = drag_context['mousePos1']['y'] - mouse_pos['y']

            # Move the center point
            self.p1['x'] = self.p1['x'] - mouse_diff_x
            self.p1['y'] = self.p1['y'] - mouse_diff_y
            # Move the point on the circumference
            self.p2['x'] = self.p2['x'] - mouse_diff_x
            self.p2['y'] = self.p2['y'] - mouse_diff_y

            # Update mouse position
            drag_context['mousePos1'] = mouse_pos

    def check_ray_intersects_shape(self, ray):
        """
        Check if a ray intersects the circle.

        In the child class, this can be called from the `check_ray_intersects` method.

        Args:
            ray: The ray object (with p1 and p2 attributes).

        Returns:
            Point object representing the intersection, or None if there is no intersection.
        """
        # Convert dict points to Point objects
        ray_p1 = geometry.point(ray.p1['x'], ray.p1['y'])
        ray_p2 = geometry.point(ray.p2['x'], ray.p2['y'])
        circle_center = geometry.point(self.p1['x'], self.p1['y'])
        circle_point = geometry.point(self.p2['x'], self.p2['y'])

        # Calculate intersections
        rp_temp = geometry.line_circle_intersections(
            geometry.line(ray_p1, ray_p2),
            geometry.circle(circle_center, circle_point)
        )

        # Check which intersections are valid (on the ray and far enough from start)
        rp_exist = [None, None, None]  # 1-indexed like JavaScript
        rp_lensq = [None, None, None]

        for i in [1, 2]:
            if rp_temp and len(rp_temp) >= 3 and rp_temp[i] is not None:
                ray_line = geometry.line(ray_p1, ray_p2)
                is_on_ray = geometry.intersection_is_on_ray(rp_temp[i], ray_line)

                # Check if intersection is far enough from ray start
                # (to avoid numerical issues with very small segments)
                dist_sq = geometry.distance_squared(rp_temp[i], ray_p1)
                min_dist_sq = MIN_RAY_SEGMENT_LENGTH_SQUARED * self.scene.lengthScale * self.scene.lengthScale

                rp_exist[i] = is_on_ray and dist_sq > min_dist_sq
                rp_lensq[i] = dist_sq
            else:
                rp_exist[i] = False
                rp_lensq[i] = float('inf')

        # Return the closest valid intersection
        if rp_exist[1] and (not rp_exist[2] or rp_lensq[1] < rp_lensq[2]):
            return rp_temp[1]
        if rp_exist[2] and (not rp_exist[1] or rp_lensq[2] < rp_lensq[1]):
            return rp_temp[2]

        return None


# Example usage
if __name__ == "__main__":
    # Add parent directory to path for BaseSceneObj import
    from base_scene_obj import BaseSceneObj

    # Example class combining CircleObjMixin with BaseSceneObj
    class CircleObject(CircleObjMixin, BaseSceneObj):
        type = 'circle_object'
        serializable_defaults = {
            'p1': {'x': 0, 'y': 0},    # Center
            'p2': {'x': 50, 'y': 0}    # Point on circumference (radius = 50)
        }
        is_optical = True

        def __init__(self, scene, json_obj=None):
            super().__init__(scene, json_obj)

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.lengthScale = 1.0

    scene = MockScene()
    obj = CircleObject(scene)

    print("Initial circle object:")
    print(f"  p1 (center): {obj.p1}")
    print(f"  p2 (circumference): {obj.p2}")

    # Calculate and display radius
    p1_point = geometry.point(obj.p1['x'], obj.p1['y'])
    p2_point = geometry.point(obj.p2['x'], obj.p2['y'])
    radius = geometry.distance(p1_point, p2_point)
    print(f"  Radius: {radius}")

    # Test move
    obj.move(10, 20)
    print("\nAfter move(10, 20):")
    print(f"  p1 (center): {obj.p1}")
    print(f"  p2 (circumference): {obj.p2}")

    # Test rotate
    obj.rotate(math.pi / 4)  # 45 degrees
    print(f"\nAfter rotate(45 degrees):")
    print(f"  p1 (center): {obj.p1}")
    print(f"  p2 (circumference): {obj.p2}")

    # Test rotate back
    obj.rotate(-math.pi / 4)  # -45 degrees
    print(f"\nAfter rotate back to original position (-45 degrees):")
    print(f"  p1 (center): {obj.p1}")
    print(f"  p2 (circumference): {obj.p2}")

    # Test scale
    obj.scale(2.0)
    print(f"\nAfter scale(2.0):")
    print(f"  p1 (center): {obj.p1}")
    print(f"  p2 (circumference): {obj.p2}")

    # Recalculate radius after transformations
    p1_point = geometry.point(obj.p1['x'], obj.p1['y'])
    p2_point = geometry.point(obj.p2['x'], obj.p2['y'])
    radius = geometry.distance(p1_point, p2_point)
    print(f"  New radius: {radius}")

    # Test get_default_center
    center = obj.get_default_center()
    print(f"\nDefault center: {center}")
