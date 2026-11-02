"""
Python-specific module: right angle
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
RIGHT-ANGLE PRISM
===============================================================================
A 45-90-45 right-angle prism for TIR applications.

The right-angle prism uses total internal reflection at the hypotenuse
to deflect light by 90 degrees (or 180 degrees with two reflections).
Often used as a mirror substitute.

Vertex layout (before rotation):

    Coordinate system: +X = East, +Y = North

                         N
                         |
        V2 (right angle, 90 deg)
        |\\
        | \\
        |  \\   <- Edge 1: Hypotenuse (H) -- cardinal: East (E)
        |   \\
        |    \\
        V0----V1  -> E
          Edge 0: Entrance Face (E) -- cardinal: South (S)

    Edge 2 (V2->V0): Exit Face (X) -- cardinal: West (W)

    Vertex traversal V0->V1->V2->V0 is counterclockwise (positive signed area).

Functional labels:
    Edge 0: E (Entrance Face) - one of the two leg faces
    Edge 1: H (Hypotenuse) - TIR surface (when n >= sqrt(2))
    Edge 2: X (Exit Face) - the other leg face

Minimum n for TIR:
    n >= sqrt(2) ~ 1.414
    At 45 deg incidence on the hypotenuse, TIR requires the critical angle
    to be <= 45 deg, which means n >= 1/sin(45 deg) = sqrt(2).
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, Dict, List, Tuple, Union, TYPE_CHECKING

from .base_prism import BasePrism

if TYPE_CHECKING:
    from ...core.scene import Scene


# Minimum refractive index for TIR at 45-degree incidence
MIN_N_FOR_TIR = math.sqrt(2)  # ~1.414


class RightAnglePrism(BasePrism):
    """
    45-90-45 right-angle prism.

    The right-angle prism is commonly used for:
    - 90-degree beam deflection via TIR
    - 180-degree retroreflection (using both legs)
    - Image inversion
    - As a mirror substitute (avoids coating issues)

    Attributes:
        leg_length: Length of each leg (the two equal sides).

    Note:
        For TIR to occur at the hypotenuse, n >= sqrt(2) ~ 1.414.
        Most optical glasses (n ~ 1.5) satisfy this requirement.

    Example:
        >>> from ray_tracing_shapely.core.scene import Scene
        >>> scene = Scene()
        >>> prism = RightAnglePrism(scene, leg_length=30.0, n=1.5)
        >>> print(prism.label_summary())
        Edge 0: Entrance Face (E) | facing South Edge (S)
        Edge 1: Hypotenuse (H) | facing North East Edge (NE)
        Edge 2: Exit Face (X) | facing West Edge (W)
    """

    # Functional labels for edges (in path order)
    _edge_roles: ClassVar[List[Tuple[str, str]]] = [
        ("E", "Entrance Face"),
        ("H", "Hypotenuse"),
        ("X", "Exit Face"),
    ]

    # Labels for vertices (in path order)
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = [
        ("A1", "Acute Vertex 1"),
        ("A2", "Acute Vertex 2"),
        ("R", "Right-Angle Vertex"),
    ]

    # No unique apex (two acute vertices are symmetric)
    _apex_vertex_index: ClassVar[None] = None

    # Prism-specific type identifier
    type = 'RightAnglePrism'

    def __init__(
        self,
        scene: 'Scene',
        leg_length: float,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        n: float = 1.5,
        anchor: str = 'centroid',
        **kwargs: Any
    ) -> None:
        """
        Create a right-angle prism.

        Args:
            scene: The scene this prism belongs to.
            leg_length: Length of each leg (the two equal sides).
            position: Reference point coordinates.
            rotation: Rotation angle in degrees (counterclockwise).
            n: Refractive index.
            anchor: Position reference - 'centroid' or 'apex'.

        Note:
            For TIR at the hypotenuse, n should be >= sqrt(2) ~ 1.414.
        """
        self.leg_length = leg_length
        super().__init__(
            scene=scene,
            size=leg_length,
            position=position,
            rotation=rotation,
            n=n,
            anchor=anchor,
            **kwargs
        )

    def _compute_path(self) -> List[Dict[str, Union[float, bool]]]:
        """
        Compute vertex path for right-angle triangle.

        Vertices (CCW, before rotation/translation):
            V0 = (0, 0)      Acute Vertex 1
            V1 = (leg, 0)    Acute Vertex 2
            V2 = (0, leg)    Right-Angle Vertex

        Edge 0 (V0->V1): Entrance face (bottom leg)
        Edge 1 (V1->V2): Hypotenuse
        Edge 2 (V2->V0): Exit face (left leg)

        Returns:
            List of vertex dictionaries with 'x', 'y', 'arc' keys.
        """
        leg = self.leg_length

        vertices = [
            (0.0, 0.0),       # V0: Acute Vertex 1
            (leg, 0.0),       # V1: Acute Vertex 2
            (0.0, leg),       # V2: Right-Angle Vertex
        ]

        return self._apply_rotation_and_translation(vertices)

    @property
    def hypotenuse_length(self) -> float:
        """
        Return the hypotenuse length.
        """
        return self.leg_length * math.sqrt(2)

    @property
    def supports_tir(self) -> bool:
        """
        Check if TIR is possible at the hypotenuse.

        Returns:
            True if n >= sqrt(2), False otherwise.
        """
        return self.refIndex >= MIN_N_FOR_TIR

    def critical_angle_at_hypotenuse(self) -> float:
        """
        Calculate the critical angle at the hypotenuse (glass to air).

        Returns:
            Critical angle in degrees.

        Raises:
            ValueError: If n < 1 (no TIR possible).
        """
        if self.refIndex < 1.0:
            raise ValueError(
                f"No TIR possible: n ({self.refIndex}) must be >= 1"
            )
        # Critical angle: sin(theta_c) = n_air / n_glass = 1 / n
        return math.degrees(math.asin(1.0 / self.refIndex))

    def tir_margin(self) -> float:
        """
        Calculate how far above the TIR threshold this prism is.

        Returns:
            The margin in degrees between the 45-degree incidence angle
            and the critical angle. Positive means TIR will occur.
        """
        if self.refIndex < 1.0:
            return float('-inf')
        critical = self.critical_angle_at_hypotenuse()
        return 45.0 - critical

    @property
    def right_angle_vertex(self) -> Tuple[float, float]:
        """
        Return the coordinates of the right-angle vertex.
        """
        if not self.path or len(self.path) < 3:
            return (0.0, 0.0)
        v = self.path[2]
        return (v['x'], v['y'])

    def get_entrance_face_endpoints(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        Get the endpoints of the entrance face (Edge 0).

        Returns:
            Tuple of ((x1, y1), (x2, y2)).
        """
        return self.get_edge_endpoints(0)

    def get_hypotenuse_endpoints(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        Get the endpoints of the hypotenuse (Edge 1).

        Returns:
            Tuple of ((x1, y1), (x2, y2)).
        """
        return self.get_edge_endpoints(1)

    def get_exit_face_endpoints(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        Get the endpoints of the exit face (Edge 2).

        Returns:
            Tuple of ((x1, y1), (x2, y2)).
        """
        return self.get_edge_endpoints(2)
