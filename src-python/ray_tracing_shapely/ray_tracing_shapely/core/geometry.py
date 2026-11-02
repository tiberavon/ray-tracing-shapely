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
from typing import Union, List, Tuple, Dict
from shapely.geometry import Point as ShapelyPoint, LineString, LinearRing
from shapely.ops import nearest_points
import numpy as np


class Point:
    """
    A point in 2D space.
    Can be converted to/from Shapely Point objects.
    """
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    def to_shapely(self) -> ShapelyPoint:
        """Convert to Shapely Point."""
        return ShapelyPoint(self.x, self.y)

    @classmethod
    def from_shapely(cls, sp: ShapelyPoint) -> 'Point':
        """Create Point from Shapely Point."""
        return cls(sp.x, sp.y)

    def __repr__(self) -> str:
        return f"Point(x={self.x}, y={self.y})"

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary representation."""
        return {'x': self.x, 'y': self.y}


class Line:
    """
    A line in 2D space, defined by two points.
    Can represent a line, ray, or segment depending on context.
    - As a line: p1 and p2 are two distinct points on the line.
    - As a ray: p1 is the starting point and p2 is another point on the ray.
    - As a segment: p1 and p2 are the two endpoints.
    """
    def __init__(self, p1: Point, p2: Point):
        self.p1 = p1
        self.p2 = p2

    def to_shapely(self) -> LineString:
        """Convert to Shapely LineString."""
        return LineString([(self.p1.x, self.p1.y), (self.p2.x, self.p2.y)])

    @classmethod
    def from_shapely(cls, sl: LineString) -> 'Line':
        """Create Line from Shapely LineString."""
        coords = list(sl.coords)
        return cls(Point(coords[0][0], coords[0][1]), Point(coords[1][0], coords[1][1]))

    def __repr__(self) -> str:
        return f"Line(p1={self.p1}, p2={self.p2})"


class Circle:
    """
    A circle in 2D space.
    Can be defined by a center point and either a radius (number) or a line to a point on the circle.
    """
    def __init__(self, c: Point, r: Union[float, Line]):
        self.c = c
        if isinstance(r, Point):
            # If a point is passed, create a line from center to that point
            self.r = Line(c, r)
        else:
            self.r = r

    def get_radius(self) -> float:
        """Get the numerical radius value."""
        if isinstance(self.r, Line):
            dx = self.r.p1.x - self.r.p2.x
            dy = self.r.p1.y - self.r.p2.y
            return math.sqrt(dx * dx + dy * dy)
        else:
            return self.r

    def to_shapely(self) -> ShapelyPoint:
        """Convert to Shapely Point with buffer (approximation of circle)."""
        return self.c.to_shapely().buffer(self.get_radius())

    def __repr__(self) -> str:
        return f"Circle(c={self.c}, r={self.r})"


class Geometry:
    """
    The geometry module, which provides basic geometric figures and operations.
    This is a Python translation of the JavaScript geometry module using Shapely where appropriate.
    """

    @staticmethod
    def point(x: float, y: float) -> Point:
        """
        Create a point.

        Args:
            x: The x-coordinate of the point.
            y: The y-coordinate of the point.

        Returns:
            Point object
        """
        return Point(x, y)

    @staticmethod
    def line(p1: Point, p2: Point) -> Line:
        """
        Create a line, which also represents a ray or a segment.
        When used as a line, p1 and p2 are two distinct points on the line.
        When used as a ray, p1 is the starting point and p2 is another point on the ray.
        When used as a segment, p1 and p2 are the two endpoints of the segment.

        Args:
            p1: First point
            p2: Second point

        Returns:
            Line object
        """
        return Line(p1, p2)

    @staticmethod
    def circle(c: Point, r: Union[float, Point]) -> Circle:
        """
        Create a circle.

        Args:
            c: The center point of the circle.
            r: The radius of the circle or a point on the circle.

        Returns:
            Circle object
        """
        return Circle(c, r)

    @staticmethod
    def dot(p1: Point, p2: Point) -> float:
        """
        Calculate the dot product, where the two points are treated as vectors.

        Args:
            p1: First point (as vector)
            p2: Second point (as vector)

        Returns:
            Dot product
        """
        return p1.x * p2.x + p1.y * p2.y

    @staticmethod
    def cross(p1: Point, p2: Point) -> float:
        """
        Calculate the cross product, where the two points are treated as vectors.

        Args:
            p1: First point (as vector)
            p2: Second point (as vector)

        Returns:
            Cross product (z-component in 2D)
        """
        return p1.x * p2.y - p1.y * p2.x

    @staticmethod
    def lines_intersection(l1: Line, l2: Line) -> Point:
        """
        Calculate the intersection of two lines.

        Args:
            l1: First line
            l2: Second line

        Returns:
            Intersection point
        """
        A = l1.p2.x * l1.p1.y - l1.p1.x * l1.p2.y
        B = l2.p2.x * l2.p1.y - l2.p1.x * l2.p2.y
        xa = l1.p2.x - l1.p1.x
        xb = l2.p2.x - l2.p1.x
        ya = l1.p2.y - l1.p1.y
        yb = l2.p2.y - l2.p1.y

        denominator = xa * yb - xb * ya

        # Handle parallel lines (denominator = 0)
        if abs(denominator) < 1e-12:
            # Lines are parallel or coincident - return a point at infinity
            # This signals "no intersection" to the caller
            return Geometry.point(float('inf'), float('inf'))

        x = (A * xb - B * xa) / denominator
        y = (A * yb - B * ya) / denominator

        return Geometry.point(x, y)

    @staticmethod
    def line_circle_intersections(l1: Line, c1: Circle) -> List[Point]:
        """
        Calculate the intersections of a line and a circle.

        Args:
            l1: Line
            c1: Circle

        Returns:
            List of intersection points (may be empty, or contain 1-2 points)
        """
        xa = l1.p2.x - l1.p1.x
        ya = l1.p2.y - l1.p1.y
        cx = c1.c.x
        cy = c1.c.y

        # Calculate radius squared
        if isinstance(c1.r, Line):
            dx = c1.r.p1.x - c1.r.p2.x
            dy = c1.r.p1.y - c1.r.p2.y
            r_sq = dx * dx + dy * dy
        else:
            r_sq = c1.r * c1.r

        # Normalize the line direction
        l = math.sqrt(xa * xa + ya * ya)
        ux = xa / l
        uy = ya / l

        # Project circle center onto line
        cu = (cx - l1.p1.x) * ux + (cy - l1.p1.y) * uy
        px = l1.p1.x + cu * ux
        py = l1.p1.y + cu * uy

        # Calculate distance from projected point to intersections
        dist_sq = r_sq - (px - cx) * (px - cx) - (py - cy) * (py - cy)

        if dist_sq < 0:
            # No intersection
            return []

        d = math.sqrt(dist_sq)

        # Return two intersection points (they may be the same if tangent)
        ret = [None, None, None]  # Using 1-indexed like JavaScript
        ret[1] = Geometry.point(px + ux * d, py + uy * d)
        ret[2] = Geometry.point(px - ux * d, py - uy * d)

        return ret

    @staticmethod
    def line_curve_intersections(l1: Line, c1) -> List[Point]:
        """
        Calculate the intersections of a line and a curve.
        Note: This assumes the curve object has an intersects method (e.g., Bezier curve).

        Args:
            l1: Line
            c1: Curve object with intersects method

        Returns:
            List of intersection points
        """
        return c1.intersects(l1)

    @staticmethod
    def intersection_is_on_ray(p1: Point, r1: Line) -> bool:
        """
        Test if a point on the extension of a ray is actually on the ray.

        Args:
            p1: Point to test
            r1: Ray (line where p1 is the start)

        Returns:
            True if point is on the ray
        """
        return (p1.x - r1.p1.x) * (r1.p2.x - r1.p1.x) + (p1.y - r1.p1.y) * (r1.p2.y - r1.p1.y) >= 0

    @staticmethod
    def intersection_is_on_segment(p1: Point, s1: Line) -> bool:
        """
        Test if a point on the extension of a segment is actually on the segment.

        Args:
            p1: Point to test
            s1: Segment (line with two endpoints)

        Returns:
            True if point is on the segment
        """
        cond1 = (p1.x - s1.p1.x) * (s1.p2.x - s1.p1.x) + (p1.y - s1.p1.y) * (s1.p2.y - s1.p1.y) >= 0
        cond2 = (p1.x - s1.p2.x) * (s1.p1.x - s1.p2.x) + (p1.y - s1.p2.y) * (s1.p1.y - s1.p2.y) >= 0
        return cond1 and cond2

    @staticmethod
    def intersection_is_on_curve(p1: Point, curve, threshold: float) -> bool:
        """
        Test if a point on the extension of a curve is actually on the curve.
        Note: This assumes the curve object has a project method.

        Args:
            p1: Point to test
            curve: Curve object with project method
            threshold: Distance threshold

        Returns:
            True if point is on the curve
        """
        d_proj = curve.project(Geometry.point(p1.x, p1.y)).d
        return d_proj ** 2 < threshold

    @staticmethod
    def scale_ray_for_curve(r1: Line, curve) -> Line:
        """
        Scale the ray based on the bounding box of the curve.

        Args:
            r1: Ray to scale
            curve: Curve object with bbox method

        Returns:
            Line - Returns the vector pointing from r1.p1 to the farthest point on the curve's bounding box.
        """
        bbox = curve.bbox()

        # Offset each line from 0,0 by r1.p1
        bbox_x_min = bbox['x']['min'] - r1.p1.x
        bbox_x_max = bbox['x']['max'] - r1.p1.x
        bbox_y_min = bbox['y']['min'] - r1.p1.y
        bbox_y_max = bbox['y']['max'] - r1.p1.y

        # Get vector (as a point) pointing from r1.p1 to r1.p2
        v1 = Geometry.point(r1.p2.x - r1.p1.x, r1.p2.y - r1.p1.y)

        # Figure out which bounding box corner is farthest from r1.p1
        farthest = {'x': float('inf'), 'y': float('inf')}
        if abs(bbox_x_min) > abs(bbox_x_max):
            farthest['x'] = bbox_x_min
        else:
            farthest['x'] = bbox_x_max

        if abs(bbox_y_min) > abs(bbox_y_max):
            farthest['y'] = bbox_y_min
        else:
            farthest['y'] = bbox_y_max

        # Get distance between p1 and farthest point
        dist = math.sqrt(farthest['x'] ** 2 + farthest['y'] ** 2)

        # Normalize v1 then scale it by dist
        len_v1 = math.sqrt(v1.x ** 2 + v1.y ** 2)
        v1.x = (v1.x / len_v1) * dist * 1.001
        v1.y = (v1.y / len_v1) * dist * 1.001

        return Geometry.line(r1.p1, Geometry.point(v1.x + r1.p1.x, v1.y + r1.p1.y))

    @staticmethod
    def segment_length(seg: Line) -> float:
        """
        Calculate the length of a line segment.

        Args:
            seg: Line segment

        Returns:
            Length of segment
        """
        return math.sqrt(Geometry.segment_length_squared(seg))

    @staticmethod
    def segment_length_squared(seg: Line) -> float:
        """
        Calculate the squared length of a line segment.

        Args:
            seg: Line segment

        Returns:
            Squared length of segment
        """
        return Geometry.distance_squared(seg.p1, seg.p2)

    @staticmethod
    def distance(p1: Point, p2: Point) -> float:
        """
        Calculate the distance between two points.

        Args:
            p1: First point
            p2: Second point

        Returns:
            Distance between points
        """
        return math.sqrt(Geometry.distance_squared(p1, p2))

    @staticmethod
    def distance_squared(p1: Point, p2: Point) -> float:
        """
        Calculate the squared distance between two points.

        Args:
            p1: First point
            p2: Second point

        Returns:
            Squared distance between points
        """
        dx = p1.x - p2.x
        dy = p1.y - p2.y
        return dx * dx + dy * dy

    @staticmethod
    def segment_midpoint(l1: Line) -> Point:
        """
        Calculate the midpoint of a segment.

        Args:
            l1: Line segment

        Returns:
            Midpoint
        """
        nx = (l1.p1.x + l1.p2.x) * 0.5
        ny = (l1.p1.y + l1.p2.y) * 0.5
        return Geometry.point(nx, ny)

    @staticmethod
    def midpoint(p1: Point, p2: Point) -> Point:
        """
        Calculate the midpoint between two points.

        Args:
            p1: First point
            p2: Second point

        Returns:
            Midpoint
        """
        nx = (p1.x + p2.x) * 0.5
        ny = (p1.y + p2.y) * 0.5
        return Geometry.point(nx, ny)

    @staticmethod
    def perpendicular_bisector(l1: Line) -> Line:
        """
        Calculate the perpendicular bisector of a segment.

        Args:
            l1: Line segment

        Returns:
            Perpendicular bisector line
        """
        return Geometry.line(
            Geometry.point(
                (-l1.p1.y + l1.p2.y + l1.p1.x + l1.p2.x) * 0.5,
                (l1.p1.x - l1.p2.x + l1.p1.y + l1.p2.y) * 0.5
            ),
            Geometry.point(
                (l1.p1.y - l1.p2.y + l1.p1.x + l1.p2.x) * 0.5,
                (-l1.p1.x + l1.p2.x + l1.p1.y + l1.p2.y) * 0.5
            )
        )

    @staticmethod
    def parallel_line_through_point(l1: Line, p1: Point) -> Line:
        """
        Calculate the line through p1 and parallel to l1.

        Args:
            l1: Reference line
            p1: Point the parallel line passes through

        Returns:
            Parallel line
        """
        dx = l1.p2.x - l1.p1.x
        dy = l1.p2.y - l1.p1.y
        return Geometry.line(p1, Geometry.point(p1.x + dx, p1.y + dy))

    @staticmethod
    def normalize_vec(p1: Point) -> Point:
        """
        Normalize the given point as if it were a vector.

        Args:
            p1: Point (as vector)

        Returns:
            Normalized vector
        """
        len_val = Geometry.distance(Geometry.point(0, 0), p1)
        return Geometry.point(p1.x / len_val, p1.y / len_val)

    @staticmethod
    def rotate_vec(p1: Point, angle: float) -> Point:
        """
        Rotate the given point as if it were a vector by the given angle in radians.

        Args:
            p1: Point (as vector)
            angle: Rotation angle in radians

        Returns:
            Rotated vector
        """
        # Rotate by the rotation matrix
        return Geometry.point(
            p1.x * math.cos(angle) - p1.y * math.sin(angle),
            p1.x * math.sin(angle) + p1.y * math.cos(angle)
        )


# Create a singleton instance for convenience
geometry = Geometry()


# Example usage and testing
if __name__ == "__main__":
    # Create points
    p1 = geometry.point(0, 0)
    p2 = geometry.point(3, 4)

    # Test distance
    dist = geometry.distance(p1, p2)
    print(f"Distance between {p1} and {p2}: {dist}")

    # Create a line
    l1 = geometry.line(p1, p2)
    print(f"Line: {l1}")

    # Create a circle
    c1 = geometry.circle(p1, 5.0)
    print(f"Circle: {c1}, radius: {c1.get_radius()}")

    # Test line intersection
    l2 = geometry.line(geometry.point(0, 4), geometry.point(3, 0))
    intersection = geometry.lines_intersection(l1, l2)
    print(f"Intersection of {l1} and {l2}: {intersection}")

    # Test dot product
    dot = geometry.dot(p1, p2)
    print(f"Dot product: {dot}")

    # Test cross product
    cross = geometry.cross(geometry.point(1, 0), geometry.point(0, 1))
    print(f"Cross product: {cross}")

    # Test vector operations
    normalized = geometry.normalize_vec(p2)
    print(f"Normalized vector of {p2}: {normalized}")

    rotated = geometry.rotate_vec(geometry.point(1, 0), math.pi / 2)
    print(f"Rotated vector (90 degrees): {rotated}")
