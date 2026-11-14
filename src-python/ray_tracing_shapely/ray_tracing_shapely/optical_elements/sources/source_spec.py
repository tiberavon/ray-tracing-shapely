"""
Python-specific module: source_spec
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
SOURCE SPEC -- one light source, described once, built in 2D and in 3D
===============================================================================
``profile.json`` hands an element's optics from 2D to 3D; its ``sources``
list (schema 1.3; 1.4 adds the ``rayfile`` kind) hands over the light it is
designed for. A source
specification is a JSON-shaped dict in the 2D scene's coordinates, extended
by one coordinate out of the plane:

    scene frame (a, b, c): (a, b) is the 2D scene plane, c is out of it.
    world (Optiland):      x = a, y = c, z = b

The (a, b) -> (a, 0, b) half is the scene bridge's plane mapping (C-BRIDGE-10),
so a source lands where the optics land. The c -> +y half is this module's.

Fields (``validate_source_spec`` fills the defaults):

    name             str, unique within a profile
    kind             "pencil" (one ray), "point", "patch" (a flat rectangle),
                     "rayfile" (a measured LED's rays, below)
    position         [a, b] or [a, b, c]; for a patch, the point ``anchor`` names
    direction_deg    the emission axis, an angle in the 2D plane from +a
                     towards +b. Emission axes out of the plane are not
                     supported: every optic here has its axis in the plane.
    emission         "uniform" (equal intensity in every direction of a cone)
                     or "lambertian" (intensity ~ cos of the angle from the
                     axis); not for a pencil
    half_angle_deg   the cone's half-angle; a lambertian source fills the
                     hemisphere, so it must be 90 (the default for it)
    size             a patch's [in_plane, out_of_plane] lengths
    roll_deg         a patch's turn about its axis: 0 puts its first side in
                     the plane; positive turns that side from the plane
                     towards +c
    anchor           where ``position`` is on a patch, as fractions of
                     ``size``: [0.5, 0.5] its centre (default), [0, 0] a corner
    flux, flux_unit  total flux, "W" (default) or "lm"
    wavelength_um    one wavelength, in micrometres

A ``rayfile`` source (schema 1.4) is placed as ``rayfile_frame`` places a
file: ``position`` its origin, ``direction_deg`` its z, ``roll_deg`` a turn
about it. It has no emission law, size or flux of its own; instead:

    rayfile          {"path", "format", "n_rays", "flux", "flux_unit", "sha256"}
                     ``format`` is the argument ``read_rayfile`` takes (one
                     of its ``FORMATS``). A relative ``path`` is relative to
                     the profile's folder (the builders' ``base_dir``). The
                     count, flux and digest are the file's when the spec was
                     written; a file that no longer matches them is refused.
    slice            {"max_offset_mm", "kept_share", "rays_kept"}: how the 2D
                     section is taken (``slice_rayfile``), and what it kept.
                     Needed in 2D only; 3D traces every ray.
    wavelength_um    optional: one wavelength; the file's spectrum otherwise
                     (its peak, in 2D).

``flux`` and ``flux_unit`` are filled in from the ``rayfile`` block (given,
they must equal it).

The patch's axes, for an emission direction d = (da, db) in the plane:
    n     = (da, db, 0)             the emission axis
    p     = (-db, da, 0)            in the plane, across the axis
    o     = (0, 0, 1)               out of the plane
    e_in  = cos(roll) p + sin(roll) o     the first side (``size[0]``)
    e_out = -sin(roll) p + cos(roll) o    the second side (``size[1]``)

2D: a 2D scene sees the section of a source by its plane, c = 0.
- A pencil or a point must lie in the plane.
- A patch is a rectangle square to an axis that lies in the plane, so its
  section is a segment along p, found exactly (``patch_section``). It need
  not be the patch's in-plane side: a rolled patch's section is longer than
  its side (``size[0] / cos(roll)`` when a corner is on the plane), and an
  offset patch can miss the plane entirely.

The 2D source is a RaySetSource with deterministic samples: positions at the
midpoints of equal steps along the section, angles at the midpoints of equal
steps across the cone, each ray weighted by its emission law's in-plane
intensity (1, or the cosine). In a plane through its axis, a 3D uniform or
Lambertian emitter has exactly that intensity per unit angle, which is what
makes the 2D source the meridional section of the 3D one. Brightnesses are
scaled so the largest is 1, and ``flux_per_brightness`` carries the flux back
-- a 2D section's flux is the flux of the rays in it, a share of the whole
that the section alone cannot know, so the 2D value is per unit brightness of
the section's own rays, not the 3D source's total.
===============================================================================
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .ray_set_source import RaySetSource
from .rayfile import FORMATS, Rayfile, read_rayfile
from .rayfile_slice import slice_rayfile

if TYPE_CHECKING:
    from ...core.scene import Scene

KINDS = ("pencil", "point", "patch", "rayfile")
EMISSIONS = ("uniform", "lambertian")
FLUX_UNITS = ("W", "lm")

#: Distance from the 2D plane below which a point is taken to lie in it, in
#: scene units.
PLANE_TOL = 1e-9

Vec3 = Tuple[float, float, float]


def _floats(value: Any, n: Sequence[int], field: str, name: str) -> List[float]:
    try:
        out = [float(v) for v in value]
    except (TypeError, ValueError):
        raise ValueError(f"source {name!r}: {field} must be a list of numbers, got {value!r}") from None
    if len(out) not in n:
        raise ValueError(f"source {name!r}: {field} must have {' or '.join(map(str, n))} numbers, "
                         f"got {len(out)}")
    if not all(math.isfinite(v) for v in out):
        raise ValueError(f"source {name!r}: {field} must be finite, got {out}")
    return out


def validate_source_spec(spec: Mapping[str, Any]) -> Dict[str, Any]:
    """Check a source specification and return it with its defaults filled in.

    Raises:
        ValueError: On any unknown field, missing field, or value the 3D
            engine cannot represent as stated (a lambertian cone narrower
            than the hemisphere, a uniform patch filling the hemisphere).
            Loud, because a source quietly built as something else is a
            plausible wrong number in every result that follows.
    """
    if not isinstance(spec, Mapping):
        raise ValueError(f"a source spec is a dict, got {type(spec).__name__}")
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"a source spec needs a non-empty 'name', got {name!r}")
    kind = spec.get("kind")
    if kind not in KINDS:
        raise ValueError(f"source {name!r}: kind must be one of {KINDS}, got {kind!r}")

    if kind == "rayfile":
        return _validate_rayfile_spec(spec, name)
    allowed = {"name", "kind", "position", "direction_deg", "flux", "flux_unit", "wavelength_um"}
    if kind != "pencil":
        allowed |= {"emission", "half_angle_deg"}
    if kind == "patch":
        allowed |= {"size", "roll_deg", "anchor"}
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise ValueError(f"source {name!r}: unknown field(s) {unknown} for kind {kind!r}")

    out: Dict[str, Any] = {"name": name, "kind": kind}
    if "position" not in spec:
        raise ValueError(f"source {name!r}: needs 'position'")
    pos = _floats(spec["position"], (2, 3), "position", name)
    out["position"] = pos if len(pos) == 3 else pos + [0.0]
    if "direction_deg" not in spec:
        raise ValueError(f"source {name!r}: needs 'direction_deg'")
    out["direction_deg"] = float(spec["direction_deg"])

    if kind != "pencil":
        emission = spec.get("emission")
        if emission not in EMISSIONS:
            raise ValueError(f"source {name!r}: emission must be one of {EMISSIONS}, got {emission!r}")
        out["emission"] = emission
        default_half = 90.0 if emission == "lambertian" else None
        half = spec.get("half_angle_deg", default_half)
        if half is None:
            raise ValueError(f"source {name!r}: a uniform source needs 'half_angle_deg'")
        half = float(half)
        if not 0.0 < half <= 90.0:
            raise ValueError(f"source {name!r}: half_angle_deg must be in (0, 90], got {half}")
        if emission == "lambertian" and half != 90.0:
            raise ValueError(f"source {name!r}: a lambertian source fills the hemisphere (half_angle_deg 90); "
                             f"a lambertian cone cut at {half} deg has no 3D counterpart")
        if emission == "uniform" and half == 90.0 and kind == "patch":
            raise ValueError(f"source {name!r}: a uniform patch filling the hemisphere has no 3D counterpart "
                             "(the 3D extended source is lambertian at 90 deg); use a cone below 90 deg")
        out["half_angle_deg"] = half

    if kind == "patch":
        size = _floats(spec.get("size"), (2,), "size", name) if "size" in spec else None
        if size is None or min(size) <= 0.0:
            raise ValueError(f"source {name!r}: a patch needs 'size': [in_plane, out_of_plane], both > 0")
        out["size"] = size
        out["roll_deg"] = float(spec.get("roll_deg", 0.0))
        anchor = _floats(spec.get("anchor", [0.5, 0.5]), (2,), "anchor", name)
        if not all(0.0 <= v <= 1.0 for v in anchor):
            raise ValueError(f"source {name!r}: anchor fractions must be in [0, 1], got {anchor}")
        out["anchor"] = anchor

    out["flux"] = float(spec.get("flux", 1.0))
    if not out["flux"] > 0.0:
        raise ValueError(f"source {name!r}: flux must be > 0, got {out['flux']}")
    out["flux_unit"] = spec.get("flux_unit", "W")
    if out["flux_unit"] not in FLUX_UNITS:
        raise ValueError(f"source {name!r}: flux_unit must be one of {FLUX_UNITS}, got {out['flux_unit']!r}")
    out["wavelength_um"] = float(spec.get("wavelength_um", 0.55))
    if not out["wavelength_um"] > 0.0:
        raise ValueError(f"source {name!r}: wavelength_um must be > 0, got {out['wavelength_um']}")
    return out


_RAYFILE_FIELDS = {"path", "format", "n_rays", "flux", "flux_unit", "sha256"}
_SLICE_FIELDS = {"max_offset_mm", "kept_share", "rays_kept"}


def _validate_rayfile_spec(spec: Mapping[str, Any], name: str) -> Dict[str, Any]:
    allowed = {"name", "kind", "position", "direction_deg", "roll_deg", "rayfile", "slice", "wavelength_um",
               "flux", "flux_unit"}
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise ValueError(f"source {name!r}: unknown field(s) {unknown} for kind 'rayfile'")
    out: Dict[str, Any] = {"name": name, "kind": "rayfile"}
    for field in ("position", "direction_deg", "rayfile"):
        if field not in spec:
            raise ValueError(f"source {name!r}: needs {field!r}")
    pos = _floats(spec["position"], (2, 3), "position", name)
    out["position"] = pos if len(pos) == 3 else pos + [0.0]
    out["direction_deg"] = float(spec["direction_deg"])
    out["roll_deg"] = float(spec.get("roll_deg", 0.0))

    rf = spec["rayfile"]
    if not isinstance(rf, Mapping) or set(rf) != _RAYFILE_FIELDS:
        raise ValueError(f"source {name!r}: 'rayfile' must have exactly {sorted(_RAYFILE_FIELDS)}, got "
                         f"{sorted(rf) if isinstance(rf, Mapping) else rf!r}")
    if not isinstance(rf["path"], str) or not rf["path"]:
        raise ValueError(f"source {name!r}: rayfile path must be a non-empty string, got {rf['path']!r}")
    if rf["format"] not in FORMATS:
        raise ValueError(f"source {name!r}: rayfile format must be one of {FORMATS}, got {rf['format']!r}")
    if isinstance(rf["n_rays"], bool) or not isinstance(rf["n_rays"], int) or rf["n_rays"] < 1:
        raise ValueError(f"source {name!r}: rayfile n_rays must be a positive integer, got {rf['n_rays']!r}")
    flux = float(rf["flux"])
    if not flux > 0.0 or rf["flux_unit"] not in FLUX_UNITS:
        raise ValueError(f"source {name!r}: rayfile flux must be > 0 in one of {FLUX_UNITS}, "
                         f"got {rf['flux']!r} {rf['flux_unit']!r}")
    digest = rf["sha256"]
    if not (isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)):
        raise ValueError(f"source {name!r}: rayfile sha256 must be 64 lowercase hex digits, got {digest!r}")
    out["rayfile"] = {"path": rf["path"], "format": rf["format"], "n_rays": rf["n_rays"], "flux": flux,
                      "flux_unit": rf["flux_unit"], "sha256": digest}
    for field, value in (("flux", flux), ("flux_unit", rf["flux_unit"])):
        if field in spec and spec[field] != value:
            raise ValueError(f"source {name!r}: a rayfile's {field} is its file's, {value!r}, got {spec[field]!r}")
    out["flux"], out["flux_unit"] = flux, rf["flux_unit"]

    if "slice" in spec:
        sl = spec["slice"]
        if not isinstance(sl, Mapping) or set(sl) != _SLICE_FIELDS:
            raise ValueError(f"source {name!r}: 'slice' must have exactly {sorted(_SLICE_FIELDS)}, got "
                             f"{sorted(sl) if isinstance(sl, Mapping) else sl!r}")
        limit, share = float(sl["max_offset_mm"]), float(sl["kept_share"])
        kept = sl["rays_kept"]
        if limit < 0.0 or not 0.0 <= share <= 1.0 or isinstance(kept, bool) or not isinstance(kept, int) \
                or not 0 <= kept <= rf["n_rays"]:
            raise ValueError(f"source {name!r}: slice needs max_offset_mm >= 0, kept_share in [0, 1] and "
                             f"rays_kept in [0, n_rays], got {dict(sl)}")
        out["slice"] = {"max_offset_mm": limit, "kept_share": share, "rays_kept": kept}
    wl = spec.get("wavelength_um")
    if wl is not None and not float(wl) > 0.0:
        raise ValueError(f"source {name!r}: wavelength_um must be > 0, got {wl}")
    out["wavelength_um"] = None if wl is None else float(wl)
    return out


def file_sha256(path: Any) -> str:
    """The SHA-256 digest of a file, as 64 lowercase hex digits."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _resolve(path: str, base_dir: Any) -> Path:
    p = Path(path)
    return p if p.is_absolute() or base_dir is None else Path(base_dir) / p


