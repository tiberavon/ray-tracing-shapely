"""
Python-specific module: Angular subtense of the apparent source (Eye safety framework)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

===============================================================================
PYTHON-SPECIFIC MODULE: Angular subtense (alpha)
===============================================================================
Standard-agnostic geometry: given the long and short angular dimensions of a
non-circular apparent source, clamp each to [alpha_min, alpha_max] and take
the arithmetic mean. Both governing standards use this same construction
(IEC 62471 Sec. 4.2.2; Henderson & Schulmeister eq. (3.13)) but disagree on
the numeric value of alpha_min, which is why it is a required parameter
here rather than a hardcoded constant:

    IEC 62471    alpha_min = 0.0017 rad (1.7 mrad)  [IEC 62471]
    IEC 60825-1  alpha_min = 0.0015 rad (1.5 mrad)  [Chaves Ch. 3:214]

Both standards agree alpha_max = 0.1 rad (100 mrad).

See dev_doc/architecture/components/eye_safety.md
===============================================================================
"""

from __future__ import annotations

import math


#: IEC 62471 Sec. 4.2.2: "the value for alpha_min is 0,0017 radian."
ALPHA_MIN_IEC62471_RAD: float = 0.0017

#: Henderson & Schulmeister eq. (3.10)/Sec. 3.12.5.1: "alpha_min ... 1.5 mrad."
ALPHA_MIN_IEC60825_1_RAD: float = 0.0015

#: Both standards agree: "The maximum value of the angular subtense, ...
#: is 0,1 radian for all retinal hazards" (IEC 62471 Sec. 4.2.2); Henderson
#: Sec. 3.12.5.1 states the same 100 mrad value.
ALPHA_MAX_RAD: float = 0.1


def clip_alpha(alpha_rad: float, alpha_min_rad: float, alpha_max_rad: float = ALPHA_MAX_RAD) -> float:
    """Clamp an angular subtense to [alpha_min_rad, alpha_max_rad].

    Args:
        alpha_rad: Angular subtense in radians.
        alpha_min_rad: Standard-specific minimum angular subtense in radians
            (use `ALPHA_MIN_IEC62471_RAD` or `ALPHA_MIN_IEC60825_1_RAD`).
        alpha_max_rad: Maximum angular subtense in radians. Default 0.1 rad
            (100 mrad), shared by both standards.

    Returns:
        `alpha_rad` clamped to the closed interval [alpha_min_rad, alpha_max_rad].

    Raises:
        ValueError: If `alpha_rad` is negative, or `alpha_min_rad` is not
            positive, or `alpha_max_rad < alpha_min_rad`.
    """
    if alpha_rad < 0.0:
        raise ValueError("alpha_rad must be non-negative.")
    if alpha_min_rad <= 0.0:
        raise ValueError("alpha_min_rad must be positive.")
    if alpha_max_rad < alpha_min_rad:
        raise ValueError("alpha_max_rad must be >= alpha_min_rad.")
    return max(alpha_min_rad, min(alpha_rad, alpha_max_rad))


def alpha_from_axes(
    alpha_long_rad: float,
    alpha_short_rad: float,
    alpha_min_rad: float,
    alpha_max_rad: float = ALPHA_MAX_RAD,
) -> float:
    """Effective angular subtense for a non-circular apparent source.

    Each axis is clamped to [alpha_min_rad, alpha_max_rad] *before*
    averaging -- both standards specify this order explicitly. IEC 62471
    Sec. 4.2.2: "Any angular dimension larger than alpha_max shall be
    limited to alpha_max and any angular dimension smaller than alpha_min
    shall be limited to alpha_min, prior to the determination of the
    arithmetic mean." Henderson & Schulmeister eq. (3.13):
    alpha = (alpha_x + alpha_y) / 2, with alpha_x and alpha_y "again
    limited to a minimum value of 1.5 mrad and to a maximum of 100 mrad."

    Args:
        alpha_long_rad: Angular subtense along the long axis, in radians.
        alpha_short_rad: Angular subtense along the short axis, in radians.
        alpha_min_rad: Standard-specific minimum angular subtense in radians.
        alpha_max_rad: Maximum angular subtense in radians (default 0.1 rad).

    Returns:
        The effective (clamp-then-average) angular subtense, in radians.
    """
    long_clamped = clip_alpha(alpha_long_rad, alpha_min_rad, alpha_max_rad)
    short_clamped = clip_alpha(alpha_short_rad, alpha_min_rad, alpha_max_rad)
    return (long_clamped + short_clamped) / 2.0


def angle_from_size_distance(size_m: float, distance_m: float) -> float:
    """Angular subtense of a physical dimension viewed from a distance.

    The first half of the angular-subtense chain --
    `alpha_from_axes` above clamps and averages angles that are already
    known; nothing in this module previously turned a raw physical size
    and viewing distance (the numbers an actual problem statement or
    datasheet gives) into that angle in the first place. Uses the full
    `2*atan(size/(2*distance))` relation rather than the small-angle
    approximation `size/distance` -- both standards' own worked examples
    (e.g. the non-binding guide's Appendix D) use sources small enough
    that the two agree to several significant figures, but the exact form
    costs nothing and removes a silent approximation error for a source
    that turns out not to be small.

    For a non-circular source, call this once per axis (long and short
    physical dimension, same distance) and pass both results to
    `alpha_from_axes`.

    Args:
        size_m: Physical dimension of the source (e.g. diameter, or one
            axis of a non-circular source), in metres. Must be positive.
        distance_m: Viewing distance from the source, in metres. Must be
            positive.

    Returns:
        The angular subtense in radians, unclamped -- pass through
        `clip_alpha`/`alpha_from_axes` before use in an MPE/AEL function,
        which expect the standard's own [alpha_min, alpha_max] clamping to
        already have been applied.

    Raises:
        ValueError: If `size_m` or `distance_m` is not positive.
    """
    if size_m <= 0.0:
        raise ValueError("size_m must be positive.")
    if distance_m <= 0.0:
        raise ValueError("distance_m must be positive.")
    return 2.0 * math.atan(size_m / (2.0 * distance_m))
