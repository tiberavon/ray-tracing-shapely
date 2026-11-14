"""
Python-specific module: rayfile
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
RAYFILE -- a measured LED's rays, read from an IES TM-25 file
===============================================================================
An LED maker measures the light leaving a package and ships it as a rayfile:
one record per ray, its start point, its direction and its flux. The rays
are given in the LED's own frame, usually z along its axis, and start in air
outside the package. ``read_rayfile`` returns them as NumPy arrays, in
millimetres and with the file's flux unit; the 2D and the 3D engines both
take their rays from it.

The format is IES TM-25 (binary). The standard is sold, and this reader was
written from a file, so it reads only the layout it has been checked
against, and refuses any other rather than guessing. The layout, all
little-endian:

    offset   type            field
    0x0000   char[4]         "TM25"
    0x0004   int32           version: 2013
    0x0008   int32           (not decoded; -1 in the file read)
    0x000C   float32         (probably the luminous flux, lm; not checked)
    0x0010   float32         radiant flux, W
    0x0014   int64           number of rays
    0x001C   char[20]        creation date, "YYYY-MM-DD hh:mm:ss"
    0x0030   (28 bytes)      (not decoded)
    0x0044   float32 x 2     the spectrum's shortest and longest wavelength, nm
    0x004C   (180 bytes)     (not decoded)
    0x0100   int32 x 8       ray-data flags: (1, 1, 1, 0, 0, 0, 0, 0) is the
                             layout read here: position, direction, flux
    0x0120   9 x 1000 UTF-32 text fields: product, maker, ...
    0x8DC0   int32 n, then n x (float32 nm, float32 value): the spectrum
             int32           (not decoded; 0)
    then     n_rays x 7 float32: x, y, z (mm), direction (unit), flux

"Not decoded" fields are returned raw in ``Rayfile.header``; nothing uses
them. The ray count must fill the rest of the file exactly, and every
direction must be a unit vector.

``write_tm25`` writes the same layout, so tests and examples can make a
small synthetic file; a measured file is the supplier's, used under its
terms, and is never needed by a shipped test.
===============================================================================
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import numpy as np

PathLike = Union[str, Path]

MAGIC = b"TM25"
#: The formats ``read_rayfile`` reads: the values its ``format`` argument, and a
#: source spec's ``rayfile.format``, take.
FORMATS = ("tm25",)
VERSION = 2013
#: The ray-data flags of the one layout this reader has been checked against.
RAY_FLAGS = (1, 1, 1, 0, 0, 0, 0, 0)
TEXT_FIELDS = 9
TEXT_CHARS = 1000
_TEXT_START = 0x120
_SPECTRUM_START = _TEXT_START + TEXT_FIELDS * TEXT_CHARS * 4      # 0x8DC0
_RECORD = 7                                                        # float32 per ray
#: How far a direction's length may be from 1 (float32 rounding is ~1e-7).
UNIT_TOLERANCE = 1e-4


@dataclass(frozen=True)
class Rayfile:
    """A rayfile's rays and what its header says about them.

    Attributes:
        positions: (n, 3) start points, mm, in the LED's frame.
        directions: (n, 3) unit directions.
        flux: (n,) flux per ray, in ``flux_unit``.
        flux_unit: "W".
        spectrum_nm: (k, 2) the file's spectrum, (wavelength nm, relative
            value), or None. One spectrum for every ray.
        name: The product, from the first text field.
        header: Every header field read, decoded or raw.
        path: The file read, if any.
    """

    positions: np.ndarray
    directions: np.ndarray
    flux: np.ndarray
    flux_unit: str = "W"
    spectrum_nm: Optional[np.ndarray] = None
    name: str = ""
    header: Dict[str, Any] = field(default_factory=dict)
    path: Optional[str] = None

    @property
    def n_rays(self) -> int:
        return int(len(self.flux))

    @property
    def total_flux(self) -> float:
        """The sum of the rays' flux."""
        return float(self.flux.sum())

    def subset(self, indices) -> "Rayfile":
        """The same rayfile with only the records ``indices`` (indices or a boolean mask)."""
        idx = np.asarray(indices)
        return Rayfile(positions=self.positions[idx], directions=self.directions[idx], flux=self.flux[idx],
                       flux_unit=self.flux_unit, spectrum_nm=self.spectrum_nm, name=self.name,
                       header=self.header, path=self.path)

    def peak_wavelength_um(self) -> Optional[float]:
        """The spectrum's peak, in micrometres, or None without a spectrum."""
        if self.spectrum_nm is None:
            return None
        return float(self.spectrum_nm[int(np.argmax(self.spectrum_nm[:, 1])), 0]) / 1000.0


