"""
Python-specific module: equilateral
Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
EQUILATERAL PRISM
===============================================================================
A 60-60-60 equilateral dispersing prism.

Classic prism for spectrum demonstration and wavelength separation.
All three sides are equal length, all three angles are 60 degrees.

Vertex layout (before rotation):

    Coordinate system: +X = East, +Y = North

                     N
                     |
            V2 (apex, top) -- Apex vertex (A)
           / \
          /   \\   <- Edge 1: Exit Face (X) -- cardinal: NE
         /     \
        V0-----V1  -> E
          Edge 0: Base (B) -- cardinal: South (S)

    Edge 2 (V2->V0): Entrance Face (E) -- cardinal: NW

    Vertex traversal V0->V1->V2->V0 is counterclockwise (positive signed area).

Functional labels:
    Edge 0: B (Base) - bottom edge, opposite the apex
    Edge 1: X (Exit Face) - right refracting surface
    Edge 2: E (Entrance Face) - left refracting surface

Note on E/X symmetry:
    In an equilateral prism, entrance and exit faces are interchangeable.
    The labels assume canonical orientation (light enters from the left).
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, Dict, List, Tuple, Union, TYPE_CHECKING

from .base_prism import BasePrism

if TYPE_CHECKING:
    from ...core.scene import Scene


class EquilateralPrism(BasePrism):
    """
    60-60-60 equilateral dispersing prism.

    The equilateral prism is the classic dispersive element for separating
    white light into its spectrum. All three internal angles are 60 degrees.

    Attributes:
        side_length: Length of each side of the equilateral triangle.

    Example:
        >>> from ray_tracing_shapely.core.scene import Scene
        >>> scene = Scene()
        >>> prism = EquilateralPrism(scene, side_length=50.0, n=1.5)
        >>> print(prism.label_summary())
        Edge 0: Base (B) | facing South Edge (S)
        Edge 1: Exit Face (X) | facing North East Edge (NE)
        Edge 2: Entrance Face (E) | facing North West Edge (NW)
    """

    # Functional labels for edges (in path order)
    _edge_roles: ClassVar[List[Tuple[str, str]]] = [
        ("B", "Base"),
        ("X", "Exit Face"),
        ("E", "Entrance Face"),
    ]

    # Labels for vertices (in path order)
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = [
        ("BL", "Base Left"),
        ("BR", "Base Right"),
        ("A", "Apex"),
    ]

    # Apex is vertex 2 (the top vertex)
    _apex_vertex_index: ClassVar[int] = 2

    # Prism-specific type identifier
    type = 'EquilateralPrism'

    def __init__(
        self,
        scene: 'Scene',
        side_length: float,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        n: float = 1.5,
        anchor: str = 'centroid',
        **kwargs: Any
    ) -> None:
        """
        Create an equilateral prism.

        Args:
            scene: The scene this prism belongs to.
            side_length: Length of each side of the triangle.
            position: Reference point coordinates.
            rotation: Rotation angle in degrees (counterclockwise).
            n: Refractive index.
            anchor: Position reference - 'centroid' or 'apex'.
        """
        self.side_length = side_length
        super().__init__(
            scene=scene,
            size=side_length,
            position=position,
            rotation=rotation,
            n=n,
            anchor=anchor,
            **kwargs
        )

    def _compute_path(self) -> List[Dict[str, Union[float, bool]]]:
        """
        Compute vertex path for equilateral triangle.

        Vertices (CCW, before rotation/translation):
            V0 = (0, 0)                      Base Left
            V1 = (side, 0)                   Base Right
            V2 = (side/2, side*sqrt(3)/2)    Apex

        Edge 0 (V0->V1): Base (bottom)
        Edge 1 (V1->V2): Exit Face (right side)
        Edge 2 (V2->V0): Entrance Face (left side)

        Returns:
            List of vertex dictionaries with 'x', 'y', 'arc' keys.
        """
        s = self.side_length
        h = s * math.sqrt(3) / 2  # Height of equilateral triangle

        # Vertices centered around (s/2, h/3) for centroid at origin
        # But we'll use corner at origin and let _apply_rotation_and_translation handle it
        vertices = [
            (0.0, 0.0),           # V0: Base Left
            (s, 0.0),             # V1: Base Right
            (s / 2, h),           # V2: Apex
        ]

        return self._apply_rotation_and_translation(vertices)

    def swap_entrance_exit(self) -> None:
        """
        Swap the Entrance and Exit face labels.

        In an equilateral prism, the two refracting faces are symmetric.
        This method swaps the E/X labels to reflect a different light
        direction convention.
        """
        # Swap edges 1 and 2 in functional labels
        self._functional_labels[1] = ("E", "Entrance Face")
        self._functional_labels[2] = ("X", "Exit Face")

    @property
    def apex_angle(self) -> float:
        """
        Return the apex angle in degrees.

        For an equilateral prism, this is always 60 degrees.
        """
        return 60.0

    @property
    def base_length(self) -> float:
        """
        Return the base length (same as side_length for equilateral).
        """
        return self.side_length

    def minimum_deviation(self, n: float = None) -> float:
        """
        Calculate the minimum deviation angle for this prism.

        Args:
            n: Refractive index (uses self.refIndex if not provided).

        Returns:
            Minimum deviation angle in degrees.
        """
        from .prism_utils import minimum_deviation
        if n is None:
            n = self.refIndex
        return minimum_deviation(60.0, n)

    def incidence_for_minimum_deviation(self, n: float = None) -> float:
        """
        Calculate the incidence angle that produces minimum deviation.

        Args:
            n: Refractive index (uses self.refIndex if not provided).

        Returns:
            Incidence angle in degrees.
        """
        from .prism_utils import incidence_for_minimum_deviation
        if n is None:
            n = self.refIndex
        return incidence_for_minimum_deviation(60.0, n)
