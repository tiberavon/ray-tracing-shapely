"""
Python-specific module: irradiance
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
IRRADIANCE -- where the light that left an optic crosses a plane
===============================================================================
The rays that leave an optic are carried on to a plane square to its axis,
and binned there by flux:

- in 3D, an irradiance map: flux per mm^2 on a grid of pixels;
- in 2D, a line profile: flux per mm along the line the plane cuts in the
  2D scene. A 2D scene's flux is per ray, not per unit length out of the
  plane, so a 2D profile and a 3D map compare in shape, not in value.

The plane is written in the 2D scene's frame, as a source specification is
(``optical_elements.sources.source_spec``): a point (a, b, c) and an axis
``direction_deg`` in the 2D plane. Its two axes on the plane are

    u  in the 2D plane, across the axis: (-sin t, cos t, 0)
    v  out of the 2D plane: (0, 0, 1)

so the map's section along u at v = 0 is the line a 2D trace sees.

**A 2D section is not a section of the irradiance.** A meridional 2D trace
of a rotationally symmetric beam carries, along u, the flux per mm of
radius, dPhi/dr = 2 pi r E(r): the light in a ring, not on a point. It is
low near the axis even where the irradiance is high. So the 3D quantity to
lay over a 2D ``LineProfile`` is ``IrradianceMap.radial_profile``, against
the profile folded about the axis (``LineProfile.folded``), not a section. Only rays
heading towards the plane's far side (direction . axis > 0) and starting
before it are counted; the rest are reported, not binned. Rays heading out
whose last segment starts past the plane are counted apart
(``rays_past_plane``): a plane that cuts through the optic misses the light
still inside it, and shows a hole that is not in the beam.

Everything returned has ``summary()`` and ``to_dict()``, plain JSON, so a
tool can return it as it is.
===============================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class ExitPlane:
    """A plane square to an axis in the 2D plane, in the scene frame (a, b, c).

    Attributes:
        origin: A point of the plane, (a, b, c); the map's (0, 0).
        direction_deg: The axis, an angle in the 2D plane from +a.
    """

    origin: Tuple[float, float, float]
    direction_deg: float

    @classmethod
    def at(cls, origin: Sequence[float], direction_deg: float) -> "ExitPlane":
        o = [float(x) for x in origin]
        if len(o) not in (2, 3):
            raise ValueError(f"origin must be (a, b) or (a, b, c), got {origin!r}")
        return cls(tuple(o + [0.0] * (3 - len(o))), float(direction_deg))

    @property
    def axes(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(n, u, v): the axis, and the plane's two axes, in the scene frame."""
        t = math.radians(self.direction_deg)
        return (np.array([math.cos(t), math.sin(t), 0.0]), np.array([-math.sin(t), math.cos(t), 0.0]),
                np.array([0.0, 0.0, 1.0]))

    def to_dict(self) -> Dict[str, Any]:
        return {"origin": list(self.origin), "direction_deg": self.direction_deg}


def _onto_plane(points: np.ndarray, directions: np.ndarray, plane: ExitPlane):
    """Each ray's (u, v) on the plane, which rays reach it heading out, and which head out from past it."""
    n, u, v = plane.axes
    rel = points - np.asarray(plane.origin)
    along, speed = rel @ n, directions @ n
    reach = (speed > 1e-12) & (along <= 1e-9)
    t = np.where(reach, -along / np.where(reach, speed, 1.0), 0.0)
    hit = rel + t[:, None] * directions
    return hit @ u, hit @ v, reach, (speed > 1e-12) & (along > 1e-9)


def _fwhm(centres: np.ndarray, values: np.ndarray) -> Optional[float]:
    """Width between the outermost half-maximum crossings either side of the peak."""
    if len(values) == 0 or values.max() <= 0.0:
        return None
    half = 0.5 * float(values.max())
    above = np.flatnonzero(values >= half)
    lo, hi = above[0], above[-1]

    def cross(i, j):
        if not 0 <= j < len(values):
            return None
        return centres[i] + (centres[j] - centres[i]) * (values[i] - half) / (values[i] - values[j])

    left, right = cross(lo, lo - 1), cross(hi, hi + 1)
    return None if left is None or right is None else float(right - left)