def _check_rays(positions: np.ndarray, directions: np.ndarray, flux: np.ndarray, where: str) -> None:
    n = len(flux)
    if positions.shape != (n, 3) or directions.shape != (n, 3):
        raise ValueError(f"{where}: positions and directions must be (n, 3) for n = {n} rays")
    if not (np.all(np.isfinite(positions)) and np.all(np.isfinite(directions)) and np.all(np.isfinite(flux))):
        raise ValueError(f"{where}: a ray has a non-finite value")
    length = np.linalg.norm(directions, axis=1)
    worst = float(np.abs(length - 1.0).max()) if n else 0.0
    if worst > UNIT_TOLERANCE:
        raise ValueError(f"{where}: a direction is {worst:.2e} away from unit length: not a direction, "
                         "or not the layout this reader reads")
    if np.any(flux < 0.0):
        raise ValueError(f"{where}: a ray has negative flux")


def read_rayfile(path: PathLike, format: Optional[str] = None) -> Rayfile:
    """Read a rayfile.

    Args:
        path: The file.
        format: One of ``FORMATS``, or None to tell by its first four bytes.

    Returns:
        A ``Rayfile``, its arrays float64.

    Raises:
        ValueError: If the format is not one this reader reads, or the file
            does not have the layout described in this module.
    """
    if format is not None and format not in FORMATS:
        raise ValueError(f"rayfile format {format!r} is not one of {FORMATS}")
    path = Path(path)
    data = path.read_bytes()
    fmt = format or ("tm25" if data[:4] == MAGIC else None)
    if fmt not in FORMATS:
        raise ValueError(f"{path.name}: not a format this reader reads (IES TM-25 only); "
                         f"it starts {data[:4]!r}")
    return _read_tm25(data, str(path))


def _read_tm25(data: bytes, where: str) -> Rayfile:
    if len(data) < _SPECTRUM_START + 8 or data[:4] != MAGIC:
        raise ValueError(f"{where}: too short, or not a TM-25 file")
    version, field_08, lum, rad, n_rays = struct.unpack_from("<iiffq", data, 4)
    if version != VERSION:
        raise ValueError(f"{where}: TM-25 version {version}; this reader has been checked only against {VERSION}")
    flags = struct.unpack_from("<8i", data, 0x100)
    if flags != RAY_FLAGS:
        raise ValueError(f"{where}: ray-data flags {flags}; this reader reads only {RAY_FLAGS} "
                         "(position, direction, flux per ray)")
    date = data[0x1C:0x30].split(b"\x00", 1)[0].decode("ascii", "replace")
    wl_min, wl_max = struct.unpack_from("<ff", data, 0x44)
    texts = [data[_TEXT_START + k * TEXT_CHARS * 4:_TEXT_START + (k + 1) * TEXT_CHARS * 4]
             .decode("utf-32-le").split("\x00", 1)[0] for k in range(TEXT_FIELDS)]
    (n_spec,) = struct.unpack_from("<i", data, _SPECTRUM_START)
    if n_spec < 0:
        raise ValueError(f"{where}: negative spectrum length {n_spec}")
    spec_end = _SPECTRUM_START + 4 + 8 * n_spec
    spectrum = (np.frombuffer(data, dtype="<f4", count=2 * n_spec, offset=_SPECTRUM_START + 4)
                .reshape(n_spec, 2).astype(float) if n_spec else None)
    (field_after_spectrum,) = struct.unpack_from("<i", data, spec_end)
    start = spec_end + 4
    if n_rays < 0 or len(data) - start != _RECORD * 4 * n_rays:
        raise ValueError(f"{where}: {n_rays} rays of {_RECORD} float32 need {_RECORD * 4 * n_rays} bytes after "
                         f"the header; the file has {len(data) - start}")
    rays = np.frombuffer(data, dtype="<f4", count=_RECORD * n_rays, offset=start).reshape(n_rays, _RECORD)
    rays = rays.astype(float)
    positions, directions, flux = rays[:, 0:3], rays[:, 3:6], rays[:, 6]
    _check_rays(positions, directions, flux, where)
    header = {
        "version": version, "radiant_flux_W": float(rad), "n_rays": int(n_rays), "date": date,
        "wavelength_range_nm": (float(wl_min), float(wl_max)), "texts": texts, "ray_flags": flags,
        "header_bytes": start,
        "not_decoded": {"0x0008_int32": field_08, "0x000C_float32_probably_lm": float(lum),
                        "0x0030": data[0x30:0x44].hex(), "0x004C": data[0x4C:0x100].hex(),
                        "after_spectrum_int32": field_after_spectrum},
    }
    return Rayfile(positions=positions, directions=directions, flux=flux, flux_unit="W",
                   spectrum_nm=spectrum, name=texts[0], header=header, path=where)


