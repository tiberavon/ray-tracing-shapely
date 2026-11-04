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
from typing import List, Dict, Any, Optional

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_scene_obj import BaseSceneObj, SimulationReturn
    from ray_tracing_shapely.core import geometry
    from ray_tracing_shapely.core.equation import evaluate_latex
    from ray_tracing_shapely.core.constants import GREEN_WAVELENGTH
else:
    from .base_scene_obj import BaseSceneObj, SimulationReturn
    from .. import geometry
    from ..equation import evaluate_latex
    from ..constants import GREEN_WAVELENGTH


class BaseCustomSurface(BaseSceneObj):
    """
    The base class for custom surfaces (surfaces where ray interaction is defined by custom equations).

    Custom surfaces allow users to define arbitrary optical behavior by specifying:
    - Angle equations: Direction of outgoing rays as a function of incident angle
    - Brightness equations: Intensity of outgoing rays (can model reflection, transmission, etc.)

    Attributes:
        outRays: List of outgoing ray specifications. Each element is a dict with:
            - 'eqnTheta': LaTeX expression for the angle θ_j of the jth outgoing ray
            - 'eqnP': LaTeX expression for the brightness P_j of the jth outgoing ray
        twoSided: Whether the surface interacts with rays from both sides

    Variables available in equations:
        - θ_0 (theta_0): Angle of the incident ray
        - λ (lambda): Wavelength of the incident ray
        - t: Position of the incident ray on the surface
        - p: Polarization of the incident ray (0 for s-polarized, 1 for p-polarized)
        - n_0: Refractive index of the source medium
        - n_1: Refractive index of the destination medium
        - θ_j (theta_j): Angles of previous outgoing rays (for j < current ray)
        - P_j: Brightnesses of previous outgoing rays (for j < current ray)

    Note:
        Custom surfaces are very flexible and can model complex optical phenomena
        including beam splitters, dichroic mirrors, diffraction gratings, etc.
    """

    merges_with_glass = True

    def __init__(self, scene, json_obj: Optional[Dict[str, Any]] = None):
        """
        Initialize the custom surface.

        Args:
            scene: The scene the object belongs to.
            json_obj: The JSON object to be deserialized, if any.
        """
        super().__init__(scene, json_obj)

        # Check for unknown keys in outRays
        if hasattr(self, 'outRays'):
            known_keys = ['eqnTheta', 'eqnP']
            for i, out_ray in enumerate(self.outRays):
                for key in out_ray:
                    if key not in known_keys:
                        if hasattr(self.scene, 'error'):
                            self.scene.error = f"Unknown key 'outRays[{i}].{key}' for type '{self.type}'"

        # Initialize the equation functions
        self.fns = []
        if hasattr(self, 'outRays'):
            self.init_out_ray_fns()

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with custom surface controls.

        Args:
            obj_bar: The object bar to populate.
        """
        # Create info box with instructions
        obj_bar.create_info_box(
            "Custom Surface Equations:\n"
            "- θ_j: Angle of jth outgoing ray\n"
            "- P_j: Brightness of jth outgoing ray\n"
            "Available variables: theta_0, lambda, t, p, n_0, n_1\n"
            "Can reference previous rays: theta_1, theta_2, ..., P_1, P_2, ..."
        )

        # Create equations for each outgoing ray
        for i in range(len(self.outRays)):
            ray_index = i + 1

            # Angle equation
            obj_bar.create_equation(
                f"θ_{ray_index} =",
                self.outRays[i]['eqnTheta'],
                lambda obj, value, idx=i: self._update_theta(obj, idx, value)
            )

            # Brightness equation
            obj_bar.create_equation(
                f"P_{ray_index} =",
                self.outRays[i]['eqnP'],
                lambda obj, value, idx=i: self._update_brightness(obj, idx, value)
            )

        # Two-sided checkbox
        obj_bar.create_boolean(
            "Two-sided",
            self.twoSided,
            lambda obj, value: setattr(obj, 'twoSided', value)
        )

    def _update_theta(self, obj, index, value):
        """Helper to update angle equation."""
        obj.outRays[index]['eqnTheta'] = value
        obj.init_out_ray_fns()

    def _update_brightness(self, obj, index, value):
        """Helper to update brightness equation."""
        obj.outRays[index]['eqnP'] = value
        obj.init_out_ray_fns()

    def handle_out_rays(
        self,
        ray,
        ray_index: int,
        incident_point,
        normal,
        incident_pos: float,
        surface_merging_objs: List,
        body_merging_obj
    ) -> SimulationReturn:
        """
        Handle ray interaction with the custom surface.

        This method evaluates the custom equations to determine the outgoing rays.

        Args:
            ray: The incident ray (modified in-place).
            ray_index: Index of the ray in the simulation.
            incident_point: Point where ray hits the surface.
            normal: Normal vector at the incident point.
            incident_pos: Position parameter t on the surface.
            surface_merging_objs: Glass objects merged at this surface.
            body_merging_obj: GRIN glass object for body merging.

        Returns:
            SimulationReturn dict with newRays, isAbsorbed, and truncation.
        """
        if not self.fns:
            self.init_out_ray_fns()

        if len(self.fns) == 0:
            # No outgoing rays defined - absorb the incident ray
            return {'isAbsorbed': True}

        # Determine source and destination glasses
        source_glasses = []
        destination_glasses = []

        for obj in surface_merging_objs:
            incident_type = obj.get_incident_type(ray)
            if incident_type == 1:
                source_glasses.append(obj)
            elif incident_type == -1:
                destination_glasses.append(obj)
            else:
                # Undefined behavior
                return {
                    'isAbsorbed': True,
                    'isUndefinedBehavior': True
                }

        # Calculate refractive indices
        n0 = 1.0
        n1 = 1.0
        for obj in source_glasses:
            n0 *= obj.get_ref_index_at(incident_point, ray)
        for obj in destination_glasses:
            n1 *= obj.get_ref_index_at(incident_point, ray)

        # Calculate incident angle
        if hasattr(normal, 'x'):
            normal_angle = math.atan2(normal.y, normal.x)
        else:
            normal_angle = math.atan2(normal['y'], normal['x'])

        if hasattr(ray.p2, 'x'):
            ray_angle = math.atan2(ray.p2.y - ray.p1.y, ray.p2.x - ray.p1.x)
        else:
            ray_angle = math.atan2(ray.p2['y'] - ray.p1['y'], ray.p2['x'] - ray.p1['x'])

        incident_angle = normal_angle - (ray_angle + math.pi)

        # Normalize to -pi/2 to pi/2
        incident_angle = (incident_angle + 3 * math.pi) % (2 * math.pi) - math.pi

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Surface Hit Records (Step B, opt-in)
        # =====================================================================
        # Record hit geometry onto `ray` (the simulator's output_ray_geom) before
        # it is modified below. Uses the geometric normal passed in and the
        # incident ray direction; the recorded incident_angle is measured from the
        # normal, clamped into [0, pi/2] (CONTRIBUTING.md acos clamp rule).
        if getattr(ray, 'record_surface_hits', False):
            if hasattr(normal, 'x'):
                nrm_x, nrm_y = normal.x, normal.y
            else:
                nrm_x, nrm_y = normal['x'], normal['y']
            if hasattr(ray.p2, 'x'):
                di_x = ray.p2.x - ray.p1.x
                di_y = ray.p2.y - ray.p1.y
            else:
                di_x = ray.p2['x'] - ray.p1['x']
                di_y = ray.p2['y'] - ray.p1['y']
            if hasattr(incident_point, 'x'):
                hp_x, hp_y = incident_point.x, incident_point.y
            else:
                hp_x, hp_y = incident_point['x'], incident_point['y']
            n_len = math.hypot(nrm_x, nrm_y)
            di_len = math.hypot(di_x, di_y)
            if n_len > 0 and di_len > 0:
                unx = nrm_x / n_len
                uny = nrm_y / n_len
                cos_inc = abs((di_x * unx + di_y * uny) / di_len)
                ray.hit_surface_uuid = self._uuid
                ray.hit_point = {'x': hp_x, 'y': hp_y}
                ray.hit_normal = {'x': unx, 'y': uny}
                ray.incident_angle = math.acos(max(-1.0, min(1.0, cos_inc)))

        # Store original ray properties
        original_brightness_s = ray.brightness_s
        original_brightness_p = ray.brightness_p
        original_wavelength = ray.wavelength if hasattr(ray, 'wavelength') else GREEN_WAVELENGTH
        original_body_merging_obj = body_merging_obj
        original_gap = ray.gap if hasattr(ray, 'gap') else False

        new_rays = []
        is_absorbed = False
        truncation = 0

        # Create parameter dicts for s and p polarizations
        params = [
            {
                'theta0': incident_angle,
                'P0': original_brightness_s,
                'lambda': original_wavelength,
                't': incident_pos,
                'n0': n0,
                'n1': n1,
                'p': 0
            },
            {
                'theta0': incident_angle,
                'P0': original_brightness_p,
                'lambda': original_wavelength,
                't': incident_pos,
                'n0': n0,
                'n1': n1,
                'p': 1
            }
        ]

        # Evaluate each outgoing ray
        for i, fn in enumerate(self.fns):
            # Evaluate angles for both polarizations
            try:
                angles = [
                    fn['angleFn'](params[0]),
                    fn['angleFn'](params[1])
                ]
            except Exception as e:
                self.error = f"Error evaluating theta_{i+1}: {str(e)}"
                return {'isAbsorbed': True}

            # Store angles for use in subsequent equations
            params[0][f'theta{i+1}'] = angles[0]
            params[1][f'theta{i+1}'] = angles[1]

            # Evaluate brightnesses for both polarizations
            try:
                brightnesses = [
                    fn['brightnessFn'](params[0]),
                    fn['brightnessFn'](params[1])
                ]
            except Exception as e:
                self.error = f"Error evaluating P_{i+1}: {str(e)}"
                return {'isAbsorbed': True}

            # Validate results
            for p in [0, 1]:
                if not (brightnesses[p] > 0) or not math.isfinite(angles[p]):
                    brightnesses[p] = 0

            # Store brightnesses for use in subsequent equations
            params[0][f'P{i+1}'] = brightnesses[0]
            params[1][f'P{i+1}'] = brightnesses[1]

            # Determine if we need one or two rays
            if angles[0] == angles[1]:
                # Same angle for both polarizations - one ray
                ray_num = 1
            else:
                # Different angles - split into two rays
                ray_num = 2

            # Create outgoing rays
            for j in range(ray_num):
                # First ray reuses the incident ray object
                if i == 0 and j == 0:
                    ray1 = ray
                else:
                    # Create new ray
                    ray1 = type('Ray', (), {
                        'wavelength': original_wavelength,
                        'bodyMergingObj': original_body_merging_obj,
                        'gap': original_gap
                    })()

                # Normalize angle to -pi to pi
                angles[j] = ((angles[j] + math.pi) % (2 * math.pi) + 2 * math.pi) % (2 * math.pi) - math.pi

                # Handle glass transitions
                if -math.pi / 2 < angles[j] < math.pi / 2:
                    # Going to destination medium
                    for obj in source_glasses:
                        obj.on_ray_exit(ray1)
                    for obj in destination_glasses:
                        obj.on_ray_enter(ray1)
                    # PYTHON-SPECIFIC: Optical path length (P-RAY-LINEAGE) -- n1 here
                    # is already the absolute destination refractive index
                    # (product of get_ref_index_at over destination_glasses),
                    # unlike base_glass.py's refract() where n1 is a ratio.
                    ray1.medium_index = n1
                else:
                    # Staying in / returning to the source medium.
                    ray1.medium_index = getattr(ray, 'medium_index', n0)

                # Set ray parameters
                out_angle = (normal_angle + math.pi) - angles[j]

                if ray_num == 1:
                    ray1.brightness_s = brightnesses[0]
                    ray1.brightness_p = brightnesses[1]
                elif j == 0:
                    ray1.brightness_s = brightnesses[0]
                    ray1.brightness_p = 0
                else:
                    ray1.brightness_s = 0
                    ray1.brightness_p = brightnesses[1]

                # Set ray direction
                if hasattr(incident_point, 'x'):
                    inc_x, inc_y = incident_point.x, incident_point.y
                else:
                    inc_x, inc_y = incident_point['x'], incident_point['y']

                if isinstance(ray1.p1 if hasattr(ray1, 'p1') else None, dict):
                    ray1.p1 = {'x': inc_x, 'y': inc_y}
                    ray1.p2 = {
                        'x': inc_x + math.cos(out_angle),
                        'y': inc_y + math.sin(out_angle)
                    }
                else:
                    ray1.p1 = incident_point
                    ray1.p2 = geometry.point(
                        inc_x + math.cos(out_angle),
                        inc_y + math.sin(out_angle)
                    )

                # Check if ray is bright enough
                # =====================================================================
                # PYTHON-SPECIFIC FEATURE: Use scene's configurable brightness threshold
                # =====================================================================
                # In JavaScript, the threshold is hardcoded based on color_mode.
                # In Python, we use scene.get_min_brightness_threshold() which allows
                # explicit control via scene.min_brightness_exp property.
                # =====================================================================
                total_brightness = ray1.brightness_s + ray1.brightness_p
                brightness_threshold = self.scene.get_min_brightness_threshold()

                if total_brightness > brightness_threshold:
                    if ray1 is not ray:
                        new_rays.append(ray1)
                else:
                    truncation += total_brightness
                    if ray1 is ray:
                        is_absorbed = True

        # Handle multi-ray warning
        self.warning = None
        if len(new_rays) > 1:
            # Disable image detection for multiple rays
            for new_ray in new_rays:
                new_ray.gap = True

            if hasattr(self.scene, 'mode') and self.scene.mode in ['images', 'observer']:
                self.warning = "Image detection does not work when there are multiple outgoing rays"

        self.error = None
        return {
            'newRays': new_rays,
            'isAbsorbed': is_absorbed,
            'truncation': truncation
        }

    def init_out_ray_fns(self):
        """
        Parse the expressions of the outgoing rays and store them in the fns property.
        """
        def replace_variables(latex_expr: str) -> str:
            """Replace LaTeX variables with evaluatable forms."""
            result = latex_expr
            # Replace standard variables (without extra parentheses)
            result = result.replace("\\theta_0", "theta0").replace("\\theta_{0}", "theta0")
            result = result.replace("P_0", "P0").replace("P_{0}", "P0")
            result = result.replace("\\lambda", "lambda")
            result = result.replace("n_0", "n0").replace("n_{0}", "n0")
            result = result.replace("n_1", "n1").replace("n_{1}", "n1")

            # Replace indexed variables (theta_i, P_i)
            for i in range(len(self.outRays)):
                if i + 1 < 10:
                    result = result.replace(f"\\theta_{i+1}", f"theta{i+1}")
                    result = result.replace(f"P_{i+1}", f"P{i+1}")
                result = result.replace(f"\\theta_{{{i+1}}}", f"theta{i+1}")
                result = result.replace(f"P_{{{i+1}}}", f"P{i+1}")

            return result

        def build_fn(latex_expr: str):
            """Build an evaluatable function from LaTeX expression."""
            import sympy as sp
            eqn = replace_variables(latex_expr)

            # Create symbol definitions for all possible variables
            additional_context = {
                'theta0': sp.Symbol('theta0'),
                'P0': sp.Symbol('P0'),
                'lambda': sp.Symbol('lambda'),
                't': sp.Symbol('t'),
                'n0': sp.Symbol('n0'),
                'n1': sp.Symbol('n1'),
                'p': sp.Symbol('p')
            }

            # Add symbols for outgoing rays
            for i in range(len(self.outRays)):
                additional_context[f'theta{i+1}'] = sp.Symbol(f'theta{i+1}')
                additional_context[f'P{i+1}'] = sp.Symbol(f'P{i+1}')

            fn = evaluate_latex(eqn, additional_context)

            # Track which theta parameters this function depends on
            theta_deps = []
            for i in range(len(self.outRays)):
                theta_deps.append(f"theta{i+1}" in eqn)

            def wrapped_fn(params):
                # Propagate NaN in theta parameters
                for i in range(len(self.outRays)):
                    if f'theta{i+1}' in params and not math.isfinite(params[f'theta{i+1}']) and theta_deps[i]:
                        return float('nan')
                # Call the function with keyword arguments
                return fn(**params)

            return wrapped_fn

        self.error = None
        try:
            self.fns = []
            for out_ray in self.outRays:
                self.fns.append({
                    'angleFn': build_fn(out_ray['eqnTheta']),
                    'brightnessFn': build_fn(out_ray['eqnP'])
                })
        except Exception as e:
            self.fns = []
            self.error = str(e)


# Example usage
if __name__ == "__main__":
    # Example: Simple mirror (reflects at opposite angle)
    class CustomMirror(BaseCustomSurface, BaseSceneObj):
        type = 'custom_mirror'
        serializable_defaults = {
            'outRays': [{'eqnTheta': '-\\theta_0', 'eqnP': 'P_0'}],
            'twoSided': False
        }
        is_optical = True

        def __init__(self, scene, json_obj=None):
            super().__init__(scene, json_obj)

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.color_mode = 'default'

    scene = MockScene()
    mirror = CustomMirror(scene)

    print("Custom Surface (Mirror) Test:")
    print(f"  Number of outgoing rays: {len(mirror.outRays)}")
    print(f"  Ray 1 angle equation: {mirror.outRays[0]['eqnTheta']}")
    print(f"  Ray 1 brightness equation: {mirror.outRays[0]['eqnP']}")
    print(f"  Two-sided: {mirror.twoSided}")

    # Test equation evaluation
    mirror.init_out_ray_fns()
    if mirror.error:
        print(f"  Error: {mirror.error}")
    else:
        print(f"  Functions initialized: {len(mirror.fns)}")

        # Test with sample parameters
        test_params = {
            'theta0': 0.5,  # ~28.6 degrees
            'P0': 1.0,
            'lambda': 532,
            't': 0.5,
            'n0': 1.0,
            'n1': 1.5,
            'p': 0
        }

        angle_result = mirror.fns[0]['angleFn'](test_params)
        brightness_result = mirror.fns[0]['brightnessFn'](test_params)

        print(f"\nTest evaluation (incident angle = {test_params['theta0']:.3f} rad):")
        print(f"  Reflected angle: {angle_result:.3f} rad")
        print(f"  Reflected brightness: {brightness_result:.2f}")
        print("  -> Mirror correctly reflects at opposite angle with same brightness")

    print("\nBaseCustomSurface test completed successfully!")

    # test glossy
    class CustomGlossy(BaseCustomSurface, BaseSceneObj):
        type = 'custom_glossy'
        serializable_defaults = {
            'outRays': [
            {'eqnTheta': '-\\theta_0 - 0.2', 'eqnP': 'P_0 * 0.1'},
            {'eqnTheta': '-\\theta_0 - 0.1', 'eqnP': 'P_0 * 0.2'},
            {'eqnTheta': '-\\theta_0', 'eqnP': 'P_0 * 0.4'},
            {'eqnTheta': '-\\theta_0 + 0.1', 'eqnP': 'P_0 * 0.2'},
            {'eqnTheta': '-\\theta_0 + 0.2', 'eqnP': 'P_0 * 0.1'}],
            'twoSided': False
        }
        is_optical = True

        def __init__(self, scene, json_obj=None):
            super().__init__(scene, json_obj)
    
    print("Custom BRDF (Glossy) Test:")
    
    scene = MockScene()
    glossy = CustomGlossy(scene)
    glossy.init_out_ray_fns()
    
    print(f"Functions initialized: {len(glossy.fns)}")
    test_params = {
        'theta0': 0.5,
        'P0': 1.0,
        'lambda': 532,
        't': 0.5,
        'n0': 1.0,
        'n1': 1.5,
        'p': 0
    }
    print(f"\nTest evaluation (incident angle = {test_params['theta0']:.3f} rad):")
    total_brightness = 0
    for i, fn in enumerate(glossy.fns):
        angle = fn['angleFn'](test_params)
        brightness = fn['brightnessFn'](test_params)
        total_brightness += brightness
        print(f"Ray {i+1}: angle={angle:.3f}, brightness={brightness:.2f}")
    print(f"\nTotal brightness: {total_brightness:.2f} (should be 1.0 for energy conservation)")