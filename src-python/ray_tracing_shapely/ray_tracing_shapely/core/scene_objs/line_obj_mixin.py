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


class LineObjMixin:
    """
    Mixin class for scene objects that are defined by a line segment.

    This mixin provides common functionality for objects with two endpoints (p1 and p2):
    - Transformation methods (move, rotate, scale)
    - Construction methods for user interaction
    - Mouse interaction (dragging endpoints or entire line)
    - Ray intersection testing

    Usage:
        class MyLineObject(LineObjMixin, BaseSceneObj):
            serializable_defaults = {
                'p1': {'x': 0, 'y': 0},
                'p2': {'x': 100, 'y': 100}
            }

    Note: This class should be used as a mixin with BaseSceneObj or its subclasses.
          In Python's MRO (Method Resolution Order), mixins should come before the base class.
    """

    def move(self, diff_x: float, diff_y: float) -> bool:
        """
        Move the line segment by the given displacement.

        Args:
            diff_x: The x-coordinate displacement.
            diff_y: The y-coordinate displacement.

        Returns:
            True, indicating the movement was successful.
        """
        # Move the first point
        self.p1['x'] = self.p1['x'] + diff_x
        self.p1['y'] = self.p1['y'] + diff_y
        # Move the second point
        self.p2['x'] = self.p2['x'] + diff_x
        self.p2['y'] = self.p2['y'] + diff_y

        return True

    def rotate(self, angle: float, center=None) -> bool:
        """
        Rotate the line segment by the given angle.

        Args:
            angle: The angle in radians. Positive for counter-clockwise.
            center: The center of rotation (dict with 'x' and 'y' keys).
                   If None, uses the midpoint of the line segment.

        Returns:
            True, indicating the rotation was successful.
        """
        # Use midpoint as default rotation center if none is provided
        rotation_center = center if center is not None else self.get_default_center()

        # Calculate differences from rotation center for both points
        diff_p1_x = self.p1['x'] - rotation_center.x
        diff_p1_y = self.p1['y'] - rotation_center.y
        diff_p2_x = self.p2['x'] - rotation_center.x
        diff_p2_y = self.p2['y'] - rotation_center.y

        # Apply rotation matrix to p1
        self.p1['x'] = rotation_center.x + diff_p1_x * math.cos(angle) - diff_p1_y * math.sin(angle)
        self.p1['y'] = rotation_center.y + diff_p1_x * math.sin(angle) + diff_p1_y * math.cos(angle)

        # Apply rotation matrix to p2
        self.p2['x'] = rotation_center.x + diff_p2_x * math.cos(angle) - diff_p2_y * math.sin(angle)
        self.p2['y'] = rotation_center.y + diff_p2_x * math.sin(angle) + diff_p2_y * math.cos(angle)

        return True

    def scale(self, scale: float, center=None) -> bool:
        """
        Scale the line segment by the given scale factor.

        Args:
            scale: The scale factor.
            center: The center of scaling (dict with 'x' and 'y' keys).
                   If None, uses the midpoint of the line segment.

        Returns:
            True, indicating the scaling was successful.
        """
        # Use midpoint as default scaling center if none is provided
        scaling_center = center if center is not None else self.get_default_center()

        # Calculate differences from scaling center for both points
        diff_p1_x = self.p1['x'] - scaling_center.x
        diff_p1_y = self.p1['y'] - scaling_center.y
        diff_p2_x = self.p2['x'] - scaling_center.x
        diff_p2_y = self.p2['y'] - scaling_center.y

        # Apply scaling to p1
        self.p1['x'] = scaling_center.x + diff_p1_x * scale
        self.p1['y'] = scaling_center.y + diff_p1_y * scale

        # Apply scaling to p2
        self.p2['x'] = scaling_center.x + diff_p2_x * scale
        self.p2['y'] = scaling_center.y + diff_p2_y * scale

        return True

    def get_default_center(self):
        """
        Get the default center of rotation or scaling.

        Returns:
            Point object representing the midpoint of the line segment.
        """
        # Return the midpoint of the line segment
        return geometry.point(
            (self.p1['x'] + self.p2['x']) / 2,
            (self.p1['y'] + self.p2['y']) / 2
        )

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

        if ctrl:
            # Mirror mode: make the line symmetric around construction_point
            self.p1 = geometry.point(
                2 * self.construction_point['x'] - self.p2['x'],
                2 * self.construction_point['y'] - self.p2['y']
            ).to_dict()
        else:
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
        Check whether the mouse is over the line segment.

        Args:
            mouse: The mouse object.

        Returns:
            Drag context dictionary if the mouse is over the object, None otherwise.
        """
        drag_context = {}

        # Convert dict points to Point objects for geometry operations
        p1_point = geometry.point(self.p1['x'], self.p1['y'])
        p2_point = geometry.point(self.p2['x'], self.p2['y'])

        # Check if mouse is on p1 (and closer to p1 than p2)
        if (mouse.is_on_point(self.p1) and
            geometry.distance_squared(mouse.pos, p1_point) <= geometry.distance_squared(mouse.pos, p2_point)):
            drag_context['part'] = 1
            drag_context['targetPoint'] = geometry.point(self.p1['x'], self.p1['y'])
            return drag_context

        # Check if mouse is on p2
        if mouse.is_on_point(self.p2):
            drag_context['part'] = 2
            drag_context['targetPoint'] = geometry.point(self.p2['x'], self.p2['y'])
            return drag_context

        # Check if mouse is on the segment
        if mouse.is_on_segment(self):
            mouse_pos = mouse.get_pos_snapped_to_grid()
            drag_context['part'] = 0
            drag_context['mousePos0'] = mouse_pos  # Mouse position when user starts dragging
            drag_context['mousePos1'] = mouse_pos  # Mouse position at the last moment during dragging
            drag_context['snapContext'] = {}
            return drag_context

        return None

    def on_drag(self, mouse, drag_context, ctrl: bool, shift: bool) -> None:
        """
        Handle dragging of the line segment or its endpoints.

        Args:
            mouse: The mouse object.
            drag_context: The drag context from check_mouse_over.
            ctrl: Whether the control key is pressed.
            shift: Whether the shift key is pressed.
        """
        if drag_context['part'] == 1:
            # Dragging the first endpoint
            if ctrl:
                base_point = geometry.segment_midpoint(
                    geometry.line(
                        geometry.point(drag_context['originalObj'].p1['x'], drag_context['originalObj'].p1['y']),
                        geometry.point(drag_context['originalObj'].p2['x'], drag_context['originalObj'].p2['y'])
                    )
                )
            else:
                base_point = geometry.point(drag_context['originalObj'].p2['x'], drag_context['originalObj'].p2['y'])

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

            if ctrl:
                # Mirror mode
                self.p2 = geometry.point(
                    2 * base_point.x - self.p1['x'],
                    2 * base_point.y - self.p1['y']
                ).to_dict()
            else:
                self.p2 = base_point.to_dict()

        elif drag_context['part'] == 2:
            # Dragging the second endpoint
            if ctrl:
                base_point = geometry.segment_midpoint(
                    geometry.line(
                        geometry.point(drag_context['originalObj'].p1['x'], drag_context['originalObj'].p1['y']),
                        geometry.point(drag_context['originalObj'].p2['x'], drag_context['originalObj'].p2['y'])
                    )
                )
            else:
                base_point = geometry.point(drag_context['originalObj'].p1['x'], drag_context['originalObj'].p1['y'])

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

            if ctrl:
                # Mirror mode
                self.p1 = geometry.point(
                    2 * base_point.x - self.p2['x'],
                    2 * base_point.y - self.p2['y']
                ).to_dict()
            else:
                self.p1 = base_point.to_dict()

        elif drag_context['part'] == 0:
            # Dragging the entire line
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

            # Move both points
            self.p1['x'] = self.p1['x'] - mouse_diff_x
            self.p1['y'] = self.p1['y'] - mouse_diff_y
            self.p2['x'] = self.p2['x'] - mouse_diff_x
            self.p2['y'] = self.p2['y'] - mouse_diff_y

            # Update mouse position
            drag_context['mousePos1'] = mouse_pos

    def check_ray_intersects_shape(self, ray):
        """
        Check if a ray intersects the line segment.

        In the child class, this can be called from the `check_ray_intersects` method.

        Args:
            ray: The ray object (with p1 and p2 attributes).

        Returns:
            Point object representing the intersection, or None if there is no intersection.
        """
        # Convert dict points to Point objects
        ray_p1 = geometry.point(ray.p1['x'], ray.p1['y'])
        ray_p2 = geometry.point(ray.p2['x'], ray.p2['y'])
        obj_p1 = geometry.point(self.p1['x'], self.p1['y'])
        obj_p2 = geometry.point(self.p2['x'], self.p2['y'])

        # Calculate intersection
        rp_temp = geometry.lines_intersection(
            geometry.line(ray_p1, ray_p2),
            geometry.line(obj_p1, obj_p2)
        )

        # Check if intersection is on both the segment and the ray
        segment = geometry.line(obj_p1, obj_p2)
        ray_line = geometry.line(ray_p1, ray_p2)

        if geometry.intersection_is_on_segment(rp_temp, segment) and geometry.intersection_is_on_ray(rp_temp, ray_line):
            return rp_temp
        else:
            return None


# Example usage
if __name__ == "__main__":
    # Add parent directory to path for BaseSceneObj import
    from base_scene_obj import BaseSceneObj

    # Example class combining LineObjMixin with BaseSceneObj
    class LineObject(LineObjMixin, BaseSceneObj):
        type = 'line_object'
        serializable_defaults = {
            'p1': {'x': 0, 'y': 0},
            'p2': {'x': 100, 'y': 100}
        }
        is_optical = True

        def __init__(self, scene, json_obj=None):
            super().__init__(scene, json_obj)

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None

    scene = MockScene()
    obj = LineObject(scene)

    print("Initial line object:")
    print(f"  p1: {obj.p1}")
    print(f"  p2: {obj.p2}")

    # Test move
    obj.move(10, 20)
    print("\nAfter move(10, 20):")
    print(f"  p1: {obj.p1}")
    print(f"  p2: {obj.p2}")

    # Test rotate
    obj.rotate(math.pi / 4)  # 45 degrees
    print(f"\nAfter rotate(45 degrees):")
    print(f"  p1: {obj.p1}")
    print(f"  p2: {obj.p2}")

    # Test rotate back
    obj.rotate(- math.pi / 4)  # - 45 degrees
    print(f"\nAfter rotate back to original position (- 45 degrees):")
    print(f"  p1: {obj.p1}")
    print(f"  p2: {obj.p2}")

    # Test scale
    obj.scale(2.0)
    print(f"\nAfter scale(2.0):")
    print(f"  p1: {obj.p1}")
    print(f"  p2: {obj.p2}")

    # Test get_default_center
    center = obj.get_default_center()
    print(f"\nDefault center (midpoint): {center}")
