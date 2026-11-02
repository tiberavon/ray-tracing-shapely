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
import sympy as sp
from typing import Dict, Any, Callable, Optional

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_glass import BaseGlass
    from ray_tracing_shapely.core import geometry
    from ray_tracing_shapely.core.equation import evaluate_latex
    from ray_tracing_shapely.core.constants import GREEN_WAVELENGTH
else:
    from .base_glass import BaseGlass
    from .. import geometry
    from ..equation import evaluate_latex
    from ..constants import GREEN_WAVELENGTH


class BaseGrinGlass(BaseGlass):
    """
    The base class for GRIN (Gradient-Index) glasses.

    GRIN glasses have a spatially varying refractive index n(x, y) instead of a uniform
    refractive index. Rays propagating through GRIN media follow curved paths according
    to the ray trajectory equation.

    Attributes:
        refIndexFn: The refractive index function n(x,y) in LaTeX format.
        absorptionFn: The absorption coefficient α(x,y) in LaTeX format.
        origin: The origin point for the (x,y) coordinate system used in equations.
        stepSize: The step size for numerical integration of ray trajectory equation.
        intersectTol: Tolerance for intersection calculations (epsilon).

        p: The refractive index function as a SymPy expression string.
        p_der_x: The x-derivative of p as a SymPy expression string.
        p_der_y: The y-derivative of p as a SymPy expression string.
        p_der_x_tex: The x-derivative in LaTeX format.
        p_der_y_tex: The y-derivative in LaTeX format.

        fn_p: Evaluatable function for n(x,y,λ).
        fn_p_der_x: Evaluatable function for ∂n/∂x.
        fn_p_der_y: Evaluatable function for ∂n/∂y.
        fn_alpha: Evaluatable function for α(x,y,λ).

    Notes:
        - Ray trajectories in GRIN media are computed using Euler's method
        - Supports body merging: overlapping GRIN glasses combine multiplicatively
        - Uses symbolic differentiation via SymPy for computing gradients
        - Based on: https://doi.org/10.1007/BFb0012092 (sections 11.1 and 11.2)

    Body Merging:
        When multiple GRIN glasses overlap, a temporary "bodyMergingObj" is attached
        to each ray. This object stores the combined refractive index function and
        its derivatives for the overlapping region. The functions are combined as:
        - Refractive index: multiplied (n_combined = n1 * n2 * ...)
        - Absorption: added (α_combined = α1 + α2 + ...)
    """

    merges_with_glass = True

    def __init__(self, scene, json_obj: Optional[Dict[str, Any]] = None):
        """
        Initialize the GRIN glass.

        Args:
            scene: The scene the object belongs to.
            json_obj: The JSON object to be deserialized, if any.
        """
        super().__init__(scene, json_obj)
        self.init_fns()

    def populate_obj_bar(self, obj_bar):
        """
        Populate the object bar with GRIN glass controls.

        Args:
            obj_bar: The object bar to populate.
        """
        if not hasattr(self, 'fn_p') or self.fn_p is None:
            self.init_fns()

        # Refractive index function
        obj_bar.create_equation(
            'n(x,y) = ',
            self.refIndexFn,
            lambda obj, value: self._update_ref_index_fn(obj, value),
            "GRIN refractive index function. Use 'lambda' for wavelength."
        )

        # Absorption function
        obj_bar.create_equation(
            'α(x,y) = ',
            self.absorptionFn,
            lambda obj, value: self._update_absorption_fn(obj, value),
            "Absorption coefficient function (Beta version)"
        )

        # Origin (not for ParamGrinGlass)
        if self.type != 'ParamGrinGlass':
            obj_bar.create_tuple(
                'Coordinate Origin',
                f'({self.origin.x},{self.origin.y})',
                lambda obj, value: self._update_origin(obj, value)
            )

        # Advanced: Step size
        if obj_bar.show_advanced(not self.are_properties_default(['stepSize'])):
            obj_bar.create_number(
                'Step Size',
                0.1 * self.scene.length_scale,
                1 * self.scene.length_scale,
                0.1 * self.scene.length_scale,
                self.stepSize,
                lambda obj, value: setattr(obj, 'stepSize', float(value)),
                'Step size for numerical integration of ray trajectory',
                True
            )

        # Advanced: Intersection tolerance
        if obj_bar.show_advanced(not self.are_properties_default(['intersectTol'])):
            obj_bar.create_number(
                'Intersection Tolerance',
                1e-3,
                1e-2,
                1e-3,
                self.intersectTol,
                lambda obj, value: setattr(obj, 'intersectTol', float(value)),
                'Epsilon for intersection calculations',
                True
            )

        # Advanced: Symbolic body merging
        if obj_bar.show_advanced(self.scene.symbolic_body_merging):
            obj_bar.create_boolean(
                'Symbolic Body Merging',
                self.scene.symbolic_body_merging,
                lambda obj, value: setattr(obj.scene, 'symbolic_body_merging', value),
                'Use symbolic computation for body merging (slower but more accurate)'
            )

    def _update_ref_index_fn(self, obj, value):
        """Helper to update refractive index function."""
        obj.refIndexFn = value
        obj.init_fns()

    def _update_absorption_fn(self, obj, value):
        """Helper to update absorption function."""
        obj.absorptionFn = value
        obj.init_fns()

    def _update_origin(self, obj, value):
        """Helper to update origin."""
        comma_pos = value.find(',')
        if comma_pos != -1:
            n_origin_x = float(value[1:comma_pos])
            n_origin_y = float(value[comma_pos + 1:-1])
            obj.origin = geometry.point(n_origin_x, n_origin_y)
            obj.init_fns()

    def get_z_index(self):
        """Get the z-index for rendering order."""
        return 0

    def fill_glass(self, canvas_renderer, is_above_light, is_hovered):
        """
        Fill the glass with the GRIN glass color.

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether rendering above the light layer.
            is_hovered: Whether the object is hovered.
        """
        ctx = canvas_renderer.ctx

        if is_above_light:
            # Draw the highlight only
            ctx.globalAlpha = 0.1
            ctx.fillStyle = self.scene.highlight_color_css if is_hovered else 'transparent'
            ctx.fill('evenodd')
            ctx.globalAlpha = 1
            return

        # Draw GRIN glass with specific color
        ctx.fillStyle = canvas_renderer.rgba_to_css_color(self.scene.theme.grin_glass.color)
        ctx.fill('evenodd')
        ctx.globalAlpha = 1

    def get_ref_index_at(self, point, ray):
        """
        Get the refractive index at a point for a ray.

        Args:
            point: The point to get the refractive index.
            ray: The ray (for wavelength information).

        Returns:
            The refractive index at the point.
        """
        if hasattr(point, 'x'):
            x, y = point.x, point.y
        else:
            x, y = point['x'], point['y']

        wavelength = ray.wavelength if hasattr(ray, 'wavelength') else GREEN_WAVELENGTH
        return self.fn_p(x=x, y=y, z=wavelength)

    def on_ray_enter(self, ray):
        """
        Handle the event when a ray enters the GRIN glass.

        Updates the ray's bodyMergingObj to include this glass's refractive index.

        Args:
            ray: The ray that enters the glass.
        """
        if not hasattr(ray, 'bodyMergingObj') or ray.bodyMergingObj is None:
            ray.bodyMergingObj = self.init_ref_index(ray)
        ray.bodyMergingObj = self.mult_ref_index(ray.bodyMergingObj)

    def on_ray_exit(self, ray):
        """
        Handle the event when a ray exits the GRIN glass.

        Updates the ray's bodyMergingObj to remove this glass's refractive index.

        Args:
            ray: The ray that exits the glass.
        """
        if not hasattr(ray, 'bodyMergingObj') or ray.bodyMergingObj is None:
            ray.bodyMergingObj = self.init_ref_index(ray)
        ray.bodyMergingObj = self.dev_ref_index(ray.bodyMergingObj)

    # Utility Methods

    def init_fns(self):
        """
        Compute partial derivatives and parse the refractive index function.

        This method:
        1. Parses the LaTeX refractive index function
        2. Computes symbolic derivatives ∂n/∂x and ∂n/∂y using SymPy
        3. Creates evaluatable functions for n, ∂n/∂x, ∂n/∂y, and α
        """
        self.error = None
        try:
            # Parse the refractive index function
            # Replace \lambda with z (wavelength variable)
            ref_index_str = self.refIndexFn.replace("\\lambda", "z")

            # Parse LaTeX to SymPy expression
            x_sym, y_sym, z_sym = sp.symbols('x y z')
            p_expr = sp.sympify(ref_index_str, locals={'x': x_sym, 'y': y_sym, 'z': z_sym})

            self.p = str(p_expr)

            # Compute derivatives
            p_der_x_expr = sp.diff(p_expr, x_sym)
            p_der_y_expr = sp.diff(p_expr, y_sym)

            self.p_der_x = str(p_der_x_expr)
            self.p_der_y = str(p_der_y_expr)

            # Convert to LaTeX (and clean up {+ patterns that evaluateLatex can't handle)
            self.p_der_x_tex = sp.latex(p_der_x_expr).replace("{+", "{")
            self.p_der_y_tex = sp.latex(p_der_y_expr).replace("{+", "{")

            # Create evaluatable functions with origin shift
            self.fn_p = evaluate_latex(self.shift_origin(ref_index_str))
            self.fn_p_der_x = evaluate_latex(self.shift_origin(self.p_der_x_tex))
            self.fn_p_der_y = evaluate_latex(self.shift_origin(self.p_der_y_tex))

            # Parse absorption function
            absorption_str = self.absorptionFn.replace("\\lambda", "z")
            self.fn_alpha = evaluate_latex(self.shift_origin(absorption_str))

        except Exception as e:
            # Clear functions on error
            self.fn_p = None
            self.fn_p_der_x = None
            self.fn_p_der_y = None
            self.fn_alpha = None
            self.error = str(e)

    def shift_origin(self, equation: str) -> str:
        """
        Shift the x and y variables in the equation from relative to origin to absolute.

        Args:
            equation: The equation string (in LaTeX or standard notation).

        Returns:
            The equation with shifted coordinates.
        """
        # Get origin coordinates (handle both dict and point)
        if hasattr(self.origin, 'x'):
            origin_x, origin_y = self.origin.x, self.origin.y
        else:
            origin_x, origin_y = self.origin['x'], self.origin['y']

        # Replace x and y with (x - origin.x) and (y - origin.y)
        result = equation.replace("x", f"(x-{origin_x})")
        result = result.replace("y", f"(y-{origin_y})")
        return result

    def mult_ref_index(self, body_merging_obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine this GRIN glass with an existing body merging object.

        The refractive indices are multiplied: n_combined = n_existing * n_this
        The absorptions are added: α_combined = α_existing + α_this

        Args:
            body_merging_obj: The existing body merging object.

        Returns:
            A new body merging object for the overlapping region.
        """
        if hasattr(self.scene, 'symbolic_body_merging') and self.scene.symbolic_body_merging:
            # Symbolic mode: use SymPy for exact symbolic computation
            x_sym, y_sym, z_sym = sp.symbols('x y z')

            # Multiply refractive indices symbolically
            p_existing = sp.sympify(body_merging_obj['p'], locals={'x': x_sym, 'y': y_sym, 'z': z_sym})
            p_this = sp.sympify(self.shift_origin(self.p), locals={'x': x_sym, 'y': y_sym, 'z': z_sym})
            mul_p_expr = sp.simplify(p_existing * p_this)
            mul_p = str(mul_p_expr)

            # Create evaluatable functions
            mul_fn_p = evaluate_latex(sp.latex(mul_p_expr))
            mul_fn_p_der_x = evaluate_latex(sp.latex(sp.diff(mul_p_expr, x_sym)))
            mul_fn_p_der_y = evaluate_latex(sp.latex(sp.diff(mul_p_expr, y_sym)))

            # Add absorption
            shifted_absorption = self.shift_origin(self.absorptionFn.replace('\\lambda', 'z'))
            sum_alpha = f"\\left({body_merging_obj['alpha']}\\right) + \\left({shifted_absorption}\\right)"
            sum_fn_alpha = evaluate_latex(sum_alpha)

            return {
                'p': mul_p,
                'fn_p': mul_fn_p,
                'fn_p_der_x': mul_fn_p_der_x,
                'fn_p_der_y': mul_fn_p_der_y,
                'alpha': sum_alpha,
                'fn_alpha': sum_fn_alpha
            }
        else:
            # Numerical mode: compose functions directly
            fn_p = self.fn_p
            fn_p_der_x = self.fn_p_der_x
            fn_p_der_y = self.fn_p_der_y
            new_fn_p = body_merging_obj['fn_p']
            new_fn_p_der_x = body_merging_obj['fn_p_der_x']
            new_fn_p_der_y = body_merging_obj['fn_p_der_y']

            # Product: (f * g)
            def mul_fn_p(**kwargs):
                return fn_p(**kwargs) * new_fn_p(**kwargs)

            # Product rule: (f * g)' = f' * g + f * g'
            def mul_fn_p_der_x(**kwargs):
                return fn_p(**kwargs) * new_fn_p_der_x(**kwargs) + fn_p_der_x(**kwargs) * new_fn_p(**kwargs)

            def mul_fn_p_der_y(**kwargs):
                return fn_p(**kwargs) * new_fn_p_der_y(**kwargs) + fn_p_der_y(**kwargs) * new_fn_p(**kwargs)

            # Sum of absorption
            fn_alpha = self.fn_alpha
            new_fn_alpha = body_merging_obj['fn_alpha']

            def sum_fn_alpha(**kwargs):
                return fn_alpha(**kwargs) + new_fn_alpha(**kwargs)

            return {
                'fn_p': mul_fn_p,
                'fn_p_der_x': mul_fn_p_der_x,
                'fn_p_der_y': mul_fn_p_der_y,
                'fn_alpha': sum_fn_alpha
            }

    def dev_ref_index(self, body_merging_obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove this GRIN glass from a body merging object.

        The refractive indices are divided: n_result = n_existing / n_this
        The absorptions are subtracted: α_result = α_existing - α_this

        Args:
            body_merging_obj: The existing body merging object.

        Returns:
            A new body merging object with this glass removed.
        """
        if hasattr(self.scene, 'symbolic_body_merging') and self.scene.symbolic_body_merging:
            # Symbolic mode: use SymPy for exact symbolic computation
            x_sym, y_sym, z_sym = sp.symbols('x y z')

            # Divide refractive indices symbolically
            p_existing = sp.sympify(body_merging_obj['p'], locals={'x': x_sym, 'y': y_sym, 'z': z_sym})
            p_this = sp.sympify(self.shift_origin(self.p), locals={'x': x_sym, 'y': y_sym, 'z': z_sym})
            dev_p_expr = sp.simplify(p_existing / p_this)
            dev_p = str(dev_p_expr)

            # Create evaluatable functions
            dev_fn_p = evaluate_latex(sp.latex(dev_p_expr))
            dev_fn_p_der_x = evaluate_latex(sp.latex(sp.diff(dev_p_expr, x_sym)))
            dev_fn_p_der_y = evaluate_latex(sp.latex(sp.diff(dev_p_expr, y_sym)))

            # Subtract absorption
            shifted_absorption = self.shift_origin(self.absorptionFn.replace('\\lambda', 'z'))
            diff_alpha = f"\\left({body_merging_obj['alpha']}\\right) - \\left({shifted_absorption}\\right)"
            diff_fn_alpha = evaluate_latex(diff_alpha)

            return {
                'p': dev_p,
                'fn_p': dev_fn_p,
                'fn_p_der_x': dev_fn_p_der_x,
                'fn_p_der_y': dev_fn_p_der_y,
                'alpha': diff_alpha,
                'fn_alpha': diff_fn_alpha
            }
        else:
            # Numerical mode: compose functions directly
            fn_p = self.fn_p
            fn_p_der_x = self.fn_p_der_x
            fn_p_der_y = self.fn_p_der_y
            new_fn_p = body_merging_obj['fn_p']
            new_fn_p_der_x = body_merging_obj['fn_p_der_x']
            new_fn_p_der_y = body_merging_obj['fn_p_der_y']

            # Quotient: (g / f)
            def dev_fn_p(**kwargs):
                return new_fn_p(**kwargs) / fn_p(**kwargs)

            # Quotient rule: (g / f)' = (g' * f - g * f') / f^2
            def dev_fn_p_der_x(**kwargs):
                f_val = fn_p(**kwargs)
                return new_fn_p_der_x(**kwargs) / f_val - new_fn_p(**kwargs) * fn_p_der_x(**kwargs) / (f_val ** 2)

            def dev_fn_p_der_y(**kwargs):
                f_val = fn_p(**kwargs)
                return new_fn_p_der_y(**kwargs) / f_val - new_fn_p(**kwargs) * fn_p_der_y(**kwargs) / (f_val ** 2)

            # Difference of absorption
            fn_alpha = self.fn_alpha
            new_fn_alpha = body_merging_obj['fn_alpha']

            def diff_fn_alpha(**kwargs):
                return new_fn_alpha(**kwargs) - fn_alpha(**kwargs)

            return {
                'fn_p': dev_fn_p,
                'fn_p_der_x': dev_fn_p_der_x,
                'fn_p_der_y': dev_fn_p_der_y,
                'fn_alpha': diff_fn_alpha
            }

    def init_ref_index(self, ray) -> Dict[str, Any]:
        """
        Initialize a body merging object for a ray at position ray.p1.

        This finds all GRIN glasses that contain the point ray.p1 and combines them.

        Args:
            ray: The ray to initialize the body merging object for.

        Returns:
            A body merging object representing the combined refractive index at ray.p1.
        """
        obj_tmp = None

        # Find all GRIN glasses that contain this point
        for obj in self.scene.optical_objs:
            if isinstance(obj, BaseGrinGlass):
                if obj.is_on_boundary(ray.p1) or obj.is_inside_glass(ray.p1):
                    if obj_tmp is None:
                        # First GRIN glass found
                        obj_tmp = {
                            'p': obj.shift_origin(obj.p),
                            'fn_p': obj.fn_p,
                            'fn_p_der_x': obj.fn_p_der_x,
                            'fn_p_der_y': obj.fn_p_der_y,
                            'alpha': obj.shift_origin(obj.absorptionFn.replace("\\lambda", "z")),
                            'fn_alpha': obj.fn_alpha
                        }
                    else:
                        # Merge with existing GRIN glasses
                        obj_tmp = obj.mult_ref_index(obj_tmp)

        if obj_tmp is None:
            # No GRIN glass found - return identity (n=1, α=0)
            obj_tmp = {
                'p': '1',
                'fn_p': lambda **kwargs: 1.0,
                'fn_p_der_x': lambda **kwargs: 0.0,
                'fn_p_der_y': lambda **kwargs: 0.0,
                'alpha': '0',
                'fn_alpha': lambda **kwargs: 0.0
            }

        return obj_tmp

    def step(self, p1, p2, ray):
        """
        Compute the next point in the ray trajectory using Euler's method.

        This implements equation 11.1 from https://doi.org/10.1007/BFb0012092
        The ray trajectory equation in GRIN media is:
            d²r/ds² = ∇n / n
        where s is arc length and n is the refractive index.

        Args:
            p1: The previous point on the ray path.
            p2: The current point on the ray path.
            ray: The ray object (contains bodyMergingObj with refractive index info).

        Returns:
            The next point on the ray path.
        """
        # Calculate arc length parameterization derivatives
        length = geometry.distance(p1, p2)

        if hasattr(p2, 'x'):
            x, y = p2.x, p2.y
            p1_x, p1_y = p1.x, p1.y
        else:
            x, y = p2['x'], p2['y']
            p1_x, p1_y = p1['x'], p1['y']

        x_der_s_prev = (x - p1_x) / length
        y_der_s_prev = math.copysign(1, y - p1_y) * math.sqrt(1 - x_der_s_prev ** 2)

        wavelength = ray.wavelength if hasattr(ray, 'wavelength') else GREEN_WAVELENGTH

        # Get refractive index and its derivatives
        n = ray.bodyMergingObj['fn_p'](x=x, y=y, z=wavelength)
        n_der_x = ray.bodyMergingObj['fn_p_der_x'](x=x, y=y, z=wavelength)
        n_der_y = ray.bodyMergingObj['fn_p_der_y'](x=x, y=y, z=wavelength)

        # Euler's method for ray trajectory equation
        x_der_s = x_der_s_prev + self.stepSize * (n_der_x * (1 - x_der_s_prev ** 2) - n_der_y * x_der_s_prev * y_der_s_prev) / n
        y_der_s = y_der_s_prev + self.stepSize * (n_der_y * (1 - y_der_s_prev ** 2) - n_der_x * x_der_s_prev * y_der_s_prev) / n

        # Next position
        x_new = x + self.stepSize * x_der_s
        y_new = y + self.stepSize * y_der_s

        # Apply absorption
        alpha = ray.bodyMergingObj['fn_alpha'](x=x, y=y, z=wavelength)
        absorption = math.exp(-alpha * self.stepSize)

        ray.brightness_s *= absorption
        ray.brightness_p *= absorption

        return geometry.point(x_new, y_new)

    # Abstract methods (to be implemented in subclasses)

    def is_outside_glass(self, point):
        """
        Check if a point is outside the glass.

        Args:
            point: The point to check.

        Returns:
            True if the point is outside the glass, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement is_outside_glass()")

    def is_inside_glass(self, point):
        """
        Check if a point is inside the glass.

        Args:
            point: The point to check.

        Returns:
            True if the point is inside the glass, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement is_inside_glass()")

    def is_on_boundary(self, point):
        """
        Check if a point is on the boundary of the glass.

        Args:
            point: The point to check.

        Returns:
            True if the point is on the boundary, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement is_on_boundary()")


# Example usage
if __name__ == "__main__":
    # Example GRIN glass with quadratic refractive index profile
    class CircleGrinGlass(BaseGrinGlass):
        type = 'circle_grin_glass'
        serializable_defaults = {
            'refIndexFn': '1 + 0.1 * (x^2 + y^2)',  # Quadratic profile
            'absorptionFn': '0',  # No absorption
            'origin': {'x': 0, 'y': 0},
            'stepSize': 0.1,
            'intersectTol': 0.001,
            'radius': 5.0
        }
        is_optical = True

        def __init__(self, scene, json_obj=None):
            # Set defaults before calling super().__init__()
            if not hasattr(self, 'radius'):
                self.radius = 5.0
            super().__init__(scene, json_obj)

        def is_outside_glass(self, point):
            # Get point coordinates
            if hasattr(point, 'x'):
                px, py = point.x, point.y
            else:
                px, py = point['x'], point['y']

            # Get origin coordinates
            if hasattr(self.origin, 'x'):
                ox, oy = self.origin.x, self.origin.y
            else:
                ox, oy = self.origin['x'], self.origin['y']

            dx, dy = px - ox, py - oy
            return dx**2 + dy**2 > self.radius**2

        def is_inside_glass(self, point):
            # Get point coordinates
            if hasattr(point, 'x'):
                px, py = point.x, point.y
            else:
                px, py = point['x'], point['y']

            # Get origin coordinates
            if hasattr(self.origin, 'x'):
                ox, oy = self.origin.x, self.origin.y
            else:
                ox, oy = self.origin['x'], self.origin['y']

            dx, dy = px - ox, py - oy
            return dx**2 + dy**2 < self.radius**2

        def is_on_boundary(self, point):
            # Get point coordinates
            if hasattr(point, 'x'):
                px, py = point.x, point.y
            else:
                px, py = point['x'], point['y']

            # Get origin coordinates
            if hasattr(self.origin, 'x'):
                ox, oy = self.origin.x, self.origin.y
            else:
                ox, oy = self.origin['x'], self.origin['y']

            dx, dy = px - ox, py - oy
            dist_sq = dx**2 + dy**2
            return abs(dist_sq - self.radius**2) < self.intersectTol

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.color_mode = 'default'
            self.symbolic_body_merging = False
            self.optical_objs = []
            self.length_scale = 1.0

    # Mock ray
    class MockRay:
        def __init__(self):
            self.wavelength = GREEN_WAVELENGTH
            self.brightness_s = 1.0
            self.brightness_p = 1.0
            self.p1 = geometry.point(0, 0)
            self.p2 = geometry.point(1, 0)
            self.bodyMergingObj = None

    scene = MockScene()
    grin = CircleGrinGlass(scene)
    scene.optical_objs.append(grin)

    print("GRIN Glass Test:")
    print(f"  Refractive index function: {grin.refIndexFn}")
    print(f"  Absorption function: {grin.absorptionFn}")

    # Handle origin as either dict or point
    if hasattr(grin.origin, 'x'):
        print(f"  Origin: ({grin.origin.x}, {grin.origin.y})")
    else:
        print(f"  Origin: ({grin.origin['x']}, {grin.origin['y']})")

    print(f"  Step size: {grin.stepSize}")
    print(f"  Radius: {grin.radius}")

    if grin.error:
        print(f"  Error during initialization: {grin.error}")
    else:
        print(f"  Functions initialized successfully")

        # Test refractive index at various points
        print("\nRefractive index at various points:")
        ray = MockRay()
        for r in [0, 1, 2, 3]:
            point = geometry.point(r, 0)
            n = grin.get_ref_index_at(point, ray)
            print(f"  n({r}, 0) = {n:.4f}")

        # Test derivatives
        print("\nDerivatives at (1, 0):")
        x, y = 1.0, 0.0
        n_der_x = grin.fn_p_der_x(x=x, y=y, z=GREEN_WAVELENGTH)
        n_der_y = grin.fn_p_der_y(x=x, y=y, z=GREEN_WAVELENGTH)
        print(f"  dn/dx = {n_der_x:.4f}")
        print(f"  dn/dy = {n_der_y:.4f}")

        # Test ray stepping
        print("\nRay trajectory test:")
        ray = MockRay()
        ray.bodyMergingObj = grin.init_ref_index(ray)

        p1 = geometry.point(0, 0)
        p2 = geometry.point(0.1, 0)

        print(f"  Starting at ({p1.x:.2f}, {p1.y:.2f})")
        for i in range(5):
            p_next = grin.step(p1, p2, ray)
            print(f"  Step {i+1}: ({p2.x:.4f}, {p2.y:.4f})")
            p1, p2 = p2, p_next

        # Test ray stepping with angled ray 
        print("\nRay trajectory test (angled ray):")
        ray = MockRay()
        ray.bodyMergingObj = grin.init_ref_index(ray)

        p1 = geometry.point(0, 0)
        p2 = geometry.point(0.1, 0.1)  # Diagonal direction

        print(f"  Starting at ({p1.x:.2f}, {p1.y:.2f}), direction: ({p2.x:.2f}, {p2.y:.2f})")
        for i in range(10):  # More steps to see curvature
            p_next = grin.step(p1, p2, ray)
            print(f"  Step {i+1}: ({p2.x:.4f}, {p2.y:.4f})")
            p1, p2 = p2, p_next

        # Test ray stepping with angled and offset ray to see bending
        # we expect The x-coordinate is increasing (from 0.1000 to 0.1087), 
        # so the ray is bending to the right (positive x direction).
        print("\nRay trajectory test (angled ray):")
        ray = MockRay()
        ray.bodyMergingObj = grin.init_ref_index(ray)

        p1 = geometry.point(0.1, 0) # offset x 
        p2 = geometry.point(0.1, 0.1)  # y parallel direction

        print(f"  Starting at ({p1.x:.2f}, {p1.y:.2f}), direction: ({p2.x:.2f}, {p2.y:.2f})")
        for i in range(10):  # More steps to see curvature
            p_next = grin.step(p1, p2, ray)
            print(f"  Step {i+1}: ({p2.x:.4f}, {p2.y:.4f})")
            p1, p2 = p2, p_next       

    print("\nBaseGrinGlass test completed successfully!")
