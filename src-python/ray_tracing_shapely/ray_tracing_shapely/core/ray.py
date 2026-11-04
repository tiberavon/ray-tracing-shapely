"""
Original work Copyright 2024 The Ray Optics Simulation authors and contributors
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import math
import uuid as _uuid_mod
from typing import Dict, Optional, Any


class Ray:
    """
    Representation of a light ray for ray tracing simulation.

    A ray is defined by two points (p1 and p2) representing a line segment
    or infinite ray. The ray carries brightness information for both
    polarization states (s and p) and optionally wavelength information.

    Attributes:
        p1 (dict): Starting point with keys 'x' and 'y'
        p2 (dict): Direction point with keys 'x' and 'y'
        brightness_s (float): Brightness for s-polarization (0.0 to 1.0)
        brightness_p (float): Brightness for p-polarization (0.0 to 1.0)
        wavelength (float or None): Wavelength in nm, or None for white light
        gap (bool): If True, this ray segment is not drawn (gap in ray path)
        is_new (bool): If True, this ray has not been processed yet
        body_merging_obj (object or None): Object for surface merging 

    TIR Tracking Attributes (PYTHON-SPECIFIC FEATURE):
        is_tir_result (bool): True if this segment was produced BY a TIR event
        caused_tir (bool): True if this segment's endpoint caused TIR
        tir_count (int): Cumulative TIR count in this ray's lineage

    Grazing Incidence Tracking Attributes (PYTHON-SPECIFIC FEATURE):
        Grazing incidence occurs at angles near the critical angle, where
        polarization effects become extreme. Three independent criteria detect it:

        Angle criterion (near critical angle):
            is_grazing_result__angle (bool): This segment was produced by grazing refraction
            caused_grazing__angle (bool): This segment's endpoint triggered angle criterion

        Polarization criterion (extreme s/p ratio after refraction):
            is_grazing_result__polar (bool): This segment was produced by grazing refraction
            caused_grazing__polar (bool): This segment's endpoint triggered polar criterion

        Transmission criterion (very low total transmission):
            is_grazing_result__transm (bool): This segment was produced by grazing refraction
            caused_grazing__transm (bool): This segment's endpoint triggered transm criterion

    Source Tracking Attributes (PYTHON-SPECIFIC FEATURE):
        source_uuid (str or None): UUID of the light source that emitted this ray
        source_label (str or None): Human-readable label for ray identification
            (e.g., "red", "green", "blue", "chief", "marginal_upper")

    Lineage Tracking Attributes (PYTHON-SPECIFIC FEATURE):
        uuid (str): Unique identifier for this ray segment (auto-generated)
        parent_uuid (str or None): UUID of the parent ray that spawned this one
        interaction_type (str): How this ray was created:
            'source' = emitted by a light source (no parent)
            'reflect' = Fresnel reflection or mirror reflection
            'refract' = Snell's law refraction
            'tir' = total internal reflection

    Optical Path Length Attribute (PYTHON-SPECIFIC FEATURE, P-RAY-LINEAGE
    -- dev_doc/architecture/components/core_simulator.md):
        medium_index (float): Absolute refractive index of the medium this
            segment travels through. Default 1.0 (air/vacuum), correct for
            every source-emitted root ray. Propagated parent-to-child at
            each of Simulator._process_rays()'s four branch points, mirroring
            the tir_count pattern exactly. Set by base_glass.py's refract()
            on the rays it creates: unchanged on Fresnel reflection, divided
            by the surface-merging-corrected refraction ratio n1 on
            transmission (ray.medium_index already being the absolute
            incident index, by induction from this default). Objects that
            never change the medium (mirrors) need not touch it at all --
            the branch-point propagation falls back to the parent's value.
    """

    def __init__(
        self,
        p1: Dict[str, float],
        p2: Dict[str, float],
        brightness_s: float = 1.0,
        brightness_p: float = 1.0,
        wavelength: Optional[float] = None
    ) -> None:
        """
        Initialize a ray.

        Args:
            p1 (dict): Starting point {'x': float, 'y': float}
            p2 (dict): Direction point {'x': float, 'y': float}
            brightness_s (float): S-polarization brightness (default: 1.0)
            brightness_p (float): P-polarization brightness (default: 1.0)
            wavelength (float or None): Wavelength in nm (default: None for white)
        """
        self.p1: Dict[str, float] = p1
        self.p2: Dict[str, float] = p2
        self.brightness_s: float = brightness_s
        self.brightness_p: float = brightness_p
        self.wavelength: Optional[float] = wavelength
        self.gap: bool = False
        self.is_new: bool = True
        self.body_merging_obj: Optional[Any] = None  # Reserved for Phase 2.5 surface merging
        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: TIR (Total Internal Reflection) Tracking
        # =====================================================================
        # These attributes enable filtering and visualization of rays that
        # experienced Total Internal Reflection. This feature does not exist
        # in the JavaScript version.
        # =====================================================================
        self.is_tir_result: bool = False  # True if this segment was produced BY a TIR event
        self.caused_tir: bool = False     # True if this segment's endpoint caused TIR
        self.tir_count: int = 0           # Cumulative TIR count in this ray's lineage

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Grazing Incidence Tracking
        # =====================================================================
        # These attributes enable filtering and analysis of rays that experienced
        # grazing incidence (near-critical-angle refraction). Three independent
        # criteria are tracked separately, as different thresholds may apply.
        # This feature does not exist in the JavaScript version.
        # =====================================================================
        # Angle criterion: incidence angle above threshold (e.g., 85°)
        self.is_grazing_result__angle: bool = False
        self.caused_grazing__angle: bool = False
        # Polarization criterion: brightness_p / brightness_s ratio above threshold
        self.is_grazing_result__polar: bool = False
        self.caused_grazing__polar: bool = False
        # Transmission criterion: total transmission below threshold
        self.is_grazing_result__transm: bool = False
        self.caused_grazing__transm: bool = False

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Source Tracking
        # =====================================================================
        # These attributes enable correlation between rays and their sources,
        # useful for prism dispersion analysis and multi-wavelength simulations.
        # =====================================================================
        self.source_uuid: Optional[str] = None   # UUID of the emitting light source
        self.source_label: Optional[str] = None  # Human-readable label (e.g., "red", "chief")

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Ray Lineage Tracking
        # =====================================================================
        # These attributes enable reconstruction of the full ray tree after
        # simulation, tracking parent-child relationships across reflections,
        # refractions, and TIR events.
        # =====================================================================
        self.uuid: str = str(_uuid_mod.uuid4())   # Unique ID for this ray segment
        self.parent_uuid: Optional[str] = None     # UUID of the parent ray (None for source rays)
        self.interaction_type: str = 'source'      # 'source', 'reflect', 'refract', 'tir'

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Surface Hit Records (Step B, opt-in)
        # =====================================================================
        # Geometry of the surface interaction that TERMINATED this segment.
        # These describe THIS segment's own hit -- never a child's -- and stay
        # None unless Simulator(record_surface_hits=True) is used. Populated by
        # the optical object during on_ray_incident and copied onto the incident
        # segment by the simulator. See C-HIT-01
        # (dev_doc/architecture/contracts/C-HIT-01.md), Invariants.
        #
        # hit_normal is the (unit) surface normal as used by the physics at the
        # interaction (its geometric orientation from the object); consumers can
        # infer the incidence side from the ray direction. incident_angle is the
        # angle of incidence in radians, always in [0, pi/2].
        # =====================================================================
        self.hit_surface_uuid: Optional[str] = None   # _uuid of the object hit
        self.hit_point: Optional[Dict[str, float]] = None    # {'x', 'y'} intersection
        self.hit_normal: Optional[Dict[str, float]] = None   # {'x', 'y'} unit normal
        self.incident_angle: Optional[float] = None   # radians, [0, pi/2]

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Optical Path Length (P-RAY-LINEAGE)
        # =====================================================================
        # Absolute refractive index of the medium this segment travels
        # through. Default 1.0 (air/vacuum) is correct for every
        # source-emitted root ray; see the class docstring for the
        # propagation contract.
        # =====================================================================
        self.medium_index: float = 1.0

    def copy(self) -> 'Ray':
        """
        Create a copy of this ray.

        Returns:
            Ray: A new Ray object with the same properties
        """
        new_ray = Ray(
            p1={'x': self.p1['x'], 'y': self.p1['y']},
            p2={'x': self.p2['x'], 'y': self.p2['y']},
            brightness_s=self.brightness_s,
            brightness_p=self.brightness_p,
            wavelength=self.wavelength
        )
        new_ray.gap = self.gap
        new_ray.is_new = self.is_new
        new_ray.body_merging_obj = self.body_merging_obj
        # PYTHON-SPECIFIC: Copy TIR tracking attributes
        new_ray.is_tir_result = self.is_tir_result
        new_ray.caused_tir = False  # Don't copy - caused_tir is position-specific, set by simulator
        new_ray.tir_count = self.tir_count
        # PYTHON-SPECIFIC: Copy grazing incidence tracking attributes
        new_ray.is_grazing_result__angle = self.is_grazing_result__angle
        new_ray.caused_grazing__angle = False  # Position-specific, set by simulator
        new_ray.is_grazing_result__polar = self.is_grazing_result__polar
        new_ray.caused_grazing__polar = False  # Position-specific, set by simulator
        new_ray.is_grazing_result__transm = self.is_grazing_result__transm
        new_ray.caused_grazing__transm = False  # Position-specific, set by simulator
        # PYTHON-SPECIFIC: Copy source tracking attributes
        new_ray.source_uuid = self.source_uuid
        new_ray.source_label = self.source_label
        # PYTHON-SPECIFIC: Copy lineage tracking attributes
        # copy() generates a NEW uuid (it's a new segment), but preserves lineage info
        # Caller is responsible for setting parent_uuid if this copy is a child ray
        new_ray.parent_uuid = self.parent_uuid
        new_ray.interaction_type = self.interaction_type
        # PYTHON-SPECIFIC: Copy optical path length attribute (P-RAY-LINEAGE)
        new_ray.medium_index = self.medium_index
        # PYTHON-SPECIFIC: Surface hit records describe THIS segment's own hit,
        # not the copy's. A copy is a fresh segment that has not hit anything, so
        # its hit fields must start None (Ray.__init__ already sets them None; we
        # leave them None explicitly rather than copying).
        return new_ray

    @property
    def total_brightness(self) -> float:
        """
        Get the total brightness (sum of both polarizations).

        Returns:
            float: brightness_s + brightness_p
        """
        return self.brightness_s + self.brightness_p

    # =========================================================================
    # PYTHON-SPECIFIC FEATURE: Polarization Metrics
    # =========================================================================

    @property
    def polarization_ratio(self) -> float:
        """
        Ratio of p-polarized to s-polarized brightness, T_p/T_s.
        At grazing incidence p-pol transmits more than s-pol so this ratio is > 1
        

        Returns:
            float: brightness_p / brightness_s, or float('inf') if brightness_s
                   is negligible (< 1e-10).
        """
        if self.brightness_s > 1e-10:
            return self.brightness_p / self.brightness_s
        return float('inf')

    @property
    def degree_of_polarization(self) -> float:
        """
        Degree of polarization (0 = unpolarized, 1 = fully polarized).

        Computed as |brightness_p - brightness_s| / (brightness_p + brightness_s).

        Returns:
            float: Value in [0, 1], or 0.0 if total brightness is negligible.
        """
        total = self.brightness_p + self.brightness_s
        if total > 1e-10:
            return abs(self.brightness_p - self.brightness_s) / total
        return 0.0

    def __repr__(self) -> str:
        """String representation for debugging."""
        gap_str: str = ", gap=True" if self.gap else ""
        # PYTHON-SPECIFIC: Include TIR info in repr
        tir_str: str = ""
        if self.is_tir_result or self.caused_tir or self.tir_count > 0:
            tir_parts = []
            if self.is_tir_result:
                tir_parts.append("is_tir_result=True")
            if self.caused_tir:
                tir_parts.append("caused_tir=True")
            if self.tir_count > 0:
                tir_parts.append(f"tir_count={self.tir_count}")
            tir_str = ", " + ", ".join(tir_parts)
        # PYTHON-SPECIFIC: Include grazing incidence info in repr
        grazing_str: str = ""
        grazing_parts = []
        if self.is_grazing_result__angle or self.caused_grazing__angle:
            if self.is_grazing_result__angle:
                grazing_parts.append("grazing_angle")
            if self.caused_grazing__angle:
                grazing_parts.append("->grazing_angle")
        if self.is_grazing_result__polar or self.caused_grazing__polar:
            if self.is_grazing_result__polar:
                grazing_parts.append("grazing_polar")
            if self.caused_grazing__polar:
                grazing_parts.append("->grazing_polar")
        if self.is_grazing_result__transm or self.caused_grazing__transm:
            if self.is_grazing_result__transm:
                grazing_parts.append("grazing_transm")
            if self.caused_grazing__transm:
                grazing_parts.append("->grazing_transm")
        if grazing_parts:
            grazing_str = ", " + ", ".join(grazing_parts)
        # PYTHON-SPECIFIC: Include source info in repr
        source_str: str = ""
        if self.source_label:
            source_str = f", label='{self.source_label}'"
        elif self.source_uuid:
            source_str = f", source={self.source_uuid[:8]}..."
        # PYTHON-SPECIFIC: Include lineage info in repr
        lineage_str: str = f", uuid={self.uuid[:8]}..."
        if self.parent_uuid:
            lineage_str += f", parent={self.parent_uuid[:8]}..."
        if self.interaction_type != 'source':
            lineage_str += f", {self.interaction_type}"
        # PYTHON-SPECIFIC: Include surface hit record (Step B) in repr when present
        hit_str: str = ""
        if self.incident_angle is not None:
            hit_str = f", inc_angle={math.degrees(self.incident_angle):.1f}deg"
        return (f"Ray(p1={self.p1}, p2={self.p2}, "
                f"brightness=({self.brightness_s:.6f}, {self.brightness_p:.6f}), "
                f"total={self.total_brightness:.6f}, "
                f"wavelength={self.wavelength}{gap_str}{tir_str}{grazing_str}{source_str}{lineage_str}{hit_str})")


# Example usage and testing
if __name__ == "__main__":
    import math

    print("Testing Ray class...\n")

    # Test 1: Create a basic white light ray
    print("Test 1: Basic ray creation")
    ray1 = Ray(
        p1={'x': 0, 'y': 0},
        p2={'x': 100, 'y': 0},
        brightness_s=0.5,
        brightness_p=0.5
    )
    print(f"  {ray1}")
    print(f"  Total brightness: {ray1.total_brightness}")
    print(f"  Is new: {ray1.is_new}")
    print(f"  Is gap: {ray1.gap}")

    # Test 2: Create a colored ray (red light at 650nm)
    print("\nTest 2: Colored ray (red light)")
    ray2 = Ray(
        p1={'x': 0, 'y': 100},
        p2={'x': 100, 'y': 150},
        brightness_s=1.0,
        brightness_p=0.0,
        wavelength=650
    )
    print(f"  {ray2}")
    print(f"  Wavelength: {ray2.wavelength} nm")
    print(f"  S-polarization only: brightness_s={ray2.brightness_s}, brightness_p={ray2.brightness_p}")

    # Test 3: Ray copy
    print("\nTest 3: Ray copy")
    ray3 = ray1.copy()
    print(f"  Original: {ray1}")
    print(f"  Copy: {ray3}")
    print(f"  Are they the same object? {ray1 is ray3}")
    print(f"  Do they have the same values? p1={ray1.p1 == ray3.p1}, brightness={ray1.total_brightness == ray3.total_brightness}")

    # Modify copy and verify original is unchanged
    ray3.brightness_s = 0.1
    ray3.p1['x'] = 50
    print("  After modifying copy:")
    print(f"    Original brightness: {ray1.total_brightness}")
    print(f"    Copy brightness: {ray3.total_brightness}")
    print(f"    Original p1.x: {ray1.p1['x']}")
    print(f"    Copy p1.x: {ray3.p1['x']}")

    # Test 4: Ray with gap flag
    print("\nTest 4: Gap ray (not drawn)")
    ray4 = Ray(
        p1={'x': 100, 'y': 100},
        p2={'x': 200, 'y': 100}
    )
    ray4.gap = True
    print(f"  {ray4}")
    print(f"  Gap flag: {ray4.gap}")

    # Test 5: Calculate ray length
    print("\nTest 5: Ray length calculation")
    dx = ray1.p2['x'] - ray1.p1['x']
    dy = ray1.p2['y'] - ray1.p1['y']
    length = math.sqrt(dx*dx + dy*dy)
    print(f"  Ray: ({ray1.p1['x']}, {ray1.p1['y']}) -> ({ray1.p2['x']}, {ray1.p2['y']})")
    print(f"  Length: {length:.2f}")

    # Test 6: Different polarization states
    print("\nTest 6: Polarization states")
    rays = [
        Ray(p1={'x': 0, 'y': 0}, p2={'x': 1, 'y': 0}, brightness_s=1.0, brightness_p=0.0),  # S-polarized
        Ray(p1={'x': 0, 'y': 0}, p2={'x': 1, 'y': 0}, brightness_s=0.0, brightness_p=1.0),  # P-polarized
        Ray(p1={'x': 0, 'y': 0}, p2={'x': 1, 'y': 0}, brightness_s=0.5, brightness_p=0.5),  # Unpolarized
        Ray(p1={'x': 0, 'y': 0}, p2={'x': 1, 'y': 0}, brightness_s=0.0, brightness_p=0.0),  # Absorbed
    ]

    for i, ray in enumerate(rays):
        print(f"  Ray {i+1}: s={ray.brightness_s:.1f}, p={ray.brightness_p:.1f}, total={ray.total_brightness:.1f}")

    print("\nRay test completed successfully!")
