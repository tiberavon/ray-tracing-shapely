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
from typing import Optional, Dict, Any, List
# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_scene_obj import BaseSceneObj
    from ray_tracing_shapely.core.scene_objs.line_obj_mixin import LineObjMixin
    from ray_tracing_shapely.core import geometry
else:
    from ..base_scene_obj import BaseSceneObj
    from ..line_obj_mixin import LineObjMixin
    from ...geometry import geometry


class Detector(LineObjMixin, BaseSceneObj):
    """
    The detector tool for measuring optical properties of rays.

    This detector is a line segment that measures:
    - Power (P): Total brightness of rays passing through
    - Normal force (F_perp): Component perpendicular to the detector
    - Shear force (F_par): Component parallel to the detector

    It can also create an irradiance map showing the distribution
    of power along the detector length.

    Attributes:
        p1 (dict): The first endpoint of the line segment {'x': float, 'y': float}
        p2 (dict): The second endpoint of the line segment {'x': float, 'y': float}
        irrad_map (bool): Whether to display the irradiance map
        bin_size (float): The size of each bin for the irradiance map
        power (float): The measured power through the detector
        normal (float): The measured normal force through the detector
        shear (float): The measured shear force through the detector
        bin_data (list): The measured data for each bin in the irradiance map
        hit_records (list): Per-hit records linking incident ray uuids to the
            bin they crossed. Enables detector-path lineage analysis.
    """

    type = 'Detector'
    is_optical = True

    serializable_defaults = {
        'p1': None,
        'p2': None,
        'irrad_map': False,
        'bin_size': 1.0
    }

    def __init__(self, scene, json_obj: Optional[Dict[str, Any]] = None):
        """
        Initialize the detector.

        Args:
            scene: The scene the detector belongs to.
            json_obj: The JSON object to be deserialized, if any.
        """
        super().__init__(scene, json_obj)

        # Initialize the quantities to be measured
        self.power = 0.0
        self.normal = 0.0
        self.shear = 0.0
        self.bin_data: Optional[List[float]] = None
        # Per-hit lineage records: one dict per ray crossing this detector.
        self.hit_records: List[Dict[str, Any]] = []

    @property
    def length(self) -> float:
        """Calculate the length of the detector."""
        if self.p1 is None or self.p2 is None:
            return 0.0
        dx = self.p2['x'] - self.p1['x']
        dy = self.p2['y'] - self.p1['y']
        return math.sqrt(dx * dx + dy * dy)

    @property
    def bin_count(self) -> int:
        """Calculate the number of bins for the irradiance map."""
        if self.bin_size <= 0:
            return 0
        return math.ceil(self.length / self.bin_size)

    def scale(self, scale: float, center=None) -> bool:
        """
        Scale the detector by the given scale factor.

        Note: Returns False because it's unclear what properties should be scaled
        (e.g., should bin_size scale too?).

        Args:
            scale: The scale factor.
            center: The center of scaling.

        Returns:
            False, indicating scaling behavior is undefined for detectors.
        """
        super().scale(scale, center)
        return False

    def on_simulation_start(self) -> None:
        """
        Reset detector measurements at the start of simulation.

        Called when the simulation starts. Resets all measured quantities
        and initializes bin data if irradiance map is enabled.
        """
        self.power = 0.0
        self.normal = 0.0
        self.shear = 0.0
        self.hit_records = []

        if self.irrad_map:
            bin_num = self.bin_count
            self.bin_data = [0.0] * bin_num
        else:
            self.bin_data = None

    def check_ray_intersects(self, ray) -> Optional[Any]:
        """
        Check whether the detector intersects with the given ray.

        Args:
            ray: The ray object.

        Returns:
            The intersection point if they intersect, None otherwise.
        """
        return self.check_ray_intersects_shape(ray)

    def on_ray_incident(
        self,
        ray,
        ray_index: int,
        incident_point,
        surface_merging_objs: List['BaseSceneObj'],
        verbose: int = 0
    ) -> None:
        """
        Handle ray incident on the detector.

        Measures power, normal force, and shear force from the incident ray.
        The ray passes through unchanged (detector doesn't affect ray direction).

        Physics:
        - Power = sum of (sign * total_brightness) for all rays
        - Normal force = sum of (sign * sin(theta) * total_brightness)
        - Shear force = sum of (-sign * cos(theta) * total_brightness)

        where sign is +1 if ray crosses from left to right (relative to p1->p2),
        -1 otherwise, and theta is the angle between the ray and the detector.

        Args:
            ray: The ray object.
            ray_index: The index of the ray.
            incident_point: The point where the ray intersects the detector.
            surface_merging_objs: Objects merged with this surface (unused for detector).
            verbose: Verbosity level for debugging.
        """
        # Calculate ray direction vector
        ray_dx = ray.p2['x'] - ray.p1['x']
        ray_dy = ray.p2['y'] - ray.p1['y']
        ray_len = math.sqrt(ray_dx * ray_dx + ray_dy * ray_dy)

        # Calculate detector direction vector
        det_dx = self.p2['x'] - self.p1['x']
        det_dy = self.p2['y'] - self.p1['y']
        det_len = math.sqrt(det_dx * det_dx + det_dy * det_dy)

        if ray_len == 0 or det_len == 0:
            return

        # Cross product determines which side ray is coming from
        # rcrosss = ray_direction x detector_direction
        rcrosss = ray_dx * det_dy - ray_dy * det_dx

        # sin(theta) = |cross product| / (|ray| * |detector|)
        sint = rcrosss / (ray_len * det_len)

        # cos(theta) = dot product / (|ray| * |detector|)
        cost = (ray_dx * det_dx + ray_dy * det_dy) / (ray_len * det_len)

        # Get total brightness of the ray
        total_brightness = ray.brightness_s + ray.brightness_p

        # Sign determines direction of crossing
        sign = 1 if rcrosss > 0 else -1

        # Update measurements
        self.power += sign * total_brightness
        self.normal += sign * sint * total_brightness
        self.shear -= sign * cost * total_brightness

        # Distance from p1 to incident point (along the detector), used both for
        # the irradiance bin and the lineage hit record.
        dist_x = incident_point['x'] - self.p1['x']
        dist_y = incident_point['y'] - self.p1['y']
        dist = math.sqrt(dist_x * dist_x + dist_y * dist_y)
        bin_index = int(dist / self.bin_size) if self.bin_size > 0 else None

        # Update irradiance map if enabled
        if self.irrad_map and self.bin_data is not None:
            # Make sure index is within bounds
            if bin_index is not None and 0 <= bin_index < len(self.bin_data):
                self.bin_data[bin_index] += sign * total_brightness

        # Record the incident ray's lineage identity so post-hoc analysis can
        # link detector bins back to optical paths. The simulator exposes the
        # incident segment's uuid as 'incident_uuid' on the output geometry
        # (getattr guards standalone callers such as the __main__ demo).
        self.hit_records.append({
            'ray_uuid': getattr(ray, 'incident_uuid', None),
            'bin_index': bin_index,
            'position': dist,
            'incident_point': {'x': incident_point['x'], 'y': incident_point['y']},
            'brightness_s': ray.brightness_s,
            'brightness_p': ray.brightness_p,
            'brightness_total': total_brightness,
            'sign': sign,
        })

        # Update ray position (ray passes through unchanged)
        # Move ray origin to incident point, keeping same direction
        ray.p2 = {'x': incident_point['x'] + ray_dx, 'y': incident_point['y'] + ray_dy}
        ray.p1 = {'x': incident_point['x'], 'y': incident_point['y']}

    def get_irradiance_data(self) -> List[Dict[str, float]]:
        """
        Get the irradiance map data as a list of position-irradiance pairs.

        Returns:
            List of dictionaries with 'position' and 'irradiance' keys.
        """
        if self.bin_data is None:
            return []

        result = []
        for i, power in enumerate(self.bin_data):
            result.append({
                'position': i * self.bin_size,
                'irradiance': power / self.bin_size if self.bin_size > 0 else 0
            })
        return result

    def get_hit_records(self) -> List[Dict[str, Any]]:
        """
        Get the per-hit lineage records collected during the simulation.

        Each record is a dict with keys: 'ray_uuid', 'bin_index', 'position',
        'incident_point', 'brightness_s', 'brightness_p', 'brightness_total',
        and 'sign'. Records are in the order rays crossed the detector.

        Returns:
            List of hit-record dicts (empty if no ray crossed the detector).
        """
        return self.hit_records

    def get_hit_uuids(self) -> List[str]:
        """
        Get the unique ray uuids that crossed this detector.

        These are the terminal-side segment uuids reaching the detector; they
        can be passed as `leaf_uuids` to lineage-analysis functions such as
        rank_paths_by_energy() to isolate the optical paths that hit it.

        Returns:
            List of unique ray uuids (order-preserving, None values dropped).
        """
        seen: Dict[str, None] = {}
        for record in self.hit_records:
            uuid = record['ray_uuid']
            if uuid is not None and uuid not in seen:
                seen[uuid] = None
        return list(seen)

    def get_bin_uuids(self, bin_index: int) -> List[str]:
        """
        Get the ray uuids that crossed a specific irradiance bin.

        Args:
            bin_index: The bin index (as used by bin_data / get_irradiance_data).

        Returns:
            List of unique ray uuids that hit the given bin (may be empty).
        """
        seen: Dict[str, None] = {}
        for record in self.hit_records:
            if record['bin_index'] == bin_index:
                uuid = record['ray_uuid']
                if uuid is not None and uuid not in seen:
                    seen[uuid] = None
        return list(seen)

    def export_csv(self) -> str:
        """
        Export the irradiance map data as CSV format.

        Returns:
            CSV string with Position and Irradiance columns.
        """
        lines = ["Position,Irradiance"]

        if self.bin_data is not None:
            for i, power in enumerate(self.bin_data):
                position = i * self.bin_size
                irradiance = power / self.bin_size if self.bin_size > 0 else 0
                lines.append(f"{position},{irradiance}")

        return "\n".join(lines)

    def get_measurements(self) -> Dict[str, float]:
        """
        Get all detector measurements.

        Returns:
            Dictionary with 'power', 'normal', 'shear', and 'length' keys.
        """
        return {
            'power': self.power,
            'normal': self.normal,
            'shear': self.shear,
            'length': self.length
        }

    def __repr__(self) -> str:
        """String representation of the detector."""
        return (f"Detector(p1={self.p1}, p2={self.p2}, "
                f"power={self.power:.4f}, normal={self.normal:.4f}, shear={self.shear:.4f})")