def spec_rayfile(spec: Mapping[str, Any], base_dir: Any = None) -> Rayfile:
    """Read a ``rayfile`` spec's file, checked against the count, flux and digest the spec recorded.

    Args:
        spec: A ``rayfile`` source spec (validated here).
        base_dir: The folder a relative path is relative to: the profile's.

    Raises:
        ValueError: If the spec is not a rayfile's, or the file is not the
            one it was written for.
    """
    spec = validate_source_spec(spec)
    if spec["kind"] != "rayfile":
        raise ValueError(f"source {spec['name']!r} is a {spec['kind']}, not a rayfile")
    rec = spec["rayfile"]
    path = _resolve(rec["path"], base_dir)
    digest = file_sha256(path)
    if digest != rec["sha256"]:
        raise ValueError(f"source {spec['name']!r}: {path} is not the file the spec was written for "
                         f"(sha256 {digest[:12]}..., the spec's {rec['sha256'][:12]}...)")
    rayfile = read_rayfile(path, rec["format"])
    if rayfile.n_rays != rec["n_rays"] or not math.isclose(rayfile.total_flux, rec["flux"], rel_tol=1e-6):
        raise ValueError(f"source {spec['name']!r}: {path} holds {rayfile.n_rays} rays, {rayfile.total_flux} "
                         f"{rayfile.flux_unit}; the spec recorded {rec['n_rays']}, {rec['flux']}")
    return rayfile


