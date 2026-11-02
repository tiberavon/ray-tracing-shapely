"""
Python-specific module: tir utils
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
TIR (Total Internal Reflection) UTILITIES
===============================================================================
Design utilities for refractometer prisms and TIR-based optical systems.

These functions help design prisms for refractometer applications by
computing optimal angles and measurement ranges from physical parameters.

The existing analysis/fresnel_utils.py provides ANALYSIS utilities
(computing reflection/transmission for given angles). This module provides
DESIGN utilities (computing prism angles from measurement requirements).
===============================================================================
"""

from __future__ import annotations

import math
from typing import List, Tuple

# Import existing critical_angle from fresnel_utils for consistency
from ...analysis.fresnel_utils import critical_angle as _critical_angle_deg


def critical_angle(n_sample: float, n_prism: float) -> float:
    """
    Calculate critical angle in degrees for TIR at prism-sample interface.

    TIR occurs when light travels from the prism (denser) to the sample
    (rarer) at angles exceeding this value.

    Args:
        n_sample: Refractive index of the sample.
        n_prism: Refractive index of the prism (must be > n_sample).

    Returns:
        Critical angle in degrees.

    Raises:
        ValueError: If n_prism <= n_sample (TIR impossible).

    Example:
        >>> critical_angle(1.333, 1.72)  # Water on high-index prism
        50.8...  # degrees
    """
    if n_prism <= n_sample:
        raise ValueError(
            f"TIR impossible: n_prism ({n_prism}) must be > n_sample ({n_sample})"
        )
    return _critical_angle_deg(n_prism, n_sample)


def critical_angle_rad(n_sample: float, n_prism: float) -> float:
    """
    Calculate critical angle in radians.

    Args:
        n_sample: Refractive index of the sample.
        n_prism: Refractive index of the prism.

    Returns:
        Critical angle in radians.
    """
    return math.radians(critical_angle(n_sample, n_prism))


def prism_face_angle_for_normal_exit(
    n_sample_range: Tuple[float, float],
    n_prism: float
) -> float:
    """
    Calculate prism face angle for normal exit at mid-range.

    The face angle is chosen so that light reflected at the critical
    angle for the CENTER of the measurement range exits perpendicular
    to the exit face. This minimizes ghost reflections and simplifies
    the optical path.

    Formula:
        theta_c_mid = arcsin(n_mid / n_prism)
        face_angle = 90 - theta_c_mid

    Args:
        n_sample_range: Tuple of (n_min, n_max) for expected samples.
        n_prism: Refractive index of the prism material.

    Returns:
        Face angle in degrees (angle between measuring surface and
        entrance/exit faces).

    Raises:
        ValueError: If n_prism <= n_max (TIR impossible for entire range).

    Example:
        >>> prism_face_angle_for_normal_exit((1.30, 1.50), 1.72)
        35.4...  # degrees
    """
    n_min, n_max = n_sample_range

    if n_prism <= n_max:
        raise ValueError(
            f"TIR impossible: n_prism ({n_prism}) must be > n_max ({n_max})"
        )

    # Mid-range refractive index
    n_mid = (n_min + n_max) / 2

    # Critical angle at mid-range
    theta_c_mid = math.asin(n_mid / n_prism)

    # Face angle for normal exit
    face_angle = 90 - math.degrees(theta_c_mid)

    return face_angle


def prism_angle_for_refractometer(
    n_sample_range: Tuple[float, float],
    n_prism: float,
    margin_deg: float = 5.0
) -> float:
    """
    Calculate optimal prism angle for a given measurement range.

    This is an alternative formulation that adds a margin to ensure
    TIR occurs across the full measurement range.

    Args:
        n_sample_range: Tuple of (n_min, n_max) for expected samples.
        n_prism: Refractive index of the prism material.
        margin_deg: Safety margin in degrees.

    Returns:
        Recommended prism face angle in degrees.

    Example:
        >>> prism_angle_for_refractometer((1.30, 1.50), 1.72, margin_deg=5.0)
        40.4...  # degrees
    """
    theta_c_max = critical_angle(n_sample_range[1], n_prism)
    return 90 - theta_c_max + margin_deg


def critical_angle_range(
    n_sample_range: Tuple[float, float],
    n_prism: float
) -> Tuple[float, float]:
    """
    Calculate the range of critical angles for a measurement range.

    Args:
        n_sample_range: Tuple of (n_min, n_max) for expected samples.
        n_prism: Refractive index of the prism material.

    Returns:
        Tuple of (theta_c_min, theta_c_max) in degrees.

    Example:
        >>> critical_angle_range((1.30, 1.50), 1.72)
        (49.1, 60.7)  # degrees
    """
    n_min, n_max = n_sample_range
    theta_c_min = critical_angle(n_min, n_prism)
    theta_c_max = critical_angle(n_max, n_prism)
    return (theta_c_min, theta_c_max)


