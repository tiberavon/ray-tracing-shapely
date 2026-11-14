"""
Python-specific module: rayfile slice
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

===============================================================================
RAYFILE SLICE -- a measured LED's rays, for a 2D section of a symmetric optic
===============================================================================
A 2D section of a rotationally symmetric optic traces meridional rays: rays
in a plane that contains the axis. Turning a ray about the axis is a
symmetry of such an optic, so any ray of a rayfile may be turned before it
is used. What no turn changes is the ray's skewness: the distance h at which
its line passes the axis (its skew invariant, r x d along the axis, over the
transverse length of d). A meridional ray has h = 0.

``slice_rayfile`` turns every ray about the LED's axis until its transverse
direction lies in the 2D plane, then drops its offset h out of the plane:

    the 2D ray has the 3D ray's direction exactly (its axial component, and
    its transverse length now in the plane) and is displaced by h.

Rays with |h| above ``max_offset_mm`` are not kept: they are the light the
2D section cannot represent. Their share of the flux, ``skew_share``, is
reported with every slice; it says before any 3D run how far a 2D result
lit by this LED can be trusted. It depends on ``max_offset_mm``, which the
caller states, so it is reported with it, and with the flux-weighted
quantiles of |h|.

Of the two turns that put a ray's direction in the plane, the smaller is
taken, so a ray already near the plane keeps its side. A ray parallel to the
axis has no transverse direction: its start point is turned into the plane
instead, and its h is 0.

The kept rays keep their flux. A 2D result lit by a slice is therefore the
behaviour of the near-meridional rays of the 3D source, ray for ray, not an
in-plane intensity law (``source_spec``'s sections are that).

The placement is ``rayfile_frame``'s (the 3D bridge): the file's z along
the emission axis at ``direction_deg``, its y along the in-plane side at
``roll_deg`` = 0, its x out of the plane.
===============================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .ray_set_source import RaySetSource
from .rayfile import Rayfile

#: A transverse direction shorter than this is a ray along the axis.
_ALONG_AXIS = 1e-12
#: Rounding allowed on h, mm: a meridional ray's computed h is ~1e-16, not 0.
H_ROUNDING_MM = 1e-9


@dataclass(frozen=True)
class RayfileSlice:
    """The kept rays of a rayfile, in the 2D scene, and what was not kept.

    Attributes:
        points: (k, 2) start points of the kept rays, in the 2D scene.
        directions: (k, 2) their unit directions.
        flux: (k,) their flux, in the rayfile's unit.
        indices: (k,) the record each came from.
        offsets_mm: (n,) every record's h, signed (positive: anticlockwise
            about the axis, seen from +z).
        max_offset_mm: The limit on |h| that decided what was kept.
        total_flux: The rayfile's flux.
        flux_unit: The rayfile's flux unit.
        direction_deg: The LED's axis in the 2D scene, from +a.
        roll_deg: The roll the slice was taken at.
    """

    points: np.ndarray
    directions: np.ndarray
    flux: np.ndarray
    indices: np.ndarray
    offsets_mm: np.ndarray
    max_offset_mm: float
    total_flux: float
    flux_unit: str
    direction_deg: float = 0.0
    roll_deg: float = 0.0

    @property
    def kept_flux(self) -> float:
        return float(self.flux.sum())

    @property
    def skew_share(self) -> float:
        """The share of the rayfile's flux in rays with |h| > max_offset_mm."""
        return 1.0 - self.kept_flux / self.total_flux if self.total_flux > 0 else 0.0

    def offset_quantiles(self, weights_flux: np.ndarray,
                         q: Sequence[float] = (0.5, 0.9, 0.99)) -> Dict[float, float]:
        """Flux-weighted quantiles of |h| over every record (``weights_flux``: the rayfile's flux)."""
        h = np.abs(self.offsets_mm)
        order = np.argsort(h)
        cum = np.cumsum(np.asarray(weights_flux, dtype=float)[order])
        cum /= cum[-1]
        return {float(x): float(h[order][min(np.searchsorted(cum, x), len(h) - 1)]) for x in q}

    def angles_deg(self) -> np.ndarray:
        """Each kept ray's angle from the LED's axis in the plane, signed (positive: the in-plane side)."""
        t = math.radians(self.direction_deg)
        along = self.directions[:, 0] * math.cos(t) + self.directions[:, 1] * math.sin(t)
        across = -self.directions[:, 0] * math.sin(t) + self.directions[:, 1] * math.cos(t)
        return np.degrees(np.arctan2(across, along))

    def rays(self) -> List[Tuple[Tuple[float, float], float]]:
        """The kept rays as ((a, b), angle in degrees), the form ``compare_2d_3d`` takes."""
        return [((float(p[0]), float(p[1])), math.degrees(math.atan2(d[1], d[0])))
                for p, d in zip(self.points, self.directions)]

    def source_2d(self, scene, name: str = "rayfile slice",
                  wavelength_nm: Optional[float] = None) -> RaySetSource:
        """A RaySetSource emitting the kept rays, the brightest at brightness 1.

        ``flux_per_brightness`` is the flux of brightness 1, so a 2D result
        reads back in the rayfile's unit.

        Raises:
            ValueError: If no ray was kept.
        """
        if len(self.flux) == 0 or self.flux.max() <= 0.0:
            raise ValueError(f"no ray of the rayfile passes within {self.max_offset_mm} mm of the axis")
        peak = float(self.flux.max())
        kwargs = {} if wavelength_nm is None else {"wavelength": float(wavelength_nm)}
        source = RaySetSource.from_rays(scene, self.points, self.directions, self.flux / peak,
                                        flux_per_brightness=peak, **kwargs)
        source.name = name
        return source


