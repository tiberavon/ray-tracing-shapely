"""
Python-specific module: linear sensor
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
LINEAR SENSOR
===============================================================================
A physical linear CCD/CMOS array modelled as a Detector + optional collinear
edge Blockers.  Each Detector bin maps one-to-one to a physical pixel --
P-HIT-RECORD, see dev_doc/architecture/components/optical_elements_physics.md.

Design rationale: dev_doc/architecture/components/optical_elements_physics.md.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pint
    from ...core.scene import Scene
    from ..physics.photoconversion import Photoconversion

from ...core.scene_objs.other.detector import Detector
from ...core.scene_objs.blocker.blocker import Blocker
from ..physical_scene import PhysicalScene
from ..physics.exceptions import PhysicsContextError


# ---------------------------------------------------------------------------
# Datasheet catalogue
# ---------------------------------------------------------------------------

_CATALOGUE: Dict[str, Dict] = {
    'S13131-1536': {
        'n_pixels': 1536,
        'pixel_pitch': 0.0055,  # 5.5 µm → mm
    },
}


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class LinearSensor:
    """
    A physical linear CCD/CMOS pixel array for ray-tracing simulations.

    Composes a core Detector and optional edge Blockers into a single object
    that exposes a pixel-indexed view of the simulation result.

    Orientation is given by p1→p2 (unit direction only; magnitude ignored).
    Light enters from the left of the p1→p2 vector (inherited from Detector).
    The physical position of the active area is set by the construction method.

    Three construction methods:
        __init__        — p1 is the physical start of the active area.
        from_center     — centre of the array is placed at a given scene point.
        from_pixel_0    — pixel 0 centre is placed at a given scene point.

    All methods accept a `count_pixels_from_p1` flag (default True):
        True  → pixel 0 is at the p1-side end; index increases toward p2.
        False → pixel 0 is at the p2-side end; index increases toward p1.

    After simulation:
        sensor.pixel_data         # List[float] | None — one value per pixel
        sensor.pixel_positions    # List[float] — centre distance from pixel 0
    """

    def __init__(
        self,
        scene: 'Scene',
        p1: Dict[str, float],
        p2: Dict[str, float],
        n_pixels: int,
        pixel_pitch: Optional[float] = None,
        active_length: Optional[float] = None,
        count_pixels_from_p1: bool = True,
        use_edge_blockers: bool = True,
        name: str = 'linear_sensor',
        photoconversion: Optional['Photoconversion'] = None,
    ) -> None:
        """
        Place the sensor with p1 as the physical start of the active area.

        p2 supplies the axis direction only; its magnitude is ignored.
        Exactly one of pixel_pitch or active_length must be supplied.

        Args:
            scene:                The simulation scene.
            p1:                   Physical start of the active area (pixel 0 side
                                  when count_pixels_from_p1=True).
            p2:                   Axis direction reference (magnitude ignored).
            n_pixels:             Number of pixels.
            pixel_pitch:          Width of each pixel in scene units.
            active_length:        Total photosensitive length in scene units.
            count_pixels_from_p1: If True, pixel 0 is at the p1 end.
            use_edge_blockers:    Add collinear Blockers one pixel_pitch long
                                  beyond each end of the active area.
            name:                 Base name; internal objects use suffixes
                                  '_detector', '_blocker_lo', '_blocker_hi'.
            photoconversion:      Optional Photoconversion model. Required for the
                                  physical conversion methods (compute_irradiance,
                                  compute_vout); those also require ``scene`` to be
                                  a calibrated PhysicalScene.

        Raises:
            ValueError: If neither or both of pixel_pitch / active_length
                        are supplied, or if p1 == p2.
        """
        pixel_pitch = _resolve_pixel_pitch(n_pixels, pixel_pitch, active_length)
        ux, uy = _unit_vector(p1, p2)

        detector_start = {'x': float(p1['x']), 'y': float(p1['y'])}
        detector_end = {
            'x': p1['x'] + n_pixels * pixel_pitch * ux,
            'y': p1['y'] + n_pixels * pixel_pitch * uy,
        }

        self._scene = scene
        self._photoconversion = photoconversion
        self._n_pixels = n_pixels
        self._pixel_pitch = pixel_pitch
        self._count_pixels_from_p1 = count_pixels_from_p1

        self._detector = Detector(scene, {
            'type': 'Detector',
            'p1': detector_start,
            'p2': detector_end,
            'irrad_map': True,
            'bin_size': pixel_pitch,
        })
        self._detector._name = f'{name}_detector'
        scene.add_object(self._detector)

        self._blocker_lo: Optional[Blocker] = None
        self._blocker_hi: Optional[Blocker] = None

        if use_edge_blockers:
            lo_start = {
                'x': detector_start['x'] - pixel_pitch * ux,
                'y': detector_start['y'] - pixel_pitch * uy,
            }
            self._blocker_lo = Blocker(scene, {
                'type': 'Blocker',
                'p1': lo_start,
                'p2': detector_start,
            })
            self._blocker_lo._name = f'{name}_blocker_lo'
            scene.add_object(self._blocker_lo)

            hi_end = {
                'x': detector_end['x'] + pixel_pitch * ux,
                'y': detector_end['y'] + pixel_pitch * uy,
            }
            self._blocker_hi = Blocker(scene, {
                'type': 'Blocker',
                'p1': detector_end,
                'p2': hi_end,
            })
            self._blocker_hi._name = f'{name}_blocker_hi'
            scene.add_object(self._blocker_hi)

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def n_pixels(self) -> int:
        """Number of pixels in the array."""
        return self._n_pixels

    @property
    def pixel_pitch(self) -> float:
        """Width of one pixel in scene units."""
        return self._pixel_pitch

    @property
    def active_length(self) -> float:
        """Total photosensitive length in scene units (n_pixels × pixel_pitch)."""
        return self._n_pixels * self._pixel_pitch

    @property
    def detector(self) -> Detector:
        """The underlying Detector scene object."""
        return self._detector

    @property
    def pixel_data(self) -> Optional[List[float]]:
        """
        Per-pixel irradiance after simulation; pixel_data[0] is always pixel 0.

        Returns bin_data directly when count_pixels_from_p1=True, or reversed
        when False.  Returns None if on_simulation_start() has not been called.

        Truncates to _n_pixels to absorb the off-by-one that arises from
        math.ceil floating-point rounding in Detector.bin_count.
        """
        data = self._detector.bin_data
        if data is None:
            return None
        data = data[:self._n_pixels]
        return data if self._count_pixels_from_p1 else list(reversed(data))

    @property
    def pixel_positions(self) -> List[float]:
        """
        Distance from pixel 0 to the centre of each pixel in scene units.

        pixel_positions[0] = pixel_pitch / 2
        pixel_positions[-1] = active_length - pixel_pitch / 2
        """
        return [(i + 0.5) * self._pixel_pitch for i in range(self._n_pixels)]

    @property
    def hit_uuids(self) -> List[str]:
        """
        Unique ray uuids that reached this sensor, in crossing order.

        These are the terminal-side lineage segment uuids for every ray that
        crossed the active area. Pass them as `leaf_uuids` to lineage-analysis
        functions (e.g. rank_paths_by_energy) to isolate the optical paths that
        contribute to this sensor's signal.
        """
        return self._detector.get_hit_uuids()

    @property
    def pixel_hit_uuids(self) -> List[List[str]]:
        """
        Per-pixel ray uuids: pixel_hit_uuids[p] lists the uuids that hit pixel p.

        Indexed in pixel order (pixel 0 first), honouring the same
        count_pixels_from_p1 convention as pixel_data. Hits outside the active
        area (bins ≥ n_pixels from math.ceil rounding) are ignored.
        """
        buckets: List[List[str]] = [[] for _ in range(self._n_pixels)]
        seen: List[set] = [set() for _ in range(self._n_pixels)]
        for record in self._detector.hit_records:
            bin_index = record['bin_index']
            uuid = record['ray_uuid']
            if bin_index is None or uuid is None:
                continue
            if not (0 <= bin_index < self._n_pixels):
                continue
            pixel = bin_index if self._count_pixels_from_p1 \
                else self._n_pixels - 1 - bin_index
            if uuid not in seen[pixel]:
                seen[pixel].add(uuid)
                buckets[pixel].append(uuid)
        return buckets

    # -------------------------------------------------------------------------
    # Alternative constructors
    # -------------------------------------------------------------------------

    @classmethod
    def from_center(
        cls,
        scene: 'Scene',
        p1: Dict[str, float],
        p2: Dict[str, float],
        center_point: Dict[str, float],
        n_pixels: int,
        pixel_pitch: Optional[float] = None,
        active_length: Optional[float] = None,
        count_pixels_from_p1: bool = True,
        use_edge_blockers: bool = True,
        name: str = 'linear_sensor',
        photoconversion: Optional['Photoconversion'] = None,
    ) -> 'LinearSensor':
        """
        Place the sensor so that center_point aligns with the array centre.

        center_point is projected onto the p1→p2 axis. The active area extends
        active_length/2 on each side of that projection along the axis.

        count_pixels_from_p1=True  (default): pixel 0 is at the p1-side end.
        count_pixels_from_p1=False:           pixel 0 is at the p2-side end.
        """
        pixel_pitch = _resolve_pixel_pitch(n_pixels, pixel_pitch, active_length)
        ux, uy = _unit_vector(p1, p2)

        t = (
            (center_point['x'] - p1['x']) * ux
            + (center_point['y'] - p1['y']) * uy
        )
        half_l = 0.5 * n_pixels * pixel_pitch

        new_p1 = {
            'x': p1['x'] + (t - half_l) * ux,
            'y': p1['y'] + (t - half_l) * uy,
        }
        new_p2 = {
            'x': p1['x'] + (t + half_l) * ux,
            'y': p1['y'] + (t + half_l) * uy,
        }

        return cls(
            scene, new_p1, new_p2, n_pixels,
            pixel_pitch=pixel_pitch,
            count_pixels_from_p1=count_pixels_from_p1,
            use_edge_blockers=use_edge_blockers,
            name=name,
            photoconversion=photoconversion,
        )

    @classmethod
    def from_pixel_0(
        cls,
        scene: 'Scene',
        p1: Dict[str, float],
        p2: Dict[str, float],
        pixel_0_point: Dict[str, float],
        n_pixels: int,
        pixel_pitch: Optional[float] = None,
        active_length: Optional[float] = None,
        count_pixels_from_p1: bool = True,
        use_edge_blockers: bool = True,
        name: str = 'linear_sensor',
        photoconversion: Optional['Photoconversion'] = None,
    ) -> 'LinearSensor':
        """
        Place the sensor so that pixel 0 is centred at pixel_0_point.

        pixel_0_point is projected onto the p1→p2 axis to find the centre
        of pixel 0.  The remaining pixels extend from there.

        count_pixels_from_p1=True  (default): the array runs in the p1→p2
            direction from pixel_0_point, so the active area starts at
            pixel_0_point − pixel_pitch/2 × u.

        count_pixels_from_p1=False: the array runs in the p2→p1 direction
            from pixel_0_point, so the active area ends at
            pixel_0_point + pixel_pitch/2 × u.  The internal Detector still
            runs p1→p2; pixel_data reverses bin_data.
        """
        pixel_pitch = _resolve_pixel_pitch(n_pixels, pixel_pitch, active_length)
        ux, uy = _unit_vector(p1, p2)

        t = (
            (pixel_0_point['x'] - p1['x']) * ux
            + (pixel_0_point['y'] - p1['y']) * uy
        )
        px0_x = p1['x'] + t * ux
        px0_y = p1['y'] + t * uy

        if count_pixels_from_p1:
            new_p1 = {
                'x': px0_x - 0.5 * pixel_pitch * ux,
                'y': px0_y - 0.5 * pixel_pitch * uy,
            }
            new_p2 = {
                'x': px0_x + (n_pixels - 0.5) * pixel_pitch * ux,
                'y': px0_y + (n_pixels - 0.5) * pixel_pitch * uy,
            }
        else:
            new_p1 = {
                'x': px0_x - (n_pixels - 0.5) * pixel_pitch * ux,
                'y': px0_y - (n_pixels - 0.5) * pixel_pitch * uy,
            }
            new_p2 = {
                'x': px0_x + 0.5 * pixel_pitch * ux,
                'y': px0_y + 0.5 * pixel_pitch * uy,
            }

        return cls(
            scene, new_p1, new_p2, n_pixels,
            pixel_pitch=pixel_pitch,
            count_pixels_from_p1=count_pixels_from_p1,
            use_edge_blockers=use_edge_blockers,
            name=name,
            photoconversion=photoconversion,
        )

    @classmethod
    def from_datasheet(
        cls,
        scene: 'Scene',
        model: str,
        p1: Dict[str, float],
        p2: Dict[str, float],
        *,
        center_point: Optional[Dict[str, float]] = None,
        pixel_0_point: Optional[Dict[str, float]] = None,
        **kwargs,
    ) -> 'LinearSensor':
        """
        Instantiate a LinearSensor from a known sensor model name.

        Supported models:
            'S13131-1536'  — Hamamatsu CMOS, 1536 px, 5.5 µm pitch (0.0055 mm)

        Supply at most one of center_point or pixel_0_point to choose
        which alternative constructor is called.  If neither is given, p1 is
        used as the physical start of the active area.  Additional keyword
        arguments are forwarded to the chosen constructor.

        Args:
            scene:          The simulation scene.
            model:          Sensor model name (see _CATALOGUE).
            p1:             Orientation reference point 1.
            p2:             Orientation reference point 2.
            center_point:   If given, delegates to from_center.
            pixel_0_point:  If given, delegates to from_pixel_0.
            **kwargs:       Forwarded to constructor (e.g. count_pixels_from_p1).

        Raises:
            ValueError: If model is unknown or both placement helpers are given.
        """
        if model not in _CATALOGUE:
            raise ValueError(
                f"Unknown sensor model '{model}'. "
                f"Known models: {list(_CATALOGUE)}"
            )
        params = _CATALOGUE[model]

        if center_point is not None and pixel_0_point is not None:
            raise ValueError(
                "Provide at most one of center_point or pixel_0_point."
            )
        if center_point is not None:
            return cls.from_center(scene, p1, p2, center_point, **params, **kwargs)
        if pixel_0_point is not None:
            return cls.from_pixel_0(scene, p1, p2, pixel_0_point, **params, **kwargs)
        return cls(scene, p1, p2, **params, **kwargs)

    # -------------------------------------------------------------------------
    # Physical conversions (Photometry Framework)
    # -------------------------------------------------------------------------

    @property
    def photoconversion(self) -> Optional['Photoconversion']:
        """The attached Photoconversion model, or None."""
        return self._photoconversion

    def compute_irradiance(self) -> 'pint.Quantity':
        """
        Convert pixel_data to irradiance per pixel in W/m².

        Delegates to the attached Photoconversion using the sensor's scene.
        Returns a pint.Quantity wrapping a NumPy array (dimensionality
        W/m^2), not a plain List[float] [KC4: a quantity leaving the
        radiometric layer carries its unit].

        Requires:
            - a Photoconversion attached (photoconversion= at construction), and
            - the scene to be a PhysicalScene with calibration_factor set.

        Raises:
            PhysicsContextError: If either requirement is unmet, or if the
                simulation has not populated pixel_data.
        """
        if self._photoconversion is None:
            raise PhysicsContextError(
                "compute_irradiance requires a Photoconversion object. "
                "Pass photoconversion= to LinearSensor.__init__ / from_*()."
            )
        if not isinstance(self._scene, PhysicalScene):
            raise PhysicsContextError(
                "compute_irradiance requires a PhysicalScene. "
                "Replace Scene() with PhysicalScene(scene_unit='mm')."
            )
        return self._photoconversion.compute_irradiance(self.pixel_data, self._scene)

    def compute_vout(self) -> List[float]:
        """
        Convert pixel_data to output voltage per pixel (V). DEFERRED.

        The structural context (Photoconversion + PhysicalScene) is validated
        here, but the radiometric→photometric step is not yet pinned, so the
        underlying Photoconversion.compute_vout raises NotImplementedError. Use
        compute_irradiance() for W/m² in the meantime.

        Raises:
            PhysicsContextError: If no Photoconversion is attached or the scene
                is not a PhysicalScene.
            NotImplementedError: When structurally valid — pending the
                luminous-efficacy convention.
        """
        if self._photoconversion is None:
            raise PhysicsContextError(
                "compute_vout requires a Photoconversion object. "
                "Pass photoconversion= to LinearSensor.__init__ / from_*()."
            )
        if not isinstance(self._scene, PhysicalScene):
            raise PhysicsContextError(
                "compute_vout requires a PhysicalScene. "
                "Replace Scene() with PhysicalScene(scene_unit='mm')."
            )
        return self._photoconversion.compute_vout(self.pixel_data, self._scene)

    def __repr__(self) -> str:
        return (
            f"LinearSensor(n_pixels={self._n_pixels}, "
            f"pixel_pitch={self._pixel_pitch}, "
            f"active_length={self.active_length:.6g})"
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_pixel_pitch(
    n_pixels: int,
    pixel_pitch: Optional[float],
    active_length: Optional[float],
) -> float:
    if (pixel_pitch is None) == (active_length is None):
        raise ValueError(
            "Exactly one of pixel_pitch or active_length must be supplied."
        )
    if pixel_pitch is not None:
        return float(pixel_pitch)
    return float(active_length) / n_pixels


def _unit_vector(
    p1: Dict[str, float],
    p2: Dict[str, float],
) -> tuple:
    dx = p2['x'] - p1['x']
    dy = p2['y'] - p1['y']
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0.0:
        raise ValueError("p1 and p2 must be distinct points.")
    return dx / length, dy / length
