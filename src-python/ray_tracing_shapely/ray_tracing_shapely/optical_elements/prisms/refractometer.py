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

    The sample sits on the measuring surface M, which is the WIDE edge:
    for a valid TIR design theta_c > 45 deg, so face_angle < 45 deg and
    the slanted faces lean inwards going from M down to the base B
    (M > B, as drawn above).

Angle conventions:
    face_angle (stored attribute, degrees):
        angle between the entrance/exit face and the NORMAL of the
        measuring surface. For the mid-range design,
        face_angle = 90 - theta_c_mid.
    meas2edge_angle (derived property, degrees):
        the interior polygon angle at V3 (equal to the one at V2, by
        symmetry), between the measuring surface and the entrance/exit
        face. meas2edge_angle = 90 - face_angle, so for the mid-range
        design it equals theta_c_mid.

    With b the inward overhang of each slanted face measured along M
    (V3 -> V0) and H the height:
        tan(face_angle) = b / H,   tan(meas2edge_angle) = H / b,
        B = M - 2 b.
    b < 0 (meas2edge_angle > 90 deg) gives a wide-base trapezoid,
    meas2edge_angle = 90 deg a rectangle.

Two system architectures:
    - 'angular': Abbe-like with focusing lens (measuring surface length is free)
    - 'geometric': Lensless direct imaging (length constrained by geometry)