def measurement_range_from_prism(
    face_angle_deg: float,
    n_prism: float,
    exit_angle_range_deg: Tuple[float, float] = (-10.0, 10.0)
) -> Tuple[float, float]:
    """
    Calculate measurable n_sample range for a given prism geometry.

    Given a prism with known face angle, calculate what sample refractive
    indices can be measured within a specified exit angle range.

    Args:
        face_angle_deg: Prism face angle in degrees.
        n_prism: Refractive index of the prism material.
        exit_angle_range_deg: Acceptable exit angle range from normal
                              (default: -10 to +10 degrees).

    Returns:
        Tuple of (n_min, n_max) that can be measured.

    Example:
        >>> measurement_range_from_prism(35.0, 1.72, (-10.0, 10.0))
        (1.28, 1.52)  # approximately
    """
    # Critical angle at mid-range corresponds to normal exit
    # face_angle = 90 - theta_c_mid
    # theta_c_mid = 90 - face_angle
    theta_c_mid = 90 - face_angle_deg

    # Exit angle range maps to critical angle range
    # exit_angle = critical_angle - theta_c_mid (approximately for small angles)
    theta_c_min = theta_c_mid + exit_angle_range_deg[0]
    theta_c_max = theta_c_mid + exit_angle_range_deg[1]

    # Convert critical angles to sample indices
    # n_sample = n_prism * sin(theta_c)
    n_min = n_prism * math.sin(math.radians(theta_c_min))
    n_max = n_prism * math.sin(math.radians(theta_c_max))

    return (n_min, n_max)


def exit_angle_for_sample(
    n_sample: float,
    n_prism: float,
    face_angle_deg: float
) -> float:
    """
    Calculate exit angle for a given sample refractive index.

    The exit angle is measured from the normal to the exit face.
    A value of 0 means the light exits perpendicular to the face.

    Args:
        n_sample: Refractive index of the sample.
        n_prism: Refractive index of the prism.
        face_angle_deg: Prism face angle in degrees.

    Returns:
        Exit angle in degrees from normal.
        Positive values indicate deviation toward the apex.

    Raises:
        ValueError: If n_sample >= n_prism (no TIR).
    """
    if n_sample >= n_prism:
        raise ValueError(
            f"TIR impossible: n_sample ({n_sample}) must be < n_prism ({n_prism})"
        )

    # Critical angle for this sample
    theta_c = math.asin(n_sample / n_prism)

    # The beam reflects at theta_c and propagates inside the prism
    # It hits the exit face at an angle relative to the normal
    # For normal exit design: face_angle = 90 - theta_c_mid
    theta_c_mid = 90 - face_angle_deg
    theta_c_mid_rad = math.radians(theta_c_mid)

    # Exit angle = theta_c - theta_c_mid (small angle approximation)
    exit_angle = math.degrees(theta_c) - theta_c_mid

    return exit_angle


def sensor_position_for_sample(
    n_sample: float,
    n_prism: float,
    face_angle_deg: float,
    path_length: float,
    center_offset: float = 0.0
) -> float:
    """
    Calculate sensor position for a given sample (geometric system).

    For lensless (geometric) refractometer systems, the sensor position
    corresponds to the exit angle multiplied by the path length.

    Args:
        n_sample: Refractive index of the sample.
        n_prism: Refractive index of the prism.
        face_angle_deg: Prism face angle in degrees.
        path_length: Distance from prism exit face to sensor.
        center_offset: Sensor center position (default: 0).

    Returns:
        Position on sensor (in same units as path_length).
    """
    exit_angle = exit_angle_for_sample(n_sample, n_prism, face_angle_deg)
    exit_angle_rad = math.radians(exit_angle)

    # Position = path_length * tan(exit_angle)
    position = path_length * math.tan(exit_angle_rad)

    return center_offset + position