@dataclass(frozen=True)
class IrradianceMap:
    """Flux per mm^2 on a square grid of the plane.

    Attributes:
        plane: The plane.
        u_edges_mm, v_edges_mm: Pixel edges along u and v.
        values: (len(v) - 1, len(u) - 1) flux per mm^2; row k is v between
            ``v_edges_mm[k]`` and ``[k + 1]``.
        flux_unit: The rays' flux unit.
        flux_on_map: The flux of the rays that land on the map.
        flux_total: The flux of every ray given.
        rays_on_map: How many land on it.
        rays_total: How many were given.
        rays_past_plane: How many head out from past the plane: not 0 when
            the plane cuts the optic.
    """

    plane: ExitPlane
    u_edges_mm: np.ndarray
    v_edges_mm: np.ndarray
    values: np.ndarray
    flux_unit: str
    flux_on_map: float
    flux_total: float
    rays_on_map: int
    rays_total: int
    rays_past_plane: int = 0

    @property
    def u_centres_mm(self) -> np.ndarray:
        return 0.5 * (self.u_edges_mm[:-1] + self.u_edges_mm[1:])

    @property
    def v_centres_mm(self) -> np.ndarray:
        return 0.5 * (self.v_edges_mm[:-1] + self.v_edges_mm[1:])

    def section(self, axis: str = "u", at_mm: float = 0.0, half_width_mm: float = 0.0
                ) -> Tuple[np.ndarray, np.ndarray]:
        """The map along ``axis`` ("u" or "v"), at ``at_mm`` on the other.

        The mean of the pixel rows (or columns) whose centres lie within
        ``half_width_mm`` of ``at_mm``, and at least the one holding it: a
        wider band is less noisy and less sharp.

        Raises:
            ValueError: For another axis, or ``at_mm`` off the map.
        """
        if axis not in ("u", "v"):
            raise ValueError(f"axis must be 'u' or 'v', got {axis!r}")
        across = self.v_edges_mm if axis == "u" else self.u_edges_mm
        k = int(np.searchsorted(across, at_mm, side="right")) - 1
        if not 0 <= k < len(across) - 1:
            raise ValueError(f"{at_mm} mm is off the map ({across[0]:g} to {across[-1]:g} mm)")
        centres = 0.5 * (across[:-1] + across[1:])
        band = np.flatnonzero(np.abs(centres - at_mm) <= half_width_mm)
        rows = np.union1d(band, [k])
        if axis == "u":
            return self.u_centres_mm, self.values[rows, :].mean(axis=0)
        return self.v_centres_mm, self.values[:, rows].mean(axis=1)

    def radial_profile(self, r_edges_mm: Optional[np.ndarray] = None, subdivide: int = 4
                       ) -> Tuple[np.ndarray, np.ndarray]:
        """Flux per mm of radius about the plane's origin, dPhi/dr: what a 2D section carries.

        Each pixel's flux is spread over ``subdivide`` x ``subdivide`` points
        across it before binning by distance from (0, 0): binning whole
        pixels into rings a pixel wide aliases. ``r_edges_mm`` from 0 to the
        map's half size in pixel steps by default.
        """
        du, dv = float(self.u_edges_mm[1] - self.u_edges_mm[0]), float(self.v_edges_mm[1] - self.v_edges_mm[0])
        edges = np.arange(0.0, float(self.u_edges_mm[-1]) + 0.5 * du, du) if r_edges_mm is None \
            else np.asarray(r_edges_mm, dtype=float)
        sub = (np.arange(subdivide) + 0.5) / subdivide - 0.5
        uu = (self.u_centres_mm[None, :, None, None] + du * sub[None, None, None, :])
        vv = (self.v_centres_mm[:, None, None, None] + dv * sub[None, None, :, None])
        r = np.hypot(uu, vv)                                         # (v, u, sub_v, sub_u)
        w = np.broadcast_to((self.values * du * dv / subdivide ** 2)[:, :, None, None], r.shape)
        flux, _ = np.histogram(r.ravel(), bins=edges, weights=w.ravel())
        return 0.5 * (edges[:-1] + edges[1:]), flux / np.diff(edges)

    def _section_fwhm(self, axis: str) -> Optional[float]:
        across = self.v_edges_mm if axis == "u" else self.u_edges_mm
        return _fwhm(*self.section(axis, 0.0)) if across[0] <= 0.0 < across[-1] else None

    def summary(self) -> Dict[str, Any]:
        """Plain JSON: the flux on the map, the peak and where, the centroid, the widths, the sections' FWHM."""
        unit = f"{self.flux_unit}/mm^2"
        out: Dict[str, Any] = {
            "plane": self.plane.to_dict(), "unit": unit,
            "extent_mm": {"u": [float(self.u_edges_mm[0]), float(self.u_edges_mm[-1])],
                          "v": [float(self.v_edges_mm[0]), float(self.v_edges_mm[-1])]},
            "pixels": [int(self.values.shape[1]), int(self.values.shape[0])],
            "flux_on_map": self.flux_on_map, "flux_total": self.flux_total,
            "share_on_map": self.flux_on_map / self.flux_total if self.flux_total > 0 else 0.0,
            "rays_on_map": self.rays_on_map, "rays_total": self.rays_total,
            "rays_past_plane": self.rays_past_plane,
        }
        if self.flux_on_map > 0.0:
            k = np.unravel_index(int(np.argmax(self.values)), self.values.shape)
            weight = self.values / self.values.sum()
            uu, vv = np.meshgrid(self.u_centres_mm, self.v_centres_mm)
            cu, cv = float((weight * uu).sum()), float((weight * vv).sum())
            out.update({
                "peak": float(self.values[k]),
                "peak_at_mm": [float(self.u_centres_mm[k[1]]), float(self.v_centres_mm[k[0]])],
                "mean_on_map": self.flux_on_map / float(np.ptp(self.u_edges_mm) * np.ptp(self.v_edges_mm)),
                "centroid_mm": [cu, cv],
                "rms_width_mm": [math.sqrt(float((weight * (uu - cu) ** 2).sum())),
                                 math.sqrt(float((weight * (vv - cv) ** 2).sum()))],
                "fwhm_mm": {"u_at_v0": self._section_fwhm("u"), "v_at_u0": self._section_fwhm("v")},
            })
        return out

    def to_dict(self) -> Dict[str, Any]:
        """The summary and the grid itself, plain JSON."""
        return {**self.summary(), "u_edges_mm": self.u_edges_mm.tolist(), "v_edges_mm": self.v_edges_mm.tolist(),
                "values": self.values.tolist()}