===============================================================================
"""

from __future__ import annotations

import copy
import math
import uuid as uuid_module
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
            face_angle_deg: Face angle in degrees: angle between the
                           entrance/exit faces and the NORMAL of the
                           measuring surface (see "Angle conventions" in
                           the module docstring). Must be < 45 deg for the
                           default height, otherwise the base vanishes.
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
        Compute vertex path for the symmetric wide-top trapezoid.

        Used by the primary constructor, from_apex_angle and
        from_geometric_constraints; from_critical_ray_path replaces the
        path afterwards with its own height.

        The trapezoid has:
        - Top (measuring surface, edge 2) of length M
        - Default height H = M / 2
        - Slanted faces leaning by face_angle from the measuring surface's
          normal, so each face is inset by b = H * tan(face_angle) and
          the base is B = M - 2 b (wide top for face_angle > 0).

        The interior angle at V3/V2 is therefore 90 - face_angle (see
        meas2edge_angle). No small-angle guard is applied: tan() is well
        behaved near 0, and a guard would break that identity.

        Returns:
            List of vertex dictionaries with 'x', 'y', 'arc' keys.

        Raises:
            ValueError: If the base length is not strictly positive
                (face_angle >= 45 deg for the default H = M / 2). A
                degenerate or self-intersecting polygon would otherwise be
                traced silently.
        """
        M = self.measuring_surface_length
        alpha = math.radians(self.face_angle)

        H = M * 0.5  # Default height; from_critical_ray_path overrides the path

        b = H * math.tan(alpha)  # inward overhang of each slanted face
        B = M - 2 * b
        if B <= 0:
            raise ValueError(
                f"Degenerate RefractometerPrism: face_angle={self.face_angle:.4f} deg "
                f"gives base length {B:.6g} <= 0 for the default height H = M/2. "
                f"face_angle must be < 45 deg (a valid TIR design has "
                f"theta_c > 45 deg, i.e. face_angle < 45 deg)."
            )

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

    @property
    def meas2edge_angle(self) -> float:
        """
        Interior polygon angle at V3 (Top Left), in degrees.

        This is the angle between the measuring surface (edge 2) and the
        entrance face (edge 3); by the left-right symmetry it equals the
        angle at V2 between the measuring surface and the exit face.

        Angle conventions:
            face_angle (stored attribute): angle between the entrance/exit
                face and the NORMAL of the measuring surface. For the
                mid-range design face_angle = 90 - theta_c_mid.
            meas2edge_angle (this property): the interior angle between the
                measuring surface and the entrance/exit face.
                meas2edge_angle = 90 - face_angle, so for the mid-range
                design it equals theta_c_mid.

        Computed from the actual vertices of self.path, not read from
        face_angle, so it is correct for every constructor, any rotation,
        and after morphing.
        """
        return self.get_interior_angle(3)

    # =========================================================================
    # Morphing (re-shape an existing prism in place)
    # =========================================================================

    def _detached_copy(self) -> 'RefractometerPrism':
        """
        Return an independent copy of this prism that shares the scene.

        Design decision: copy.deepcopy(self) would also deep-copy the
        `scene` the prism references (and everything the scene holds).
        Instead the scene is pre-seeded in the deepcopy memo, so the copy
        keeps a reference to the SAME scene while path, labels and every
        other attribute are copied. The copy is not added to scene.objs
        (construction never registers an object; scene.add_object() does),
        and it gets a fresh uuid so lineage records cannot confuse the two.
        """
        memo: Dict[int, Any] = {}
        scene = getattr(self, 'scene', None)
        if scene is not None:
            memo[id(scene)] = scene
        clone = copy.deepcopy(self, memo)
        clone._uuid = str(uuid_module.uuid4())
        return clone

    def morphing_meas2edge_angle(
        self,
        new_angle_deg: float,
        *,
        inplace: bool = True
    ) -> 'RefractometerPrism':
        """
        Change the top-corner angle (meas2edge_angle) of an existing prism.

        The measuring surface (V2, V3: length, position, orientation) and
        the height are kept fixed; only the two base vertices V0, V1 move.
        Works from the stored vertices with vectors, so it is valid for a
        rotated prism. 90 deg gives a rectangle (B = M); smaller angles
        shrink the base (wide top); larger angles, up to 180, give B > M.

        State kept in sync:
            - face_angle = 90 - new_angle_deg
            - cardinal edge labels (auto_label_cardinal())
            - _position is moved to the new vertex mean, so that it stays
              the 'centroid' anchor of the stored path (moving V0, V1 moves
              the vertex mean). measuring_surface_length and size are
              unchanged because edge 2 is unchanged.

        Deliberately NOT touched: n_prism, n_sample_range, theta_c_range,
        system_type, measuring_surface_length, refIndex. The prism is
        re-shaped, not re-designed for another sample range; note that
        exit_angle_for() uses the new face_angle, so the mid-range sample
        no longer exits normally unless new_angle_deg == theta_c_mid.

        Args:
            new_angle_deg: The new interior angle at V3/V2, in degrees,
                in the open interval (0, 180).
            inplace: Keyword-only. True modifies and returns self; False
                returns a detached copy (see _detached_copy) and leaves
                this prism untouched.

        Returns:
            The morphed prism (self when inplace=True).

        Raises:
            ValueError: If new_angle_deg is not in (0, 180) exclusive.
            ValueError: If the new base length would not be strictly
                positive; the message gives the minimum valid angle,
                degrees(atan2(H, M/2)). Raised before anything changes.
        """
        if not (0.0 < new_angle_deg < 180.0):
            raise ValueError(
                f"new_angle_deg must be in (0, 180) exclusive, got {new_angle_deg}"
            )

        V0, V1, V2, V3 = [(v['x'], v['y']) for v in self.path[:4]]

        dx, dy = V2[0] - V3[0], V2[1] - V3[1]
        M = math.hypot(dx, dy)
        half_M = M / 2
        m_dir = (dx / M, dy / M)              # along the measuring surface, V3 -> V2
        m_perp = (m_dir[1], -m_dir[0])        # from edge 2 towards the base
        m_mid = ((V2[0] + V3[0]) / 2, (V2[1] + V3[1]) / 2)
        b_mid = ((V0[0] + V1[0]) / 2, (V0[1] + V1[1]) / 2)
        H = (b_mid[0] - m_mid[0]) * m_perp[0] + (b_mid[1] - m_mid[1]) * m_perp[1]

        b = H / math.tan(math.radians(new_angle_deg))   # negative above 90 deg
        half_B = half_M - b
        if 2 * half_B <= 0:
            min_angle = math.degrees(math.atan2(H, half_M))
            raise ValueError(
                f"new_angle_deg={new_angle_deg} gives a non-positive base length "
                f"({2 * half_B:.6g}); the minimum valid angle for this prism "
                f"(H={H:.6g}, M={M:.6g}) is ~{min_angle:.3f} deg"
            )

        target = self if inplace else self._detached_copy()

        target.path[0]['x'] = m_mid[0] - half_B * m_dir[0] + H * m_perp[0]
        target.path[0]['y'] = m_mid[1] - half_B * m_dir[1] + H * m_perp[1]
        target.path[1]['x'] = m_mid[0] + half_B * m_dir[0] + H * m_perp[0]
        target.path[1]['y'] = m_mid[1] + half_B * m_dir[1] + H * m_perp[1]

        target.face_angle = 90.0 - new_angle_deg
        target._position = target._get_centroid()
        target.auto_label_cardinal()
        return target

    def morphing_scale(
        self,
        *,
        scale: Optional[float] = None,
        target_measuring_surface_length: Optional[float] = None,
        inplace: bool = True
    ) -> 'RefractometerPrism':
        """
        Uniformly scale an existing prism about its vertex mean.

        Every vertex is scaled about _get_centroid() (the vertex mean, i.e.
        the 'centroid' anchor), so the prism stays where it was placed.
        All angles (face_angle, meas2edge_angle) are invariant.

        Updated by the factor: measuring_surface_length; size (BasePrism's
        characteristic size, which for this class is the measuring surface
        length); and every length attribute that is set:
        source_distance, sensor_length, path_length (lensless system) and
        ray_path_length (from_critical_ray_path). n_target and the other
        dimensionless physics attributes are unchanged. Edge labels are
        recomputed.

        Args:
            scale: Keyword-only. Percentage, > 0: 100 = unchanged,
                50 = half, 200 = double (slider semantics).
            target_measuring_surface_length: Keyword-only. Desired
                measuring surface length, > 0; the factor is derived as
                target / measuring_surface_length.
            inplace: Keyword-only. True modifies and returns self; False
                returns a detached copy (see _detached_copy) and leaves
                this prism untouched.

        Exactly one of scale and target_measuring_surface_length must be
        given.

        Returns:
            The scaled prism (self when inplace=True).

        Raises:
            ValueError: If neither or both of scale and
                target_measuring_surface_length are given, or the given one
                is not > 0.
        """
        if (scale is None) == (target_measuring_surface_length is None):
            raise ValueError(
                "exactly one of scale and target_measuring_surface_length "
                "must be given"
            )
        if target_measuring_surface_length is not None:
            if target_measuring_surface_length <= 0:
                raise ValueError(
                    f"target_measuring_surface_length must be > 0, "
                    f"got {target_measuring_surface_length}"
                )
            factor = target_measuring_surface_length / self.measuring_surface_length
        else:
            if scale <= 0:
                raise ValueError(f"scale must be > 0 (a percentage), got {scale}")
            factor = scale / 100.0

        target = self if inplace else self._detached_copy()

        cx, cy = target._get_centroid()
        for v in target.path:
            v['x'] = cx + (v['x'] - cx) * factor
            v['y'] = cy + (v['y'] - cy) * factor

        target.measuring_surface_length *= factor
        target.size *= factor
        for name in ('source_distance', 'sensor_length', 'path_length',
                     'ray_path_length'):
            value = getattr(target, name, None)
            if value is not None:
                setattr(target, name, value * factor)

        target.auto_label_cardinal()
        return target
