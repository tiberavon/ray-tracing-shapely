"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
BASE PRISM CLASS
===============================================================================
Base class for all prisms with:
- Dual-labeling architecture (functional + cardinal labels)
- Physics-driven geometry from parameters
- Convenient constructors

The dual-labeling system supports LLM-agent-in-the-loop optical design:
- Functional labels: what an edge does optically (invariant under rotation)
- Cardinal labels: where an edge points in scene coordinates (rotation-dependent)
===============================================================================
"""

from __future__ import annotations

import math
from abc import abstractmethod
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from ...core.scene import Scene

# Import Glass class
from ...core.scene_objs.glass.glass import Glass


class BasePrism(Glass):
    """
    Base class for all prisms with convenient constructors.

    This class provides:
    - Dual-labeling architecture (functional labels + cardinal labels)
    - Abstract _compute_path() method for subclasses to define geometry
    - Anchor point support ('centroid' or 'apex' positioning)
    - apex_vertex property for querying apex location

    Subclasses must:
    1. Define _edge_roles and _vertex_roles class variables
    2. Define _apex_vertex_index class variable (or None if no apex)
    3. Implement _compute_path() to return vertex coordinates

    Attributes:
        size: Characteristic size parameter (meaning depends on subclass)
        _position: Reference point coordinates
        _rotation: Rotation angle in degrees
        _anchor: Position reference type ('centroid' or 'apex')
        _functional_labels: Dict mapping edge index to (short, long) functional labels
        _vertex_labels: Dict mapping vertex index to (short, long) labels
    """

    # --- Class variables (overridden by subclasses) ---
    _edge_roles: ClassVar[List[Tuple[str, str]]] = []
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None

    # Classes that support local mesh refinement (15_p7_mesh_refinement_and_convergence.md)
    # override this to True and give _compute_path() a refinement_spans keyword
    # parameter. False by default so straight-edge subclasses (nothing to
    # refine) need no changes at all.
    _supports_refinement: ClassVar[bool] = False

    # Prism-specific type identifier
    type = 'BasePrism'

    def __init__(
        self,
        scene: 'Scene',
        size: float,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        n: float = 1.5,
        anchor: str = 'centroid',
        refinement_spans: Optional[List[Tuple[float, float, int]]] = None,
        **kwargs: Any
    ) -> None:
        """
        Initialize a prism.

        Args:
            scene: The scene this prism belongs to.
            size: Characteristic size (meaning depends on subclass).
            position: Reference point coordinates.
            rotation: Rotation angle in degrees (counterclockwise).
            n: Refractive index.
            anchor: Position reference - 'centroid' or 'apex'.
            refinement_spans: Local mesh-refinement spans, passed through to
                _compute_path() only for subclasses with
                _supports_refinement = True (15_p7_mesh_refinement_and_convergence.md
                §4.1); ignored otherwise so straight-edge subclasses need no
                changes.
            **kwargs: Additional arguments passed to parent class.

        Raises:
            ValueError: If anchor is not 'centroid' or 'apex'.
        """
        if anchor not in ('centroid', 'apex'):
            raise ValueError(f"anchor must be 'centroid' or 'apex', got '{anchor}'")

        # Store parameters before calling parent __init__
        self.size = size
        self._position = position
        self._rotation = rotation
        self._anchor = anchor

        # Initialize parent class with empty JSON to avoid path issues
        super().__init__(scene, json_obj=None)

        # Set refractive index
        self.refIndex = n

        # Build geometry - this calls the subclass's _compute_path()
        if self._supports_refinement:
            self.path = self._compute_path(refinement_spans=refinement_spans)
        else:
            self.path = self._compute_path()

        # Apply both label layers
        self._apply_functional_labels()
        self._apply_vertex_labels()
        self.auto_label_cardinal()

    @abstractmethod
    def _compute_path(self) -> List[Dict[str, Union[float, bool]]]:
        """
        Compute vertex path from parameters.

        Contract:
        - Return vertices in counterclockwise order (Shapely convention).
        - Each vertex is {'x': float, 'y': float, 'arc': False}.
        - Edge i connects vertex i to vertex (i+1) % n.
        - The ordering must match _edge_roles and _vertex_roles indices.

        The implementation should:
        1. Compute vertices at origin in canonical orientation
        2. Apply rotation around origin
        3. Apply translation based on anchor point

        Returns:
            List of vertex dictionaries.
        """
        ...

    def _apply_rotation_and_translation(
        self,
        vertices: List[Tuple[float, float]]
    ) -> List[Dict[str, Union[float, bool]]]:
        """
        Apply rotation and translation to vertices based on anchor setting.

        Args:
            vertices: List of (x, y) tuples in canonical position/orientation.

        Returns:
            List of vertex dicts with 'x', 'y', 'arc' keys, properly positioned.
        """
        # Convert to radians
        theta = math.radians(self._rotation)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        # First, rotate all vertices around origin
        rotated = []
        for x, y in vertices:
            rx = x * cos_t - y * sin_t
            ry = x * sin_t + y * cos_t
            rotated.append((rx, ry))

        # Compute centroid of rotated vertices
        cx = sum(v[0] for v in rotated) / len(rotated)
        cy = sum(v[1] for v in rotated) / len(rotated)

        # Determine translation offset based on anchor
        if self._anchor == 'centroid':
            # Move centroid to position
            offset_x = self._position[0] - cx
            offset_y = self._position[1] - cy
        elif self._anchor == 'apex':
            # Move apex vertex to position
            if self._apex_vertex_index is not None:
                apex = rotated[self._apex_vertex_index]
                offset_x = self._position[0] - apex[0]
                offset_y = self._position[1] - apex[1]
            else:
                # No apex defined, fall back to centroid
                offset_x = self._position[0] - cx
                offset_y = self._position[1] - cy
        else:
            offset_x = self._position[0] - cx
            offset_y = self._position[1] - cy

        # Apply translation and convert to path format
        path = []
        for rx, ry in rotated:
            path.append({
                'x': rx + offset_x,
                'y': ry + offset_y,
                'arc': False
            })

        return path

    # =========================================================================
    # Functional Labels (optical-function labels, rotation-invariant)
    # =========================================================================

    def _apply_functional_labels(self) -> None:
        """
        Apply optical-function labels to edges.

        Stored in a separate attribute from the cardinal labels in BaseGlass.
        Functional labels describe what an edge does optically (e.g., "Entrance",
        "Hypotenuse", "TIR Surface") and are invariant under rotation.

        Each _edge_roles entry is (short, long) or (short, long, role), where
        role is an optical_elements.roles.Role tag -- the third element is
        optional so existing 2-tuple _edge_roles keep working unchanged.
        """
        self._functional_labels: Dict[int, Tuple[str, str]] = {}
        self._edge_role_tags: Dict[int, Optional[Any]] = {}
        for i, entry in enumerate(self._edge_roles):
            short, long = entry[0], entry[1]
            self._functional_labels[i] = (short, long)
            self._edge_role_tags[i] = entry[2] if len(entry) > 2 else None

    def _apply_vertex_labels(self) -> None:
        """
        Apply optical-function labels to vertices.

        Vertex labels identify specific vertices (e.g., "Apex", "Right-Angle").
        """
        self._vertex_labels: Dict[int, Tuple[str, str]] = {}
        for i, (short, long) in enumerate(self._vertex_roles):
            self._vertex_labels[i] = (short, long)

    def get_functional_label(self, edge_index: int) -> Optional[Tuple[str, str]]:
        """
        Return (short, long) functional label for an edge.

        Args:
            edge_index: The edge index (0-based).

        Returns:
            Tuple of (short_label, long_label), or None if not found.
        """
        return self._functional_labels.get(edge_index)

    def get_edge_role(self, edge_index: int) -> Optional[Any]:
        """
        Return the Role tag for an edge, if its _edge_roles entry supplied one.

        Args:
            edge_index: The edge index (0-based).

        Returns:
            The optical_elements.roles.Role, or None if not tagged.
        """
        return self._edge_role_tags.get(edge_index)

    def find_edge_by_functional_label(self, short_label: str) -> Optional[int]:
        """
        Return edge index for a functional short label.

        Args:
            short_label: The functional short label (e.g., 'E', 'H', 'X').

        Returns:
            The edge index, or None if not found.
        """
        for i, (s, _) in self._functional_labels.items():
            if s == short_label:
                return i
        return None

    def get_vertex_label(self, vertex_index: int) -> Optional[Tuple[str, str]]:
        """
        Return (short, long) label for a vertex.

        Args:
            vertex_index: The vertex index (0-based).

        Returns:
            Tuple of (short_label, long_label), or None if not found.
        """
        return self._vertex_labels.get(vertex_index)

    def find_vertex_by_label(self, short_label: str) -> Optional[int]:
        """
        Return vertex index for a short label.

        Args:
            short_label: The vertex short label (e.g., 'A' for Apex).

        Returns:
            The vertex index, or None if not found.
        """
        for i, (s, _) in self._vertex_labels.items():
            if s == short_label:
                return i
        return None

    # =========================================================================
    # Apex Vertex Property
    # =========================================================================

    @property
    def apex_vertex(self) -> Optional[Tuple[float, float]]:
        """
        Return the coordinates of the apex vertex.

        The apex is defined as the vertex with the smallest interior angle,
        or the vertex explicitly designated by the subclass. For prisms with
        multiple equal-smallest angles (e.g., equilateral), the subclass
        defines which vertex is considered the "apex" for positioning.

        Returns:
            Tuple of (x, y) coordinates, or None if no apex is defined.
        """
        if self._apex_vertex_index is None:
            return None
        if not self.path or self._apex_vertex_index >= len(self.path):
            return None
        v = self.path[self._apex_vertex_index]
        return (v['x'], v['y'])

    # =========================================================================
    # Label Summary (for LLM agents)
    # =========================================================================

    def label_summary(self) -> str:
        """
        Return a text summary combining functional and cardinal labels.

        Useful for LLM agents to understand the full edge semantics.

        Example output:
          Edge 0: Entrance Face (E) | facing West (W)
          Edge 1: Hypotenuse (H)    | facing North-East (NE)
          Edge 2: Exit Face (X)     | facing South (S)

        Returns:
            Multi-line string describing all edges.
        """
        lines: List[str] = []
        for i in range(self._get_edge_count()):
            func = self._functional_labels.get(i, (str(i), str(i)))
            card = self.get_edge_label(i)  # cardinal, from BaseGlass
            card_short = card[0] if card else "?"
            card_long = card[1] if card else "?"
            lines.append(
                f"Edge {i}: {func[1]} ({func[0]}) | facing {card_long} ({card_short})"
            )
        return "\n".join(lines)

    # =========================================================================
    # Escape Hatch Constructor
    # =========================================================================

    @classmethod
    def from_vertices(
        cls,
        scene: 'Scene',
        vertices: List[Tuple[float, float]],
        n: float = 1.5
    ) -> 'BasePrism':
        """
        Create from explicit vertex coordinates (escape hatch).

        Contract:
        - This method lives on BasePrism only. Subclasses inherit but do not override.
        - Functional labels (_edge_roles, _vertex_roles) are NOT applied, because
          the geometry may not match the subclass's expected angles.
        - Cardinal labels ARE applied via auto_label_cardinal().
        - The returned instance has numeric edge labels (0, 1, 2, ...) for the
          functional layer.
        - Use this when you have a custom geometry that doesn't fit standard
          prism templates but still want dual-labeling infrastructure.

        Args:
            scene: The scene this prism belongs to.
            vertices: List of (x, y) tuples defining the prism boundary (CCW order).
            n: Refractive index.

        Returns:
            A new BasePrism instance with custom geometry.
        """
        # Create instance without calling __init__ to avoid _compute_path
        instance = object.__new__(cls)

        # Initialize parent class manually
        Glass.__init__(instance, scene, json_obj=None)

        # Set attributes
        instance.size = 0.0  # Not meaningful for custom geometry
        instance._position = (0.0, 0.0)
        instance._rotation = 0.0
        instance._anchor = 'centroid'
        instance.refIndex = n

        # Build path from vertices
        instance.path = [
            {'x': x, 'y': y, 'arc': False}
            for x, y in vertices
        ]

        # Apply numeric functional labels (not type-specific)
        instance._functional_labels = {
            i: (str(i), f"Edge {i}")
            for i in range(len(vertices))
        }
        instance._vertex_labels = {
            i: (str(i), f"Vertex {i}")
            for i in range(len(vertices))
        }

        # Apply cardinal labels based on geometry
        instance.auto_label_cardinal()

        return instance

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_edge_endpoints(self, edge_index: int) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """
        Get the start and end points of an edge.

        Args:
            edge_index: The edge index (0-based).

        Returns:
            Tuple of ((x1, y1), (x2, y2)), or None if invalid index.
        """
        if not self.path or edge_index < 0 or edge_index >= len(self.path):
            return None
        p1 = self.path[edge_index]
        p2 = self.path[(edge_index + 1) % len(self.path)]
        return ((p1['x'], p1['y']), (p2['x'], p2['y']))

    def get_edge_length(self, edge_index: int) -> float:
        """
        Get the length of an edge.

        Args:
            edge_index: The edge index (0-based).

        Returns:
            The edge length, or 0.0 if invalid index.
        """
        endpoints = self.get_edge_endpoints(edge_index)
        if endpoints is None:
            return 0.0
        (x1, y1), (x2, y2) = endpoints
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    def get_interior_angle(self, vertex_index: int) -> float:
        """
        Get the interior angle at a vertex in degrees.

        Args:
            vertex_index: The vertex index (0-based).

        Returns:
            The interior angle in degrees, or 0.0 if invalid.
        """
        if not self.path or vertex_index < 0 or vertex_index >= len(self.path):
            return 0.0

        n = len(self.path)
        # Get three consecutive vertices
        p0 = self.path[(vertex_index - 1) % n]
        p1 = self.path[vertex_index]
        p2 = self.path[(vertex_index + 1) % n]

        # Vectors from p1 to p0 and p1 to p2
        v1 = (p0['x'] - p1['x'], p0['y'] - p1['y'])
        v2 = (p2['x'] - p1['x'], p2['y'] - p1['y'])

        # Dot product and magnitudes
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
        mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

        if mag1 == 0 or mag2 == 0:
            return 0.0

        # Clamp to avoid numerical issues with acos
        cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
        return math.degrees(math.acos(cos_angle))

    def get_centroid(self) -> Tuple[float, float]:
        """
        Get the centroid of the prism.

        Returns:
            Tuple of (x, y) coordinates.
        """
        return self._get_centroid()

    def signed_area(self) -> float:
        """
        Compute the signed area of the prism polygon.

        Positive area indicates counterclockwise vertex ordering.
        Negative area indicates clockwise ordering.

        Returns:
            The signed area.
        """
        if not self.path or len(self.path) < 3:
            return 0.0

        area = 0.0
        n = len(self.path)
        for i in range(n):
            j = (i + 1) % n
            area += self.path[i]['x'] * self.path[j]['y']
            area -= self.path[j]['x'] * self.path[i]['y']
        return area / 2.0