def irradiance_map(points: np.ndarray, directions: np.ndarray, flux: np.ndarray, plane: ExitPlane, *,
                   half_size_mm: float, pixels: int = 101, flux_unit: str = "W") -> IrradianceMap:
    """Carry rays on to a plane and bin their flux per mm^2.

    Args:
        points, directions: (k, 3) in the scene frame (a, b, c): where each
            ray last starts, and its direction there.
        flux: (k,) each ray's flux.
        plane: The plane.
        half_size_mm: The map spans -half_size_mm to half_size_mm on u and v.
        pixels: Pixels along each side; odd puts a pixel on (0, 0).

    Raises:
        ValueError: On mismatched arrays, a non-positive size, or fewer than 1 pixel.
    """
    points, directions, flux = (np.asarray(x, dtype=float) for x in (points, directions, flux))
    if points.ndim != 2 or points.shape[1] != 3 or directions.shape != points.shape or flux.shape != (len(points),):
        raise ValueError("points and directions must be (k, 3) and flux (k,)")
    if not half_size_mm > 0.0 or pixels < 1:
        raise ValueError(f"half_size_mm must be > 0 and pixels >= 1, got {half_size_mm}, {pixels}")
    u, v, reach, past = _onto_plane(points, directions, plane)
    edges = np.linspace(-half_size_mm, half_size_mm, pixels + 1)
    binned, _, _ = np.histogram2d(v[reach], u[reach], bins=[edges, edges], weights=flux[reach])
    on = reach & (np.abs(u) <= half_size_mm) & (np.abs(v) <= half_size_mm)
    pixel_area = (edges[1] - edges[0]) ** 2
    return IrradianceMap(plane=plane, u_edges_mm=edges, v_edges_mm=edges.copy(), values=binned / pixel_area,
                         flux_unit=flux_unit, flux_on_map=float(flux[on].sum()), flux_total=float(flux.sum()),
                         rays_on_map=int(on.sum()), rays_total=int(len(flux)), rays_past_plane=int(past.sum()))


@dataclass(frozen=True)
class LineProfile:
    """Flux per mm along the line a plane cuts in the 2D scene.

    Attributes:
        plane: The plane (its c is ignored: a 2D scene is the plane c = 0).
        u_edges_mm: Bin edges along u.
        values: Flux per mm in each bin.
        flux_unit, flux_on_line, flux_total, rays_on_line, rays_total,
            rays_past_plane: As for ``IrradianceMap``.
    """

    plane: ExitPlane
    u_edges_mm: np.ndarray
    values: np.ndarray
    flux_unit: str
    flux_on_line: float
    flux_total: float
    rays_on_line: int
    rays_total: int
    rays_past_plane: int = 0

    @property
    def u_centres_mm(self) -> np.ndarray:
        return 0.5 * (self.u_edges_mm[:-1] + self.u_edges_mm[1:])

    def folded(self, r_edges_mm: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """The profile folded about the axis: flux per mm of |u|, both sides summed.

        Comparable with ``IrradianceMap.radial_profile`` in shape. Each bin's
        flux goes to the radial bin holding its centre's |u|.
        """
        step = float(self.u_edges_mm[1] - self.u_edges_mm[0])
        edges = np.arange(0.0, float(self.u_edges_mm[-1]) + 0.5 * step, step) if r_edges_mm is None \
            else np.asarray(r_edges_mm, dtype=float)
        flux, _ = np.histogram(np.abs(self.u_centres_mm), bins=edges, weights=self.values * step)
        return 0.5 * (edges[:-1] + edges[1:]), flux / np.diff(edges)

    def summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "plane": self.plane.to_dict(), "unit": f"{self.flux_unit}/mm",
            "extent_mm": [float(self.u_edges_mm[0]), float(self.u_edges_mm[-1])], "bins": int(len(self.values)),
            "flux_on_line": self.flux_on_line, "flux_total": self.flux_total,
            "share_on_line": self.flux_on_line / self.flux_total if self.flux_total > 0 else 0.0,
            "rays_on_line": self.rays_on_line, "rays_total": self.rays_total,
            "rays_past_plane": self.rays_past_plane,
        }
        if self.flux_on_line > 0.0:
            c, w = self.u_centres_mm, self.values / self.values.sum()
            k = int(np.argmax(self.values))
            centroid = float((w * c).sum())
            out.update({"peak": float(self.values[k]), "peak_at_mm": float(c[k]), "centroid_mm": centroid,
                        "rms_width_mm": math.sqrt(float((w * (c - centroid) ** 2).sum())),
                        "fwhm_mm": _fwhm(c, self.values)})
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {**self.summary(), "u_edges_mm": self.u_edges_mm.tolist(), "values": self.values.tolist()}


