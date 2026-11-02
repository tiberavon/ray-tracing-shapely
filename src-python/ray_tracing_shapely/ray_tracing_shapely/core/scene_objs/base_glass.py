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
from typing import List, Optional, Dict, Any, Union, Tuple, TYPE_CHECKING

# Handle both relative imports (when used as a module) and absolute imports (when run as script)
if __name__ == "__main__":
    from ray_tracing_shapely.core.scene_objs.base_scene_obj import BaseSceneObj, SimulationReturn
    from ray_tracing_shapely.core import geometry
    from ray_tracing_shapely.core.constants import MIN_RAY_SEGMENT_LENGTH
else:
    from .base_scene_obj import BaseSceneObj, SimulationReturn
    from .. import geometry
    from ..constants import MIN_RAY_SEGMENT_LENGTH

if TYPE_CHECKING:
    from ..ray import Ray
    from ..geometry import Point


class BaseGlass(BaseSceneObj):
    """
    The base class for glasses.

    Attributes:
        refIndex: The refractive index of the glass, or the Cauchy coefficient A
                  of the glass if "Simulate Colors" is on.
        cauchyB: The Cauchy coefficient B of the glass if "Simulate Colors" is on,
                 in micrometer squared.

    Notes:
        - The `merges_with_glass` property is set to True for all glass objects
        - Implements Snell's law for refraction and Fresnel equations for reflection
        - Supports surface merging with other glasses for complex optical systems
        - Handles both normal and negative refractive indices
    Features:
        - Refractive index handling (including Cauchy's equation for dispersion)
        - Snell's law implementation for refraction
        - Fresnel equations for reflection coefficients
        - Surface merging for complex optical systems
        - Support for negative refractive indices
        - Adaptive ray sampling for dim rays
    key features:
        - Dispersion modeling: Uses Cauchy's equation n(λ) = A + B/λ² to model wavelength-dependent refractive index
        - Fresnel reflection: Correctly calculates s- and p-polarized reflection coefficients
        - Total internal reflection: Handles cases where refraction is impossible
        - Adaptive sampling: For very dim reflected rays, uses statistical sampling to reduce ray count while preserving energy
    """

    merges_with_glass = True

    # =========================================================================
    # PYTHON-SPECIFIC FEATURE: Edge Labeling
    # =========================================================================
    # Allows labeling individual edges of glass objects with short and long
    # labels for identification and tracking. Supports both manual labeling
    # and automatic cardinal direction labeling based on edge orientation.
    # =========================================================================

    def _get_edge_count(self) -> int:
        """
        Get the number of edges in this glass object.

        Returns:
            Number of edges (based on path length). Subclasses should override
            this if edges are determined differently.
        """
        if hasattr(self, 'path') and self.path:
            return len(self.path)
        return 0

    def _initialize_edge_labels(self) -> None:
        """
        Initialize edge_labels with default numeric labels.

        Creates labels {0: ("0", "0"), 1: ("1", "1"), ...} for all edges.
        Called automatically when edge_labels is first accessed.
        """
        edge_count = self._get_edge_count()
        self._edge_labels: Dict[int, Tuple[str, str]] = {
            i: (str(i), str(i)) for i in range(edge_count)
        }

    @property
    def edge_labels(self) -> Dict[int, Tuple[str, str]]:
        """
        Get the edge labels dictionary.

        Returns:
            Dict mapping edge index to (short_label, long_name) tuple.
            Auto-initialized with numeric labels on first access.
        """
        if not hasattr(self, '_edge_labels') or self._edge_labels is None:
            self._initialize_edge_labels()
        return self._edge_labels

    @edge_labels.setter
    def edge_labels(self, value: Dict[int, Tuple[str, str]]) -> None:
        """Set the edge labels dictionary."""
        self._edge_labels = value

    def label_edge(self, edge_index: int, short_label: str, long_name: str) -> None:
        """
        Set labels for a specific edge.

        Args:
            edge_index: The index of the edge to label.
            short_label: Short label for the edge (e.g., "N", "E").
            long_name: Long descriptive name (e.g., "North Edge").

        Raises:
            IndexError: If edge_index is out of range.
        """
        edge_count = self._get_edge_count()
        if edge_index < 0 or edge_index >= edge_count:
            raise IndexError(f"Edge index {edge_index} out of range [0, {edge_count})")
        self.edge_labels[edge_index] = (short_label, long_name)

    def get_edge_label(self, edge_index: int) -> Optional[Tuple[str, str]]:
        """
        Get both labels for an edge.

        Args:
            edge_index: The index of the edge.

        Returns:
            Tuple of (short_label, long_name), or None if edge doesn't exist.
        """
        return self.edge_labels.get(edge_index)

    def get_edge_short_label(self, edge_index: int) -> Optional[str]:
        """
        Get the short label for an edge.

        Args:
            edge_index: The index of the edge.

        Returns:
            The short label, or None if edge doesn't exist.
        """
        label = self.edge_labels.get(edge_index)
        return label[0] if label else None

    def get_edge_long_name(self, edge_index: int) -> Optional[str]:
        """
        Get the long name for an edge.

        Args:
            edge_index: The index of the edge.

        Returns:
            The long name, or None if edge doesn't exist.
        """
        label = self.edge_labels.get(edge_index)
        return label[1] if label else None

    def find_edge_by_short_label(self, short_label: str) -> Optional[int]:
        """
        Find an edge index by its short label.

        Args:
            short_label: The short label to search for.

        Returns:
            The edge index, or None if not found.
        """
        for idx, (short, _) in self.edge_labels.items():
            if short == short_label:
                return idx
        return None

    def find_edge_by_long_name(self, long_name: str) -> Optional[int]:
        """
        Find an edge index by its long name.

        Args:
            long_name: The long name to search for.

        Returns:
            The edge index, or None if not found.
        """
        for idx, (_, long) in self.edge_labels.items():
            if long == long_name:
                return idx
        return None

    def _get_centroid(self) -> Tuple[float, float]:
        """
        Calculate the centroid of the glass object.

        Returns:
            Tuple of (x, y) coordinates of the centroid.
        """
        if not hasattr(self, 'path') or not self.path:
            return (0.0, 0.0)

        sum_x = sum(p['x'] for p in self.path)
        sum_y = sum(p['y'] for p in self.path)
        n = len(self.path)
        return (sum_x / n, sum_y / n)

    def _get_edge_midpoint(self, edge_index: int) -> Tuple[float, float]:
        """
        Calculate the midpoint of an edge.

        Args:
            edge_index: The index of the edge.

        Returns:
            Tuple of (x, y) coordinates of the midpoint.
        """
        if not hasattr(self, 'path') or not self.path:
            return (0.0, 0.0)

        p1 = self.path[edge_index]
        p2 = self.path[(edge_index + 1) % len(self.path)]
        return ((p1['x'] + p2['x']) / 2, (p1['y'] + p2['y']) / 2)

    def auto_label_cardinal(self) -> None:
        """
        Automatically label edges with cardinal directions based on their
        position relative to the centroid.

        The algorithm:
        1. Calculate the centroid of the glass object
        2. Determine quadrant count based on edge count:
           - ≤4 edges: 4 quadrants (N, S, E, W)
           - 5-8 edges: 8 quadrants (N, NE, E, SE, S, SW, W, NW)
           - 9-12 edges: 12 quadrants (adds NNE, ENE, ESE, SSE, SSW, WSW, WNW, NNW)
           - 13+ edges: 16 quadrants
        3. For each edge, calculate angle from centroid to edge midpoint
        4. Assign to nearest cardinal direction

        Coordinate system:
        - North (N): positive y (top)
        - South (S): negative y (bottom)
        - East (E): positive x (right)
        - West (W): negative x (left)
        """
        edge_count = self._get_edge_count()
        if edge_count == 0:
            return

        # Define direction systems based on edge count
        directions_4 = [
            ("E", "East Edge"),
            ("N", "North Edge"),
            ("W", "West Edge"),
            ("S", "South Edge"),
        ]

        directions_8 = [
            ("E", "East Edge"),
            ("NE", "North East Edge"),
            ("N", "North Edge"),
            ("NW", "North West Edge"),
            ("W", "West Edge"),
            ("SW", "South West Edge"),
            ("S", "South Edge"),
            ("SE", "South East Edge"),
        ]

        directions_12 = [
            ("E", "East Edge"),
            ("ENE", "East North East Edge"),
            ("NNE", "North North East Edge"),
            ("N", "North Edge"),
            ("NNW", "North North West Edge"),
            ("WNW", "West North West Edge"),
            ("W", "West Edge"),
            ("WSW", "West South West Edge"),
            ("SSW", "South South West Edge"),
            ("S", "South Edge"),
            ("SSE", "South South East Edge"),
            ("ESE", "East South East Edge"),
        ]

        directions_16 = [
            ("E", "East Edge"),
            ("ENE", "East North East Edge"),
            ("NE", "North East Edge"),
            ("NNE", "North North East Edge"),
            ("N", "North Edge"),
            ("NNW", "North North West Edge"),
            ("NW", "North West Edge"),
            ("WNW", "West North West Edge"),
            ("W", "West Edge"),
            ("WSW", "West South West Edge"),
            ("SW", "South West Edge"),
            ("SSW", "South South West Edge"),
            ("S", "South Edge"),
            ("SSE", "South South East Edge"),
            ("SE", "South East Edge"),
            ("ESE", "East South East Edge"),
        ]

        # Select direction system based on edge count
        if edge_count <= 4:
            directions = directions_4
        elif edge_count <= 8:
            directions = directions_8
        elif edge_count <= 12:
            directions = directions_12
        else:
            directions = directions_16

        num_directions = len(directions)
        angle_per_direction = 2 * math.pi / num_directions

        centroid = self._get_centroid()

        # Label each edge
        for i in range(edge_count):
            midpoint = self._get_edge_midpoint(i)

            # Calculate angle from centroid to midpoint
            # atan2 returns angle in range [-π, π], with 0 pointing East
            dx = midpoint[0] - centroid[0]
            dy = midpoint[1] - centroid[1]
            angle = math.atan2(dy, dx)

            # Convert to [0, 2π) range
            if angle < 0:
                angle += 2 * math.pi

            # Find nearest direction
            # Add half the angle per direction for proper rounding to nearest
            direction_index = int((angle + angle_per_direction / 2) / angle_per_direction) % num_directions

            short_label, long_name = directions[direction_index]
            self.edge_labels[i] = (short_label, long_name)

    def populate_obj_bar(self, obj_bar: Any) -> None:
        """
        Populate the object bar with refractive index controls.

        Args:
            obj_bar: The object bar to populate.
        """
        if self.scene.simulate_colors:
            obj_bar.create_number(
                "Cauchy Coefficient A",  # i18next.t('simulator:sceneObjs.BaseGlass.cauchyCoeff') + " A"
                1,
                3,
                0.01,
                self.refIndex,
                lambda obj, value: setattr(obj, 'refIndex', value * 1),
                '<p>*Relative refractive index</p><p>Effective refractive index</p>'
            )
            obj_bar.create_number(
                "B(μm²)",
                0.0001,
                0.02,
                0.0001,
                self.cauchyB,
                lambda obj, value: setattr(obj, 'cauchyB', value)
            )
        else:
            obj_bar.create_number(
                "Refractive Index*",  # i18next.t('simulator:sceneObjs.BaseGlass.refIndex') + '*'
                0.5,
                2.5,
                0.01,
                self.refIndex,
                lambda obj, value: setattr(obj, 'refIndex', value * 1),
                '<p>*Relative refractive index</p><p>Effective refractive index</p>'
            )

    def get_z_index(self) -> int:
        """
        Get the z-index for drawing order.

        Materials with refractive index < 1 should be drawn after those with > 1
        so that color subtraction in fillGlass works correctly.

        Returns:
            The z-index (negative of refractive index).
        """
        return int(self.refIndex * (-1))

    def fill_glass(self, canvas_renderer: Any, is_above_light: bool, is_hovered: bool) -> None:
        """
        Fill the glass with color representing the refractive index.

        This is a rendering method for UI/visualization. In Python, this serves
        as documentation of the rendering interface. Actual implementation would
        depend on the rendering backend.

        Args:
            canvas_renderer: The canvas renderer.
            is_above_light: Whether the rendering layer is above the light layer.
            is_hovered: Whether the object is hovered by the mouse.
        """
        # This method is primarily for rendering in the JavaScript UI
        # In Python, we keep it as a stub for interface compatibility
        return True

    def refract(
        self,
        ray: 'Ray',
        ray_index: int,
        incident_point: Union['Point', Dict[str, float]],
        normal: Union['Point', Dict[str, float]],
        n1: float,
        surface_merging_objs: List['BaseGlass'],
        body_merging_obj: Optional['BaseGlass'] = None,
        verbose: int = 0
    ) -> Optional[SimulationReturn]:
        """
        Perform refraction calculation at the glass surface.

        This method implements Snell's law and Fresnel equations to calculate
        refraction and reflection at the glass surface. The incident ray is
        modified in-place to become the refracted (or reflected) ray.

        Args:
            ray: The ray to be refracted. This object is modified in-place to
                 become the refracted ray (or reflected ray in case of total
                 internal reflection).
            ray_index: The index of the ray in the ray array.
            incident_point: The incident point (Point object or dict).
            normal: The normal vector at the incident point (Point object or dict).
            n1: The effective refractive index ratio (before surface merging).
            surface_merging_objs: Glass objects to be merged with current object.
            body_merging_obj: The GRIN glass object for body merging (if any).

        Returns:
            Optional[SimulationReturn]: The return value depends on the situation:

            - **None**: Total internal reflection occurred. The incident ray has
              been modified in-place to become the reflected ray. No secondary
              rays are created. The caller should continue tracing the ray.

            - **Dict with 'isAbsorbed': False**: Normal refraction occurred. The
              incident ray has been modified in-place to become the refracted ray.
              Secondary reflected rays (from Fresnel reflection) are in 'newRays'.
              The caller should continue tracing both the refracted ray and any
              secondary rays.

            - **Dict with 'isAbsorbed': True**: The refracted ray was too dim and
              was absorbed. Secondary reflected rays may still exist in 'newRays'.
              The caller should NOT continue tracing the incident ray, but should
              trace any secondary rays.

            The dictionary may contain:
                - 'newRays': List of secondary rays (typically Fresnel reflection)
                - 'truncation': Total brightness of rays that were truncated
                - 'isAbsorbed': Whether the refracted ray was absorbed
                - 'isUndefinedBehavior': Error condition (e.g., edge case)

        Note:
            The design uses in-place modification of the incident ray for efficiency,
            avoiding unnecessary object creation. This matches the JavaScript
            implementation and maintains compatibility with the simulation engine.
        """
        # Surface merging - combine refractive indices from multiple glass surfaces
        if verbose >= 2:
            print(f"  Surface merging: {len(surface_merging_objs)} objects, n1 before={n1:.4f}")
        for obj in surface_merging_objs:
            incident_type = obj.get_incident_type(ray)

            if verbose >= 2:
                print(f"    Merging obj: incident_type={incident_type}, refIndex={obj.get_ref_index_at(incident_point, ray):.4f}")

            if incident_type == 1:
                # From inside to outside
                n1 *= obj.get_ref_index_at(incident_point, ray)
                obj.on_ray_exit(ray)
                if verbose >= 2:
                    print(f"      Inside->Outside: n1 *= {obj.get_ref_index_at(incident_point, ray):.4f} => n1={n1:.4f}")
            elif incident_type == -1:
                # From outside to inside
                n1 /= obj.get_ref_index_at(incident_point, ray)
                obj.on_ray_enter(ray)
                if verbose >= 2:
                    print(f"      Outside->Inside: n1 /= {obj.get_ref_index_at(incident_point, ray):.4f} => n1={n1:.4f}")
            elif incident_type == 0:
                # Equivalent to not intersecting (e.g. two overlapping interfaces)
                if verbose >= 2:
                    print(f"      Overlapping surfaces: n1 unchanged")
                pass
            else:
                # Undefined behavior (e.g. incident on an edge point)
                # Absorb the ray to prevent incorrect ray direction
                if verbose >= 2:
                    print(f"      UNDEFINED BEHAVIOR")
                return {
                    'isAbsorbed': True,
                    'isUndefinedBehavior': True
                }
        if verbose >= 2:
            print(f"  Surface merging: n1 after={n1:.4f}")

        # Handle negative refractive indices
        mod_neg = False
        if n1 < 0:
            n1 = -n1  # Flip n1 for compatibility with equations
            mod_neg = True

        # Normalize the normal vector
        if hasattr(normal, 'x'):
            normal_x, normal_y = normal.x, normal.y
        else:
            normal_x, normal_y = normal['x'], normal['y']

        normal_len = math.sqrt(normal_x * normal_x + normal_y * normal_y)
        if normal_len == 0:
            # Invalid normal vector - this can happen when:
            # 1. Ray hits exactly at an edge/corner (geometrically ambiguous)
            # 2. There's a numerical precision issue
            # 3. Mismatch between check_ray_intersects and get_incident_data
            # In JavaScript this would result in NaN propagation; we absorb instead
            return {
                'isAbsorbed': True,
                'isUndefinedBehavior': True
            }
        normal_x /= normal_len
        normal_y /= normal_len

        # Get ray direction
        if hasattr(ray.p1, 'x'):
            ray_dx = ray.p2.x - ray.p1.x
            ray_dy = ray.p2.y - ray.p1.y
        else:
            ray_dx = ray.p2['x'] - ray.p1['x']
            ray_dy = ray.p2['y'] - ray.p1['y']

        ray_len = math.sqrt(ray_dx * ray_dx + ray_dy * ray_dy)
        ray_x = ray_dx / ray_len
        ray_y = ray_dy / ray_len

        # Snell's law in vector form
        # Reference: http://en.wikipedia.org/wiki/Snell%27s_law#Vector_form
        cos1 = -normal_x * ray_x - normal_y * ray_y
        sq1 = 1 - n1 * n1 * (1 - cos1 * cos1)

        # Convert incident_point to dict for consistency
        if hasattr(incident_point, 'x'):
            inc_x, inc_y = incident_point.x, incident_point.y
        else:
            inc_x, inc_y = incident_point['x'], incident_point['y']

        # =====================================================================
        # PYTHON-SPECIFIC FEATURE: Surface Hit Records (Step B, opt-in)
        # =====================================================================
        # Record the geometry of this interaction onto `ray` (the simulator's
        # output_ray_geom). Placed before the TIR/refraction branch so both are
        # captured. The recorded normal is exactly the (normalized) vector the
        # refraction uses; incident_angle is clamped into [0, pi/2] (abs(cos1),
        # since cos1's sign flips with inside->outside vs outside->inside).
        # CONTRIBUTING.md acos clamp rule applies.
        if getattr(ray, 'record_surface_hits', False):
            ray.hit_surface_uuid = self._uuid
            ray.hit_point = {'x': inc_x, 'y': inc_y}
            ray.hit_normal = {'x': normal_x, 'y': normal_y}
            ray.incident_angle = math.acos(max(-1.0, min(1.0, abs(cos1))))

        # DEBUG: Print all refract calls
        if verbose >= 2:
            print(f"\nDEBUG REFRACT CALL:")
            print(f"  Incident point: ({inc_x:.4f}, {inc_y:.4f})")
            print(f"  n1={n1:.4f}, cos1={cos1:.4f}, sq1={sq1:.6f}")
            print(f"  Normal: ({normal_x:.4f}, {normal_y:.4f})")
            print(f"  Ray: ({ray_x:.4f}, {ray_y:.4f})")

        if sq1 < 0:
            # Total internal reflection
            if verbose >= 2:
                print(f"  -> TIR (sq1 < 0)")
            ray.p1 = {'x': inc_x, 'y': inc_y} if isinstance(ray.p1, dict) else incident_point

            refl_x = inc_x + ray_x + 2 * cos1 * normal_x
            refl_y = inc_y + ray_y + 2 * cos1 * normal_y

            if isinstance(ray.p2, dict):
                ray.p2 = {'x': refl_x, 'y': refl_y}
            else:
                ray.p2 = geometry.point(refl_x, refl_y)

            if body_merging_obj:
                ray.bodyMergingObj = body_merging_obj

            # =====================================================================
            # PYTHON-SPECIFIC FEATURE: TIR Tracking
            # =====================================================================
            # Mark this ray as having been produced by Total Internal Reflection.
            # This enables filtering and visualization of TIR events.
            # =====================================================================
            ray.is_tir_result = True
            ray.tir_count = getattr(ray, 'tir_count', 0) + 1

            return None

        else:
            # Refraction occurs
            if verbose >= 2:
                print(f"  -> REFRACTION")
            cos2 = math.sqrt(sq1)

            # Fresnel equations for reflection coefficients
            # Reference: http://en.wikipedia.org/wiki/Fresnel_equations
            R_s = ((n1 * cos1 - cos2) / (n1 * cos1 + cos2)) ** 2
            R_p = ((n1 * cos2 - cos1) / (n1 * cos2 + cos1)) ** 2

            # Transmission coefficients
            T_s = 1 - R_s
            T_p = 1 - R_p

            # =====================================================================
            # PYTHON-SPECIFIC FEATURE: Grazing Incidence Detection
            # =====================================================================
            # Detect grazing incidence using three independent criteria.
            # Grazing incidence occurs near the critical angle where polarization
            # effects become extreme (useful for Abbe refractometer analysis).
            # =====================================================================
            grazing_angle = False
            grazing_polar = False
            grazing_transm = False

            # Criterion 1: Angle threshold
            # Convert cos1 to angle in degrees (cos1 is cosine of incidence angle)
            incidence_angle_deg = math.degrees(math.acos(min(1.0, abs(cos1))))
            if incidence_angle_deg >= self.scene.grazing_angle_threshold:
                grazing_angle = True

            # Criterion 2: Polarization ratio threshold
            # Check if transmitted p/s ratio exceeds threshold (extreme polarization)
            # Only meaningful when both have non-zero transmission
            if T_s > 1e-10:  # Avoid division by zero
                polar_ratio = T_p / T_s
                if polar_ratio >= self.scene.grazing_polarization_ratio_threshold:
                    grazing_polar = True

            # Criterion 3: Transmission ratio threshold
            # T_ratio = (brightness_s * T_s + brightness_p * T_p) / (brightness_s + brightness_p)
            # For unpolarized light this simplifies to (T_s + T_p) / 2
            original_total = ray.brightness_s + ray.brightness_p
            if original_total > 1e-10:  # Avoid division by zero
                transmitted_total = ray.brightness_s * T_s + ray.brightness_p * T_p
                T_ratio = transmitted_total / original_total
                if T_ratio < self.scene.grazing_transmission_threshold:
                    grazing_transm = True

            if verbose >= 2 and (grazing_angle or grazing_polar or grazing_transm):
                print(f"  GRAZING DETECTED: angle={grazing_angle} (angle={incidence_angle_deg:.1f} deg), "
                      f"polar={grazing_polar}, transm={grazing_transm}")

            new_rays = []
            truncation = 0

            # Handle the reflected ray
            refl_x = inc_x + ray_x + 2 * cos1 * normal_x
            refl_y = inc_y + ray_y + 2 * cos1 * normal_y

            ray2 = geometry.line(
                geometry.point(inc_x, inc_y),
                geometry.point(refl_x, refl_y)
            )

            # Store original brightness before any modifications
            original_brightness_s = ray.brightness_s
            original_brightness_p = ray.brightness_p

            ray2.brightness_s = original_brightness_s * R_s
            ray2.brightness_p = original_brightness_p * R_p
            ray2.wavelength = ray.wavelength
            # PYTHON-SPECIFIC: Optical path length (P-RAY-LINEAGE) -- Fresnel reflection
            # stays in the incident medium.
            ray2.medium_index = getattr(ray, 'medium_index', 1.0)
            ray2.gap = getattr(ray, 'gap', False)
            ray2.interaction_type = 'reflect'

            if body_merging_obj:
                ray2.bodyMergingObj = body_merging_obj

            # Check if reflected ray is bright enough to keep
            # =====================================================================
            # PYTHON-SPECIFIC FEATURE: Use scene's configurable brightness threshold
            # =====================================================================
            # In JavaScript, the threshold is hardcoded based on color_mode:
            #   brightness_threshold = 1e-6 if color_mode != 'default' else 0.01
            # In Python, we use scene.get_min_brightness_threshold() which allows
            # explicit control via scene.min_brightness_exp property.
            # =====================================================================
            brightness_threshold = self.scene.get_min_brightness_threshold()
            total_brightness = ray2.brightness_s + ray2.brightness_p

            if total_brightness > brightness_threshold:
                new_rays.append(ray2)
            else:
                # Adaptive ray sampling for dim rays
                # Note: adaptive sampling only applies when using automatic threshold (min_brightness_exp=None)
                # and color_mode='default', to maintain JavaScript compatibility
                use_adaptive_sampling = (
                    self.scene._min_brightness_exp is None and
                    self.scene.color_mode == 'default'
                )
                if not getattr(ray, 'gap', False) and use_adaptive_sampling and total_brightness > 0:
                    amp = math.floor(0.01 / total_brightness) + 1
                    if ray_index % amp == 0:
                        # Keep this ray but amplify it
                        ray2.brightness_s *= amp
                        ray2.brightness_p *= amp
                        new_rays.append(ray2)
                    else:
                        # Truncate this ray (not selected by sampling)
                        truncation += total_brightness
                else:
                    # Truncate this ray (too dim and no adaptive sampling)
                    truncation += total_brightness

            # Handle the refracted ray

            # Handle negative refractive index
            if mod_neg:
                n1 = -n1  # Restore n1
                cos2 = math.cos(2 * math.pi - math.acos(max(-1.0, min(1.0, cos2))))

            # Create refracted ray
            # Calculate refracted direction
            refr_dx = n1 * ray_x + (n1 * cos1 - cos2) * normal_x
            refr_dy = n1 * ray_y + (n1 * cos1 - cos2) * normal_y

            # p2 is along the refracted direction (represents ray direction)
            refr_x = inc_x + refr_dx
            refr_y = inc_y + refr_dy

            # DEBUG: Print refraction details
            if verbose >= 2:
                print(f"DEBUG REFRACTION:")
                print(f"  Incident point: ({inc_x:.4f}, {inc_y:.4f})")
                print(f"  Ray direction: ({ray_x:.4f}, {ray_y:.4f})")
                print(f"  Normal: ({normal_x:.4f}, {normal_y:.4f})")
                print(f"  n1={n1:.4f}, cos1={cos1:.4f}, cos2={cos2:.4f}")
                print(f"  Refracted direction: ({refr_dx:.4f}, {refr_dy:.4f})")

            # Create new ray for refracted light (don't modify input ray)
            # NOTE: Start at incident point, just like JavaScript version
            ray3 = geometry.line(
                geometry.point(inc_x, inc_y),
                geometry.point(refr_x, refr_y)
            )

            # Use original brightness values, not potentially modified ones
            ray3.brightness_s = original_brightness_s * (1 - R_s)
            ray3.brightness_p = original_brightness_p * (1 - R_p)
            ray3.wavelength = ray.wavelength
            # PYTHON-SPECIFIC: Optical path length (P-RAY-LINEAGE) -- n1 here is the
            # fully surface-merging-corrected ratio n_incident/n_transmitted
            # already in scope; ray.medium_index is n_incident (absolute, by
            # induction from Ray's default of 1.0 for every root ray), so
            # dividing recovers n_transmitted (absolute) with nested/overlapping
            # glass corrections already folded in for free.
            ray3.medium_index = getattr(ray, 'medium_index', 1.0) / n1
            ray3.gap = getattr(ray, 'gap', False)
            ray3.interaction_type = 'refract'

            # =====================================================================
            # PYTHON-SPECIFIC FEATURE: Set grazing incidence flags on refracted ray
            # =====================================================================
            # Mark the refracted ray as a result of grazing incidence if any
            # criterion was triggered. Also mark the incoming ray as having caused it.
            # =====================================================================
            if grazing_angle:
                ray3.is_grazing_result__angle = True
                ray.caused_grazing__angle = True
            if grazing_polar:
                ray3.is_grazing_result__polar = True
                ray.caused_grazing__polar = True
            if grazing_transm:
                ray3.is_grazing_result__transm = True
                ray.caused_grazing__transm = True

            if body_merging_obj:
                ray3.bodyMergingObj = body_merging_obj

            # Check if refracted ray is bright enough to continue
            # =====================================================================
            # PYTHON-SPECIFIC FEATURE: Use scene's configurable brightness threshold
            # =====================================================================
            # In JavaScript, the refracted ray threshold is:
            #   brightness_threshold_refr = 1e-6 if color_mode != 'default' else 0
            # Note: JavaScript uses 0 for default mode (always keep refracted rays).
            # In Python, we use scene.get_min_brightness_threshold() for consistency,
            # but preserve JavaScript behavior when min_brightness_exp is None.
            # =====================================================================
            refracted_brightness = ray3.brightness_s + ray3.brightness_p
            if self.scene._min_brightness_exp is not None:
                # Explicit threshold set - use it for refracted rays too
                brightness_threshold_refr = self.scene.get_min_brightness_threshold()
            else:
                # JavaScript-compatible behavior: 0 for default, 1e-6 for others
                brightness_threshold_refr = 1e-6 if self.scene.color_mode != 'default' else 0

            if refracted_brightness > brightness_threshold_refr:
                new_rays.append(ray3)
                if verbose >= 2:
                    print(f"  Added refracted ray to newRays list")
                return {
                    'newRays': new_rays,
                    'truncation': truncation
                }
            else:
                if verbose >= 2:
                    print(f"  Refracted ray too dim, absorbed")
                return {
                    'isAbsorbed': True,
                    'newRays': new_rays,
                    'truncation': truncation + refracted_brightness
                }

    def get_ref_index_at(self, point: Union['Point', Dict[str, float]], ray: 'Ray') -> float:
        """
        Get the refractive index at a specific point for a given ray.

        For normal glasses, the point parameter is not used, but it's needed
        for GRIN (Gradient Index) glasses.

        Args:
            point: The point to get the refractive index at.
            ray: The ray being refracted.

        Returns:
            The refractive index at the point.
        """
        if self.scene.simulate_colors:
            # Cauchy's equation: n(λ) = A + B/λ²
            # wavelength is in nm, cauchyB is in μm²
            return self.refIndex + self.cauchyB / (ray.wavelength * ray.wavelength * 0.000001)
        else:
            return self.refIndex

    # Abstract methods to be implemented in subclasses

    def get_incident_type(self, ray: 'Ray') -> float:
        """
        Get whether the ray is incident from inside or outside the glass.

        This is an abstract method that must be implemented by subclasses.

        Args:
            ray: The ray to check.

        Returns:
            1 if incident from inside to outside,
            -1 if incident from outside to inside,
            0 if equivalent to not intersecting (e.g. overlapping surfaces),
            NaN for other situations (e.g. parallel to surface).
        """
        # To be implemented in subclasses
        return float('nan')

    def on_ray_enter(self, ray: 'Ray') -> None:
        """
        Handle the event when a ray enters the glass.

        Called during surface merging process. For normal glasses, nothing needs
        to be done, but GRIN glasses update the body-merging object here.

        Args:
            ray: The ray entering the glass.
        """
        # Nothing to do for normal glasses
        return True

    def on_ray_exit(self, ray: 'Ray') -> None:
        """
        Handle the event when a ray exits the glass.

        Called during surface merging process. For normal glasses, nothing needs
        to be done, but GRIN glasses update the body-merging object here.

        Args:
            ray: The ray exiting the glass.
        """
        # Nothing to do for normal glasses
        return True