def write_tm25(
    path: PathLike,
    positions: np.ndarray,
    directions: np.ndarray,
    flux: np.ndarray,
    *,
    name: str = "synthetic",
    spectrum_nm: Optional[Sequence[Tuple[float, float]]] = None,
    date: str = "",
) -> Path:
    """Write rays as a TM-25 file in the layout ``read_rayfile`` reads.

    For synthetic test files. The header's radiant flux is the rays' sum; the
    creation date is ``date`` (empty by default); the fields this module does
    not decode are written as zeros.

    Returns:
        The path written.

    Raises:
        ValueError: If a direction is not a unit vector or a flux is negative.
    """
    positions = np.asarray(positions, dtype=float)
    directions = np.asarray(directions, dtype=float)
    flux = np.asarray(flux, dtype=float)
    _check_rays(positions, directions, flux, "write_tm25")
    spec = np.asarray(spectrum_nm if spectrum_nm is not None else [], dtype=float).reshape(-1, 2)
    head = bytearray(_SPECTRUM_START)
    head[0:4] = MAGIC
    struct.pack_into("<iiffq", head, 4, VERSION, -1, 0.0, float(flux.sum()), len(flux))
    head[0x1C:0x1C + len(date)] = date.encode("ascii")[:19]
    if len(spec):
        struct.pack_into("<ff", head, 0x44, float(spec[:, 0].min()), float(spec[:, 0].max()))
    struct.pack_into("<8i", head, 0x100, *RAY_FLAGS)
    head[_TEXT_START:_TEXT_START + 4 * min(len(name), TEXT_CHARS - 1)] = \
        name[:TEXT_CHARS - 1].encode("utf-32-le")
    tail = struct.pack("<i", len(spec)) + spec.astype("<f4").tobytes() + struct.pack("<i", 0)
    rays = np.column_stack([positions, directions, flux]).astype("<f4").tobytes()
    path = Path(path)
    path.write_bytes(bytes(head) + tail + rays)
    return path


def intensity_vs_angle(rayfile: Rayfile, n_bins: int = 90) -> Tuple[np.ndarray, np.ndarray]:
    """The far-field intensity against the angle from the LED's axis (+z).

    Flux per solid angle in equal polar-angle bins over the whole sphere,
    averaged over azimuth: what a goniometer far away reads.

    Returns:
        (theta_deg, intensity): bin centres in degrees, and flux_unit / sr.
    """
    cos_t = np.clip(rayfile.directions[:, 2], -1.0, 1.0)
    theta = np.degrees(np.arccos(cos_t))
    edges = np.linspace(0.0, 180.0, n_bins + 1)
    flux, _ = np.histogram(theta, bins=edges, weights=rayfile.flux)
    omega = 2.0 * np.pi * (np.cos(np.radians(edges[:-1])) - np.cos(np.radians(edges[1:])))
    return 0.5 * (edges[:-1] + edges[1:]), flux / omega


__all__ = ["FORMATS", "Rayfile", "intensity_vs_angle", "read_rayfile", "write_tm25"]
