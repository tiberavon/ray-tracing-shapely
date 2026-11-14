"""
Python-specific module: profile scan
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
PROFILE SCAN -- a measured lens face: read a profilometer scan, fit an asphere
===============================================================================
Every surface elsewhere in this package is designed: exact points, exact
normals. A scanned one is neither. Its points are noisy and quantised, its
x origin is not the vertex, the scan line is tilted, and it has no normals.

**Reading** (``read_profile_scan``). An ASCII DXF, read by its group-code
pairs, for ``POINT``, ``LINE``, ``LWPOLYLINE`` and ``POLYLINE``/``VERTEX``;
any other entity raises, by name. The scan must lie in one plane z =
const; the profile is its (x, y). The unit is the caller's: a DXF often
does not state it. Each meridian is a connected chain of short segments.
Long segments (more than ``LONG_SEGMENT_FACTOR`` times the median, such as
a base line or a chord) and points not on a chain are returned apart, as
references, not as surface.

**Fitting** (``fit_scan_asphere``). An even asphere, its vertex position
and its axis' tilt fitted with its shape, by least squares on the sag
alone (a scan has no normals):

    z = c s**2 / (1 + sqrt(1 - (1 + K) c**2 s**2)) + A2 s**4 + A3 s**6 + ...

with s across the axis and z along it from the vertex. The s**2 term is
left out: it is the curvature again. The polynomial is fitted in s over the
aperture's half width, for conditioning, and reported in the descriptor's
order (``core.glass_curves.AsphereCurve``).

**What a fit reports, and why the correlations.** One meridian determines
the conic constant and the polynomial terms poorly: K and the A's trade
against each other, and near a paraboloid exactly so (at K = -1 a change of
K is a change of A2 s**4, c**3/8 of it). Two fits that describe the surface
equally well can report very different lenses. So:
- **The surface, not the numbers, is what a fit determines.** The number of
  terms, when not given, is the fewest beyond which one more term lowers the
  RMS by less than ``min_gain``.
- **Every fit reports its parameters' correlation** (from the covariance at
  the solution), and a warning names each pair of shape parameters above
  ``correlation_limit``: their values are not separately determined, and
  should not be read as the lens's.
- **K can be fixed** (``conic=``), the usual remedy: then the A's carry the
  departure from that conic.
The vertex position and the tilt are degenerate for a sphere (a tilted
sphere is a shifted sphere), so their correlation is reported apart.

Also reported:
- the residual's RMS and peak-to-valley;
- its slope, by local line fits over ``slope_window_mm``: a ray feels slope,
  not sag. With it, the slope white noise of the residual's RMS would give
  over the same windows: on a noisy scan the slope is mostly noise, and the
  floor says how much;
- with ``design``, the form error: the design surface aligned to the scan
  (vertex and tilt fitted, shape fixed), and what is left.

**Two models of one lens** (``scanned_face``), both kept, so that their
difference is a result:

- ``fitted``: the fitted asphere, exact. How the lens would perform if its
  only error were its fitted R, K and coefficients.
- ``as_measured``: the fitted asphere plus a smooth fit of its residual (a
  local quadratic over ``smoothing_mm``), as a spline through points spaced
  half that, with tangents from the smooth fit's own slope: the normals come
  from the smooth fit, not from the noisy points. How the lens performs with
  its measured form error, mid-spatial ripple included.

A revolved model needs one half-profile, the same at every azimuth. The
residual is folded about the axis: its even part (the mean of +s and -s) is
the rotationally symmetric form error, and goes into the model; its odd
part, the asymmetry the one meridian shows (or what is left of the tilt),
is reported, not modelled.

**The record** (``fit_record``): what a span built from a scan says about
itself in ``profile.json``'s ``fit`` field: the scan file and its digest,
the meridian, the model, the fitted surface, the residual, the warnings,
the smoothing, and the symmetry the revolve assumes (``symmetry_record``).
Its normals are the model's, exact for the model, not the lens's: the
record says so.

**Symmetry.** Revolving one meridian assumes the lens is rotationally
symmetric; ``symmetry_record`` records that as an assumption. Given two or
more meridians, each fitted, the spread between their fitted surfaces is the
measured asymmetry; above ``tolerance_um`` it raises unless the caller
accepts it, and the spread is recorded either way.

numpy only.
===============================================================================
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ...core.glass_curves import AsphereCurve

#: Millimetres per unit.
UNITS_MM = {"mm": 1.0, "um": 1e-3, "cm": 10.0, "m": 1000.0, "in": 25.4}
#: A segment this many times the median length is a reference, not surface.
LONG_SEGMENT_FACTOR = 10.0
#: The entities the reader reads.
ENTITIES = ("POINT", "LINE", "LWPOLYLINE", "POLYLINE", "VERTEX", "SEQEND")


# --- reading ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileScan:
    """A scan's meridians and references, in millimetres, in the scan's (x, y).

    Attributes:
        meridians: One (k, 2) array per meridian, ordered along it, longest first.
        reference_segments: Long segments, as ((x0, y0), (x1, y1)).
        reference_points: (m, 2) points not on any meridian, each once.
        plane_z: The scan plane's z, in mm.
        unit: The unit the file was read in.
        path: The file.
        sha256: Its digest.
        entities: How many of each entity the file holds.
    """

    meridians: List[np.ndarray]
    reference_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]]
    reference_points: np.ndarray
    plane_z: float
    unit: str
    path: str
    sha256: str
    entities: Dict[str, int]

    def summary(self) -> Dict[str, Any]:
        """Plain JSON: the counts, each meridian's extent, the references."""
        return {"path": self.path, "sha256": self.sha256, "unit": self.unit, "plane_z_mm": self.plane_z,
                "entities": dict(self.entities),
                "meridians": [{"points": int(len(m)), "x_mm": [float(m[:, 0].min()), float(m[:, 0].max())],
                               "y_mm": [float(m[:, 1].min()), float(m[:, 1].max())]} for m in self.meridians],
                "reference_segments": [[list(a), list(b)] for a, b in self.reference_segments],
                "reference_points": self.reference_points.tolist()}


