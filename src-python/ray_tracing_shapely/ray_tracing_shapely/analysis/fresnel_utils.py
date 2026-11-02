"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Fresnel Equation Utilities
===============================================================================
Standalone functions that solve the Fresnel equations to compute expected
transmittances, reflectances, polarization ratios, and critical angles.

The physics is already implemented inside BaseGlass.refract() but is not
callable standalone.  These utilities let a designer or agent ask
"what should I expect?" without running a simulation.

All functions return values; no print() side effects.
===============================================================================
"""

from __future__ import annotations
import math
from typing import Any, Dict, Optional


def fresnel_transmittances(
    n1: float, n2: float, theta_i_deg: float
) -> Dict[str, float]:
    """
    Compute Fresnel power transmittances and reflectances at an interface.

    Uses the standard Fresnel equations for a planar interface between
    two dielectric media.

    Args:
        n1: Refractive index of the incident medium.
        n2: Refractive index of the transmitting medium.
        theta_i_deg: Angle of incidence in degrees (from normal).

    Returns:
        Dict with keys:
        - 'T_s': s-polarization power transmittance
        - 'T_p': p-polarization power transmittance
        - 'R_s': s-polarization power reflectance
        - 'R_p': p-polarization power reflectance
        - 'ratio_Tp_Ts': T_p / T_s (or float('inf') if T_s ~ 0)
        - 'theta_t_deg': refraction angle in degrees

    Raises:
        ValueError: If the angle exceeds the critical angle (TIR).
    """
    theta_i = math.radians(theta_i_deg)
    cos_i = math.cos(theta_i)
    sin_i = math.sin(theta_i)

    # Snell's law: n1 * sin(theta_i) = n2 * sin(theta_t)
    sin_t = (n1 / n2) * sin_i
    if abs(sin_t) > 1.0:
        raise ValueError(
            f"Total internal reflection: angle {theta_i_deg:.2f}° exceeds "
            f"critical angle {critical_angle(n1, n2):.2f}° for n1={n1}, n2={n2}."
        )

    cos_t = math.sqrt(1.0 - sin_t * sin_t)
    theta_t_deg = math.degrees(math.asin(sin_t))

    # Fresnel reflection coefficients (intensity)
    R_s = ((n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)) ** 2
    R_p = ((n2 * cos_i - n1 * cos_t) / (n2 * cos_i + n1 * cos_t)) ** 2

    T_s = 1.0 - R_s
    T_p = 1.0 - R_p

    if T_s > 1e-10:
        ratio = T_p / T_s
    else:
        ratio = float('inf')

    return {
        'T_s': T_s,
        'T_p': T_p,
        'R_s': R_s,
        'R_p': R_p,
        'ratio_Tp_Ts': ratio,
        'theta_t_deg': theta_t_deg,
    }


def critical_angle(n1: float, n2: float) -> float:
    """
    Compute the critical angle for total internal reflection.

    TIR occurs when light travels from a denser to a rarer medium
    (n1 > n2) at an angle exceeding this value.

    Args:
        n1: Refractive index of the denser medium (must be > n2).
        n2: Refractive index of the rarer medium.

    Returns:
        Critical angle in degrees.

    Raises:
        ValueError: If n1 <= n2 (no TIR possible).
    """
    if n1 <= n2:
        raise ValueError(
            f"No TIR possible: n1={n1} must be greater than n2={n2}."
        )
    return math.degrees(math.asin(n2 / n1))


def brewster_angle(n1: float, n2: float) -> float:
    """
    Compute Brewster's angle (where R_p = 0).

    At Brewster's angle, reflected light is fully s-polarized.
    This angle exists for any pair of dielectric media.

    Args:
        n1: Refractive index of the incident medium.
        n2: Refractive index of the transmitting medium.

    Returns:
        Brewster's angle in degrees.
    """
    return math.degrees(math.atan(n2 / n1))


def tir_analysis(
    n1: float,
    n2: float,
    theta_i_deg: Optional[float] = None,
    delta_angle_deg: float = 1.0,
) -> Dict[str, Any]:
    """
    Compute TIR critical angle, Brewster angle, Fresnel quantities, and
    phase shifts for light travelling from a denser to a rarer medium.

    Covers both the sub-critical (refraction) and super-critical (TIR)
    regimes in a single call.

    Args:
        n1: Refractive index of the denser (incident) medium.  Must be > n2.
        n2: Refractive index of the rarer (transmitting) medium.
        theta_i_deg: Angle of incidence in degrees (from normal).
            If None, defaults to ``critical_angle + delta_angle_deg``.
        delta_angle_deg: Proximity threshold in degrees for the near-TIR
            and near-Brewster flags.  Also used as the offset from TIR
            when *theta_i_deg* is not provided.  Default 1.0.

    Returns:
        Dict with keys documented in the output-schema section of the
        TIR roadmap.  Highlights:

        - ``regime``: ``"refraction"`` or ``"tir"``
        - ``near_tir`` / ``near_brewster``: proximity flags
        - ``angle_provided``: whether the caller supplied an angle
        - ``T_s``, ``T_p``, ``R_s``, ``R_p``, ``ratio_Tp_Ts``,
          ``theta_t_deg``: Fresnel power quantities (``None`` in TIR)
        - ``delta_s_deg``, ``delta_p_deg``, ``delta_relative_deg``:
          phase shifts on reflection in degrees

    Raises:
        ValueError: If n1 <= n2 (no TIR possible).
    """
    if n1 <= n2:
        raise ValueError(
            f"No TIR possible: n1={n1} must be greater than n2={n2}."
        )

    tir_deg = critical_angle(n1, n2)
    brew_deg = brewster_angle(n1, n2)

    angle_provided = theta_i_deg is not None
    if not angle_provided:
        theta_i_deg = tir_deg + delta_angle_deg

    theta_i = math.radians(theta_i_deg)
    cos_i = math.cos(theta_i)
    sin_i = math.sin(theta_i)

    near_tir = abs(theta_i_deg - tir_deg) <= delta_angle_deg
    near_brewster = abs(theta_i_deg - brew_deg) <= delta_angle_deg

    # Relative refractive index (used in TIR phase-shift formulas)
    n_rel = n1 / n2

    sin_t = n_rel * sin_i

    if abs(sin_t) <= 1.0:
        # ----- Sub-critical (refraction) regime -----
        cos_t = math.sqrt(1.0 - sin_t * sin_t)
        theta_t_deg = math.degrees(math.asin(max(-1.0, min(1.0, sin_t))))

        # Fresnel amplitude reflection coefficients
        r_s = (n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)
        r_p = (n2 * cos_i - n1 * cos_t) / (n2 * cos_i + n1 * cos_t)

        # Power reflectances / transmittances
        R_s = r_s * r_s
        R_p = r_p * r_p
        T_s = 1.0 - R_s
        T_p = 1.0 - R_p
        if T_s > 1e-10:
            ratio = T_p / T_s
        else:
            ratio = float('inf')

        # Phase shifts (trivial: 0 or 180 degrees)
        delta_s_deg = 0.0 if r_s >= 0.0 else 180.0
        delta_p_deg = 0.0 if r_p >= 0.0 else 180.0
        delta_relative_deg = delta_p_deg - delta_s_deg

        return {
            'regime': 'refraction',
            'near_tir': near_tir,
            'near_brewster': near_brewster,
            'angle_provided': angle_provided,
            'n1': n1,
            'n2': n2,
            'theta_i_deg': theta_i_deg,
            'tir_angle_deg': tir_deg,
            'brewster_angle_deg': brew_deg,
            'delta_angle_deg': delta_angle_deg,
            'T_s': T_s,
            'T_p': T_p,
            'R_s': R_s,
            'R_p': R_p,
            'ratio_Tp_Ts': ratio,
            'theta_t_deg': theta_t_deg,
            'delta_s_deg': delta_s_deg,
            'delta_p_deg': delta_p_deg,
            'delta_relative_deg': delta_relative_deg,
        }

    # ----- TIR regime -----
    # Phase-shift formulas:
    #   tan(delta_s / 2) = sqrt(n^2 sin^2(theta_i) - 1) / (n cos(theta_i))
    #   tan(delta_p / 2) = n^2 * tan(delta_s / 2)
    # where n = n1/n2.
    evanescent = math.sqrt(n_rel * n_rel * sin_i * sin_i - 1.0)

    tan_half_delta_s = evanescent / (n_rel * cos_i)
    delta_s = 2.0 * math.atan(tan_half_delta_s)
    delta_s_deg = math.degrees(delta_s)

    tan_half_delta_p = n_rel * n_rel * tan_half_delta_s
    delta_p = 2.0 * math.atan(tan_half_delta_p)
    delta_p_deg = math.degrees(delta_p)

    delta_relative_deg = delta_p_deg - delta_s_deg

    return {
        'regime': 'tir',
        'near_tir': near_tir,
        'near_brewster': near_brewster,
        'angle_provided': angle_provided,
        'n1': n1,
        'n2': n2,
        'theta_i_deg': theta_i_deg,
        'tir_angle_deg': tir_deg,
        'brewster_angle_deg': brew_deg,
        'delta_angle_deg': delta_angle_deg,
        'T_s': None,
        'T_p': None,
        'R_s': 1.0,
        'R_p': 1.0,
        'ratio_Tp_Ts': None,
        'theta_t_deg': None,
        'delta_s_deg': delta_s_deg,
        'delta_p_deg': delta_p_deg,
        'delta_relative_deg': delta_relative_deg,
    }
