"""
Python-specific module: prisms package
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
PRISMS SUB-MODULE
===============================================================================
Prism types with physics-driven constructors and dual-labeling architecture.

Classes:
- BasePrism: Base class for all prisms (dual labeling, geometry from parameters)
- EquilateralPrism: 60-60-60 dispersing prism
- RightAnglePrism: 45-90-45 TIR prism
- RefractometerPrism: Symmetric trapezoid for critical-angle measurements
- DTIRCPrism: Dielectric TIR concentrator with a curved entrance aperture

Factory Functions:
- equilateral_prism(): Create an equilateral prism
- right_angle_prism(): Create a right-angle prism
- refractometer_prism(): Create a refractometer prism
- dtirc_prism(): Create a DTIRC prism

Utility Modules:
- prism_utils: Deviation, dispersion, and geometry calculations
- tir_utils: Critical angle and refractometer design utilities
- nonimaging_geometry: isl/rfr/coptpt general 2-D ray-geometry primitives
===============================================================================
"""

from typing import Tuple, TYPE_CHECKING

# Import classes
from .base_prism import BasePrism
from .equilateral import EquilateralPrism
from .right_angle import RightAnglePrism
from .refractometer import RefractometerPrism
from .dtirc import DTIRCPrism
from .angle_transformer import build_angle_transformer
from .rxi import RXIOptic
from .rr_lens import RRLens
from .rx_concentrator import RXConcentrator
from .rxi_direct import RXIOpticDirect

# Import utility modules
from . import prism_utils
from . import tir_utils
from . import nonimaging_geometry
from . import sms_chain

if TYPE_CHECKING:
    from ....core.scene import Scene


# ============================================================================
# Factory Functions
# ============================================================================

def equilateral_prism(
    scene: 'Scene',
    side_length: float,
    position: Tuple[float, float] = (0.0, 0.0),
    rotation: float = 0.0,
    n: float = 1.5,
    anchor: str = 'centroid'
) -> EquilateralPrism:
    """
    Create an equilateral (60-60-60) dispersing prism.

    Args:
        scene: The scene this prism belongs to.
        side_length: Length of each side.
        position: Reference point coordinates.
        rotation: Rotation angle in degrees.
        n: Refractive index.
        anchor: Position reference ('centroid' or 'apex').

    Returns:
        A new EquilateralPrism instance.
    """
    return EquilateralPrism(
        scene=scene,
        side_length=side_length,
        position=position,
        rotation=rotation,
        n=n,
        anchor=anchor
    )


def right_angle_prism(
    scene: 'Scene',
    leg_length: float,
    position: Tuple[float, float] = (0.0, 0.0),
    rotation: float = 0.0,
    n: float = 1.5,
    anchor: str = 'centroid'
) -> RightAnglePrism:
    """
    Create a 45-90-45 right-angle prism for TIR applications.

    Args:
        scene: The scene this prism belongs to.
        leg_length: Length of each leg (the two equal sides).
        position: Reference point coordinates.
        rotation: Rotation angle in degrees.
        n: Refractive index.
        anchor: Position reference ('centroid' or 'apex').

    Returns:
        A new RightAnglePrism instance.
    """
    return RightAnglePrism(
        scene=scene,
        leg_length=leg_length,
        position=position,
        rotation=rotation,
        n=n,
        anchor=anchor
    )


def refractometer_prism(
    scene: 'Scene',
    n_prism: float,
    n_sample_range: Tuple[float, float],
    measuring_surface_length: float,
    system_type: str = 'angular',
    position: Tuple[float, float] = (0.0, 0.0),
    rotation: float = 0.0
) -> RefractometerPrism:
    """
    Create a refractometer prism from physics parameters.

    The face angle is computed automatically from the sample refractive
    index range to ensure normal exit at mid-range.

    Args:
        scene: The scene this prism belongs to.
        n_prism: Refractive index of the prism material.
        n_sample_range: Tuple of (n_min, n_max) for the sample.
        measuring_surface_length: Length of the measuring surface.
        system_type: 'angular' (Abbe-like) or 'geometric' (lensless).
        position: Reference point coordinates.
        rotation: Rotation angle in degrees.

    Returns:
        A new RefractometerPrism instance.
    """
    return RefractometerPrism(
        scene=scene,
        n_prism=n_prism,
        n_sample_range=n_sample_range,
        measuring_surface_length=measuring_surface_length,
        system_type=system_type,
        position=position,
        rotation=rotation
    )


def dtirc_prism(
    scene: 'Scene',
    theta_deg: float,
    n: float,
    phi_edge_deg: float = 50.0,
    size: float = 1.0,
    wall_segments: int = 16,
    entrance_arc_segments: int = 8,
    position: Tuple[float, float] = (0.0, 0.0),
    rotation: float = 0.0
) -> DTIRCPrism:
    """
    Create a dielectric TIR concentrator (DTIRC) from physics parameters.

    Args:
        scene: The scene this prism belongs to.
        theta_deg: Half-acceptance angle in degrees.
        n: Refractive index of the prism material.
        phi_edge_deg: Entrance-aperture angular half-width in degrees.
        size: Scale factor (entrance aperture's radius of curvature).
        wall_segments: Number of straight segments per sidewall.
        entrance_arc_segments: Number of straight segments for the entrance.
        position: Reference point coordinates.
        rotation: Rotation angle in degrees.

    Returns:
        A new DTIRCPrism instance.
    """
    return DTIRCPrism(
        scene=scene,
        theta_deg=theta_deg,
        n=n,
        phi_edge_deg=phi_edge_deg,
        size=size,
        wall_segments=wall_segments,
        entrance_arc_segments=entrance_arc_segments,
        position=position,
        rotation=rotation
    )


def refractometer_prism_from_critical_ray_path(
    scene: 'Scene',
    n_prism: float,
    n_target: float,
    ray_path_length: float,
    position: Tuple[float, float] = (0.0, 0.0),
    rotation: float = 0.0
) -> RefractometerPrism:
    """
    Create a refractometer prism from critical ray path constraints.

    All prism dimensions are derived from the TIR critical angle
    (determined by n_prism and n_target) and the desired total ray
    path length inside the prism.

    Args:
        scene: The scene this prism belongs to.
        n_prism: Refractive index of the prism material.
        n_target: Refractive index of the target sample.
        ray_path_length: Total ray path length (L) inside the prism.
        position: Reference point coordinates.
        rotation: Rotation angle in degrees.

    Returns:
        A new RefractometerPrism instance.
    """
    return RefractometerPrism.from_critical_ray_path(
        scene=scene,
        n_prism=n_prism,
        n_target=n_target,
        ray_path_length=ray_path_length,
        position=position,
        rotation=rotation
    )


__all__ = [
    # Base class
    'BasePrism',
    # Prism classes
    'EquilateralPrism',
    'RightAnglePrism',
    'RefractometerPrism',
    'DTIRCPrism',
    'RXIOptic',
    'RRLens',
    'RXConcentrator',
    'RXIOpticDirect',
    # Factory functions
    'equilateral_prism',
    'right_angle_prism',
    'refractometer_prism',
    'refractometer_prism_from_critical_ray_path',
    'dtirc_prism',
    'build_angle_transformer',
    # Utility modules
    'prism_utils',
    'tir_utils',
    'nonimaging_geometry',
    'sms_chain',
]