# Example usage
if __name__ == "__main__":
    # Example class combining BaseGlass with BaseSceneObj
    class GlassObject(BaseGlass, BaseSceneObj):
        type = 'glass_object'
        serializable_defaults = {
            'refIndex': 1.5,
            'cauchyB': 0.004
        }
        is_optical = True

        def __init__(self, scene, json_obj=None):
            super().__init__(scene, json_obj)

        def get_incident_type(self, ray):
            # Simple example: always incident from outside
            return -1

    # Mock scene
    class MockScene:
        def __init__(self):
            self.error = None
            self.simulate_colors = False
            self.color_mode = 'default'
            self.length_scale = 1.0
            self._min_brightness_exp = None

        def get_min_brightness_threshold(self):
            """Return brightness threshold for ray truncation."""
            if self._min_brightness_exp is not None:
                return 10 ** self._min_brightness_exp
            return 0.01 if self.color_mode == 'default' else 1e-6

    # Mock ray for testing
    class MockRay:
        def __init__(self):
            self.p1 = {'x': 0, 'y': 0}
            self.p2 = {'x': 1, 'y': 0}
            self.wavelength = 532  # Green light
            self.brightness_s = 1.0
            self.brightness_p = 1.0
            self.gap = False

    scene = MockScene()
    glass = GlassObject(scene)

    print("Initial glass object:")
    print(f"  Refractive index: {glass.refIndex}")
    print(f"  Cauchy B: {glass.cauchyB}")
    print(f"  Z-index: {glass.get_z_index()}")
    print(f"  Merges with glass: {glass.merges_with_glass}")

    # Test get_ref_index_at
    ray = MockRay()
    print(f"\nRefractive index at point (no color simulation): {glass.get_ref_index_at(None, ray)}")

    # Test with color simulation
    scene.simulate_colors = True
    glass.refIndex = 1.5
    glass.cauchyB = 0.004
    n_green = glass.get_ref_index_at(None, ray)
    print(f"Refractive index for green light (532 nm): {n_green:.6f}")

    # Test with different wavelengths
    ray.wavelength = 450  # Blue
    n_blue = glass.get_ref_index_at(None, ray)
    print(f"Refractive index for blue light (450 nm): {n_blue:.6f}")

    ray.wavelength = 650  # Red
    n_red = glass.get_ref_index_at(None, ray)
    print(f"Refractive index for red light (650 nm): {n_red:.6f}")

    print(f"\nDispersion (blue - red): {n_blue - n_red:.6f}")

    # Test refraction
    print("\n--- Testing refraction ---")
    scene.color_mode = 'default'
    ray = MockRay()
    ray.p1 = {'x': -1, 'y': 0}
    ray.p2 = {'x': 0, 'y': 0}

    print(f"Initial ray brightness: s={ray.brightness_s}, p={ray.brightness_p}")

    incident_point = geometry.point(0, 0)
    normal = geometry.point(-1, 0)  # Normal pointing left (opposite to ray direction)

    result = glass.refract(ray, 0, incident_point, normal, 1.5, [], None)

    print(f"After refraction brightness: s={ray.brightness_s:.6f}, p={ray.brightness_p:.6f}")

    if result:
        print(f"Refraction result:")
        print(f"  New rays created: {len(result.get('newRays', []))}")
        if result.get('newRays'):
            for i, new_ray in enumerate(result.get('newRays', [])):
                print(f"    Ray {i}: s={new_ray.brightness_s:.6f}, p={new_ray.brightness_p:.6f}")
        print(f"  Truncation: {result.get('truncation', 0):.6f}")
        print(f"  Ray absorbed: {result.get('isAbsorbed', False)}")
    else:
        print("Total internal reflection occurred")

    print(f"Refracted ray direction: ({ray.p2['x']:.3f}, {ray.p2['y']:.3f})")

    print("\nBaseGlass test completed successfully!")