def _pairs(text: str) -> List[Tuple[int, str]]:
    lines = text.splitlines()
    if len(lines) % 2:
        lines = lines[:-1]
    out = []
    for k in range(0, len(lines), 2):
        try:
            out.append((int(lines[k].strip()), lines[k + 1].strip()))
        except ValueError:
            raise ValueError(f"line {k + 1}: {lines[k]!r} is not a DXF group code; is this an ASCII DXF?") from None
    return out


def _entities(pairs: List[Tuple[int, str]]) -> List[Tuple[str, List[Tuple[int, str]]]]:
    """The ENTITIES section's entities: (type, its group pairs)."""
    out: List[Tuple[str, List[Tuple[int, str]]]] = []
    in_entities = False
    current: Optional[Tuple[str, List[Tuple[int, str]]]] = None
    for k, (code, value) in enumerate(pairs):
        if code == 2 and k > 0 and pairs[k - 1] == (0, "SECTION"):
            in_entities = value == "ENTITIES"
            continue
        if not in_entities:
            continue
        if code == 0:
            if current is not None:
                out.append(current)
            current = None if value == "ENDSEC" else (value, [])
            if value == "ENDSEC":
                in_entities = False
        elif current is not None:
            current[1].append((code, value))
    if current is not None:
        out.append(current)
    return out


def _xyz(pairs: List[Tuple[int, str]], first: int) -> Tuple[float, float, float]:
    vals = {c: float(v) for c, v in pairs if c in (first, first + 10, first + 20)}
    return vals.get(first, 0.0), vals.get(first + 10, 0.0), vals.get(first + 20, 0.0)