def trapezoid_from_critical_ray_path(
    n_target: float,
    n_prism: float,
    ray_path_length: float
) -> dict:
    """
    Compute symmetric trapezoid dimensions from TIR critical angle
    and total internal ray path length.

    The prism is designed so that a ray entering perpendicular to the
    entrance face at its midpoint hits the measuring surface at the
    critical angle at its midpoint, reflects via TIR, and exits
    perpendicular to the exit face at its midpoint.

    Args:
        n_target: Refractive index of the target sample.
        n_prism: Refractive index of the prism (must be > n_target).
        ray_path_length: Total ray path length (L) inside the prism,
                         from entrance face midpoint to exit face midpoint
                         via measuring surface midpoint.

    Returns:
        Dict with keys:
            'theta_c_deg': Critical angle in degrees.
            'h': Height of the prism.
            'E': Length of the entrance/exit face.
            'M': Length of the measuring surface.
            'B': Length of the base.
            'b': Horizontal overhang of each slanted edge.
            'face_angle_deg': Face angle (90 - theta_c) in degrees.

    Raises:
        ValueError: If n_prism <= n_target (TIR impossible).
        ValueError: If theta_c <= 45 deg (base length would be non-positive).
    """
    if n_prism <= n_target:
        raise ValueError(
            f"TIR impossible: n_prism ({n_prism}) must be > n_target ({n_target})"
        )

    theta_c_rad = math.asin(n_target / n_prism)
    theta_c_deg = math.degrees(theta_c_rad)

    if theta_c_deg <= 45.0:
        raise ValueError(
            f"Critical angle ({theta_c_deg:.2f} deg) must be > 45 deg "
            f"for a valid trapezoid. Increase n_target/n_prism ratio."
        )

    L = ray_path_length
    cos_tc = math.cos(theta_c_rad)
    sin_tc = math.sin(theta_c_rad)

    h = L * cos_tc
    E = L * cos_tc / sin_tc
    M = L / sin_tc
    b = math.sqrt(E ** 2 - h ** 2)
    B = M - 2 * b
    face_angle_deg = 90.0 - theta_c_deg

    return {
        'theta_c_deg': theta_c_deg,
        'h': h,
        'E': E,
        'M': M,
        'B': B,
        'b': b,
        'face_angle_deg': face_angle_deg,
    }


def validate_refractometer_geometry(
    n_prism: float,
    n_sample_range: Tuple[float, float],
    face_angle_deg: float,
    measuring_surface_length: float,
    source_distance: Optional[float] = None,
    sensor_length: Optional[float] = None,
    path_length: Optional[float] = None
) -> List[str]:
    """
    Validate refractometer prism geometry and return warnings.

    Checks for:
    - TIR possible across full range
    - Exit angles within reasonable bounds
    - (For geometric systems) Sensor coverage adequate

    Args:
        n_prism: Refractive index of the prism.
        n_sample_range: Tuple of (n_min, n_max) for samples.
        face_angle_deg: Prism face angle in degrees.
        measuring_surface_length: Length of measuring surface.
        source_distance: (Geometric only) Distance from source to prism.
        sensor_length: (Geometric only) Sensor array length.
        path_length: (Geometric only) Distance from prism to sensor.

    Returns:
        List of warning messages (empty if geometry is valid).
    """
    warnings: List[str] = []
    n_min, n_max = n_sample_range

    # Check TIR possible
    if n_prism <= n_max:
        warnings.append(
            f"TIR impossible: n_prism ({n_prism}) must be > n_max ({n_max})"
        )
        return warnings  # Can't check further

    # Check critical angle range
    theta_c_min = critical_angle(n_min, n_prism)
    theta_c_max = critical_angle(n_max, n_prism)

    # Check exit angles
    exit_min = exit_angle_for_sample(n_min, n_prism, face_angle_deg)
    exit_max = exit_angle_for_sample(n_max, n_prism, face_angle_deg)

    if abs(exit_min) > 15 or abs(exit_max) > 15:
        warnings.append(
            f"Exit angles exceed 15 deg: [{exit_min:.1f}, {exit_max:.1f}]. "
            f"Consider adjusting face angle for reduced ghost reflections."
        )

    # Geometric system checks
    if source_distance is not None and path_length is not None:
        # Check angular range coverage
        angular_span = theta_c_max - theta_c_min
        if angular_span < 5:
            warnings.append(
                f"Small angular range ({angular_span:.1f} deg). "
                f"Consider expanding n_sample_range for better resolution."
            )

        # Check sensor coverage
        if sensor_length is not None:
            pos_min = sensor_position_for_sample(n_min, n_prism, face_angle_deg, path_length)
            pos_max = sensor_position_for_sample(n_max, n_prism, face_angle_deg, path_length)
            required_length = abs(pos_max - pos_min)

            if required_length > sensor_length:
                warnings.append(
                    f"Sensor too small: need {required_length:.2f}, "
                    f"have {sensor_length:.2f}. Range will be clipped."
                )

    return warnings


# Import Optional for type hints
from typing import Optional