def line_profile(points: np.ndarray, directions: np.ndarray, flux: np.ndarray, plane: ExitPlane, *,
                 half_size_mm: float, bins: int = 101, flux_unit: str = "W") -> LineProfile:
    """Carry 2D rays on to the line a plane cuts in the scene, and bin their flux per mm.

    Args:
        points, directions: (k, 2) in the 2D scene.
        flux: (k,) each ray's flux.
    """
    points, directions, flux = (np.asarray(x, dtype=float) for x in (points, directions, flux))
    if points.ndim != 2 or points.shape[1] != 2 or directions.shape != points.shape or flux.shape != (len(points),):
        raise ValueError("points and directions must be (k, 2) and flux (k,)")
    if not half_size_mm > 0.0 or bins < 1:
        raise ValueError(f"half_size_mm must be > 0 and bins >= 1, got {half_size_mm}, {bins}")
    zeros = np.zeros((len(points), 1))
    u, _, reach, past = _onto_plane(np.hstack([points, zeros]), np.hstack([directions, zeros]),
                              ExitPlane.at(plane.origin[:2], plane.direction_deg))
    edges = np.linspace(-half_size_mm, half_size_mm, bins + 1)
    binned, _ = np.histogram(u[reach], bins=edges, weights=flux[reach])
    on = reach & (np.abs(u) <= half_size_mm)
    return LineProfile(plane=plane, u_edges_mm=edges, values=binned / (edges[1] - edges[0]), flux_unit=flux_unit,
                       flux_on_line=float(flux[on].sum()), flux_total=float(flux.sum()), rays_on_line=int(on.sum()),
                       rays_total=int(len(flux)), rays_past_plane=int(past.sum()))


def exit_rays_2d(segments: Sequence[Any], flux_per_brightness: float = 1.0
                 ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The 2D rays that left the scene: the last segment of each branch that ends on nothing.

    Needs a run with ``Simulator(record_surface_hits=True)``: without it a
    segment does not say whether it ended on a surface, and a ray absorbed
    or stopped there would be counted as leaving.

    The flux is the simulator's: a dim Fresnel reflection is kept for one
    ray in ``amp`` and multiplied by ``amp`` (upstream's sampling), so the
    flux that leaves equals what entered in expectation, not ray by ray.

    Returns:
        (points, directions, flux): (k, 2), (k, 2) unit, (k,) each
        segment's brightness times ``flux_per_brightness``.

    Raises:
        ValueError: If the run did not record surface hits.
    """
    segments = list(segments)
    parents = {s.parent_uuid for s in segments}
    if any(s.uuid in parents for s in segments) and all(s.hit_surface_uuid is None for s in segments):
        raise ValueError("these segments carry no surface hits: run the Simulator with record_surface_hits=True")
    leaves = [s for s in segments if s.uuid not in parents and s.hit_surface_uuid is None]
    if not leaves:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0)
    p = np.array([[s.p1["x"], s.p1["y"]] for s in leaves])
    d = np.array([[s.p2["x"] - s.p1["x"], s.p2["y"] - s.p1["y"]] for s in leaves])
    d /= np.linalg.norm(d, axis=1)[:, None]
    return p, d, np.array([s.total_brightness for s in leaves]) * float(flux_per_brightness)


__all__ = ["ExitPlane", "IrradianceMap", "LineProfile", "exit_rays_2d", "irradiance_map", "line_profile"]