def read_profile_scan(path: Any, *, unit: str) -> ProfileScan:
    """Read a profilometer scan from an ASCII DXF: its meridians and its references, in mm.

    Args:
        path: The file.
        unit: The unit the file's numbers are in, one of ``UNITS_MM``. Stated
            by the caller: a DXF often does not say, and a wrong unit is out
            by a factor of 10 or more.

    Raises:
        ValueError: For an unknown unit, a file that is not ASCII DXF, a
            scan not in one plane z = const, or a meridian that branches or
            closes on itself.
        NotImplementedError: For an entity the reader does not read, by name.
    """
    if unit not in UNITS_MM:
        raise ValueError(f"unit must be one of {sorted(UNITS_MM)}, got {unit!r}")
    scale = UNITS_MM[unit]
    raw = Path(path).read_bytes()
    entities = _entities(_pairs(raw.decode("utf-8", errors="replace")))
    counts: Dict[str, int] = {}
    points3: List[Tuple[float, float, float]] = []
    segments3: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = []
    polyline: Optional[List[Tuple[float, float, float]]] = None
    for kind, pairs in entities:
        counts[kind] = counts.get(kind, 0) + 1
        if kind not in ENTITIES:
            raise NotImplementedError(f"{Path(path).name}: a {kind} entity; the scan reader reads "
                                      f"{', '.join(ENTITIES[:4])} only.")
        if kind == "POINT":
            points3.append(_xyz(pairs, 10))
        elif kind == "LINE":
            segments3.append((_xyz(pairs, 10), _xyz(pairs, 11)))
        elif kind == "LWPOLYLINE":
            elevation = next((float(v) for c, v in pairs if c == 38), 0.0)
            xs = [float(v) for c, v in pairs if c == 10]
            ys = [float(v) for c, v in pairs if c == 20]
            vertices = [(x, y, elevation) for x, y in zip(xs, ys)]
            if any(c == 70 and int(v) & 1 for c, v in pairs):
                vertices.append(vertices[0])
            segments3.extend(zip(vertices[:-1], vertices[1:]))
        elif kind == "POLYLINE":
            polyline = []
        elif kind == "VERTEX":
            if polyline is None:
                raise ValueError(f"{Path(path).name}: a VERTEX outside a POLYLINE.")
            polyline.append(_xyz(pairs, 10))
        elif kind == "SEQEND" and polyline is not None:
            segments3.extend(zip(polyline[:-1], polyline[1:]))
            polyline = None
    zs = [p[2] for p in points3] + [q[2] for s in segments3 for q in s]
    if not zs:
        raise ValueError(f"{Path(path).name}: no points or segments in its ENTITIES section.")
    extent = max(max(abs(v) for p in points3 for v in p[:2]) if points3 else 0.0,
                 max(abs(v) for s in segments3 for q in s for v in q[:2]) if segments3 else 0.0, 1.0)
    if max(zs) - min(zs) > 1e-9 * extent:
        raise ValueError(f"{Path(path).name}: the scan is not in one plane z = const "
                         f"(z from {min(zs)} to {max(zs)}).")
    seg2 = [((a[0] * scale, a[1] * scale), (b[0] * scale, b[1] * scale)) for a, b in segments3]
    pts2 = np.array([(p[0] * scale, p[1] * scale) for p in points3], dtype=float).reshape(-1, 2)
    meridians, refs, nodes = _chains(seg2, 1e-9 * extent * scale)
    loose: List[np.ndarray] = []
    for p in pts2:                                   # off every chain, and each once
        if not any(math.dist(p, q) <= 1e-9 * extent * scale for q in list(nodes) + loose):
            loose.append(p)
    return ProfileScan(meridians=meridians, reference_segments=refs,
                       reference_points=np.array(loose, dtype=float).reshape(-1, 2),
                       plane_z=float(zs[0]) * scale, unit=unit, path=str(path),
                       sha256=hashlib.sha256(raw).hexdigest(), entities=counts)