def rayfile_source_spec(name: str, path: Any, position: Sequence[float], direction_deg: float, *,
                        roll_deg: float = 0.0, max_offset_mm: Optional[float] = None, format: str = "tm25",
                        base_dir: Any = None, wavelength_um: Optional[float] = None) -> Dict[str, Any]:
    """Write a ``rayfile`` source spec for a file, with its slice if a limit on h is given.

    Reads the file once, to record its count, flux and digest, and, with
    ``max_offset_mm``, slices it to record what the slice keeps.

    Args:
        name: The source's name.
        path: The file, as it is to be written into the spec: relative to
            ``base_dir`` (the profile's folder) or absolute.
        position, direction_deg, roll_deg: The placement, as ``rayfile_frame``'s.
        max_offset_mm: The slice's limit on h (``slice_rayfile``), or None
            for a source used in 3D only.
        format: The parser's format, one of ``FORMATS``.
        wavelength_um: One wavelength, or None for the file's spectrum.
    """
    resolved = _resolve(str(path), base_dir)
    rayfile = read_rayfile(resolved, format)
    spec: Dict[str, Any] = {
        "name": name, "kind": "rayfile", "position": [float(v) for v in position],
        "direction_deg": float(direction_deg), "roll_deg": float(roll_deg),
        "rayfile": {"path": str(path), "format": format, "n_rays": rayfile.n_rays, "flux": rayfile.total_flux,
                    "flux_unit": rayfile.flux_unit, "sha256": file_sha256(resolved)},
    }
    if wavelength_um is not None:
        spec["wavelength_um"] = float(wavelength_um)
    if max_offset_mm is not None:
        slc = slice_rayfile(rayfile, tuple(spec["position"][:2]), direction_deg, max_offset_mm=max_offset_mm,
                            roll_deg=roll_deg)
        spec["slice"] = {"max_offset_mm": float(max_offset_mm), "kept_share": 1.0 - slc.skew_share,
                         "rays_kept": int(len(slc.flux))}
    return validate_source_spec(spec)


