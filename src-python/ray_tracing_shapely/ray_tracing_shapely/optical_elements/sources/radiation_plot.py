"""
Python-specific module: radiation plot
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
RADIATION PLOT -- a rayfile's intensity against angle, and its slice's
===============================================================================
A datasheet draws an LED's radiant intensity (flux per steradian) against
the angle from its axis, in cross sections through the axis. This module
computes those curves from a rayfile and, given a slice of it, the curve the
slice's rays make, so the two can be laid over each other:

- **3D, half averages:** the intensity averaged over each half of the
  azimuths, the half whose transverse direction points to the plane's
  positive side on the right of 0, the other on the left. The slice turns
  every ray onto the side its direction points to, so this is the curve a
  slice should reproduce if its kept rays were a fair sample of the LED.
- **3D, cross section in the plane / across it:** the intensity in a wedge
  of azimuths around the plane, and around the plane at right angles to it.
  These are what a datasheet's cross sections show.
- **Slice:** the kept rays' flux per steradian of half ring, divided by the
  kept share: the intensity the LED would have if all its light behaved as
  the kept rays do. Where it departs from the half averages, the
  near-meridional rays are not a fair sample of the LED.

The angle is signed: positive on the plane's positive side, the side a
slice's ``roll_deg`` puts the rayfile's in-plane axis on. ``radiation_plot_svg``
draws a pattern as a datasheet does, cartesian or polar, as an SVG string.
===============================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

import numpy as np
import svgwrite

from .rayfile import Rayfile
from .rayfile_slice import RayfileSlice

#: The curves a pattern may hold, in drawing order, with their labels.
CURVE_LABELS = {
    "3d_across": "3D, cross section across the plane",
    "3d_in_plane": "3D, cross section in the plane",
    "3d_halves": "3D, half averages",
    "slice": "slice, scaled to the whole flux",
}
_STYLE = {   # colour, width, dash
    "3d_across": ("#9a9893", 1.5, "5,4"),
    "3d_in_plane": ("#9a9893", 1.5, None),
    "3d_halves": ("#eb6834", 2.0, None),
    "slice": ("#2a78d6", 2.0, None),
}


@dataclass(frozen=True)
class RadiationPattern:
    """Intensity against the signed angle from the LED's axis.

    Attributes:
        edges_deg: Bin edges, -180 to 180, with 0 an edge.
        curves: Per curve name (``CURVE_LABELS``), the intensity per bin, in
            ``flux_unit`` / sr.
        flux_unit: The rayfile's flux unit.
        within_deg: Per angle, the share of the flux within it of the axis,
            for the 3D source ("3d") and the slice's kept rays ("slice").
        max_offset_mm: The slice's limit on |h|, or None without a slice.
        skew_share: The slice's skew share, or None without a slice.
        window_deg: The half width of the cross sections' azimuth wedges.
    """

    edges_deg: np.ndarray
    curves: Dict[str, np.ndarray]
    flux_unit: str
    within_deg: Dict[str, Dict[float, float]]
    max_offset_mm: Optional[float]
    skew_share: Optional[float]
    window_deg: float

    @property
    def centres_deg(self) -> np.ndarray:
        return 0.5 * (self.edges_deg[:-1] + self.edges_deg[1:])

    def summary(self) -> dict:
        """Per curve, its peak and full width at half maximum; the shares within angles."""
        c = self.centres_deg
        curves = {}
        for name, y in self.curves.items():
            k = int(np.argmax(y))
            curves[name] = {"peak": float(y[k]), "peak_at_deg": float(c[k]), "fwhm_deg": _fwhm(c, y)}
        return {"flux_unit": f"{self.flux_unit}/sr", "curves": curves,
                "within_deg": {k: dict(v) for k, v in self.within_deg.items()},
                "max_offset_mm": self.max_offset_mm, "skew_share": self.skew_share}


def _fwhm(c: np.ndarray, y: np.ndarray) -> Optional[float]:
    """Width between the outermost half-maximum crossings either side of the peak."""
    k = int(np.argmax(y))
    half = 0.5 * y[k]
    if half <= 0.0:
        return None
    sides = []
    for step in (-1, 1):
        i = k
        while 0 <= i + step < len(y) and y[i + step] >= half:
            i += step
        j = i + step
        if not 0 <= j < len(y):
            return None
        sides.append(c[i] + (c[j] - c[i]) * (y[i] - half) / (y[i] - y[j]))
    return float(sides[1] - sides[0])


def _signed_histogram(angles: np.ndarray, flux: np.ndarray, edges: np.ndarray) -> np.ndarray:
    f, _ = np.histogram(angles, bins=edges, weights=flux)
    return f


def radiation_pattern(rayfile: Rayfile, slc: Optional[RayfileSlice] = None, *, roll_deg: Optional[float] = None,
                      bin_deg: float = 2.5, window_deg: float = 10.0,
                      within: Sequence[float] = (15.0, 30.0, 45.0, 60.0, 90.0)) -> RadiationPattern:
    """The rayfile's intensity against the signed angle from its axis, and its slice's.

    Args:
        rayfile: The rays, z the LED's axis.
        slc: A slice of the same rayfile, or None for the 3D curves only.
        roll_deg: The plane's roll, as ``slice_rayfile``'s; the slice's
            when one is given (a different one is refused), else 0.
        bin_deg: The bin width; 180 must be a whole number of bins.
        window_deg: Half width of the azimuth wedge of each cross section.
        within: Angles at which to report the share of the flux.

    Raises:
        ValueError: If 180 is not a whole number of bins, the window is not
            in (0, 90], or ``roll_deg`` contradicts the slice's.
    """
    n_half = 180.0 / bin_deg
    if bin_deg <= 0.0 or abs(n_half - round(n_half)) > 1e-9:
        raise ValueError(f"180 must be a whole number of bins, got bin_deg={bin_deg}")
    if not 0.0 < window_deg <= 90.0:
        raise ValueError(f"window_deg must be in (0, 90], got {window_deg}")
    if slc is not None and roll_deg is not None and abs(roll_deg - slc.roll_deg) > 1e-12:
        raise ValueError(f"roll_deg {roll_deg} contradicts the slice's {slc.roll_deg}")
    roll = math.radians(slc.roll_deg if slc is not None else (roll_deg or 0.0))
    edges = np.linspace(-180.0, 180.0, 2 * int(round(n_half)) + 1)
    half_ring = np.pi * np.abs(np.cos(np.radians(edges[:-1])) - np.cos(np.radians(edges[1:])))

    d = rayfile.directions
    theta = np.degrees(np.arccos(np.clip(d[:, 2], -1.0, 1.0)))
    phi = np.arctan2(d[:, 1], d[:, 0])
    phi_plane = math.atan2(math.cos(roll), -math.sin(roll))      # the in-plane side: (-sin roll, cos roll)

    def side(phi0):                                               # +1 within the wedge at phi0, -1 opposite
        off = np.degrees((phi - phi0 + np.pi) % (2 * np.pi) - np.pi)
        return np.where(np.abs(off) <= window_deg, 1.0, np.where(np.abs(off) >= 180.0 - window_deg, -1.0, 0.0))

    wedge = half_ring * (2.0 * math.radians(window_deg)) / np.pi
    curves = {}
    for name, phi0 in (("3d_across", phi_plane - np.pi / 2), ("3d_in_plane", phi_plane)):
        s = side(phi0)
        m = s != 0.0
        curves[name] = _signed_histogram(s[m] * theta[m], rayfile.flux[m], edges) / wedge
    halves = np.where(np.cos(phi - phi_plane) >= 0.0, 1.0, -1.0)
    curves["3d_halves"] = _signed_histogram(halves * theta, rayfile.flux, edges) / half_ring

    total = rayfile.total_flux
    shares = {"3d": {float(a): float(rayfile.flux[theta <= a].sum() / total) for a in within}}
    if slc is not None:
        kept = slc.kept_flux
        ang = slc.angles_deg()
        if kept > 0.0:
            curves["slice"] = _signed_histogram(ang, slc.flux, edges) / half_ring * (total / kept)
            shares["slice"] = {float(a): float(slc.flux[np.abs(ang) <= a].sum() / kept) for a in within}
    return RadiationPattern(edges_deg=edges, curves=curves, flux_unit=rayfile.flux_unit, within_deg=shares,
                            max_offset_mm=None if slc is None else slc.max_offset_mm,
                            skew_share=None if slc is None else slc.skew_share, window_deg=float(window_deg))


def _nice_step(span: float) -> float:
    raw = span / 5.0
    mag = 10.0 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1.0, 2.0, 2.5, 5.0, 10.0) if m * mag >= raw)


def radiation_plot_svg(pattern: RadiationPattern, *, polar: bool = False, max_angle_deg: float = 105.0,
                       relative: bool = False, curves: Optional[Sequence[str]] = None,
                       title: Optional[str] = None, width: int = 640, height: int = 440) -> str:
    """Draw a pattern as a datasheet does, as an SVG string.

    Args:
        pattern: From ``radiation_pattern``.
        polar: A polar plot (0 up) instead of intensity against angle.
        max_angle_deg: The angles drawn, -max to max.
        relative: Each curve over its own peak, instead of flux / sr.
        curves: The curve names to draw (``CURVE_LABELS``'s keys); all by default.
        title: The plot's title; "Radiant intensity" by default.

    Raises:
        ValueError: For an unknown curve name.
    """
    names = [n for n in CURVE_LABELS if n in pattern.curves] if curves is None else list(curves)
    unknown = [n for n in names if n not in pattern.curves]
    if unknown:
        raise ValueError(f"no curve {unknown}; the pattern has {sorted(pattern.curves)}")
    c = pattern.centres_deg
    shown = np.abs(c) <= max_angle_deg
    ys = {n: (pattern.curves[n] / pattern.curves[n].max() if relative and pattern.curves[n].max() > 0
              else pattern.curves[n]) for n in names}
    top = max([float(ys[n][shown].max()) for n in names] + [1e-300])
    step = _nice_step(top)
    y_max = step * math.ceil(top / step)
    unit = "relative intensity" if relative else f"intensity, {pattern.flux_unit}/sr"

    dwg = svgwrite.Drawing(size=(width, height))
    dwg.add(dwg.rect((0, 0), (width, height), fill="#ffffff"))
    ink, muted, grid = "#0b0b0b", "#52514e", "#e4e3df"
    text = dict(font_family="sans-serif", font_size=12, fill=muted)
    dwg.add(dwg.text(title or "Radiant intensity", insert=(width / 2, 22), text_anchor="middle",
                     font_family="sans-serif", font_size=15, font_weight="bold", fill=ink))
    sub = [] if pattern.max_offset_mm is None else [
        f"slice: |h| <= {pattern.max_offset_mm:g} mm, skew share {100 * pattern.skew_share:.1f}%"]
    for k, line in enumerate(sub):
        dwg.add(dwg.text(line, insert=(width / 2, 40 + 14 * k), text_anchor="middle", **text))
    legend_h = 18 * len(names) + 8

    if not polar:
        left, right, top_px, bottom = 64, width - 20, 56, height - 46 - legend_h
        def px(a, v):
            return (left + (a + max_angle_deg) / (2 * max_angle_deg) * (right - left),
                    bottom - v / y_max * (bottom - top_px))
        tick = 15.0
        for k in range(-int(max_angle_deg // tick), int(max_angle_deg // tick) + 1):
            x, _ = px(k * tick, 0.0)
            dwg.add(dwg.line((x, top_px), (x, bottom), stroke=grid, stroke_width=1))
            dwg.add(dwg.text(f"{k * tick:g}", insert=(x, bottom + 16), text_anchor="middle", **text))
        for k in range(int(round(y_max / step)) + 1):
            _, y = px(-max_angle_deg, k * step)
            dwg.add(dwg.line((left, y), (right, y), stroke=grid, stroke_width=1))
            dwg.add(dwg.text(f"{k * step:g}", insert=(left - 6, y + 4), text_anchor="end", **text))
        dwg.add(dwg.line((left, bottom), (right, bottom), stroke=muted, stroke_width=1))
        dwg.add(dwg.text("angle from the axis, degrees", insert=((left + right) / 2, bottom + 34),
                         text_anchor="middle", **text))
        ylab = dwg.text(unit, insert=(16, (top_px + bottom) / 2), text_anchor="middle", **text)
        ylab.rotate(-90, center=(16, (top_px + bottom) / 2))
        dwg.add(ylab)
        for n in names:
            colour, w, dash = _STYLE[n]
            line = dwg.polyline([px(a, v) for a, v in zip(c[shown], ys[n][shown])], fill="none",
                                stroke=colour, stroke_width=w, stroke_linejoin="round")
            if dash:
                line["stroke-dasharray"] = dash
            dwg.add(line)
        legend_top = bottom + 48
    else:
        below = max(0.12, -math.cos(math.radians(min(max_angle_deg, 180.0))))   # the plot's depth under the centre
        radius = min(width / 2 - 50, (height - 64 - legend_h - 60) / (1.12 + below))
        cx, cy = width / 2, 64 + 1.12 * radius
        def px(a, v):
            r = radius * v / y_max
            return cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a))
        span = min(max_angle_deg, 180.0)
        for k in range(1, int(round(y_max / step)) + 1):
            v = k * step
            if span >= 180.0:
                dwg.add(dwg.circle((cx, cy), radius * v / y_max, fill="none", stroke=grid, stroke_width=1))
            else:
                r = radius * v / y_max
                arc = dwg.path(d=f"M {px(-span, v)[0]} {px(-span, v)[1]}", fill="none", stroke=grid, stroke_width=1)
                arc.push_arc(px(span, v), 0, (r, r), large_arc=2 * span > 180.0, angle_dir="+", absolute=True)
                dwg.add(arc)
            dwg.add(dwg.text(f"{v:g}", insert=(cx - radius * v / y_max, cy + 14), text_anchor="middle", **text))
        for k in range(-int(max_angle_deg // 15), int(max_angle_deg // 15) + 1):
            a = 15.0 * k
            dwg.add(dwg.line((cx, cy), px(a, y_max), stroke=grid, stroke_width=1))
            if k % 2 == 0 and not (a <= -180.0 and span >= 180.0):        # one label at 180
                x, y = px(a, y_max * 1.07)
                dwg.add(dwg.text(f"{a:g}", insert=(x, y + 4), text_anchor="middle", **text))
        for n in names:
            colour, w, dash = _STYLE[n]
            line = dwg.polyline([px(a, v) for a, v in zip(c[shown], ys[n][shown])], fill="none",
                                stroke=colour, stroke_width=w, stroke_linejoin="round")
            if dash:
                line["stroke-dasharray"] = dash
            dwg.add(line)
        gap = 40 if span > 150.0 else 24                                       # clear of the angle labels below
        dwg.add(dwg.text(unit, insert=(cx, cy + below * radius + gap), text_anchor="middle", **text))
        legend_top = cy + below * radius + gap + 22

    for k, n in enumerate(names):
        colour, w, dash = _STYLE[n]
        y = legend_top + 18 * k
        mark = dwg.line((width / 2 - 150, y - 4), (width / 2 - 122, y - 4), stroke=colour, stroke_width=w)
        if dash:
            mark["stroke-dasharray"] = dash
        dwg.add(mark)
        dwg.add(dwg.text(CURVE_LABELS[n], insert=(width / 2 - 114, y), font_family="sans-serif",
                         font_size=12, fill=ink))
    return dwg.tostring()


__all__ = ["CURVE_LABELS", "RadiationPattern", "radiation_pattern", "radiation_plot_svg"]