def _chains(segments, tol):
    """Meridians (chains of short segments), long segments, and every chain node."""
    if not segments:
        return [], [], []
    lengths = np.array([math.dist(a, b) for a, b in segments])
    median = float(np.median(lengths))
    refs = [s for s, l in zip(segments, lengths) if l > LONG_SEGMENT_FACTOR * median]
    short = [s for s, l in zip(segments, lengths) if l <= LONG_SEGMENT_FACTOR * median and l > 0.0]
    key = lambda p: (round(p[0] / tol), round(p[1] / tol))          # noqa: E731
    where: Dict[Tuple[int, int], Tuple[float, float]] = {}
    links: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for a, b in short:
        ka, kb = key(a), key(b)
        where.setdefault(ka, a)
        where.setdefault(kb, b)
        links.setdefault(ka, []).append(kb)
        links.setdefault(kb, []).append(ka)
    for k, nbrs in links.items():
        if len(nbrs) > 2:
            raise ValueError(f"the scan branches at {list(where[k])}: a meridian must be one chain.")
    seen, chains = set(), []
    for start in links:
        if start in seen or len(links[start]) != 1:
            continue
        chain, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [n for n in links[cur] if n != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            chain.append(cur)
            seen.add(cur)
        chains.append(np.array([where[k] for k in chain], dtype=float))
    if len(seen) != len(links):
        raise ValueError("part of the scan closes on itself: a meridian must run from one end to the other.")
    chains.sort(key=lambda c: -len(c))
    return chains, refs, list(where.values())


# --- fitting ------------------------------------------------------------------------------------


@dataclass
class ScanFit:
    """An even asphere fitted to one meridian, with its alignment and what is left.

    Lengths in mm, in the scan's (x, y), unless named otherwise.

    Attributes:
        vertex: The fitted vertex.
        axis: The fitted axis, a unit vector into the lens (sag increasing).
        tilt_deg: The axis' angle from the nearest scan axis (±x or ±y),
            signed anticlockwise.
        radius: The vertex radius, or None for a flat base.
        conic: K.
        coefficients: In the descriptor's order, from s**2 (the first 0).
        s_range: The meridian's extent across the axis.
        rms_um, pv_um: The residual's RMS and peak-to-valley, in µm.
        slope_rms_urad, slope_max_urad: The residual's slope, in µrad.
        slope_noise_floor_urad: The RMS slope that white noise of the
            residual's RMS would give over the same windows: a slope near it
            is noise, not form error.
        correlation: The parameters' correlation matrix.
        names: The parameters, in the matrix's order.
        max_shape_correlation: The largest |correlation| between shape
            parameters (curvature, K, the A's).
        alignment_correlation: The largest |correlation| between vertex and
            tilt parameters.
        candidates: With the number of terms chosen, each tried count's RMS
            and shape correlation.
        warnings: Each pair of shape parameters correlated beyond the limit.
        conic_fixed: Whether K was fixed rather than fitted.
        form_error: With a design: the aligned design's residual.
        s, residual_um: The residual along the meridian, for plotting.
    """

    vertex: Tuple[float, float]
    axis: Tuple[float, float]
    tilt_deg: float
    radius: Optional[float]
    conic: float
    coefficients: List[float]
    s_range: Tuple[float, float]
    rms_um: float
    pv_um: float
    slope_rms_urad: float
    slope_max_urad: float
    slope_noise_floor_urad: float
    correlation: np.ndarray
    names: List[str]
    max_shape_correlation: float
    alignment_correlation: float
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    conic_fixed: bool = False
    form_error: Optional[Dict[str, Any]] = None
    s: np.ndarray = field(default_factory=lambda: np.zeros(0))
    residual_um: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def curve(self) -> AsphereCurve:
        """The fitted face as a 2D asphere edge over the measured extent, in the scan's (x, y)."""
        return AsphereCurve(self.vertex, self.axis, self.radius, self.conic, self.coefficients, *self.s_range)

    def descriptor(self) -> Dict[str, Any]:
        return self.curve().descriptor()

    def summary(self) -> Dict[str, Any]:
        """Plain JSON, without the residual arrays."""
        out = {"vertex_mm": list(self.vertex), "axis": list(self.axis), "tilt_deg": self.tilt_deg,
               "radius_mm": self.radius, "conic": self.conic, "coefficients": list(self.coefficients),
               "s_range_mm": list(self.s_range), "rms_um": self.rms_um, "pv_um": self.pv_um,
               "slope_rms_urad": self.slope_rms_urad, "slope_max_urad": self.slope_max_urad,
               "slope_noise_floor_urad": self.slope_noise_floor_urad, "names": list(self.names), "correlation": np.round(self.correlation, 6).tolist(),
               "max_shape_correlation": self.max_shape_correlation,
               "alignment_correlation": self.alignment_correlation, "candidates": list(self.candidates),
               "warnings": list(self.warnings), "conic_fixed": self.conic_fixed}
        if self.form_error is not None:
            out["form_error"] = {k: v for k, v in self.form_error.items() if k not in ("s", "residual_um")}
        return out


def _frame(theta: float):
    a = np.array([math.cos(theta), math.sin(theta)])
    return a, np.array([-a[1], a[0]])


def _sag(s, c, k, terms, s_half):
    root = np.maximum(1.0 - (1.0 + k) * c * c * s * s, 0.0)
    z = c * s * s / (1.0 + np.sqrt(root))
    u2 = (s / s_half) ** 2
    power = u2 * u2
    for a in terms:
        z = z + a * power
        power = power * u2
    return z


def _residual(p, points, s_half, shape=None, conic=None):
    """Sag residual of every point. ``p``: vertex x, y, axis angle, then c, K, A' (K omitted when
    ``conic`` is fixed; all three omitted when ``shape`` is)."""
    a, left = _frame(p[2])
    rel = points - p[:2]
    s, z = rel @ left, rel @ a
    if shape is not None:
        c, k, terms = shape
    elif conic is not None:
        c, k, terms = p[3], conic, p[4:]
    else:
        c, k, terms = p[3], p[4], p[5:]
    if np.any(1.0 - (1.0 + k) * c * c * s * s <= 0.0):
        return np.full(len(points), 1e3)                    # past the conic's equator: rejected
    return z - _sag(s, c, k, terms, s_half)


def _least_squares(fun, p0, scales, iterations=300):
    """Levenberg-Marquardt with central-difference Jacobians; (p, residual, J)."""
    p = np.asarray(p0, dtype=float).copy()
    r = fun(p)
    cost = float(r @ r)
    lam = 1e-3

    def jac(p):
        cols = []
        for j in range(len(p)):
            h = 1e-6 * scales[j]
            dp = np.zeros_like(p)
            dp[j] = h
            cols.append((fun(p + dp) - fun(p - dp)) / (2 * h))
        return np.stack(cols, axis=1)

    J = jac(p)
    for _ in range(iterations):
        H, g = J.T @ J, J.T @ r
        d = np.diag(H).copy()
        d[d == 0.0] = 1.0
        try:
            step = np.linalg.solve(H + lam * np.diag(d), -g)
        except np.linalg.LinAlgError:
            lam *= 10.0
            continue
        trial = p + step
        r_t = fun(trial)
        c_t = float(r_t @ r_t)
        if c_t < cost:
            done = cost - c_t <= 1e-15 * max(cost, 1e-300)
            p, r, cost = trial, r_t, c_t
            lam = max(lam / 3.0, 1e-12)
            J = jac(p)
            if done:
                break
        else:
            lam *= 4.0
            if lam > 1e12:
                break
    return p, r, J


def _correlation(J, r, n_params):
    dof = max(len(r) - n_params, 1)
    cov = float(r @ r) / dof * np.linalg.pinv(J.T @ J)
    sd = np.sqrt(np.maximum(np.diag(cov), 1e-300))
    return cov / np.outer(sd, sd)


def _slopes(s, residual, window):
    """The residual's slope at each point, from a line fitted to the points within ``window`` / 2,
    and each fit's noise floor: the slope's standard error were the residual white noise of its RMS."""
    order = np.argsort(s)
    s, residual = s[order], residual[order]
    out, floor = np.empty_like(s), np.empty_like(s)
    sigma = float(np.sqrt(np.mean(residual * residual)))
    for i, si in enumerate(s):
        sel = np.abs(s - si) <= 0.5 * window
        if sel.sum() < 3:
            out[i] = floor[i] = np.nan
            continue
        x = s[sel] - s[sel].mean()
        sxx = float((x * x).sum())
        out[i] = float((x * (residual[sel] - residual[sel].mean())).sum() / sxx)
        floor[i] = sigma / math.sqrt(sxx)
    ok = np.isfinite(out)
    return out[ok], floor[ok]


def _tilt(axis) -> float:
    angle = math.degrees(math.atan2(axis[1], axis[0]))
    nearest = 90.0 * round(angle / 90.0)
    return angle - nearest


def _initial(points):
    """Vertex, axis angle and curvature from the chord and a parabola (the start is the paraboloid, K = -1)."""
    chord = points[-1] - points[0]
    u = chord / np.linalg.norm(chord)
    normal = np.array([-u[1], u[0]])
    dist = (points - points[0]) @ normal
    apex = points[int(np.argmax(np.abs(dist)))]
    a = -normal * np.sign(dist[int(np.argmax(np.abs(dist)))])     # from the apex towards the chord
    left = np.array([-a[1], a[0]])
    s, z = (points - apex) @ left, (points - apex) @ a
    q2, q1, q0 = np.polyfit(s, z, 2)
    s0 = -q1 / (2 * q2)
    vertex = apex + s0 * left + (q0 - q1 * q1 / (4 * q2)) * a
    return vertex, math.atan2(a[1], a[0]), 2.0 * q2


def fit_scan_asphere(points: np.ndarray, *, terms: Optional[int] = None, max_terms: int = 4,
                     min_gain: float = 0.1, conic: Optional[float] = None, correlation_limit: float = 0.98,
                     design: Optional[Mapping[str, Any]] = None, slope_window_mm: float = 1.0) -> ScanFit:
    """Fit an even asphere, with its vertex and tilt, to one scanned meridian.

    Args:
        points: (k, 2) the meridian, ordered along it, in mm.
        terms: Polynomial terms beyond the conic (A2 s**4, A3 s**6, ...);
            None to choose: the fewest, up to ``max_terms``, beyond which one
            more term lowers the RMS by less than ``min_gain`` (a fraction).
        conic: K fixed at this value; None to fit it.
        correlation_limit: Shape parameters correlated beyond this are named
            in the fit's ``warnings``.
        design: A design surface, ``{"radius", "conic", "coefficients"}`` in
            the descriptor's convention (coefficients from s**2), to report
            the form error against.
        slope_window_mm: The width over which the residual's slope is taken.

    Raises:
        ValueError: For fewer points than parameters.
    """
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("points must be (k, 2)")
    vertex0, theta0, c0 = _initial(points)
    a0, left0 = _frame(theta0)
    s0 = (points - vertex0) @ left0
    s_half = float(np.abs(s0).max())
    z_span = float(np.ptp((points - vertex0) @ a0))
    counts = [terms] if terms is not None else list(range(max_terms + 1))
    k_free = conic is None
    base = 5 if k_free else 4
    fits = []
    previous = np.r_[vertex0, theta0, c0, -1.0] if k_free else np.r_[vertex0, theta0, c0]
    for m in counts:
        if len(points) <= base + m:
            raise ValueError(f"{len(points)} points cannot fit {base + m} parameters")
        scales = np.r_[s_half, s_half, 1.0, max(abs(c0), 1e-6), [1.0] * k_free, np.full(m, max(z_span, 1e-6))]
        start = np.r_[previous, np.zeros(base + m - len(previous))][:base + m]
        p, r, J = _least_squares(lambda q: _residual(q, points, s_half, conic=conic), start, scales)
        corr = _correlation(J, r, len(p))
        shape = np.abs(corr[3:, 3:] - np.eye(len(p) - 3))
        fits.append({"terms": m, "p": p, "r": r, "corr": corr,
                     "rms_um": float(np.sqrt(np.mean(r * r))) * 1e3,
                     "max_shape_correlation": float(shape.max()) if len(p) > 4 else 0.0,
                     "alignment_correlation": float(np.abs(corr[:3, :3] - np.eye(3)).max())})
        previous = p
    chosen = fits[-1]
    if terms is None:
        chosen = fits[0]
        for nxt in fits[1:]:
            if nxt["rms_um"] < (1.0 - min_gain) * chosen["rms_um"]:
                chosen = nxt
            else:
                break
    candidates = [{"terms": f["terms"], "rms_um": f["rms_um"], "max_shape_correlation": f["max_shape_correlation"],
                   "chosen": f is chosen} for f in fits]
    m, p, r, corr = chosen["terms"], chosen["p"], chosen["r"], chosen["corr"]
    shape_corr, align_corr = chosen["max_shape_correlation"], chosen["alignment_correlation"]
    names = ["vertex_x", "vertex_y", "axis_angle", "curvature"] + ["conic"] * k_free + \
        [f"A{j}" for j in range(2, 2 + m)]
    warnings = [f"{names[i]} and {names[j]} are correlated {corr[i, j]:+.4f}: not separately determined"
                for i in range(3, len(names)) for j in range(i + 1, len(names))
                if abs(corr[i, j]) > correlation_limit]
    if not k_free:
        p = np.r_[p[:4], conic, p[4:]]

    a, left = _frame(p[2])
    s = (points - p[:2]) @ left
    c, k = float(p[3]), float(p[4])
    coefficients = [0.0] + [float(v) / s_half ** (2 * j) for j, v in enumerate(p[5:], start=2)]
    slopes, floor = _slopes(s, r, slope_window_mm)
    fit = ScanFit(
        vertex=(float(p[0]), float(p[1])), axis=(float(a[0]), float(a[1])), tilt_deg=_tilt(a),
        radius=None if abs(c) < 1e-15 else 1.0 / c, conic=k, coefficients=coefficients,
        s_range=(float(s.min()), float(s.max())) if s[0] < s[-1] else (float(s.max()), float(s.min())),
        rms_um=float(np.sqrt(np.mean(r * r))) * 1e3, pv_um=float(np.ptp(r)) * 1e3,
        slope_rms_urad=float(np.sqrt(np.mean(slopes ** 2))) * 1e6 if slopes.size else float("nan"),
        slope_max_urad=float(np.abs(slopes).max()) * 1e6 if slopes.size else float("nan"),
        slope_noise_floor_urad=float(np.sqrt(np.mean(floor ** 2))) * 1e6 if floor.size else float("nan"),
        correlation=corr, names=names, max_shape_correlation=shape_corr, alignment_correlation=align_corr,
        candidates=candidates if terms is None else [], warnings=warnings, conic_fixed=not k_free,
        s=s, residual_um=r * 1e3)
    if design is not None:
        fit.form_error = _form_error(points, design, p, s_half, slope_window_mm)
    return fit


def _form_error(points, design, p_fit, s_half, window):
    """The design surface aligned to the scan (vertex and tilt fitted, shape fixed), and what is left."""
    radius = design.get("radius")
    c = 0.0 if radius is None else 1.0 / float(radius)
    k = float(design.get("conic", 0.0))
    coefficients = [float(v) for v in design.get("coefficients", [])]
    if coefficients and coefficients[0] != 0.0:
        raise ValueError("a design's s**2 coefficient must be 0 here: fold it into the radius")
    terms = [v * s_half ** (2 * j) for j, v in enumerate(coefficients[1:], start=2)]
    shape = (c, k, terms)
    p, r, J = _least_squares(lambda q: _residual(np.r_[q, 0.0, 0.0], points, s_half, shape), p_fit[:3],
                             np.r_[s_half, s_half, 1.0])
    a, left = _frame(p[2])
    s = (points - p[:2]) @ left
    slopes, floor = _slopes(s, r, window)
    return {"vertex_mm": [float(p[0]), float(p[1])], "axis": [float(a[0]), float(a[1])], "tilt_deg": _tilt(a),
            "rms_um": float(np.sqrt(np.mean(r * r))) * 1e3, "pv_um": float(np.ptp(r)) * 1e3,
            "slope_rms_urad": float(np.sqrt(np.mean(slopes ** 2))) * 1e6 if slopes.size else float("nan"),
            "slope_max_urad": float(np.abs(slopes).max()) * 1e6 if slopes.size else float("nan"),
            "slope_noise_floor_urad": float(np.sqrt(np.mean(floor ** 2))) * 1e6 if floor.size else float("nan"),
            "s": s, "residual_um": r * 1e3}



# --- the two models, the record, the symmetry -------------------------------------------------------


def _sag_of(fit: "ScanFit", s):
    c = 0.0 if fit.radius is None else 1.0 / fit.radius
    z = c * s * s / (1.0 + np.sqrt(np.maximum(1.0 - (1.0 + fit.conic) * c * c * s * s, 0.0)))
    for i, a in enumerate(fit.coefficients, start=1):
        z = z + a * s ** (2 * i)
    return z


def _sag_slope_of(fit: "ScanFit", s):
    c = 0.0 if fit.radius is None else 1.0 / fit.radius
    dz = c * s / np.sqrt(np.maximum(1.0 - (1.0 + fit.conic) * c * c * s * s, 1e-300))
    for i, a in enumerate(fit.coefficients, start=1):
        dz = dz + 2 * i * a * s ** (2 * i - 1)
    return dz


def residual_parts(fit: "ScanFit") -> Dict[str, np.ndarray]:
    """The residual folded about the fitted axis: its even and odd parts on |s|, in mm.

    Each side is interpolated onto the other's |s|; only the |s| both sides
    cover is kept.
    """
    s, r = fit.s, fit.residual_um * 1e-3
    pos, neg = s >= 0.0, s <= 0.0
    if pos.sum() < 2 or neg.sum() < 2:
        raise ValueError("the meridian does not cross its fitted axis: it cannot be folded")
    sp, rp = s[pos], r[pos]
    sn, rn = -s[neg], r[neg]
    op, on = np.argsort(sp), np.argsort(sn)
    sp, rp, sn, rn = sp[op], rp[op], sn[on], rn[on]
    top = min(sp.max(), sn.max())
    grid = np.unique(np.r_[sp[sp <= top], sn[sn <= top]])
    a, b = np.interp(grid, sp, rp), np.interp(grid, sn, rn)
    return {"abs_s": grid, "even": 0.5 * (a + b), "odd": 0.5 * (a - b)}


def _smooth(x, y, at, half_width):
    """A local quadratic, tricube-weighted over ``half_width``: (value, slope) at ``at``."""
    value, slope = np.empty(len(at)), np.empty(len(at))
    for k, x0 in enumerate(at):
        d = x - x0
        w = np.clip(1.0 - (np.abs(d) / half_width) ** 3, 0.0, None) ** 3
        sel = w > 0.0
        if sel.sum() < 4:
            raise ValueError(f"too few points within {half_width} mm of s = {x0:.3g} to smooth the residual")
        A = np.stack([np.ones(sel.sum()), d[sel], d[sel] ** 2], axis=1) * np.sqrt(w[sel])[:, None]
        coef, *_ = np.linalg.lstsq(A, y[sel] * np.sqrt(w[sel]), rcond=None)
        value[k], slope[k] = coef[0], coef[1]
    return value, slope


def scanned_face(fit: "ScanFit", model: str, *, vertex: Tuple[float, float] = (0.0, 0.0),
                 axis: Tuple[float, float] = (1.0, 0.0), half_width_mm: Optional[float] = None,
                 smoothing_mm: float = 1.0) -> Dict[str, Any]:
    """A curve descriptor for a scanned face, placed at ``vertex`` with its sag along ``axis``.

    Args:
        model: ``"fitted"`` (the asphere) or ``"as_measured"`` (the asphere
            plus the residual's even part, smoothed, as a spline).
        half_width_mm: The face's half width; by default the most both sides
            of the meridian cover.
        smoothing_mm: The smoothing's half width, for ``as_measured``.

    Returns:
        The descriptor, symmetric about its axis from -half_width to
        +half_width (its ``domain`` covers it), ready for a glass path.

    Raises:
        ValueError: For an unknown model, or a half width beyond the scan.
    """
    parts = residual_parts(fit)
    reach = float(parts["abs_s"].max())
    h = reach if half_width_mm is None else float(half_width_mm)
    if h > reach + 1e-9:
        raise ValueError(f"half width {h} mm is beyond what both sides of the scan cover ({reach:.4g} mm)")
    if model == "fitted":
        return AsphereCurve(vertex, axis, fit.radius, fit.conic, fit.coefficients, -h, h).descriptor()
    if model != "as_measured":
        raise ValueError(f"model must be 'fitted' or 'as_measured', got {model!r}")
    step = 0.5 * smoothing_mm
    count = max(2, int(math.ceil(h / step)))
    abs_s = np.linspace(0.0, h, count + 1)
    even, even_slope = _smooth(parts["abs_s"], parts["even"], abs_s, smoothing_mm)
    even_slope[0] = 0.0                                  # an even function is flat on the axis
    ss = np.r_[-abs_s[:0:-1], abs_s]
    z = np.r_[even[:0:-1], even] + _sag_of(fit, ss)
    dz = np.r_[-even_slope[:0:-1], even_slope] + _sag_slope_of(fit, ss)
    a = np.asarray(axis, dtype=float) / np.linalg.norm(axis)
    left = np.array([-a[1], a[0]])
    v = np.asarray(vertex, dtype=float)
    points = v + z[:, None] * a + ss[:, None] * left
    tangents = dz[:, None] * a + left
    tangents /= np.linalg.norm(tangents, axis=1, keepdims=True)
    return {"type": "spline", "points": points.tolist(), "tangents": tangents.tolist()}


def symmetry_record(fits: Sequence["ScanFit"], *, tolerance_um: float = 2.0, accept: bool = False) -> Dict[str, Any]:
    """What a revolve of these meridians assumes, or measures, about the lens's symmetry.

    One meridian: rotational symmetry is an assumption, recorded with the
    residual's odd part (the asymmetry that meridian alone shows). Two or
    more: each fitted surface against the first, over the |s| all cover;
    the largest RMS sag difference is the spread.

    Raises:
        ValueError: If the spread exceeds ``tolerance_um`` and ``accept`` is
            False: a revolved model of an asymmetric lens is a plausible wrong
            number.
    """
    if not fits:
        raise ValueError("no meridians")
    odd = [float(np.sqrt(np.mean(residual_parts(f)["odd"] ** 2))) * 1e3 for f in fits]
    if len(fits) == 1:
        return {"meridians": 1, "status": "assumed",
                "note": "rotational symmetry assumed: one meridian was scanned",
                "odd_residual_rms_um": odd[0]}
    reach = min(float(residual_parts(f)["abs_s"].max()) for f in fits)
    grid = np.linspace(-reach, reach, 201)
    base = _sag_of(fits[0], grid)
    spreads = [float(np.sqrt(np.mean((_sag_of(f, grid) - base) ** 2))) * 1e3 for f in fits[1:]]
    spread = max(spreads)
    if spread > tolerance_um and not accept:
        raise ValueError(f"the meridians' fitted surfaces differ by up to {spread:.3g} um RMS (tolerance "
                         f"{tolerance_um:g} um): the lens is not rotationally symmetric to that tolerance. "
                         "Revolve it only with accept=True, and the spread is recorded.")
    return {"meridians": len(fits), "status": "accepted" if spread > tolerance_um else "checked",
            "spread_um": spread, "tolerance_um": tolerance_um, "odd_residual_rms_um": odd}


def fit_record(fit: "ScanFit", model: str, *, scan: Optional[ProfileScan] = None, meridian: int = 0,
               smoothing_mm: Optional[float] = None, symmetry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The record a span built from a scan carries in ``profile.json``'s ``fit``. Plain JSON."""
    if model not in ("fitted", "as_measured"):
        raise ValueError(f"model must be 'fitted' or 'as_measured', got {model!r}")
    s = fit.summary()
    record: Dict[str, Any] = {
        "model": model,
        "normals": "the model's, exact for the model; not measured (a scan has no normals)",
        "source": None if scan is None else {"path": Path(scan.path).name, "sha256": scan.sha256,
                                             "unit": scan.unit, "meridian": meridian},
        "surface": {"radius": s["radius_mm"], "conic": s["conic"], "coefficients": s["coefficients"],
                    "conic_fixed": s["conic_fixed"]},
        "alignment": {"vertex_mm": s["vertex_mm"], "axis": s["axis"], "tilt_deg": s["tilt_deg"]},
        "residual": {k: s[k] for k in ("rms_um", "pv_um", "slope_rms_urad", "slope_max_urad",
                                       "slope_noise_floor_urad")},
        "warnings": s["warnings"],
        "symmetry": symmetry if symmetry is not None else symmetry_record([fit]),
    }
    if model == "as_measured":
        record["smoothing_mm"] = 1.0 if smoothing_mm is None else float(smoothing_mm)
    if fit.form_error is not None:
        record["form_error"] = s["form_error"]
    return record


__all__ = ["ProfileScan", "ScanFit", "UNITS_MM", "fit_record", "fit_scan_asphere", "read_profile_scan",
           "residual_parts", "scanned_face", "symmetry_record"]