# --- geometry -------------------------------------------------------------------


def source_axes(spec: Mapping[str, Any]) -> Dict[str, Vec3]:
    """A validated spec's axes in the scene frame (a, b, c): ``n``, ``e_in``, ``e_out``.

    For a pencil or a point, ``e_in``/``e_out`` are the roll-0 axes, p and o.
    """
    t = math.radians(spec["direction_deg"])
    da, db = math.cos(t), math.sin(t)
    r = math.radians(spec.get("roll_deg", 0.0))
    cr, sr = math.cos(r), math.sin(r)
    return {"n": (da, db, 0.0),
            "e_in": (-db * cr, da * cr, sr),
            "e_out": (db * sr, -da * sr, cr)}


def patch_corner_range(spec: Mapping[str, Any]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """The patch's extent along ``e_in`` and ``e_out``, measured from ``position``."""
    (w_in, w_out), (f_in, f_out) = spec["size"], spec["anchor"]
    return (-f_in * w_in, (1.0 - f_in) * w_in), (-f_out * w_out, (1.0 - f_out) * w_out)


def patch_centre(spec: Mapping[str, Any]) -> Vec3:
    """The centre of a validated patch spec, in the scene frame."""
    ax = source_axes(spec)
    (s0, s1), (t0, t1) = patch_corner_range(spec)
    sc, tc = 0.5 * (s0 + s1), 0.5 * (t0 + t1)
    return tuple(spec["position"][i] + sc * ax["e_in"][i] + tc * ax["e_out"][i] for i in range(3))


def patch_section(spec: Mapping[str, Any]) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """The segment where a patch meets the 2D plane (c = 0), as two (a, b) points.

    Ordered so that the emission axis is to the RIGHT of the first point to
    the second, or None if the patch does not cross the plane (or only
    touches it at a point or along a line of zero length).
    """
    ax = source_axes(spec)
    (s0, s1), (t0, t1) = patch_corner_range(spec)
    c0 = spec["position"][2]
    gs, gt = ax["e_in"][2], ax["e_out"][2]        # c along e_in and along e_out
    hits: List[Tuple[float, float]] = []
    for s in (s0, s1):                          # the two sides s = const
        if abs(gt) > 1e-15:
            t = -(c0 + gs * s) / gt
            if t0 - 1e-12 <= t <= t1 + 1e-12:
                hits.append((s, min(max(t, t0), t1)))
    for t in (t0, t1):                          # the two sides t = const
        if abs(gs) > 1e-15:
            s = -(c0 + gt * t) / gs
            if s0 - 1e-12 <= s <= s1 + 1e-12:
                hits.append((min(max(s, s0), s1), t))
    if len(hits) < 2:
        return None
    # Everything on the section lies along p: its in-plane coordinate is
    # s cos(roll) - t sin(roll) (the in-plane parts of e_in and e_out).
    t_dir = math.radians(spec["direction_deg"])
    pa, pb = -math.sin(t_dir), math.cos(t_dir)
    r = math.radians(spec["roll_deg"])
    u = [s * math.cos(r) - t * math.sin(r) for s, t in hits]
    lo, hi = min(u), max(u)
    if hi - lo <= PLANE_TOL:
        return None
    a0, b0 = spec["position"][0], spec["position"][1]
    # p is n turned 90 deg anticlockwise, so going along +p, n is on the right.
    return (a0 + lo * pa, b0 + lo * pb), (a0 + hi * pa, b0 + hi * pb)


# --- 2D -------------------------------------------------------------------------


def _angle_samples(spec: Mapping[str, Any], n_angles: int) -> List[Tuple[float, float]]:
    """(offset from the axis in radians, in-plane intensity) at the midpoints of equal steps."""
    half = math.radians(spec["half_angle_deg"])
    out = []
    for k in range(n_angles):
        off = -half + (k + 0.5) * (2.0 * half / n_angles)
        out.append((off, math.cos(off) if spec["emission"] == "lambertian" else 1.0))
    return out


def build_source_2d(scene: "Scene", spec: Mapping[str, Any], *, n_angles: int = 90,
                    n_positions: int = 10, base_dir: Any = None) -> RaySetSource:
    """The 2D source of a spec: its section by the scene plane, as a RaySetSource.

    Args:
        scene: The 2D scene the source is for (not modified: add the
            source with ``scene.add_object``).
        spec: A source specification (validated here).
        n_angles: Rays across the cone at each position, at the midpoints
            of equal angle steps (so the axis itself is a ray only when the
            count is odd).
        n_positions: Positions along a patch's section, at the midpoints
            of equal steps.
        base_dir: For a ``rayfile`` source, the folder its relative path is
            relative to (the profile's).

    Returns:
        A RaySetSource named after the spec, rays ordered by position then
        angle, the largest brightness 1. ``flux_per_brightness`` is the
        spec's flux over the summed brightness (see the module notes for
        what it does and does not mean).

    Raises:
        ValueError: If the spec is invalid, or a pencil or point lies off
            the plane, or a patch does not cross it -- such a source has no
            2D section, and an empty one would look like a dark source.
    """
    spec = validate_source_spec(spec)
    if spec["kind"] == "rayfile":
        return _rayfile_source_2d(scene, spec, base_dir)
    if n_angles < 1 or n_positions < 1:
        raise ValueError(f"n_angles and n_positions must be >= 1, got {n_angles}, {n_positions}")
    name, kind = spec["name"], spec["kind"]
    t_dir = math.radians(spec["direction_deg"])
    if kind in ("pencil", "point"):
        if abs(spec["position"][2]) > PLANE_TOL:
            raise ValueError(f"source {name!r}: a {kind} at c = {spec['position'][2]} lies off the 2D plane "
                             "and has no 2D section")
        positions = [(spec["position"][0], spec["position"][1])]
    else:
        section = patch_section(spec)
        if section is None:
            raise ValueError(f"source {name!r}: the patch does not cross the 2D plane (c = 0), "
                             "so it has no 2D section")
        (a1, b1), (a2, b2) = section
        positions = [(a1 + (k + 0.5) / n_positions * (a2 - a1), b1 + (k + 0.5) / n_positions * (b2 - b1))
                     for k in range(n_positions)]

    angles = [(0.0, 1.0)] if kind == "pencil" else _angle_samples(spec, n_angles)
    top = max(w for _, w in angles)
    points, directions, weights = [], [], []
    for p in positions:
        for off, w in angles:
            points.append(p)
            directions.append((math.cos(t_dir + off), math.sin(t_dir + off)))
            weights.append(w / top)
    src = RaySetSource.from_rays(scene, points, directions, weights,
                                 wavelength=1000.0 * spec["wavelength_um"],
                                 flux_per_brightness=spec["flux"] / sum(weights))
    src.name = name
    return src


def _rayfile_source_2d(scene: "Scene", spec: Dict[str, Any], base_dir: Any) -> RaySetSource:
    """A rayfile's slice as a RaySetSource; the slice recorded in the spec is checked, not trusted."""
    name = spec["name"]
    if "slice" not in spec:
        raise ValueError(f"source {name!r}: a rayfile has a 2D section only once it is sliced: give 'slice' "
                         "(rayfile_source_spec with max_offset_mm)")
    if abs(spec["position"][2]) > PLANE_TOL:
        raise ValueError(f"source {name!r}: a rayfile sliced about an axis at c = {spec['position'][2]} is off "
                         "the 2D plane")
    rayfile = spec_rayfile(spec, base_dir)
    rec = spec["slice"]
    slc = slice_rayfile(rayfile, tuple(spec["position"][:2]), spec["direction_deg"],
                        max_offset_mm=rec["max_offset_mm"], roll_deg=spec["roll_deg"])
    if len(slc.flux) != rec["rays_kept"] or not math.isclose(1.0 - slc.skew_share, rec["kept_share"],
                                                             rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError(f"source {name!r}: the slice keeps {len(slc.flux)} rays, {1.0 - slc.skew_share:.6f} of the "
                         f"flux; the spec recorded {rec['rays_kept']}, {rec['kept_share']:.6f}")
    wl = spec["wavelength_um"] if spec["wavelength_um"] is not None else rayfile.peak_wavelength_um()
    return slc.source_2d(scene, name=name, wavelength_nm=None if wl is None else 1000.0 * wl)


# --- profile.json ---------------------------------------------------------------


def profile_sources(profile: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The validated source specs a profile carries; [] for a profile without any.

    Raises:
        ValueError: If a spec is invalid or two share a name.
    """
    specs = [validate_source_spec(s) for s in (profile.get("sources") or [])]
    names = [s["name"] for s in specs]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"profile carries several sources named {dupes}")
    return specs


def merged_sources(profiles: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """The sources of several profiles of one scene, each once.

    A source designed for several elements is written into each of their
    profiles. Copies of one source (one name) must agree exactly.

    Args:
        profiles: Profile dicts, keyed by a label used in error messages
            (a file name, an element name).

    Raises:
        ValueError: If two profiles carry different sources under one name,
            naming both profiles. It never picks one: the two elements were
            designed for different light.
    """
    seen: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    out: List[Dict[str, Any]] = []
    for label, profile in profiles.items():
        for spec in profile_sources(profile):
            key = json.dumps(spec, sort_keys=True)
            if spec["name"] in seen:
                other_label, other = seen[spec["name"]]
                if json.dumps(other, sort_keys=True) != key:
                    raise ValueError(f"source {spec['name']!r} differs between profiles {other_label!r} and "
                                     f"{label!r}: {other} against {spec}")
                continue
            seen[spec["name"]] = (label, spec)
            out.append(copy.deepcopy(spec))
    return out
