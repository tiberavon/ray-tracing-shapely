"""
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
PYTHON-SPECIFIC MODULE: Ground Glass Diffuser
===============================================================================
This module is a Python-specific addition and does NOT exist in the original
JavaScript Ray Optics Simulation codebase. It provides a ground glass (diffuser)
optical element that scatters incident light according to configurable patterns.

Features:
- Configurable number of scatter rays
- Multiple scatter modes: deterministic (uniform), pseudorandom (hash-based)
- Adjustable scatter angle range
- Energy conservation with optional reflection
- Two-sided operation support
===============================================================================
"""

import math
import hashlib
from typing import Dict, Any, Optional, List

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_scene_obj import BaseSceneObj, SimulationReturn
    from ray_tracing_shapely.core.scene_objs.line_obj_mixin import LineObjMixin
    from ray_tracing_shapely.core import geometry
else:
    from .base_scene_obj import BaseSceneObj, SimulationReturn
    from .line_obj_mixin import LineObjMixin
    from .. import geometry


class GroundGlass(LineObjMixin, BaseSceneObj):
    """
    Ground glass diffuser that scatters incident light.

    A ground glass surface scatters incoming light into multiple directions
    within a configurable angular range. This simulates the behavior of
    frosted glass or other diffusing optical elements.

    Attributes:
        p1 (dict): First endpoint of the diffuser line {'x': float, 'y': float}
        p2 (dict): Second endpoint of the diffuser line {'x': float, 'y': float}
        scatter_rays (int): Number of scattered rays to generate (default: 5)
        scatter_angle (float): Half-angle of scatter cone in degrees (default: 30)
        scatter_mode (str): 'deterministic' for uniform distribution,
                           'pseudorandom' for hash-based pseudo-random scatter
        reflection_fraction (float): Fraction of energy reflected (0.0 to 1.0, default: 0.0)
        two_sided (bool): Whether the surface scatters from both sides (default: True)

    Example:
        >>> from ray_tracing_shapely.core import Scene
        >>> scene = Scene()
        >>> diffuser = scene.add_object('ground_glass', {
        ...     'p1': {'x': 100, 'y': 0},
        ...     'p2': {'x': 100, 'y': 100},
        ...     'scatter_rays': 7,
        ...     'scatter_angle': 45
        ... })
    """

    type = 'ground_glass'
    serializable_defaults = {
        'p1': {'x': 0, 'y': 0},
        'p2': {'x': 100, 'y': 0},
        'scatter_rays': 5,
        'scatter_angle': 30.0,
        'scatter_mode': 'deterministic',
        'reflection_fraction': 0.0,
        'two_sided': True,
    }
    is_optical = True

    def __init__(self, scene, json_obj: Optional[Dict[str, Any]] = None):
        """
        Initialize the ground glass diffuser.

        Args:
            scene: The scene the object belongs to.
            json_obj: The JSON object to be deserialized, if any.
        """
        super().__init__(scene, json_obj)

    def check_ray_intersects(self, ray) -> Optional[Any]:
        """
        Check if a ray intersects this diffuser surface.

        Args:
            ray: The ray to check for intersection.

        Returns:
            Intersection point if hit, None otherwise.
        """
        return self.check_ray_intersects_shape(ray)

    def on_simulate(
        self,
        ray,
        ray_index: int,
        incident_point,
        surface_merging_objs: List,
        body_merging_obj
    ) -> SimulationReturn:
        """
        Handle ray interaction with the ground glass surface.

        The diffuser scatters the incident ray into multiple directions
        according to the configured scatter pattern.

        Args:
            ray: The incident ray (modified in-place for first output ray).
            ray_index: Index of the ray in the simulation.
            incident_point: Point where ray hits the surface.
            surface_merging_objs: Glass objects merged at this surface (unused).
            body_merging_obj: GRIN glass object for body merging (unused).

        Returns:
            SimulationReturn dict with newRays, isAbsorbed, and truncation.
        """
        # Get incident point coordinates
        if hasattr(incident_point, 'x'):
            inc_x, inc_y = incident_point.x, incident_point.y
        else:
            inc_x, inc_y = incident_point['x'], incident_point['y']

        # Calculate surface normal
        dx = self.p2['x'] - self.p1['x']
        dy = self.p2['y'] - self.p1['y']
        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return {'isAbsorbed': True}

        # Normal perpendicular to surface (pointing "up" relative to p1->p2 direction)
        normal_x = -dy / length
        normal_y = dx / length
        normal_angle = math.atan2(normal_y, normal_x)

        # Calculate incident ray angle
        ray_dx = ray.p2['x'] - ray.p1['x']
        ray_dy = ray.p2['y'] - ray.p1['y']
        ray_angle = math.atan2(ray_dy, ray_dx)

        # Determine which side the ray is coming from
        dot_product = ray_dx * normal_x + ray_dy * normal_y
        if dot_product > 0:
            # Ray coming from the normal side - flip normal
            normal_angle += math.pi
            if not self.two_sided:
                # Not two-sided and ray coming from wrong side - ignore
                return {'isAbsorbed': False}

        # Calculate transmitted direction (straight through for diffuser)
        transmitted_angle = ray_angle

        # Generate scatter angles
        scatter_angles = self._generate_scatter_angles(
            transmitted_angle,
            ray_index,
            inc_x,
            inc_y
        )

        # Calculate energy per ray
        total_brightness_s = ray.brightness_s
        total_brightness_p = ray.brightness_p

        # Handle reflection if configured
        reflected_brightness_s = total_brightness_s * self.reflection_fraction
        reflected_brightness_p = total_brightness_p * self.reflection_fraction
        transmitted_brightness_s = total_brightness_s - reflected_brightness_s
        transmitted_brightness_p = total_brightness_p - reflected_brightness_p

        # Distribute transmitted energy among scatter rays
        num_scatter = len(scatter_angles)
        brightness_per_ray_s = transmitted_brightness_s / num_scatter if num_scatter > 0 else 0
        brightness_per_ray_p = transmitted_brightness_p / num_scatter if num_scatter > 0 else 0

        new_rays = []
        truncation = 0.0
        is_absorbed = True

        # Get brightness threshold from scene
        brightness_threshold = self.scene.get_min_brightness_threshold()

        # Create scattered rays
        for i, angle in enumerate(scatter_angles):
            if i == 0:
                # Reuse the incident ray for the first scattered ray
                scattered_ray = ray
            else:
                # Create new ray
                scattered_ray = ray.copy()

            # Set ray position and direction
            scattered_ray.p1 = {'x': inc_x, 'y': inc_y}
            scattered_ray.p2 = {
                'x': inc_x + math.cos(angle),
                'y': inc_y + math.sin(angle)
            }
            scattered_ray.brightness_s = brightness_per_ray_s
            scattered_ray.brightness_p = brightness_per_ray_p

            # Check brightness threshold
            total_brightness = scattered_ray.brightness_s + scattered_ray.brightness_p
            if total_brightness > brightness_threshold:
                if i == 0:
                    is_absorbed = False
                else:
                    new_rays.append(scattered_ray)
            else:
                truncation += total_brightness

        # Create reflected ray if reflection is configured
        if self.reflection_fraction > 0:
            reflected_ray = ray.copy()
            # Reflect angle about the normal
            incident_to_normal = ray_angle - normal_angle
            reflected_angle = normal_angle - incident_to_normal + math.pi

            reflected_ray.p1 = {'x': inc_x, 'y': inc_y}
            reflected_ray.p2 = {
                'x': inc_x + math.cos(reflected_angle),
                'y': inc_y + math.sin(reflected_angle)
            }
            reflected_ray.brightness_s = reflected_brightness_s
            reflected_ray.brightness_p = reflected_brightness_p

            total_reflected = reflected_ray.brightness_s + reflected_ray.brightness_p
            if total_reflected > brightness_threshold:
                new_rays.append(reflected_ray)
            else:
                truncation += total_reflected

        # Disable image detection for multiple rays
        if len(new_rays) > 0:
            ray.gap = True
            for new_ray in new_rays:
                new_ray.gap = True

        return {
            'newRays': new_rays,
            'isAbsorbed': is_absorbed,
            'truncation': truncation
        }

    def _generate_scatter_angles(
        self,
        center_angle: float,
        ray_index: int,
        x: float,
        y: float
    ) -> List[float]:
        """
        Generate scatter angles based on the configured mode.

        Args:
            center_angle: The center direction for scattering (radians).
            ray_index: Index of the ray (used for pseudorandom seeding).
            x: X coordinate of intersection (used for pseudorandom seeding).
            y: Y coordinate of intersection (used for pseudorandom seeding).

        Returns:
            List of scatter angles in radians.
        """
        scatter_rad = math.radians(self.scatter_angle)
        num_rays = max(1, int(self.scatter_rays))

        if self.scatter_mode == 'pseudorandom':
            return self._generate_pseudorandom_angles(
                center_angle, scatter_rad, num_rays, ray_index, x, y
            )
        else:
            # Deterministic uniform distribution
            return self._generate_deterministic_angles(
                center_angle, scatter_rad, num_rays
            )

    def _generate_deterministic_angles(
        self,
        center_angle: float,
        scatter_rad: float,
        num_rays: int
    ) -> List[float]:
        """
        Generate uniformly distributed scatter angles.

        Args:
            center_angle: Center direction for scattering (radians).
            scatter_rad: Half-angle of scatter cone (radians).
            num_rays: Number of rays to generate.

        Returns:
            List of scatter angles in radians.
        """
        if num_rays == 1:
            return [center_angle]

        angles = []
        for i in range(num_rays):
            # Uniform distribution from -scatter_rad to +scatter_rad
            fraction = (i / (num_rays - 1)) * 2 - 1  # -1 to +1
            angle = center_angle + fraction * scatter_rad
            angles.append(angle)

        return angles

    def _generate_pseudorandom_angles(
        self,
        center_angle: float,
        scatter_rad: float,
        num_rays: int,
        ray_index: int,
        x: float,
        y: float
    ) -> List[float]:
        """
        Generate pseudo-random scatter angles using hash-based seeding.

        The angles are deterministic for a given ray position and index,
        ensuring reproducible simulations while appearing random.

        Args:
            center_angle: Center direction for scattering (radians).
            scatter_rad: Half-angle of scatter cone (radians).
            num_rays: Number of rays to generate.
            ray_index: Index of the ray.
            x: X coordinate of intersection.
            y: Y coordinate of intersection.

        Returns:
            List of scatter angles in radians.
        """
        angles = []

        for i in range(num_rays):
            # Create deterministic hash from position and indices
            seed_string = f"{x:.6f}:{y:.6f}:{ray_index}:{i}"
            hash_value = hashlib.md5(seed_string.encode()).hexdigest()

            # Convert first 8 hex chars to float in [0, 1)
            hash_int = int(hash_value[:8], 16)
            random_value = hash_int / 0xFFFFFFFF

            # Map to scatter range [-scatter_rad, +scatter_rad]
            offset = (random_value * 2 - 1) * scatter_rad
            angles.append(center_angle + offset)

        return angles


