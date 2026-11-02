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
from typing import Dict, Any, Optional

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
    from ray_tracing_shapely.core import geometry
else:
    from .glass import Glass
    from ... import geometry


class SphericalLens(Glass):
    """
    Spherical lens with user-friendly parametric definition.

    A spherical lens can be defined in two ways:
    1. By radii of curvature: thickness (d), R1, R2
    2. By focal distances: thickness (d), FFD (front focal distance), BFD (back focal distance)

    Once built, it behaves exactly like a Glass object with a specific lens-shaped path.
    If parameters are invalid, the lens remains unbuilt and stores the parameters.

    Attributes:
        path: The path of the lens if it is built (6 points forming lens shape).
        def_by: Definition mode - either 'DR1R2' or 'DFfdBfd'.
        p1: Top edge point of lens aperture (when not built).
        p2: Bottom edge point of lens aperture (when not built).
        params: Parameters dict (d, r1, r2) or (d, ffd, bfd) when not built.
        ref_index: The refractive index (or Cauchy A coefficient).
        cauchy_b: The Cauchy B coefficient (in μm²).

    Usage:
        Spherical lenses are useful for:
        - Designing optical systems with known focal lengths
        - Creating realistic lens simulations
        - Testing optical configurations with physical lens parameters
        - Prisms and other refractive elements

    Notes:
        - Lens shape has 6 path points: 4 edge points + 2 arc center points
        - Invalid parameters result in unbuilt lens (path=None, params stored)
        - Supports both converging and diverging lenses (positive/negative curvature)
        - Refractive index can be wavelength-dependent (Cauchy equation)
    """

    type = 'SphericalLens'
    is_optical = True
    merges_with_glass = True
    serializable_defaults = {
        'path': None,
        'def_by': 'DR1R2',
        'p1': None,
        'p2': None,
        'params': None,
        'refIndex': 1.5,
        'cauchyB': 0.004
    }

    def __init__(self, scene, json_obj=None):
        """
        Initialize the spherical lens.

        Args:
            scene: The scene this lens belongs to.
            json_obj: Optional JSON object with lens properties.
        """
        super().__init__(scene, json_obj)

        # If lens is not built but has parameters, build it
        if not self.path and self.p1 and self.p2:
            if self.def_by == 'DR1R2' and self.params:
                self.create_lens_with_dr1r2(
                    self.params['d'],
                    self.params['r1'],
                    self.params['r2']
                )
            elif self.def_by == 'DFfdBfd' and self.params:
                self.create_lens_with_dffd_bfd(
                    self.params['d'],
                    self.params['ffd'],
                    self.params['bfd']
                )

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with lens controls.

        Args:
            obj_bar: The object bar to populate.
        """
        obj_bar.set_title('Spherical Lens')

        # Definition mode selector
        obj_bar.create_dropdown(
            '',
            self.def_by,
            {
                'DR1R2': 'Radii of Curvature',
                'DFfdBfd': 'Focal Distances'
            },
            lambda obj, value: setattr(obj, 'def_by', value),
            None,
            True
        )

        if self.def_by == 'DR1R2':
            params = self.get_dr1r2()
            r1 = params['r1']
            r2 = params['r2']
            d = params['d']

            obj_bar.create_number('R1', 0, 100, 1, r1,
                                lambda obj, val: obj.create_lens_with_dr1r2(d, val, r2), None, True)
            obj_bar.create_number('R2', 0, 100, 1, r2,
                                lambda obj, val: obj.create_lens_with_dr1r2(d, r1, val), None, True)
            obj_bar.create_number('d', 0, 100, 1, d,
                                lambda obj, val: obj.create_lens_with_dr1r2(val, r1, r2), None, True)
        elif self.def_by == 'DFfdBfd':
            params = self.get_dffd_bfd()
            d = params['d']
            ffd = params['ffd']
            bfd = params['bfd']

            obj_bar.create_number('FFD', 0, 100, 1, ffd,
                                lambda obj, val: obj.create_lens_with_dffd_bfd(d, val, bfd), None, True)
            obj_bar.create_number('BFD', 0, 100, 1, bfd,
                                lambda obj, val: obj.create_lens_with_dffd_bfd(d, ffd, val), None, True)
            obj_bar.create_number('d', 0, 100, 1, d,
                                lambda obj, val: obj.create_lens_with_dffd_bfd(val, ffd, bfd), None, True)

        # Refractive index controls
        if self.scene.simulate_colors:
            obj_bar.create_number('Cauchy A', 1, 3, 0.01, self.ref_index,
                                lambda obj, val: self._update_ref_index(obj, val))
            obj_bar.create_number('B(μm²)', 0.0001, 0.02, 0.0001, self.cauchy_b,
                                lambda obj, val: self._update_cauchy_b(obj, val))
        else:
            obj_bar.create_number('Refractive Index', 0.5, 2.5, 0.01, self.ref_index,
                                lambda obj, val: self._update_ref_index(obj, val))

    def _update_ref_index(self, obj, value):
        """Helper to update refractive index and rebuild if needed."""
        old_params = obj.get_dffd_bfd()
        obj.ref_index = value
        if obj.def_by == 'DFfdBfd':
            obj.create_lens_with_dffd_bfd(old_params['d'], old_params['ffd'], old_params['bfd'])

    def _update_cauchy_b(self, obj, value):
        """Helper to update Cauchy B and rebuild if needed."""
        old_params = obj.get_dffd_bfd()
        obj.cauchy_b = value
        if obj.def_by == 'DFfdBfd':
            obj.create_lens_with_dffd_bfd(old_params['d'], old_params['ffd'], old_params['bfd'])

    def move(self, diff_x, diff_y):
        """
        Move the lens.

        Args:
            diff_x: X displacement.
            diff_y: Y displacement.

        Returns:
            True to indicate success.
        """
        if self.path:
            return super().move(diff_x, diff_y)
        elif self.p1 and self.p2:
            self.p1['x'] += diff_x
            self.p1['y'] += diff_y
            self.p2['x'] += diff_x
            self.p2['y'] += diff_y
            return True
        return False

    def rotate(self, angle, center=None):
        """Rotate the lens (only if built)."""
        if self.path:
            return super().rotate(angle, center)
        return False

    def scale(self, scale_factor, center=None):
        """Scale the lens (only if built)."""
        if self.path:
            return super().scale(scale_factor, center)
        return False

    def check_ray_intersects(self, ray):
        """Check if ray intersects (only if lens is built)."""
        if not self.path:
            return None
        return super().check_ray_intersects(ray)

    def create_lens_with_dr1r2(self, d, r1, r2):
        """
        Create lens using thickness and radii of curvature.

        Args:
            d: Lens thickness at center.
            r1: Radius of curvature of first surface (can be negative).
            r2: Radius of curvature of second surface (can be negative).
        """
        self.error = None

        # Get current lens endpoints (ensure they're Point objects)
        if not self.path:
            p1 = geometry.point(self.p1['x'], self.p1['y']) if isinstance(self.p1, dict) else self.p1
            p2 = geometry.point(self.p2['x'], self.p2['y']) if isinstance(self.p2, dict) else self.p2
        else:
            old_params = self.get_dr1r2()
            p1 = geometry.midpoint(self.path[0], self.path[1])
            p2 = geometry.midpoint(self.path[3], self.path[4])
            old_d = old_params['d']
            old_r1 = old_params['r1']
            old_r2 = old_params['r2']
            old_length = math.hypot(p1.x - p2.x, p1.y - p2.y)

            # Calculate correction for symmetric movement
            if math.isfinite(old_r1) and old_r1 != 0:
                old_curve_shift1 = old_r1 - math.sqrt(old_r1 ** 2 - old_length ** 2 / 4) * (1 if old_r1 > 0 else -1)
            else:
                old_curve_shift1 = 0

            if math.isfinite(old_r2) and old_r2 != 0:
                old_curve_shift2 = old_r2 - math.sqrt(old_r2 ** 2 - old_length ** 2 / 4) * (1 if old_r2 > 0 else -1)
            else:
                old_curve_shift2 = 0

            old_edge_shift1 = old_d / 2 - old_curve_shift1
            old_edge_shift2 = old_d / 2 + old_curve_shift2

        length = math.hypot(p2.x - p1.x, p2.y - p1.y)
        dx = (p2.x - p1.x) / length
        dy = (p2.y - p1.y) / length
        dpx = dy
        dpy = -dx

        # Apply correction if updating existing lens
        if self.path:
            correction = (old_edge_shift1 - old_edge_shift2) / 2
            p1_dict = {'x': p1.x + dpx * correction, 'y': p1.y + dpy * correction}
            p2_dict = {'x': p2.x + dpx * correction, 'y': p2.y + dpy * correction}
            p1 = geometry.point(p1_dict['x'], p1_dict['y'])
            p2 = geometry.point(p2_dict['x'], p2_dict['y'])

        cx = (p1.x + p2.x) * 0.5
        cy = (p1.y + p2.y) * 0.5

        # Calculate curve shifts
        if math.isfinite(r1) and r1 != 0:
            discriminant1 = r1 ** 2 - length ** 2 / 4
            if discriminant1 < 0:
                curve_shift1 = float('nan')
            else:
                curve_shift1 = r1 - math.sqrt(discriminant1) * (1 if r1 > 0 else -1)
        else:
            curve_shift1 = 0

        if math.isfinite(r2) and r2 != 0:
            discriminant2 = r2 ** 2 - length ** 2 / 4
            if discriminant2 < 0:
                curve_shift2 = float('nan')
            else:
                curve_shift2 = r2 - math.sqrt(discriminant2) * (1 if r2 > 0 else -1)
        else:
            curve_shift2 = 0

        edge_shift1 = d / 2 - curve_shift1
        edge_shift2 = d / 2 + curve_shift2

        if math.isnan(curve_shift1) or math.isnan(curve_shift2):
            # Invalid lens - store parameters
            self.p1 = {'x': p1.x, 'y': p1.y}
            self.p2 = {'x': p2.x, 'y': p2.y}
            self.path = None
            self.params = {'r1': r1, 'r2': r2, 'd': d}
            self.error = 'Invalid lens parameters'
        else:
            # Create valid lens path
            if not self.path:
                self.path = []
            self.path = [
                {'x': p1.x - dpx * edge_shift1, 'y': p1.y - dpy * edge_shift1, 'arc': False},
                {'x': p1.x + dpx * edge_shift2, 'y': p1.y + dpy * edge_shift2, 'arc': False},
                {'x': cx + dpx * (d / 2), 'y': cy + dpy * (d / 2), 'arc': True},
                {'x': p2.x + dpx * edge_shift2, 'y': p2.y + dpy * edge_shift2, 'arc': False},
                {'x': p2.x - dpx * edge_shift1, 'y': p2.y - dpy * edge_shift1, 'arc': False},
                {'x': cx - dpx * (d / 2), 'y': cy - dpy * (d / 2), 'arc': True}
            ]
            self.p1 = None
            self.p2 = None
            self.params = None
            self.not_done = False

    def create_lens_with_dffd_bfd(self, d, ffd, bfd):
        """
        Create lens using thickness and focal distances.

        Args:
            d: Lens thickness at center.
            ffd: Front focal distance.
            bfd: Back focal distance.
        """
        self.error = None

        # Get refractive index at reference wavelength (546 nm)
        n = self.get_ref_index_at(None, type('obj', (), {'wavelength': 546})())

        # Solve for r1 and r2 from focal distances
        # Two possible solutions from quadratic equation
        discriminant = d ** 2 + 4 * bfd * ffd * n ** 2

        if discriminant < 0:
            # Invalid - store parameters
            self._store_invalid_lens(d, ffd, bfd)
            return

        sqrt_disc = math.sqrt(discriminant)

        r1_1 = (d * (n - 1) * (d + 2 * ffd * n - sqrt_disc)) / (2 * n * (d + (ffd - bfd) * n))
        r2_1 = -(d * (n - 1) * (d + 2 * bfd * n - sqrt_disc)) / (2 * n * (d + (bfd - ffd) * n))

        r1_2 = (d * (n - 1) * (d + 2 * ffd * n + sqrt_disc)) / (2 * n * (d + (ffd - bfd) * n))
        r2_2 = -(d * (n - 1) * (d + 2 * bfd * n + sqrt_disc)) / (2 * n * (d + (bfd - ffd) * n))

        # Determine which solution to use
        valid_1 = not (math.isnan(r1_1) or math.isnan(r2_1))
        valid_2 = not (math.isnan(r1_2) or math.isnan(r2_2))

        if valid_1 and not valid_2:
            self.create_lens_with_dr1r2(d, r1_1, r2_1)
        elif valid_2 and not valid_1:
            self.create_lens_with_dr1r2(d, r1_2, r2_2)
        elif valid_1 and valid_2:
            # Both valid - choose based on proximity to old parameters
            if self.path:
                old_params = self.get_dr1r2()
                diff_1 = abs(old_params['r1'] - r1_1) + abs(old_params['r2'] - r2_1)
                diff_2 = abs(old_params['r1'] - r1_2) + abs(old_params['r2'] - r2_2)
                if diff_1 < diff_2:
                    r1_a, r2_a = r1_1, r2_1
                    r1_b, r2_b = r1_2, r2_2
                else:
                    r1_a, r2_a = r1_2, r2_2
                    r1_b, r2_b = r1_1, r2_1
            else:
                # Prefer smaller radii
                if abs(r1_1) + abs(r2_1) < abs(r1_2) + abs(r2_2):
                    r1_a, r2_a = r1_1, r2_1
                    r1_b, r2_b = r1_2, r2_2
                else:
                    r1_a, r2_a = r1_2, r2_2
                    r1_b, r2_b = r1_1, r2_1

            # Try preferred solution
            self.create_lens_with_dr1r2(d, r1_a, r2_a)
            if not self.path:
                # Try alternative if preferred failed
                self.create_lens_with_dr1r2(d, r1_b, r2_b)
        else:
            # Neither valid - store parameters
            self._store_invalid_lens(d, ffd, bfd)

        # If still invalid, store focal distance parameters
        if not self.path:
            self.params = {'d': d, 'ffd': ffd, 'bfd': bfd}

    def _store_invalid_lens(self, d, ffd, bfd):
        """Store parameters for invalid lens."""
        if not self.path:
            p1 = self.p1
            p2 = self.p2
        else:
            p1 = geometry.midpoint(self.path[0], self.path[1])
            p2 = geometry.midpoint(self.path[3], self.path[4])

        self.p1 = {'x': p1.x, 'y': p1.y} if hasattr(p1, 'x') else p1
        self.p2 = {'x': p2.x, 'y': p2.y} if hasattr(p2, 'x') else p2
        self.path = None
        self.params = {'d': d, 'ffd': ffd, 'bfd': bfd}
        self.error = 'Invalid lens parameters'

    def get_dr1r2(self):
        """
        Get lens parameters as thickness, R1, R2.

        Returns:
            Dict with keys: d (thickness at center), r1, r2
        """
        if self.params and 'r1' in self.params:
            return self.params

        if not self.path or len(self.path) < 6:
            return {'d': 0, 'r1': float('inf'), 'r2': float('inf')}

        # Calculate from path (convert dict points to Point objects)
        p0 = geometry.point(self.path[0]['x'], self.path[0]['y'])
        p1 = geometry.point(self.path[1]['x'], self.path[1]['y'])
        p2 = geometry.point(self.path[2]['x'], self.path[2]['y'])
        p3 = geometry.point(self.path[3]['x'], self.path[3]['y'])
        p4 = geometry.point(self.path[4]['x'], self.path[4]['y'])
        p5 = geometry.point(self.path[5]['x'], self.path[5]['y'])

        center1 = geometry.lines_intersection(
            geometry.perpendicular_bisector(geometry.line(p1, p2)),
            geometry.perpendicular_bisector(geometry.line(p3, p2))
        )
        r2 = geometry.distance(center1, p2)

        center2 = geometry.lines_intersection(
            geometry.perpendicular_bisector(geometry.line(p4, p5)),
            geometry.perpendicular_bisector(geometry.line(p0, p5))
        )
        r1 = geometry.distance(center2, p5)

        # Get optical axis direction
        midpoint1 = geometry.midpoint(p0, p1)
        midpoint2 = geometry.midpoint(p3, p4)
        length = math.hypot(midpoint2.x - midpoint1.x, midpoint2.y - midpoint1.y)
        dpx = (midpoint2.y - midpoint1.y) / length
        dpy = -(midpoint2.x - midpoint1.x) / length

        d = geometry.distance(p2, p5)

        # Correct signs
        if dpx * (center1.x - p2.x) + dpy * (center1.y - p2.y) < 0:
            r2 = -r2
        if dpx * (center2.x - p5.x) + dpy * (center2.y - p5.y) < 0:
            r1 = -r1

        if math.isnan(r1):
            r1 = float('inf')
        if math.isnan(r2):
            r2 = float('inf')

        return {'d': d, 'r1': r1, 'r2': r2}

    def get_dffd_bfd(self):
        """
        Get lens parameters as thickness, FFD, BFD.

        Returns:
            Dict with keys: d (thickness at center), ffd, bfd
        """
        if self.params and 'ffd' in self.params:
            return self.params

        dr1r2 = self.get_dr1r2()
        r1 = dr1r2['r1']
        r2 = dr1r2['r2']
        d = dr1r2['d']

        # Get refractive index
        n = self.get_ref_index_at(None, type('obj', (), {'wavelength': 546})())

        # Calculate focal length and focal distances
        f = 1 / ((n - 1) * (1 / r1 - 1 / r2 + (n - 1) * d / (n * r1 * r2)))
        ffd = f * (1 + (n - 1) * d / (n * r2))
        bfd = f * (1 - (n - 1) * d / (n * r1))

        return {'d': d, 'ffd': ffd, 'bfd': bfd}


# Example usage and testing
if __name__ == "__main__":
    print("Testing SphericalLens class...\n")

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.simulate_colors = False
            self.length_scale = 1.0
            self._rng_counter = 0

        def rng(self):
            """Simple random number generator for testing."""
            self._rng_counter += 1
            return (self._rng_counter * 0.123456789) % 1.0

    # Test 1: Create lens with radii of curvature
    print("Test 1: Lens with D, R1, R2")
    scene = MockScene()
    lens = SphericalLens(scene, {
        'p1': {'x': 0, 'y': -25},
        'p2': {'x': 0, 'y': 25},
        'def_by': 'DR1R2',
        'params': {'d': 10, 'r1': 50, 'r2': -50},
        'refIndex': 1.5
    })

    if lens.path:
        print(f"  Lens built successfully")
        print(f"  Number of path points: {len(lens.path)}")
        params = lens.get_dr1r2()
        print(f"  D={params['d']:.1f}, R1={params['r1']:.1f}, R2={params['r2']:.1f}")
    else:
        print(f"  Lens not built: {lens.error}")

    # Test 2: Get focal distances
    print("\nTest 2: Convert to focal distances")
    if lens.path:
        focal_params = lens.get_dffd_bfd()
        print(f"  D={focal_params['d']:.1f}, FFD={focal_params['ffd']:.1f}, BFD={focal_params['bfd']:.1f}")

    # Test 3: Create lens with focal distances
    print("\nTest 3: Lens with D, FFD, BFD")
    lens_focal = SphericalLens(scene, {
        'p1': {'x': 100, 'y': -30},
        'p2': {'x': 100, 'y': 30},
        'def_by': 'DFfdBfd',
        'params': {'d': 8, 'ffd': 50, 'bfd': 50},
        'refIndex': 1.5
    })

    if lens_focal.path:
        print(f"  Lens built successfully")
        params_rad = lens_focal.get_dr1r2()
        print(f"  Calculated R1={params_rad['r1']:.1f}, R2={params_rad['r2']:.1f}")
    else:
        print(f"  Lens not built: {lens_focal.error}")

    # Test 4: Invalid parameters
    print("\nTest 4: Invalid parameters")
    lens_invalid = SphericalLens(scene, {
        'p1': {'x': 0, 'y': -10},
        'p2': {'x': 0, 'y': 10},
        'def_by': 'DR1R2',
        'params': {'d': 100, 'r1': 5, 'r2': 5},  # d too large for small radii
        'refIndex': 1.5
    })

    if lens_invalid.path:
        print(f"  Lens built (unexpected)")
    else:
        print(f"  Lens not built (expected): {lens_invalid.error}")
        print(f"  Stored params: {lens_invalid.params}")

    # Test 5: Transformations
    print("\nTest 5: Transformations")
    if lens.path:
        print(f"  Initial center: {lens.get_default_center()}")
        lens.move(50, 0)
        print(f"  After move(50, 0): {lens.get_default_center()}")

    print("\nSphericalLens test completed successfully!")