def slice_rayfile(rayfile: Rayfile, position: Sequence[float], direction_deg: float, *,
                  max_offset_mm: float, roll_deg: float = 0.0) -> RayfileSlice:
    """Turn a rayfile's rays into the 2D plane about the LED's axis; keep the near-meridional ones.

    Args:
        rayfile: The rays, in the LED's frame (z its axis).
        position: The LED's origin in the 2D scene, (a, b).
        direction_deg: Its axis, an angle in the 2D plane from +a.
        max_offset_mm: Keep the rays whose line passes within this distance
            of the axis (plus ``H_ROUNDING_MM``, so 0 keeps the meridional
            rays). Required: the share left out depends on it.
        roll_deg: As ``rayfile_frame``'s; it decides only which of the two
            turns is the smaller.

    Raises:
        ValueError: If ``position`` is not a 2D point or ``max_offset_mm`` is negative.
    """
    if len(position) != 2:
        raise ValueError("a slice is taken in the 2D plane: position must be (a, b)")
    if max_offset_mm < 0.0:
        raise ValueError(f"max_offset_mm must be >= 0, got {max_offset_mm}")
    r, d = rayfile.positions, rayfile.directions
    x, y, z = r[:, 0], r[:, 1], r[:, 2]
    u, v, w = d[:, 0], d[:, 1], d[:, 2]
    m = np.hypot(u, v)
    along = m <= _ALONG_AXIS
    m_safe = np.where(along, 1.0, m)

    # the in-plane transverse direction p in the LED's frame (x = e_out, y = e_in)
    roll = math.radians(roll_deg)
    p_loc = np.array([-math.sin(roll), math.cos(roll)])

    h = np.where(along, 0.0, (x * v - y * u) / m_safe)
    t_star = np.where(along, 0.0, -(x * u + y * v) / (m_safe ** 2))   # closest approach to the axis
    axial = z + t_star * w                                            # where the line passes the axis
    sigma = np.where(along, np.sign(x * p_loc[0] + y * p_loc[1]), np.sign(u * p_loc[0] + v * p_loc[1]))
    sigma = np.where(sigma == 0.0, 1.0, sigma)
    a_loc = np.where(along, z, axial - t_star * w)                    # the start, in the plane
    b_loc = np.where(along, sigma * np.hypot(x, y), -t_star * sigma * m)
    da_loc, db_loc = w, np.where(along, 0.0, sigma * m)

    t = math.radians(direction_deg)
    n2, p2 = np.array([math.cos(t), math.sin(t)]), np.array([-math.sin(t), math.cos(t)])
    origin = np.asarray(position, dtype=float)
    points = origin + a_loc[:, None] * n2 + b_loc[:, None] * p2
    directions = da_loc[:, None] * n2 + db_loc[:, None] * p2

    keep = np.abs(h) <= max_offset_mm + H_ROUNDING_MM
    return RayfileSlice(points=points[keep], directions=directions[keep], flux=rayfile.flux[keep].copy(),
                        indices=np.flatnonzero(keep), offsets_mm=h, max_offset_mm=float(max_offset_mm),
                        total_flux=rayfile.total_flux, flux_unit=rayfile.flux_unit,
                        direction_deg=float(direction_deg), roll_deg=float(roll_deg))


__all__ = ["RayfileSlice", "slice_rayfile"]