# Example usage and testing
if __name__ == "__main__":
    print("Testing GroundGlass class...\n")

    # Mock scene for testing
    class MockScene:
        def __init__(self):
            self.error = None
            self.warning = None
            self.color_mode = 'default'
            self.min_brightness_exp = -6

        def get_min_brightness_threshold(self):
            return 10 ** self.min_brightness_exp

    # Mock ray for testing
    class MockRay:
        def __init__(self, p1, p2, brightness_s=0.5, brightness_p=0.5):
            self.p1 = p1
            self.p2 = p2
            self.brightness_s = brightness_s
            self.brightness_p = brightness_p
            self.wavelength = None
            self.gap = False
            self.is_new = True
            self.body_merging_obj = None
            self.is_tir_result = False
            self.caused_tir = False
            self.tir_count = 0
            self.source_uuid = None
            self.source_label = None

        def copy(self):
            new_ray = MockRay(
                {'x': self.p1['x'], 'y': self.p1['y']},
                {'x': self.p2['x'], 'y': self.p2['y']},
                self.brightness_s,
                self.brightness_p
            )
            new_ray.wavelength = self.wavelength
            new_ray.gap = self.gap
            new_ray.is_new = self.is_new
            return new_ray

    scene = MockScene()

    # Test 1: Basic creation
    print("Test 1: Basic creation")
    diffuser = GroundGlass(scene, {
        'p1': {'x': 100, 'y': 0},
        'p2': {'x': 100, 'y': 100},
        'scatter_rays': 5,
        'scatter_angle': 30
    })
    print(f"  Type: {diffuser.type}")
    print(f"  p1: {diffuser.p1}")
    print(f"  p2: {diffuser.p2}")
    print(f"  Scatter rays: {diffuser.scatter_rays}")
    print(f"  Scatter angle: {diffuser.scatter_angle}°")

    # Test 2: Deterministic angle generation
    print("\nTest 2: Deterministic scatter angles")
    angles = diffuser._generate_deterministic_angles(0, math.radians(30), 5)
    print(f"  Angles (deg): {[f'{math.degrees(a):.1f}' for a in angles]}")

    # Test 3: Pseudorandom angle generation
    print("\nTest 3: Pseudorandom scatter angles")
    diffuser.scatter_mode = 'pseudorandom'
    angles1 = diffuser._generate_pseudorandom_angles(0, math.radians(30), 5, 0, 100.0, 50.0)
    angles2 = diffuser._generate_pseudorandom_angles(0, math.radians(30), 5, 0, 100.0, 50.0)
    print(f"  First call (deg): {[f'{math.degrees(a):.1f}' for a in angles1]}")
    print(f"  Second call (deg): {[f'{math.degrees(a):.1f}' for a in angles2]}")
    print(f"  Reproducible: {angles1 == angles2}")

    # Test 4: Ray interaction
    print("\nTest 4: Ray scattering")
    diffuser.scatter_mode = 'deterministic'
    diffuser.scatter_rays = 3

    # Create a ray hitting the diffuser
    ray = MockRay(
        {'x': 0, 'y': 50},
        {'x': 100, 'y': 50},
        brightness_s=0.5,
        brightness_p=0.5
    )

    # Simulate intersection point
    incident_point = {'x': 100, 'y': 50}

    result = diffuser.on_simulate(ray, 0, incident_point, [], None)

    print(f"  Is absorbed: {result.get('isAbsorbed', False)}")
    print(f"  New rays created: {len(result.get('newRays', []))}")
    print(f"  Total rays (including modified original): {1 + len(result.get('newRays', []))}")

    # Check energy conservation
    total_energy = ray.brightness_s + ray.brightness_p
    for new_ray in result.get('newRays', []):
        total_energy += new_ray.brightness_s + new_ray.brightness_p
    total_energy += result.get('truncation', 0)
    print(f"  Total energy: {total_energy:.4f} (should be ~1.0)")

    # Test 5: Reflection mode
    print("\nTest 5: With reflection")
    diffuser.reflection_fraction = 0.2
    ray2 = MockRay(
        {'x': 0, 'y': 50},
        {'x': 100, 'y': 50},
        brightness_s=0.5,
        brightness_p=0.5
    )
    result2 = diffuser.on_simulate(ray2, 1, incident_point, [], None)
    print(f"  New rays created: {len(result2.get('newRays', []))}")
    print(f"  (includes {diffuser.scatter_rays - 1} scattered + 1 reflected)")

    print("\nGroundGlass test completed successfully!")