# Example usage and testing
if __name__ == "__main__":
    import sys
    import os

    # Add parent paths for imports when running as script
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

    from ray_tracing_shapely.core.scene import Scene

    print("Testing Detector class...\n")

    # Test 1: Create detector with defaults
    print("Test 1: Create detector with default values")
    scene = Scene()
    detector = Detector(scene)
    print(f"  p1: {detector.p1}")
    print(f"  p2: {detector.p2}")
    print(f"  irrad_map: {detector.irrad_map}")
    print(f"  bin_size: {detector.bin_size}")
    print(f"  power: {detector.power}")
    print(f"  normal: {detector.normal}")
    print(f"  shear: {detector.shear}")

    # Test 2: Create detector from JSON
    print("\nTest 2: Create detector from JSON")
    json_data = {
        'type': 'Detector',
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 100, 'y': 0},
        'irrad_map': True,
        'bin_size': 10.0
    }
    detector2 = Detector(scene, json_data)
    print(f"  p1: {detector2.p1}")
    print(f"  p2: {detector2.p2}")
    print(f"  irrad_map: {detector2.irrad_map}")
    print(f"  bin_size: {detector2.bin_size}")
    print(f"  length: {detector2.length}")
    print(f"  bin_count: {detector2.bin_count}")

    # Test 3: Simulation start
    print("\nTest 3: Simulation start (initialize bins)")
    detector2.on_simulation_start()
    print(f"  power (reset): {detector2.power}")
    print(f"  bin_data length: {len(detector2.bin_data) if detector2.bin_data else 0}")
    print(f"  bin_data: {detector2.bin_data}")

    # Test 4: Mock ray incident
    print("\nTest 4: Mock ray incident")

    # Create a mock ray class
    class MockRay:
        def __init__(self, p1, p2, brightness_s=0.5, brightness_p=0.5):
            self.p1 = p1
            self.p2 = p2
            self.brightness_s = brightness_s
            self.brightness_p = brightness_p

    # Ray going downward through the detector (perpendicular)
    ray1 = MockRay(
        p1={'x': 50, 'y': -50},
        p2={'x': 50, 'y': 50},
        brightness_s=0.5,
        brightness_p=0.5
    )

    # Check intersection
    intersection = detector2.check_ray_intersects(ray1)
    print(f"  Ray 1 intersection: {intersection}")

    if intersection:
        detector2.on_ray_incident(ray1, 0, intersection, [])
        print(f"  After ray 1:")
        print(f"    power: {detector2.power:.4f}")
        print(f"    normal: {detector2.normal:.4f}")
        print(f"    shear: {detector2.shear:.4f}")
        print(f"    bin_data: {detector2.bin_data}")

    # Ray going at 45 degrees
    ray2 = MockRay(
        p1={'x': 20, 'y': -20},
        p2={'x': 40, 'y': 0},  # Direction towards detector
        brightness_s=0.3,
        brightness_p=0.3
    )

    intersection2 = detector2.check_ray_intersects(ray2)
    print(f"\n  Ray 2 intersection: {intersection2}")

    if intersection2:
        detector2.on_ray_incident(ray2, 1, intersection2, [])
        print(f"  After ray 2:")
        print(f"    power: {detector2.power:.4f}")
        print(f"    normal: {detector2.normal:.4f}")
        print(f"    shear: {detector2.shear:.4f}")
        print(f"    bin_data: {detector2.bin_data}")

    # Test 5: Get measurements
    print("\nTest 5: Get measurements")
    measurements = detector2.get_measurements()
    print(f"  measurements: {measurements}")

    # Test 6: Export CSV
    print("\nTest 6: Export CSV")
    csv_data = detector2.export_csv()
    print(f"  CSV output:")
    for line in csv_data.split('\n')[:5]:  # First 5 lines
        print(f"    {line}")
    print("    ...")

    # Test 7: Serialization
    print("\nTest 7: Serialization")
    serialized = detector2.serialize()
    print(f"  Serialized: {serialized}")

    # Test 8: Detector without irradiance map
    print("\nTest 8: Detector without irradiance map")
    detector3 = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 50, 'y': 50}
    })
    detector3.on_simulation_start()
    print(f"  irrad_map: {detector3.irrad_map}")
    print(f"  bin_data: {detector3.bin_data}")
    print(f"  length: {detector3.length:.4f}")

    # Test 9: Move and transform
    print("\nTest 9: Move detector")
    detector3.move(10, 20)
    print(f"  After move(10, 20):")
    print(f"    p1: {detector3.p1}")
    print(f"    p2: {detector3.p2}")

    # Test 10: Repr
    print("\nTest 10: String representation")
    print(f"  {detector2}")

    print("\nDetector test completed successfully!")
