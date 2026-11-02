"""
Python-specific module: prism utils
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
PRISM UTILITIES
===============================================================================
Standalone functions for prism calculations:
- Minimum deviation angle
- Refractive index from deviation measurement
- Deviation at arbitrary incidence
- Angular dispersion
- Resolving power
- Wavelength-aware versions using Cauchy dispersion

These utilities let designers calculate expected optical properties
without running a full simulation.
===============================================================================
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple


# =============================================================================
# Basic Deviation Functions
# =============================================================================

def minimum_deviation(apex_angle_deg: float, n: float) -> float:
    """
    Minimum deviation angle (degrees) for a prism.

    At minimum deviation, the ray passes symmetrically through the prism
    (angle of incidence equals angle of emergence).

    Formula: D_min = 2 * arcsin(n * sin(A/2)) - A

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        n: Refractive index of the prism material.

    Returns:
        Minimum deviation angle in degrees.

    Raises:
        ValueError: If the calculation is impossible (n * sin(A/2) > 1).

    Example:
        >>> minimum_deviation(60.0, 1.5)  # Equilateral prism, n=1.5
        37.18...  # degrees
    """
    A = math.radians(apex_angle_deg)
    sin_half_A = math.sin(A / 2)
    arg = n * sin_half_A

    if arg > 1.0:
        raise ValueError(
            f"Minimum deviation impossible: n * sin(A/2) = {arg:.4f} > 1. "
            f"Try a smaller apex angle or lower refractive index."
        )

    D_min = 2 * math.asin(arg) - A
    return math.degrees(D_min)


def refractive_index_from_deviation(
    apex_angle_deg: float,
    d_min_deg: float
) -> float:
    """
    Compute refractive index from measured minimum deviation.

    This is the inverse of minimum_deviation() and is useful for
    determining material properties from experimental measurements.

    Formula: n = sin((D_min + A) / 2) / sin(A / 2)

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        d_min_deg: Measured minimum deviation angle in degrees.

    Returns:
        Refractive index of the prism material.

    Example:
        >>> refractive_index_from_deviation(60.0, 37.2)
        1.500...
    """
    A = math.radians(apex_angle_deg)
    D_min = math.radians(d_min_deg)

    n = math.sin((D_min + A) / 2) / math.sin(A / 2)
    return n


def deviation_at_incidence(
    apex_angle_deg: float,
    n: float,
    theta_i_deg: float
) -> float:
    """
    Total deviation for arbitrary incidence angle.

    Applies Snell's law at both surfaces sequentially to compute
    the total angular deviation of a ray passing through the prism.

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        n: Refractive index of the prism material.
        theta_i_deg: Angle of incidence in degrees (from surface normal).

    Returns:
        Total deviation angle in degrees.
        Returns float('nan') if TIR occurs inside the prism.

    Example:
        >>> deviation_at_incidence(60.0, 1.5, 48.59)  # Near minimum deviation
        37.18...
    """
    A = math.radians(apex_angle_deg)
    theta_i = math.radians(theta_i_deg)

    # First surface: air to glass
    sin_theta_i = math.sin(theta_i)
    sin_r1 = sin_theta_i / n

    if abs(sin_r1) > 1.0:
        # Should not happen for reasonable incidence angles
        return float('nan')

    r1 = math.asin(sin_r1)

    # Internal angle at second surface
    r2 = A - r1

    # Check for TIR at second surface
    sin_theta_t = n * math.sin(r2)
    if abs(sin_theta_t) > 1.0:
        # Total internal reflection inside prism
        return float('nan')

    theta_t = math.asin(sin_theta_t)

    # Total deviation: d1 + d2
    # d1 = theta_i - r1 (deviation at first surface)
    # d2 = theta_t - r2 (deviation at second surface)
    # Total = (theta_i - r1) + (theta_t - r2) = theta_i + theta_t - A
    deviation = theta_i + theta_t - A

    return math.degrees(deviation)


def angular_dispersion(
    apex_angle_deg: float,
    n: float,
    dn_dlambda: float
) -> float:
    """
    Angular dispersion dD/dlambda at minimum deviation.

    This measures how much the deviation angle changes per unit
    change in wavelength, which determines the spectral separation
    capability of the prism.

    Formula: dD/dlambda = (2 * sin(A/2)) / sqrt(1 - n^2 * sin^2(A/2)) * dn/dlambda

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        n: Refractive index at the wavelength of interest.
        dn_dlambda: Rate of change of refractive index with wavelength
                    (typically negative, in units of 1/nm or 1/um).

    Returns:
        Angular dispersion in degrees per unit wavelength.

    Example:
        >>> angular_dispersion(60.0, 1.5, -0.00005)  # Typical glass
        -0.0067...  # degrees per nm
    """
    A = math.radians(apex_angle_deg)
    sin_half_A = math.sin(A / 2)

    denominator_sq = 1 - n * n * sin_half_A * sin_half_A
    if denominator_sq <= 0:
        raise ValueError(
            f"Angular dispersion undefined: n * sin(A/2) >= 1"
        )

    dispersion_rad = (2 * sin_half_A) / math.sqrt(denominator_sq) * dn_dlambda
    return math.degrees(dispersion_rad)


def resolving_power(base_length: float, dn_dlambda: float) -> float:
    """
    Spectral resolving power of a prism.

    The resolving power R = lambda / delta_lambda determines the
    smallest wavelength difference that can be resolved.

    Formula: R = b * |dn/dlambda|

    where b is the prism base length (the path length through
    the prism at the base).

    Args:
        base_length: Base length of the prism in the same units as
                     the wavelength used for dn_dlambda.
        dn_dlambda: Absolute value of the rate of change of refractive
                    index with wavelength (in 1/length units).

    Returns:
        Resolving power (dimensionless).

    Example:
        >>> resolving_power(50.0, 0.00005)  # 50mm base, dn/dlambda in 1/nm
        2500  # Can resolve wavelengths differing by 1/2500 of the wavelength
    """
    return base_length * abs(dn_dlambda)


# =============================================================================
# Cauchy Dispersion Model
# =============================================================================

def n_cauchy(wavelength_nm: float, A: float, B: float) -> float:
    """
    Refractive index from Cauchy's equation.

    The Cauchy equation models wavelength-dependent refractive index:
    n(lambda) = A + B / lambda^2

    where lambda is in micrometers.

    Args:
        wavelength_nm: Wavelength in nanometers.
        A: Cauchy coefficient A (dimensionless, typically ~1.5).
        B: Cauchy coefficient B (in um^2, typically ~0.004).

    Returns:
        Refractive index at the given wavelength.

    Example:
        >>> n_cauchy(589.0, 1.5046, 0.00420)  # BK7 glass at sodium D line
        1.5168...
    """
    wavelength_um = wavelength_nm / 1000.0
    return A + B / (wavelength_um ** 2)


def dn_dlambda_cauchy(wavelength_nm: float, B: float) -> float:
    """
    Derivative of refractive index with respect to wavelength (Cauchy model).

    Formula: dn/dlambda = -2B / lambda^3

    Args:
        wavelength_nm: Wavelength in nanometers.
        B: Cauchy coefficient B (in um^2).

    Returns:
        dn/dlambda in units of 1/nm.

    Note:
        The result is always negative (n decreases with increasing wavelength).
    """
    wavelength_um = wavelength_nm / 1000.0
    # dn/d(lambda_um) = -2B / lambda_um^3
    # Convert to dn/d(lambda_nm) by dividing by 1000
    return -2 * B / (wavelength_um ** 3) / 1000.0


# =============================================================================
# Wavelength-Aware Deviation Functions
# =============================================================================

def minimum_deviation_wavelength(
    apex_angle_deg: float,
    A: float,
    B: float,
    wavelength_nm: float
) -> float:
    """
    Minimum deviation angle at a specific wavelength.

    Uses Cauchy dispersion model for refractive index.

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        A: Cauchy coefficient A.
        B: Cauchy coefficient B (in um^2).
        wavelength_nm: Wavelength in nanometers.

    Returns:
        Minimum deviation angle in degrees.

    Example:
        >>> minimum_deviation_wavelength(60.0, 1.5046, 0.0042, 400)  # Blue
        39.1...
        >>> minimum_deviation_wavelength(60.0, 1.5046, 0.0042, 700)  # Red
        36.8...
    """
    n = n_cauchy(wavelength_nm, A, B)
    return minimum_deviation(apex_angle_deg, n)


def deviation_at_incidence_wavelength(
    apex_angle_deg: float,
    A: float,
    B: float,
    wavelength_nm: float,
    theta_i_deg: float
) -> float:
    """
    Total deviation at arbitrary incidence angle for a specific wavelength.

    Uses Cauchy dispersion model for refractive index.

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        A: Cauchy coefficient A.
        B: Cauchy coefficient B (in um^2).
        wavelength_nm: Wavelength in nanometers.
        theta_i_deg: Angle of incidence in degrees.

    Returns:
        Total deviation angle in degrees.
        Returns float('nan') if TIR occurs inside the prism.
    """
    n = n_cauchy(wavelength_nm, A, B)
    return deviation_at_incidence(apex_angle_deg, n, theta_i_deg)


def dispersion_spectrum(
    apex_angle_deg: float,
    A: float,
    B: float,
    wavelengths_nm: List[float],
    theta_i_deg: Optional[float] = None
) -> List[Tuple[float, float]]:
    """
    Compute deviation angles across a spectrum of wavelengths.

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        A: Cauchy coefficient A.
        B: Cauchy coefficient B (in um^2).
        wavelengths_nm: List of wavelengths to compute (in nm).
        theta_i_deg: Incidence angle in degrees. If None, uses minimum
                     deviation for each wavelength.

    Returns:
        List of (wavelength_nm, deviation_deg) tuples.

    Example:
        >>> wavelengths = [400, 450, 500, 550, 600, 650, 700]
        >>> spectrum = dispersion_spectrum(60.0, 1.5046, 0.0042, wavelengths)
        >>> for wl, dev in spectrum:
        ...     print(f"{wl} nm: {dev:.2f} deg")
    """
    results = []
    for wl in wavelengths_nm:
        if theta_i_deg is None:
            dev = minimum_deviation_wavelength(apex_angle_deg, A, B, wl)
        else:
            dev = deviation_at_incidence_wavelength(
                apex_angle_deg, A, B, wl, theta_i_deg
            )
        results.append((wl, dev))
    return results


def visible_spectrum_deviations(
    apex_angle_deg: float,
    A: float,
    B: float,
    theta_i_deg: Optional[float] = None,
    num_points: int = 7
) -> List[Tuple[float, float]]:
    """
    Compute deviation angles across the visible spectrum.

    Convenience function that covers 400-700 nm.

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        A: Cauchy coefficient A.
        B: Cauchy coefficient B (in um^2).
        theta_i_deg: Incidence angle (None = minimum deviation).
        num_points: Number of wavelength samples.

    Returns:
        List of (wavelength_nm, deviation_deg) tuples.
    """
    wavelengths = [
        400 + i * 300 / (num_points - 1)
        for i in range(num_points)
    ]
    return dispersion_spectrum(apex_angle_deg, A, B, wavelengths, theta_i_deg)


# =============================================================================
# Incidence Angle for Minimum Deviation
# =============================================================================

def incidence_for_minimum_deviation(apex_angle_deg: float, n: float) -> float:
    """
    Calculate the incidence angle that produces minimum deviation.

    At minimum deviation, the ray passes symmetrically through the prism,
    and the incidence angle equals the emergence angle.

    Formula: theta_i = (A + D_min) / 2

    where A is the apex angle and D_min is the minimum deviation.

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        n: Refractive index of the prism material.

    Returns:
        Incidence angle in degrees that produces minimum deviation.

    Example:
        >>> incidence_for_minimum_deviation(60.0, 1.5)
        48.59...  # degrees
    """
    D_min = minimum_deviation(apex_angle_deg, n)
    return (apex_angle_deg + D_min) / 2


def incidence_for_minimum_deviation_wavelength(
    apex_angle_deg: float,
    A: float,
    B: float,
    wavelength_nm: float
) -> float:
    """
    Calculate the incidence angle for minimum deviation at a specific wavelength.

    Args:
        apex_angle_deg: Prism apex angle in degrees.
        A: Cauchy coefficient A.
        B: Cauchy coefficient B (in um^2).
        wavelength_nm: Wavelength in nanometers.

    Returns:
        Incidence angle in degrees.
    """
    n = n_cauchy(wavelength_nm, A, B)
    return incidence_for_minimum_deviation(apex_angle_deg, n)
