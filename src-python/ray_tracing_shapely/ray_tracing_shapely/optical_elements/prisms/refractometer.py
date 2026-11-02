"""
Python-specific module: refractometer
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
REFRACTOMETER PRISM
===============================================================================
A symmetric trapezoidal prism for refractometer applications.

The refractometer prism is designed for critical-angle measurements of
sample refractive index. Light hits the measuring surface at various
angles; above the critical angle, total internal reflection occurs.
The sharp boundary between reflected and transmitted light encodes
the sample's refractive index.

Vertex layout (before rotation):

    Coordinate system: +X = East, +Y = North

        V3--------------V2    <- Edge 2: Measuring Surface (M)
         \\              /
          \\            /      <- Edge 1: Exit Face (X)
           \\          /
            \\        /
             V0----V1         <- Edge 0: Base (B)

    Edge 3 (V3->V0): Entrance Face (E)

    Vertex traversal V0->V1->V2->V3->V0 is counterclockwise.

Functional labels:
    Edge 0: B (Base) - bottom edge
    Edge 1: X (Exit Face) - refracting surface
    Edge 2: M (Measuring Surface) - sample contact / TIR boundary
    Edge 3: E (Entrance Face) - refracting surface

Physics:
    The face angle is computed so that light at the CENTER of the
    measurement range exits perpendicular to the exit face, minimizing
    ghost reflections and simplifying the optical path.

Two system architectures:
    - 'angular': Abbe-like with focusing lens (measuring surface length is free)
    - 'geometric': Lensless direct imaging (length constrained by geometry)
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

from .base_prism import BasePrism
from . import tir_utils
from ..roles import Role, Mechanism

if TYPE_CHECKING:
    from ...core.scene import Scene


class RefractometerPrism(BasePrism):
    """
    Symmetric trapezoidal prism for refractometer applications.

    The prism geometry is computed from the target sample refractive
    index range. The face angle ensures normal exit at mid-range.

    Attributes:
        n_prism: Refractive index of the prism material.
        n_sample_range: Tuple of (n_min, n_max) for the measurement range.
        measuring_surface_length: Length of the measuring surface.
        system_type: 'angular' or 'geometric'.
        face_angle: Computed face angle in degrees.
        theta_c_range: Computed critical angle range in degrees.

    Example:
        >>> from ray_tracing_shapely.core.scene import Scene
        >>> scene = Scene()
        >>> prism = RefractometerPrism(
        ...     scene,
        ...     n_prism=1.72,
        ...     n_sample_range=(1.30, 1.50),
        ...     measuring_surface_length=20.0
        ... )
        >>> print(f"Face angle: {prism.face_angle:.1f} degrees")
    """

    # Functional labels for edges (in path order), each also carrying a
    # Role tag (optical_elements.roles.Role) -- the third tuple element
    # base_prism._apply_functional_labels() already knows how to read,
    # matching the pattern DTIRCPrism established. B is never on the
    # optical path (RefractometerPrism.from_apex_angle's own docstring
    # traces a ray E -> M -> X only), so Role.BLOCKER fits it more
    # precisely than Role.ABSORBER, which the vocabulary reserves for a
    # surface meant to terminate the traced beam on purpose (a detector,
    # a beam dump) -- B does neither, it is simply outside the path.
    _edge_roles: ClassVar[List[Tuple[str, str, Role]]] = [
        ("B", "Base", Role.BLOCKER),
        ("X", "Exit Face", Role.EXIT),
        ("M", "Measuring Surface", Role.SAMPLE_MEDIUM),
        ("E", "Entrance Face", Role.ENTRANCE),
    ]

    # Mechanism per edge (optical_elements.roles.Mechanism), keyed by the
    # short functional label above. Not part of BasePrism's _edge_roles
    # schema (Role only) -- this project has no design-time Mechanism
    # declaration anywhere yet (grep confirms Mechanism is otherwise only
    # ever referenced from developer_tests/test_roles.py), so this is the
    # first real one, added for profile_export's spans field.
    # M's declared mechanism is the *design* point's mechanism (n_target
    # sits exactly at the critical angle): TIR at and below n_target, but
    # a real sample above n_target transmits instead -- see
    # RefractometerPrism's own class docstring. profile_export.py
    # documents this ambiguity explicitly rather than silently picking one.
    _edge_mechanisms: ClassVar[Dict[str, Optional[Mechanism]]] = {
        "B": None,
        "X": Mechanism.REFRACT,
        "M": Mechanism.TIR,
        "E": Mechanism.REFRACT,
    }

    # Labels for vertices (in path order)
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = [
        ("BL", "Base Left"),
        ("BR", "Base Right"),
        ("TR", "Top Right"),
        ("TL", "Top Left"),
    ]

    # Trapezoid has no apex
    _apex_vertex_index: ClassVar[None] = None

    # Prism-specific type identifier
    type = 'RefractometerPrism'

    def __init__(
        self,
        scene: 'Scene',
        n_prism: float,
        n_sample_range: Tuple[float, float],
        measuring_surface_length: float,
        system_type: str = 'angular',
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0,
        **kwargs: Any
    ) -> None:
        """
        Create a refractometer prism from physics parameters.

        The face angle is computed automatically from n_sample_range
        to ensure normal exit at mid-range.

        Args:
            scene: The scene this prism belongs to.
            n_prism: Refractive index of the prism material.
            n_sample_range: Tuple of (n_min, n_max) for expected samples.
            measuring_surface_length: Length of the measuring surface.
            system_type: 'angular' (Abbe-like) or 'geometric' (lensless).
            position: Reference point coordinates.
            rotation: Rotation angle in degrees.

        Raises:
            ValueError: If n_prism <= n_max (TIR impossible).
            ValueError: If system_type is not 'angular' or 'geometric'.
        """
        n_min, n_max = n_sample_range

        if n_prism <= n_max:
            raise ValueError(
                f"TIR impossible: n_prism ({n_prism}) must be > n_max ({n_max})"
            )

        if system_type not in ('angular', 'geometric'):
            raise ValueError(
                f"system_type must be 'angular' or 'geometric', got '{system_type}'"
            )

        # Store physics parameters
        self.n_prism = n_prism
        self.n_sample_range = n_sample_range
        self.measuring_surface_length = measuring_surface_length
        self.system_type = system_type

        # Compute face angle for normal exit at mid-range
        self.face_angle = tir_utils.prism_face_angle_for_normal_exit(
            n_sample_range, n_prism
        )

        # Compute critical angle range
        self.theta_c_range = tir_utils.critical_angle_range(n_sample_range, n_prism)

        # Optional geometric system parameters (set by from_geometric_constraints)
        self.source_distance: Optional[float] = None
        self.sensor_length: Optional[float] = None
        self.path_length: Optional[float] = None

        # Initialize base class (will call _compute_path)
        super().__init__(
            scene=scene,
            size=measuring_surface_length,
            position=position,
            rotation=rotation,
            n=n_prism,
            anchor='centroid',
            **kwargs
        )

    @classmethod
    def from_apex_angle(
        cls,
        scene: 'Scene',
        face_angle_deg: float,
        n_prism: float,
        measuring_surface_length: float,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0
    ) -> 'RefractometerPrism':
        """
        Create from an explicit face angle, bypassing the physics derivation.

        Use this when you already know the exact prism geometry (e.g., from
        a manufacturer datasheet or a prior design iteration).

        Args:
            scene: The scene this prism belongs to.
            face_angle_deg: Face angle in degrees (angle between measuring
                           surface and entrance/exit faces).
            n_prism: Refractive index of the prism material.
            measuring_surface_length: Length of the measuring surface.
            position: Reference point coordinates.
            rotation: Rotation angle in degrees.

        Returns:
            A new RefractometerPrism instance.
        """
        # Back-compute the n_sample_range this geometry corresponds to
        # theta_c_mid = 90 - face_angle
        # n_mid = n_prism * sin(theta_c_mid)
        theta_c_mid_deg = 90 - face_angle_deg
        theta_c_mid_rad = math.radians(theta_c_mid_deg)
        n_mid = n_prism * math.sin(theta_c_mid_rad)

        # Estimate a reasonable range around n_mid
        # Assume +/- 5 degrees of exit angle covers the range
        delta_n = n_prism * 0.1  # ~10% range
        n_min = max(1.0, n_mid - delta_n)
        n_max = min(n_prism - 0.01, n_mid + delta_n)

        # Create instance using primary constructor
        instance = cls(
            scene=scene,
            n_prism=n_prism,
            n_sample_range=(n_min, n_max),
            measuring_surface_length=measuring_surface_length,
            system_type='angular',
            position=position,
            rotation=rotation
        )

        # Override the computed face angle with the explicit one
        instance.face_angle = face_angle_deg

        # Rebuild path with new face angle
        instance.path = instance._compute_path()
        instance.auto_label_cardinal()

        return instance

    @classmethod
    def from_geometric_constraints(
        cls,
        scene: 'Scene',
        n_prism: float,
        n_sample_range: Tuple[float, float],
        source_distance: float,
        sensor_length: float,
        path_length: float,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0
    ) -> 'RefractometerPrism':
        """
        Create from physical system constraints (lensless architecture).

        Computes both face angle AND measuring surface length from the
        hardware geometry. Use this when you have specific source/sensor
        constraints and want the prism designed to match.

        Args:
            scene: The scene this prism belongs to.
            n_prism: Refractive index of the prism material.
            n_sample_range: Tuple of (n_min, n_max) for expected samples.
            source_distance: Distance from point source to measuring surface center.
            sensor_length: Physical length of the linear sensor array.
            path_length: Distance from prism exit face to sensor.
            position: Reference point coordinates.
            rotation: Rotation angle in degrees.

        Returns:
            A new RefractometerPrism instance.

        Raises:
            ValueError: If n_prism <= n_max (TIR impossible).
            ValueError: If source_distance <= 0 or path_length <= 0.
        """
        if source_distance <= 0:
            raise ValueError(f"source_distance must be > 0, got {source_distance}")
        if path_length <= 0:
            raise ValueError(f"path_length must be > 0, got {path_length}")

        n_min, n_max = n_sample_range

        # Compute critical angle range
        theta_c_min = tir_utils.critical_angle(n_min, n_prism)
        theta_c_max = tir_utils.critical_angle(n_max, n_prism)

        # The angular span that needs to be covered
        angular_span_deg = theta_c_max - theta_c_min
        angular_span_rad = math.radians(angular_span_deg)

        # Compute required measuring surface length
        # The source must illuminate the full angular range
        # Length = 2 * source_distance * tan(angular_span / 2)
        measuring_surface_length = 2 * source_distance * math.tan(angular_span_rad / 2)

        # Create instance using primary constructor
        instance = cls(
            scene=scene,
            n_prism=n_prism,
            n_sample_range=n_sample_range,
            measuring_surface_length=measuring_surface_length,
            system_type='geometric',
            position=position,
            rotation=rotation
        )

        # Store geometric system parameters
        instance.source_distance = source_distance
        instance.sensor_length = sensor_length
        instance.path_length = path_length

        return instance

    @classmethod
    def from_critical_ray_path(
        cls,
        scene: 'Scene',
        n_prism: float,
        n_target: float,
        ray_path_length: float,
        position: Tuple[float, float] = (0.0, 0.0),
        rotation: float = 0.0
    ) -> 'RefractometerPrism':
        """
        Create a prism whose geometry is fully determined by the critical
        angle for a target sample and the desired internal ray path length.

        The ray enters perpendicular to the entrance face at its midpoint,
        hits the measuring surface at the critical angle at its midpoint,
        reflects via TIR, and exits perpendicular to the exit face at its
        midpoint.

        Args:
            scene: The scene this prism belongs to.
            n_prism: Refractive index of the prism material.
            n_target: Refractive index of the target sample.
            ray_path_length: Total ray path length (L) inside the prism
                             (from entrance face midpoint to exit face midpoint
                             via measuring surface midpoint).
            position: Reference point coordinates.
            rotation: Rotation angle in degrees.

        Returns:
            A new RefractometerPrism instance.

        Raises:
            ValueError: If n_prism <= n_target (TIR impossible).
            ValueError: If theta_c <= 45 deg (geometry invalid).
        """
        dims = tir_utils.trapezoid_from_critical_ray_path(
            n_target, n_prism, ray_path_length
        )

        # Estimate a reasonable n_sample_range centered on n_target
        n_min = max(1.0, n_target - 0.10)
        n_max = min(n_prism - 0.01, n_target + 0.10)

        # Create instance via primary constructor (uses default _compute_path)
        instance = cls(
            scene=scene,
            n_prism=n_prism,
            n_sample_range=(n_min, n_max),
            measuring_surface_length=dims['M'],
            system_type='angular',
            position=position,
            rotation=rotation
        )

        # Override face angle with the one derived from critical ray path
        instance.face_angle = dims['face_angle_deg']

        # Rebuild vertex path with the correct height (the default
        # _compute_path uses an arbitrary H = M * 0.5)
        half_B = dims['B'] / 2
        half_M = dims['M'] / 2
        H = dims['h']
        vertices = [
            (-half_B, 0.0),   # V0: Base Left
            (half_B, 0.0),    # V1: Base Right
            (half_M, H),      # V2: Top Right
            (-half_M, H),     # V3: Top Left
        ]
        instance.path = instance._apply_rotation_and_translation(vertices)
        instance.auto_label_cardinal()

        # Store extra attributes for inspection
        instance.n_target = n_target
        instance.ray_path_length = ray_path_length

        return instance

    def _compute_path(self) -> List[Dict[str, Union[float, bool]]]:
        """
        Compute vertex path for symmetric trapezoid.

        The trapezoid has:
        - Base (bottom) of computed length
        - Top (measuring surface) of specified length
        - Symmetric slanted sides at face_angle

        Returns:
            List of vertex dictionaries with 'x', 'y', 'arc' keys.
        """
        M = self.measuring_surface_length
        alpha = math.radians(self.face_angle)

        # Height of trapezoid based on face angle and measuring surface
        # The slanted side makes angle alpha with the measuring surface
        # Choose a reasonable height based on measuring surface length
        H = M * 0.5  # Default height is half the measuring surface length

        # Base length: B = M + 2 * H * tan(alpha)
        # But we need to be careful with the geometry
        # For a symmetric trapezoid with face angle alpha:
        # - The slant makes angle alpha with the horizontal (measuring surface)
        # - Width increase from top to bottom: 2 * H / tan(alpha)
        B = M + 2 * H / math.tan(alpha) if alpha > 0.01 else M

        # Vertices (CCW, centered at origin before rotation/translation)
        # V0: Bottom left
        # V1: Bottom right
        # V2: Top right
        # V3: Top left
        half_B = B / 2
        half_M = M / 2

        vertices = [
            (-half_B, 0.0),      # V0: Base Left
            (half_B, 0.0),       # V1: Base Right
            (half_M, H),         # V2: Top Right
            (-half_M, H),        # V3: Top Left
        ]

        return self._apply_rotation_and_translation(vertices)

    # =========================================================================
    # Query Methods
    # =========================================================================

    def critical_angle_for(self, n_sample: float) -> float:
        """
        Return critical angle (degrees) for a given sample index.

        Args:
            n_sample: Refractive index of the sample.

        Returns:
            Critical angle in degrees.

        Raises:
            ValueError: If n_sample >= n_prism (no TIR).
        """
        return tir_utils.critical_angle(n_sample, self.n_prism)

    def exit_angle_for(self, n_sample: float) -> float:
        """
        Return the exit angle for a given sample's critical angle reflection.

        The exit angle is measured from normal to the exit face.
        Returns 0.0 when n_sample = n_mid (normal exit by design).

        Args:
            n_sample: Refractive index of the sample.

        Returns:
            Exit angle in degrees from normal.
        """
        return tir_utils.exit_angle_for_sample(
            n_sample, self.n_prism, self.face_angle
        )

    def sensor_position_for(self, n_sample: float) -> float:
        """
        Return the expected sensor position for a given sample index.

        Only valid for geometric (lensless) system type.

        Args:
            n_sample: Refractive index of the sample.

        Returns:
            Position on sensor (in length units).

        Raises:
            ValueError: If system_type != 'geometric' or path_length not set.
        """
        if self.system_type != 'geometric':
            raise ValueError(
                "sensor_position_for() only valid for system_type='geometric'"
            )
        if self.path_length is None:
            raise ValueError(
                "path_length not set. Use from_geometric_constraints() constructor."
            )

        return tir_utils.sensor_position_for_sample(
            n_sample, self.n_prism, self.face_angle, self.path_length
        )

    def validate_geometry(self) -> List[str]:
        """
        Return a list of warning messages if the geometry has issues.

        Checks for:
        - Exit angles too far from normal (ghost reflection risk)
        - (Geometric only) Sensor too small to capture full range

        Returns:
            List of warning strings (empty if geometry is valid).
        """
        return tir_utils.validate_refractometer_geometry(
            n_prism=self.n_prism,
            n_sample_range=self.n_sample_range,
            face_angle_deg=self.face_angle,
            measuring_surface_length=self.measuring_surface_length,
            source_distance=self.source_distance,
            sensor_length=self.sensor_length,
            path_length=self.path_length
        )

    # =========================================================================
    # Convenience Properties
    # =========================================================================

    @property
    def n_mid(self) -> float:
        """Return the mid-range sample refractive index."""
        return (self.n_sample_range[0] + self.n_sample_range[1]) / 2

    @property
    def base_length(self) -> float:
        """Return the base length of the trapezoid."""
        return self.get_edge_length(0)

    @property
    def theta_c_mid(self) -> float:
        """Return the critical angle at mid-range (degrees)."""
        return tir_utils.critical_angle(self.n_mid, self.n_prism)

    def get_measuring_surface_endpoints(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        Get the endpoints of the measuring surface (Edge 2).

        Returns:
            Tuple of ((x1, y1), (x2, y2)).
        """
        return self.get_edge_endpoints(2)
