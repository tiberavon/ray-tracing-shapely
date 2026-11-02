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

import svgwrite
import math
import random


# Standard wavelengths in nm for color simulation
GREEN_WAVELENGTH = 546  # Mercury green line


def wavelength_to_rgb(wavelength):
    """
    Convert a wavelength (in nm) to an RGB color tuple.

    Based on approximation of CIE color matching functions.
    Returns values in range 0-255.

    Args:
        wavelength (float): Wavelength in nanometers (380-780 nm)

    Returns:
        tuple: (r, g, b) values from 0-255
    """
    if wavelength is None:
        wavelength = GREEN_WAVELENGTH

    # Clamp to visible range
    wavelength = max(380, min(780, wavelength))

    # Approximate RGB from wavelength using piecewise linear functions
    if wavelength < 440:
        r = -(wavelength - 440) / (440 - 380)
        g = 0.0
        b = 1.0
    elif wavelength < 490:
        r = 0.0
        g = (wavelength - 440) / (490 - 440)
        b = 1.0
    elif wavelength < 510:
        r = 0.0
        g = 1.0
        b = -(wavelength - 510) / (510 - 490)
    elif wavelength < 580:
        r = (wavelength - 510) / (580 - 510)
        g = 1.0
        b = 0.0
    elif wavelength < 645:
        r = 1.0
        g = -(wavelength - 645) / (645 - 580)
        b = 0.0
    else:
        r = 1.0
        g = 0.0
        b = 0.0

    # Intensity correction at spectrum edges
    if wavelength < 420:
        factor = 0.3 + 0.7 * (wavelength - 380) / (420 - 380)
    elif wavelength > 700:
        factor = 0.3 + 0.7 * (780 - wavelength) / (780 - 700)
    else:
        factor = 1.0

    return (
        int(255 * r * factor),
        int(255 * g * factor),
        int(255 * b * factor)
    )


def brightness_to_opacity(brightness, color_mode='default'):
    """
    Convert ray brightness to rendering opacity based on color mode.

    Args:
        brightness (float): Total ray brightness (brightness_s + brightness_p)
        color_mode (str): Color rendering mode:
            - 'default': Linear mapping, clipped to [0, 1]
            - 'linear': Linear value mapping with gamma correction
            - 'linearRGB': Linear RGB (no gamma)
            - 'reinhard': Reinhard tone mapping for HDR
            - 'colorizedIntensity': Returns 1.0 (uses color coding instead)

    Returns:
        float: Opacity value from 0.0 to 1.0
    """
    if brightness <= 0:
        return 0.0

    if color_mode == 'default':
        # Simple linear mapping, clipped
        return min(1.0, max(0.0, brightness))

    elif color_mode == 'linear':
        # Linear value with gamma correction (sRGB)
        value = min(1.0, brightness)
        # Apply gamma correction (approximate sRGB)
        if value <= 0.0031308:
            return 12.92 * value
        else:
            return 1.055 * (value ** (1 / 2.4)) - 0.055

    elif color_mode == 'linearRGB':
        # Linear RGB - no gamma correction
        return min(1.0, max(0.0, brightness))

    elif color_mode == 'reinhard':
        # Reinhard tone mapping: L / (1 + L)
        return brightness / (1 + brightness)

    elif color_mode == 'colorizedIntensity':
        # Full opacity; intensity shown via color
        return 1.0

    else:
        # Fallback to default
        return min(1.0, max(0.0, brightness))


def brightness_to_color(brightness, color_mode='default', base_color=(255, 0, 0)):
    """
    Convert ray brightness to a color based on color mode.

    For 'colorizedIntensity' mode, maps brightness to a heat-map style color.
    For other modes, returns the base_color.

    Args:
        brightness (float): Total ray brightness
        color_mode (str): Color rendering mode
        base_color (tuple): Base RGB color for non-intensity modes

    Returns:
        str: CSS color string (e.g., 'rgb(255, 0, 0)')
    """
    if color_mode == 'colorizedIntensity':
        # Heat map: black -> blue -> cyan -> green -> yellow -> red -> white
        # Logarithmic scale for better visualization
        if brightness <= 0:
            return 'rgb(0, 0, 0)'

        # Use log scale with offset
        log_val = math.log10(brightness + 0.001) + 3  # Shift so 0.001 -> 0
        normalized = max(0, min(1, log_val / 4))  # 4 decades of range

        # Heat map gradient
        if normalized < 0.2:
            # Black to blue
            t = normalized / 0.2
            r, g, b = 0, 0, int(255 * t)
        elif normalized < 0.4:
            # Blue to cyan
            t = (normalized - 0.2) / 0.2
            r, g, b = 0, int(255 * t), 255
        elif normalized < 0.6:
            # Cyan to green
            t = (normalized - 0.4) / 0.2
            r, g, b = 0, 255, int(255 * (1 - t))
        elif normalized < 0.8:
            # Green to yellow
            t = (normalized - 0.6) / 0.2
            r, g, b = int(255 * t), 255, 0
        else:
            # Yellow to red
            t = (normalized - 0.8) / 0.2
            r, g, b = 255, int(255 * (1 - t)), 0

        return f'rgb({r}, {g}, {b})'

    else:
        # Use base color
        return f'rgb({base_color[0]}, {base_color[1]}, {base_color[2]})'


class SVGRenderer:
    """
    SVG renderer for ray optics simulation.

    This class creates descriptive SVG output with metadata attributes
    that describe the simulation elements. The SVG is organized into
    five layers (similar to the JavaScript implementation which is 3 layers (no graphical annotations)):
    - objects: Optical elements (below rays)
    - graphic annotations: (below rays)
    - rays: Light rays
    - labels: Text annotations tied to physical scene objects
    - diagram annotations: Pedagogical overlays (draw_annotation_*()) -- topmost


    The SVG includes data attributes on elements for post-processing
    and analysis.

    Coordinate System:
        The renderer uses a Y-up coordinate system (positive Y points upward),
        which matches mathematical convention. This is achieved by applying
        a vertical flip transformation to the SVG coordinate system.

    Attributes:
        width (int): Canvas width in pixels
        height (int): Canvas height in pixels
        viewbox (tuple or None): SVG viewBox (min_x, min_y, width, height)
        dwg (svgwrite.Drawing): The SVG drawing object
        layer_objects (svgwrite.Group): Group for object elements
        layer_rays (svgwrite.Group): Group for ray elements
        layer_labels (svgwrite.Group): Group for label elements
    """

    def __init__(self, width=800, height=600, viewbox=None, metadata_level='full'):
        """
        Initialize the SVG renderer.

        Args:
            width (int): Canvas width in pixels (default: 800)
            height (int): Canvas height in pixels (default: 600)
            viewbox (tuple or None): SVG viewBox as (min_x, min_y, width, height)
                                    If None, uses (0, 0, width, height)
            metadata_level (str): Controls how much simulation metadata to embed.
                - 'none': No simulation metadata (smallest files)
                - 'standard': id + inkscape:label + class (good for Inkscape navigation)
                - 'full': All of 'standard' plus data-* attributes (good for scripting)

        Note:
            The viewbox coordinates use a Y-up system (positive Y goes up).
            Internally, this is converted to SVG's Y-down system with a transform.
        """
        self.width = width
        self.height = height
        self.metadata_level = metadata_level
        self.user_viewbox = viewbox if viewbox is not None else (0, 0, width, height)

        # Convert user's Y-up viewbox to SVG's Y-down viewbox
        # User specifies (min_x, min_y, width, height) in Y-up coordinates
        # SVG needs the viewbox flipped: min_y becomes -(min_y + height)
        min_x, min_y, vb_width, vb_height = self.user_viewbox
        svg_viewbox = (min_x, -(min_y + vb_height), vb_width, vb_height)
        self.viewbox = svg_viewbox

        # Create SVG drawing with profile='full' to enable data-* attributes
        # and Inkscape namespace support. debug=False disables svgwrite's
        # strict attribute validation, which rejects custom namespaces.
        self.dwg = svgwrite.Drawing(size=(f'{width}px', f'{height}px'),
                                    profile='full', debug=False)
        self.dwg.viewbox(*self.viewbox)

        # Register Inkscape namespace for layer support and inkscape:label
        self.dwg['xmlns:inkscape'] = 'http://www.inkscape.org/namespaces/inkscape'

        # Add white background (covers the entire viewbox)
        self.dwg.add(self.dwg.rect(
            insert=(self.viewbox[0], self.viewbox[1]),
            size=(self.viewbox[2], self.viewbox[3]),
            fill='white'
        ))

        # Create layers as proper Inkscape layers (bottom to top) with Y-flip
        # This makes positive Y point upward (mathematical convention)
        self.layer_objects = self.dwg.add(self.dwg.g(
            id='layer-objects',
            transform='scale(1, -1)',
            **{'inkscape:groupmode': 'layer', 'inkscape:label': 'Objects'}
        ))
        self.layer_graphic_symb = self.dwg.add(self.dwg.g(
            id='layer-graphic-symb',
            transform='scale(1, -1)',
            **{'inkscape:groupmode': 'layer', 'inkscape:label': 'Graphic Annotations'}
        ))
        self.layer_rays = self.dwg.add(self.dwg.g(
            id='layer-rays',
            transform='scale(1, -1)',
            **{'inkscape:groupmode': 'layer', 'inkscape:label': 'Rays'}
        ))
        self.layer_labels = self.dwg.add(self.dwg.g(
            id='layer-labels',
            transform='scale(1, -1)',
            **{'inkscape:groupmode': 'layer', 'inkscape:label': 'Labels'}
        ))
        # Topmost layer: pedagogical diagram overlays (point markers, vectors,
        # angle arcs) added by draw_annotation_*() -- always painted last, so
        # they stay visible over a dense ray trace. Distinct from
        # layer_graphic_symb (sub-ray construction lines) and layer_labels
        # (text tied to physical scene objects).
        self.layer_diagram_annotations = self.dwg.add(self.dwg.g(
            id='layer-diagram-annotations',
            transform='scale(1, -1)',
            **{'inkscape:groupmode': 'layer', 'inkscape:label': 'Diagram Annotations'}
        ))

        self.center_line_pattern = "20, 5, 5, 5"

    def _normalize_coord(self, value):
        """
        Normalize a coordinate value to handle edge cases.

        Handles:
        - Negative zero (-0.0) -> positive zero (0.0)
        - Very small values near zero -> zero

        Args:
            value (float): Coordinate value to normalize

        Returns:
            float: Normalized coordinate value
        """
        # Handle negative zero and very small values
        if value == 0.0 or abs(value) < 1e-10:
            return 0.0
        return value

    def _normalize_point(self, point):
        """
        Normalize a point dictionary to handle edge cases.

        Args:
            point (dict): Point with 'x' and 'y' keys

        Returns:
            dict: Normalized point
        """
        return {
            'x': self._normalize_coord(point['x']),
            'y': self._normalize_coord(point['y'])
        }

    def draw_ray_segment(self, ray, color='red', opacity=1.0, stroke_width=1.5,
                         extend_to_edge=False, draw_gap_rays=False, show_arrow=False,
                         arrow_size=None, arrow_position=0.67, dasharray=None):
        """
        Draw a ray segment with optional direction arrow.

        Args:
            ray (Ray): The ray segment to draw
            color (str): CSS color string (default: 'red')
            opacity (float): Opacity 0.0-1.0 (default: 1.0)
            stroke_width (float): Line width in pixels (default: 1.5)
            extend_to_edge (bool): If True, extend ray to viewport edge (default: False)
            draw_gap_rays (bool): If True, draw gap rays (default: False)
            show_arrow (bool): If True, draw direction arrow on the ray (default: False)
            arrow_size (float or None): Size of arrow head. If None, auto-calculated
                based on stroke_width (default: None)
            arrow_position (float): Position of arrow along ray as fraction 0.0-1.0
                (default: 0.67, i.e., 2/3 along the ray)
            dasharray (str or None): SVG stroke-dasharray value (e.g. '4,2' for a
                4-unit dash / 2-unit gap, in the same coordinate units as the ray
                itself). None (default) draws a solid line -- unchanged rendering
                unless overridden. Only applies to the simple-line path
                (show_arrow=False); ignored when show_arrow=True. A dashed
                overlay ray lets whatever is drawn underneath show through the
                gaps, instead of one solid stroke fully occluding another.
        """
        p1 = ray.p1
        p2 = ray.p2

        # Skip rays with invalid coordinates
        if (math.isnan(p1['x']) or math.isnan(p1['y']) or
            math.isnan(p2['x']) or math.isnan(p2['y']) or
            math.isinf(p1['x']) or math.isinf(p1['y']) or
            math.isinf(p2['x']) or math.isinf(p2['y'])):
            return

        if extend_to_edge:
            # Extend the ray to the edge of the viewbox
            p2 = self._extend_to_edge(p1, p2)

        # Clip the ray to the viewbox boundaries
        # This prevents drawing geometry way outside the visible area
        p1_clipped, p2_clipped = self._clip_to_viewbox(p1, p2)

        if p1_clipped is None or p2_clipped is None:
            # Ray is completely outside the viewbox
            return

        # Normalize coordinates to handle edge cases like -0.0
        p1 = self._normalize_point(p1_clipped)
        p2 = self._normalize_point(p2_clipped)

        # Don't draw if it's a gap (unless draw_gap_rays is True)
        if ray.gap and not draw_gap_rays:
            return

        # Build metadata based on metadata_level
        ray_uuid = getattr(ray, 'uuid', None)
        ray_id = None
        ray_label = None

        if self.metadata_level != 'none':
            ray_id = f'ray-{ray_uuid}' if ray_uuid else f'ray-b{ray.total_brightness:.3f}'
            label_parts = []
            if ray.wavelength is not None:
                label_parts.append(f'{ray.wavelength:.0f}nm')
            label_parts.append(f'b={ray.total_brightness:.3f}')
            interaction = getattr(ray, 'interaction_type', None)
            if interaction:
                label_parts.append(interaction)
            ray_label = ' '.join(label_parts)

        if show_arrow:
            # Draw ray with arrow
            self._draw_ray_with_arrow(p1, p2, color, opacity, stroke_width,
                                      arrow_size, arrow_position, ray_id,
                                      ray_label=ray_label, ray=ray)
        else:
            # Draw simple line
            kwargs = dict(
                start=(p1['x'], p1['y']),
                end=(p2['x'], p2['y']),
                stroke=color,
                stroke_width=stroke_width,
                stroke_opacity=opacity,
            )
            if dasharray:
                kwargs['stroke_dasharray'] = dasharray
            if ray_id:
                kwargs['id'] = ray_id
            line = self.dwg.line(**kwargs)

            if self.metadata_level != 'none':
                line['class'] = 'ray'
                line['inkscape:label'] = ray_label

            if self.metadata_level == 'full':
                self._attach_ray_data_attributes(line, ray)

            self.layer_rays.add(line)
    
    def draw_centerline_segment(self,p1:dict[str,float],p2:dict[str,float], 
                                id_str:str=None, color:str='gray', 
                                opacity:float=1.0, stroke_width:float=1.5,
                                extend_to_edge:bool=False) -> bool:
        """
        Draw a center line segment (this is a graphical annotation).

        Args:
            
            color (str): CSS color string (default: 'red')
            opacity (float): Opacity 0.0-1.0 (default: 1.0)
            stroke_width (float): Line width in pixels (default: 1.5)
            extend_to_edge (bool): If True, extend ray to viewport edge (default: False)
            draw_gap_rays (bool): If True, draw gap rays (default: False)

        """
        
        # Skip rays with invalid coordinates
        if (math.isnan(p1['x']) or math.isnan(p1['y']) or
            math.isnan(p2['x']) or math.isnan(p2['y']) or
            math.isinf(p1['x']) or math.isinf(p1['y']) or
            math.isinf(p2['x']) or math.isinf(p2['y'])):
            return False

        if extend_to_edge:
            # Extend the ray to the edge of the viewbox
            p2 = self._extend_to_edge(p1, p2)

        # Clip the ray to the viewbox boundaries
        # This prevents drawing geometry way outside the visible area
        p1_clipped, p2_clipped = self._clip_to_viewbox(p1, p2)

        if p1_clipped is None or p2_clipped is None:
            # Ray is completely outside the viewbox
            return False

        # Normalize coordinates to handle edge cases like -0.0
        p1 = self._normalize_point(p1_clipped)
        p2 = self._normalize_point(p2_clipped)

        id:str = "CL"
        if id_str is not None:
            id = id_str    

        else:
            # Draw simple line
            line = self.dwg.line(
                start=(p1['x'], p1['y']),
                end=(p2['x'], p2['y']),
                stroke=color,
                stroke_width=stroke_width,
                stroke_opacity=opacity,
                stroke_dasharray=self.center_line_pattern,
                id=id
            )
            self.layer_graphic_symb.add(line)
        
        return True    

    def _draw_ray_with_arrow(self, p1, p2, color, opacity, stroke_width,
                             arrow_size, arrow_position, ray_id=None,
                             ray_label=None, ray=None):
        """
        Draw a ray segment with a direction arrow.

        The arrow is drawn as a trapezoid shape that smoothly transitions
        from the line width to the arrow tip width, matching the JavaScript
        CanvasRenderer style.

        Args:
            p1 (dict): Start point {'x': x, 'y': y}
            p2 (dict): End point {'x': x, 'y': y}
            color (str): CSS color string
            opacity (float): Opacity 0.0-1.0
            stroke_width (float): Line width in pixels
            arrow_size (float or None): Size of arrow head
            arrow_position (float): Position of arrow along ray (0.0-1.0)
            ray_id (str or None): Optional id for the ray group
            ray_label (str or None): Inkscape label for the group
            ray (Ray or None): The ray object for data-* attributes
        """
        # Calculate ray direction and length
        dx = p2['x'] - p1['x']
        dy = p2['y'] - p1['y']
        length = math.sqrt(dx * dx + dy * dy)

        if length < 1e-6:
            return  # Ray too short to draw

        # Unit vectors
        unit_x = dx / length
        unit_y = dy / length

        # Perpendicular vector (for arrow width)
        perp_x = -unit_y
        perp_y = unit_x

        # Auto-calculate arrow size if not provided
        if arrow_size is None:
            arrow_size = min(length * 0.15, 5.0)

        # Don't draw arrow if it would be too small compared to line width
        if arrow_size < stroke_width * 1.2:
            # Just draw a simple line
            line = self.dwg.line(
                start=(p1['x'], p1['y']),
                end=(p2['x'], p2['y']),
                stroke=color,
                stroke_width=stroke_width,
                stroke_opacity=opacity
            )
            if ray_id:
                line['id'] = ray_id
            if self.metadata_level != 'none':
                line['class'] = 'ray'
                if ray_label:
                    line['inkscape:label'] = ray_label
            if self.metadata_level == 'full' and ray is not None:
                self._attach_ray_data_attributes(line, ray)
            self.layer_rays.add(line)
            return

        # Create a group for the ray with arrow — metadata goes on the group
        group = self.dwg.g()
        if ray_id:
            group['id'] = ray_id
        if self.metadata_level != 'none':
            group['class'] = 'ray'
            if ray_label:
                group['inkscape:label'] = ray_label
        if self.metadata_level == 'full' and ray is not None:
            self._attach_ray_data_attributes(group, ray)

        # Calculate arrow position
        arrow_x = p1['x'] + dx * arrow_position
        arrow_y = p1['y'] + dy * arrow_position

        # Draw first part of line (from p1 to arrow start)
        arrow_start_x = arrow_x - (arrow_size / 2) * unit_x
        arrow_start_y = arrow_y - (arrow_size / 2) * unit_y

        line1 = self.dwg.line(
            start=(p1['x'], p1['y']),
            end=(arrow_start_x, arrow_start_y),
            stroke=color,
            stroke_width=stroke_width,
            stroke_opacity=opacity
        )
        group.add(line1)

        # Draw arrow as trapezoid (wide at front, narrow at back)
        tip_width = arrow_size
        base_width = stroke_width

        # Arrow points - trapezoid shape
        # Front points (wide part at arrow_start)
        front_left_x = arrow_start_x - (tip_width / 2) * perp_x
        front_left_y = arrow_start_y - (tip_width / 2) * perp_y
        front_right_x = arrow_start_x + (tip_width / 2) * perp_x
        front_right_y = arrow_start_y + (tip_width / 2) * perp_y

        # Back points (narrow part at arrow_end)
        arrow_end_x = arrow_x + (arrow_size / 2) * unit_x
        arrow_end_y = arrow_y + (arrow_size / 2) * unit_y
        back_left_x = arrow_end_x - (base_width / 2) * perp_x
        back_left_y = arrow_end_y - (base_width / 2) * perp_y
        back_right_x = arrow_end_x + (base_width / 2) * perp_x
        back_right_y = arrow_end_y + (base_width / 2) * perp_y

        arrow_points = [
            (front_left_x, front_left_y),
            (front_right_x, front_right_y),
            (back_right_x, back_right_y),
            (back_left_x, back_left_y)
        ]

        arrow_polygon = self.dwg.polygon(
            points=arrow_points,
            fill=color,
            fill_opacity=opacity
        )
        group.add(arrow_polygon)

        # Draw second part of line (from arrow end to p2)
        line2 = self.dwg.line(
            start=(arrow_end_x, arrow_end_y),
            end=(p2['x'], p2['y']),
            stroke=color,
            stroke_width=stroke_width,
            stroke_opacity=opacity
        )
        group.add(line2)

        self.layer_rays.add(group)

    def _attach_ray_data_attributes(self, element, ray) -> None:
        """Attach data-* attributes from a Ray object to an SVG element."""
        ray_uuid = getattr(ray, 'uuid', None)
        if ray_uuid:
            element['data-uuid'] = ray_uuid
        if ray.wavelength is not None:
            element['data-wavelength'] = str(ray.wavelength)
        element['data-brightness-s'] = f'{ray.brightness_s:.6f}'
        element['data-brightness-p'] = f'{ray.brightness_p:.6f}'
        parent_uuid = getattr(ray, 'parent_uuid', None)
        if parent_uuid:
            element['data-parent-uuid'] = parent_uuid

    def _attach_scene_obj_metadata(self, element, scene_obj,
                                   css_class: str = 'scene-obj') -> None:
        """Attach id, inkscape:label, class, and data-uuid from a scene object.

        Respects self.metadata_level:
        - 'none': no metadata attached
        - 'standard': id + inkscape:label + class
        - 'full': standard + data-uuid
        """
        if self.metadata_level == 'none':
            return

        obj_uuid = getattr(scene_obj, 'uuid', None)
        obj_name = getattr(scene_obj, 'name', None)
        if obj_name is None:
            get_name = getattr(scene_obj, 'get_display_name', None)
            if get_name:
                obj_name = get_name()
        if obj_uuid:
            element['id'] = f'{css_class}-{obj_uuid}'
        if obj_name:
            element['inkscape:label'] = obj_name
        element['class'] = css_class

        if self.metadata_level == 'full' and obj_uuid:
            element['data-uuid'] = obj_uuid

    def draw_ray_with_scene_settings(self, ray, scene, base_color=(255, 0, 0),
                                     stroke_width=1.5, extend_to_edge=False):
        """
        Draw a ray segment using scene settings for color mode and arrows.

        This is a convenience method that automatically applies scene settings
        for color_mode, show_ray_arrows, and simulate_colors.

        Args:
            ray (Ray): The ray segment to draw
            scene (Scene): Scene object with color_mode, show_ray_arrows, etc.
            base_color (tuple): Base RGB color (default: red)
            stroke_width (float): Line width in pixels (default: 1.5)
            extend_to_edge (bool): If True, extend ray to viewport edge

        Example:
            scene = Scene()
            scene.color_mode = 'reinhard'
            scene.show_ray_arrows = True

            for ray in rays:
                renderer.draw_ray_with_scene_settings(ray, scene)
        """
        # Determine color based on wavelength or base color
        if scene.simulate_colors and ray.wavelength is not None:
            rgb = wavelength_to_rgb(ray.wavelength)
            color = f'rgb({rgb[0]}, {rgb[1]}, {rgb[2]})'
        elif scene.color_mode == 'colorizedIntensity':
            color = brightness_to_color(ray.total_brightness, scene.color_mode)
        else:
            color = f'rgb({base_color[0]}, {base_color[1]}, {base_color[2]})'

        # Determine opacity based on color mode
        opacity = brightness_to_opacity(ray.total_brightness, scene.color_mode)

        # Draw the ray
        self.draw_ray_segment(
            ray,
            color=color,
            opacity=opacity,
            stroke_width=stroke_width,
            extend_to_edge=extend_to_edge,
            draw_gap_rays=False,
            show_arrow=scene.show_ray_arrows
        )

    def draw_point(self, point, color='black', radius=3, label=None, scene_obj=None,
                   label_font_size='8px'):
        """
        Draw a point (circle).

        Args:
            point (dict): Point with 'x' and 'y' keys
            color (str): Fill color (default: 'black')
            radius (float): Circle radius in pixels (default: 3)
            label (str or None): Optional text label to show near point
            scene_obj: Optional scene object for simulation metadata.
            label_font_size (str): CSS font size for the label (default: '8px').
        """
        point = self._normalize_point(point)

        circle = self.dwg.circle(
            center=(point['x'], point['y']),
            r=radius,
            fill=color
        )

        if scene_obj is not None:
            self._attach_scene_obj_metadata(circle, scene_obj, css_class='point')

        self.layer_objects.add(circle)

        if label:
            font_size = label_font_size
            vertical_offset = float(font_size.replace('px', '').replace('pt', '')) * 0.35

            text = self.dwg.text(
                label,
                insert=(point['x'] + radius + 2,
                        -(point['y'] - radius - 2) + vertical_offset),
                fill=color,
                font_size=font_size,
                font_family='sans-serif',
                transform='scale(1, -1)'  # Flip text back to be readable
            )
            # Attach id from scene_obj if available
            if scene_obj is not None:
                obj_uuid = getattr(scene_obj, 'uuid', None)
                if obj_uuid:
                    text['id'] = f'label-point-{obj_uuid}'
            self.layer_labels.add(text)

    def draw_line_segment(self, p1, p2, color='gray', stroke_width=2, label=None,
                          scene_obj=None, label_font_size='8px'):
        """
        Draw a line segment (for optical elements like lenses, mirrors).

        Args:
            p1 (dict): Start point with 'x' and 'y' keys
            p2 (dict): End point with 'x' and 'y' keys
            color (str): Stroke color (default: 'gray')
            stroke_width (float): Line width in pixels (default: 2)
            label (str or None): Optional text label
            scene_obj: Optional scene object for simulation metadata.
            label_font_size (str): CSS font size for the label (default: '8px').
        """
        p1 = self._normalize_point(p1)
        p2 = self._normalize_point(p2)

        line = self.dwg.line(
            start=(p1['x'], p1['y']),
            end=(p2['x'], p2['y']),
            stroke=color,
            stroke_width=stroke_width
        )

        if scene_obj is not None:
            self._attach_scene_obj_metadata(line, scene_obj, css_class='line-segment')

        self.layer_objects.add(line)

        if label:
            # Place label at midpoint
            mid_x = self._normalize_coord((p1['x'] + p2['x']) / 2)
            mid_y = self._normalize_coord((p1['y'] + p2['y']) / 2)
            font_size = label_font_size
            vertical_offset = float(font_size.replace('px', '').replace('pt', '')) * 0.35

            text = self.dwg.text(
                label,
                insert=(mid_x, -mid_y + vertical_offset),
                fill=color,
                font_size=font_size,
                font_family='sans-serif',
                text_anchor='middle',
                transform='scale(1, -1)'  # Flip text back to be readable
            )
            # Attach id from scene_obj if available
            if scene_obj is not None:
                obj_uuid = getattr(scene_obj, 'uuid', None)
                if obj_uuid:
                    text['id'] = f'label-line-{obj_uuid}'
            self.layer_labels.add(text)

    # =========================================================================
    # Diagram annotations -- pedagogical overlays, not physical scene
    # objects. Always land in layer_diagram_annotations (topmost layer, see
    # __init__), so they stay visible over a dense ray trace -- unlike
    # draw_point() above, whose marker is in layer_objects (below rays) and
    # only its label in layer_labels. size/stroke_width/radius here are in
    # the SAME scene-coordinate units as the points passed in, not pixels --
    # choose them relative to your own scene's scale, same convention as
    # draw_point()'s radius or draw_scene()'s ray_stroke_width. This includes
    # label_font_size: SVG resolves a "px" font-size inside the current
    # (viewBox-scaled) user space, not real screen pixels, so it needs the
    # same per-scene scaling as everything else here. stroke_width and
    # label_font_size both default to None (resolved to a fraction of the
    # method's own size/arrowhead_size/radius argument) rather than a fixed
    # number, precisely because a fixed default can't be right both for a
    # scene a few units across and one spanning hundreds -- an earlier
    # version of this code shipped with flat stroke_width=1.0/
    # label_font_size='8px' defaults and produced lines ~1/3 of the canvas
    # wide, with labels thrown far off their markers (their position offset
    # is itself derived from the -- oversized -- font size), on a
    # 2.9-unit-wide canvas.
    # =========================================================================

    def draw_annotation_marker(self, point, label=None, style='cross', color='black',
                                size=0.05, stroke_width=None, label_offset=None,
                                label_font_size=None):
        """
        Draw a small point-marker diagram annotation (not a physical scene
        object -- see draw_point() for that).

        Args:
            point (dict): {'x': .., 'y': ..} in scene coordinates.
            label (str or None): Optional text drawn near the marker.
            style (str): 'cross' (two short crossing strokes, the default --
                reads clearly against a dense ray fan where a filled dot can
                get lost) or 'circle' (small open circle).
            color (str): CSS color.
            size (float): Half-width of the cross / radius of the circle, in
                the same scene-coordinate units as `point`.
            stroke_width (float or None): Line width for the 'cross' style /
                circle outline, same units as `size` (NOT pixels -- a fixed
                default here would either vanish or swamp `size` depending on
                the scene's own scale, exactly the failure this had before
                this parameter defaulted to None). Defaults to 0.15*size if None, so it scales with
                `size` automatically instead of needing to be tuned in step
                with it by hand.
            label_offset (tuple or None): (dx, dy) from `point`, same units.
                Defaults to (1.5*size, 1.5*size) if None.
            label_font_size (str or None): CSS font size for the label, in
                the same scene-coordinate units as `size` (NOT real screen
                pixels -- SVG resolves unitless/"px" font-size inside a
                scaled viewBox, so an "8px" default renders as 8 whole
                scene units tall on a small scene; see
                draw_annotation_marker's stroke_width note). Defaults to f"{3*size}px" if None.

        Raises:
            ValueError: If style is not 'cross' or 'circle'.
        """
        point = self._normalize_point(point)
        px, py = point['x'], point['y']
        if stroke_width is None:
            stroke_width = 0.15 * size
        if label_font_size is None:
            label_font_size = f"{3 * size}px"

        if style == 'cross':
            self.layer_diagram_annotations.add(self.dwg.line(
                start=(px - size, py), end=(px + size, py),
                stroke=color, stroke_width=stroke_width,
            ))
            self.layer_diagram_annotations.add(self.dwg.line(
                start=(px, py - size), end=(px, py + size),
                stroke=color, stroke_width=stroke_width,
            ))
        elif style == 'circle':
            self.layer_diagram_annotations.add(self.dwg.circle(
                center=(px, py), r=size, fill='none',
                stroke=color, stroke_width=stroke_width,
            ))
        else:
            raise ValueError(f"draw_annotation_marker: unknown style '{style}' "
                              f"(expected 'cross' or 'circle')")

        if label:
            dx, dy = label_offset if label_offset is not None else (1.5 * size, 1.5 * size)
            font_size_num = float(label_font_size.replace('px', '').replace('pt', ''))
            vertical_offset = font_size_num * 0.35
            text = self.dwg.text(
                label,
                insert=(px + dx, -(py + dy) + vertical_offset),
                fill=color,
                font_size=label_font_size,
                font_family='sans-serif',
                transform='scale(1, -1)',
            )
            self.layer_diagram_annotations.add(text)

    def draw_annotation_vector(self, origin, direction, length, color='#1f77b4',
                                stroke_width=None, arrowhead_size=0.05, label=None,
                                label_offset=None, label_font_size=None):
        """
        Draw a straight annotation arrow from `origin`, in `direction`
        (normalized internally -- need not be a unit vector), for `length`
        scene units, with a triangular arrowhead at the tip.

        Args:
            origin (dict): {'x': .., 'y': ..}.
            direction (tuple): (dx, dy), any nonzero magnitude.
            length (float): Shaft length, scene units.
            color (str): CSS color for both shaft and arrowhead.
            stroke_width (float or None): Shaft line width, scene units (NOT
                pixels). Defaults to 0.15*arrowhead_size if None, so it
                scales with the arrowhead rather than needing separate
                tuning -- see draw_annotation_marker's docstring for why a
                fixed default doesn't work across scenes of very different
                scale.
            arrowhead_size (float): Arrowhead triangle size, scene units.
            label (str or None): Optional text near the tip.
            label_offset (tuple or None): (dx, dy) from the tip. Defaults to
                a small offset perpendicular to `direction` if None.
            label_font_size (str or None): CSS font size for the label, same
                units caveat as draw_annotation_marker's. Defaults to
                f"{3*arrowhead_size}px" if None.

        Raises:
            ValueError: If direction has (numerically) zero magnitude.
        """
        origin = self._normalize_point(origin)
        ox, oy = origin['x'], origin['y']
        if stroke_width is None:
            stroke_width = 0.15 * arrowhead_size
        if label_font_size is None:
            label_font_size = f"{3 * arrowhead_size}px"

        dmag = math.hypot(direction[0], direction[1])
        if dmag < 1e-12:
            raise ValueError("draw_annotation_vector: direction has zero magnitude")
        ux, uy = direction[0] / dmag, direction[1] / dmag
        px, py = -uy, ux  # perpendicular unit vector

        tip_x, tip_y = ox + length * ux, oy + length * uy

        self.layer_diagram_annotations.add(self.dwg.line(
            start=(ox, oy), end=(tip_x, tip_y),
            stroke=color, stroke_width=stroke_width,
        ))

        base_x, base_y = tip_x - arrowhead_size * ux, tip_y - arrowhead_size * uy
        half_w = 0.5 * arrowhead_size
        arrow_points = [
            (tip_x, tip_y),
            (base_x + half_w * px, base_y + half_w * py),
            (base_x - half_w * px, base_y - half_w * py),
        ]
        self.layer_diagram_annotations.add(self.dwg.polygon(points=arrow_points, fill=color))

        if label:
            if label_offset is not None:
                dx, dy = label_offset
            else:
                dx, dy = 0.3 * arrowhead_size * px, 0.3 * arrowhead_size * py
            font_size_num = float(label_font_size.replace('px', '').replace('pt', ''))
            vertical_offset = font_size_num * 0.35
            text = self.dwg.text(
                label,
                insert=(tip_x + dx, -(tip_y + dy) + vertical_offset),
                fill=color,
                font_size=label_font_size,
                font_family='sans-serif',
                transform='scale(1, -1)',
            )
            self.layer_diagram_annotations.add(text)

    def draw_annotation_angle_arc(self, center, angle1, angle2, radius, color='#1f77b4',
                                   stroke_width=None, label=None, label_font_size=None,
                                   n_segments=24):
        """
        Draw a circular arc from `angle1` to `angle2` (radians, standard
        math convention, increasing counter-clockwise -- consistent with
        math.atan2 usage throughout the notebooks this feeds), centered at
        `center`, with the given `radius` (scene units).

        Implemented as a sampled polyline (n_segments straight segments)
        rather than a single SVG elliptical-arc ("A") path command: the "A"
        command only takes two endpoints plus a (large-arc-flag,
        sweep-flag) pair and derives the center itself from them, which
        requires solving the flag combination that reproduces OUR already-
        known `center` -- draw_glass_path()'s own arc segments (lines
        950-966) sidestep this because their center comes from 3 already-
        known path points via _calculate_arc_center(), not from an explicit
        angle pair. Sampling the known circle directly avoids re-deriving
        that flag-solving for an arbitrary angle1/angle2, at the cost of
        the arc being a fine polyline rather than a single path primitive
        -- invisible at n_segments=24 for the angle spans this is meant for.

        Args:
            center (dict): {'x': .., 'y': ..}.
            angle1 (float): Start angle, radians.
            angle2 (float): End angle, radians. Must be >= angle1.
            radius (float): Arc radius, scene units.
            color (str): CSS color.
            stroke_width (float or None): Arc line width, scene units (NOT
                pixels). Defaults to 0.05*radius if None -- see
                draw_annotation_marker's docstring for why a fixed default
                doesn't work across scenes of very different scale.
            label (str or None): Optional text placed at the arc's angular
                midpoint, offset slightly outward.
            label_font_size (str or None): CSS font size for the label, same
                units caveat as draw_annotation_marker's. Defaults to
                f"{0.2*radius}px" if None (a smaller fraction of `radius`
                than stroke_width/marker-size fractions elsewhere, since
                `radius` itself is typically a "large" quantity here, not a
                small one like `size`/`arrowhead_size`).
            n_segments (int): Number of straight segments approximating the
                arc (default: 24).

        Raises:
            ValueError: If angle2 < angle1.
        """
        if angle2 < angle1:
            raise ValueError("draw_annotation_angle_arc: angle2 must be >= angle1")

        center = self._normalize_point(center)
        cx, cy = center['x'], center['y']
        if stroke_width is None:
            stroke_width = 0.05 * radius
        if label_font_size is None:
            label_font_size = f"{0.2 * radius}px"

        points = []
        for i in range(n_segments + 1):
            a = angle1 + (angle2 - angle1) * i / n_segments
            points.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))

        path_data = "M " + " L ".join(f"{x},{y}" for x, y in points)
        self.layer_diagram_annotations.add(self.dwg.path(
            d=path_data, fill='none', stroke=color, stroke_width=stroke_width,
        ))

        if label:
            mid_angle = (angle1 + angle2) / 2.0
            label_radius = radius * 1.2
            lx = cx + label_radius * math.cos(mid_angle)
            ly = cy + label_radius * math.sin(mid_angle)
            font_size_num = float(label_font_size.replace('px', '').replace('pt', ''))
            vertical_offset = font_size_num * 0.35
            text = self.dwg.text(
                label,
                insert=(lx, -ly + vertical_offset),
                fill=color,
                font_size=label_font_size,
                font_family='sans-serif',
                transform='scale(1, -1)',
            )
            self.layer_diagram_annotations.add(text)

    def draw_lens(self, p1, p2, focal_length, color='blue', label=None,
                  scene_obj=None, label_font_size='8px'):
        """
        Draw an ideal lens with arrows indicating converging/diverging.

        Args:
            p1 (dict): First endpoint of lens
            p2 (dict): Second endpoint of lens
            focal_length (float): Focal length (positive=converging, negative=diverging)
            color (str): Color for lens (default: 'blue')
            label (str or None): Optional label
            scene_obj: Optional scene object for simulation metadata.
            label_font_size (str): CSS font size for the label (default: '8px').
        """
        p1 = self._normalize_point(p1)
        p2 = self._normalize_point(p2)

        # Draw the main line (pass scene_obj so metadata attaches to it)
        self.draw_line_segment(p1, p2, color=color, stroke_width=3,
                               scene_obj=scene_obj)

        # Calculate perpendicular direction
        dx = p2['x'] - p1['x']
        dy = p2['y'] - p1['y']
        length = math.sqrt(dx*dx + dy*dy)
        if length < 1e-6:
            return

        # Unit vectors parallel and perpendicular to lens
        par_x = dx / length
        par_y = dy / length
        per_x = par_y
        per_y = -par_x

        arrow_size = 10

        # Draw arrows at endpoints
        if focal_length > 0:
            # Converging lens - arrows point inward
            self._draw_arrow_inward(p1, par_x, par_y, per_x, per_y, arrow_size, color)
            self._draw_arrow_inward(p2, -par_x, -par_y, per_x, per_y, arrow_size, color)
        else:
            # Diverging lens - arrows point outward
            self._draw_arrow_outward(p1, par_x, par_y, per_x, per_y, arrow_size, color)
            self._draw_arrow_outward(p2, -par_x, -par_y, per_x, per_y, arrow_size, color)

        # Draw center mark
        mid_x = self._normalize_coord((p1['x'] + p2['x']) / 2)
        mid_y = self._normalize_coord((p1['y'] + p2['y']) / 2)
        center_size = 8
        center_line = self.dwg.line(
            start=(mid_x - per_x * center_size, mid_y - per_y * center_size),
            end=(mid_x + per_x * center_size, mid_y + per_y * center_size),
            stroke=color,
            stroke_width=2
        )
        self.layer_objects.add(center_line)

        if label:
            font_size = label_font_size
            vertical_offset = float(font_size.replace('px', '').replace('pt', '')) * 0.35

            text = self.dwg.text(
                label,
                insert=(mid_x, -mid_y + vertical_offset),
                fill=color,
                font_size=font_size,
                font_family='sans-serif',
                text_anchor='middle',
                transform='scale(1, -1)'  # Flip text back to be readable
            )
            # Attach id from scene_obj if available
            if scene_obj is not None:
                obj_uuid = getattr(scene_obj, 'uuid', None)
                if obj_uuid:
                    text['id'] = f'label-lens-{obj_uuid}'
            self.layer_labels.add(text)

    def _draw_arrow_inward(self, pos, par_x, par_y, per_x, per_y, size, color):
        """Draw an arrow pointing inward (for converging lens)."""
        points = [
            (pos['x'] - par_x * size, pos['y'] - par_y * size),
            (pos['x'] + par_x * size + per_x * size, pos['y'] + par_y * size + per_y * size),
            (pos['x'] + par_x * size - per_x * size, pos['y'] + par_y * size - per_y * size)
        ]
        polygon = self.dwg.polygon(points=points, fill=color)
        self.layer_objects.add(polygon)

    def _draw_arrow_outward(self, pos, par_x, par_y, per_x, per_y, size, color):
        """Draw an arrow pointing outward (for diverging lens)."""
        points = [
            (pos['x'] + par_x * size, pos['y'] + par_y * size),
            (pos['x'] - par_x * size + per_x * size, pos['y'] - par_y * size + per_y * size),
            (pos['x'] - par_x * size - per_x * size, pos['y'] - par_y * size - per_y * size)
        ]
        polygon = self.dwg.polygon(points=points, fill=color)
        self.layer_objects.add(polygon)

    def draw_glass_path(self, path, fill='cyan', fill_opacity=0.3, stroke='navy',
                       stroke_width=2, label=None, glass_obj=None, label_font_size='8px'):
        """
        Draw a Glass object with arbitrary path (lines and arcs).

        This method correctly interprets the Glass path structure where arc points
        define arcs passing through three points, matching the simulator's behavior.

        Args:
            path (list): List of path points, each a dict with 'x', 'y', and 'arc' keys.
                        When path[i+1]['arc'] == True, creates an arc from path[i]
                        through path[i+1] to path[i+2].
            fill (str): Fill color (default: 'cyan')
            fill_opacity (float): Fill opacity 0.0-1.0 (default: 0.3)
            stroke (str): Stroke color (default: 'navy')
            stroke_width (float): Stroke width in pixels (default: 2)
            label_font_size (str): CSS font size for the label (default: '8px').
            label (str or None): Optional label at center
            glass_obj: Optional Glass object for simulation metadata
                (id, inkscape:label, class, data-uuid).

        Note:
            The arc interpretation matches glass.py: when path[i+1].arc is True,
            the center is calculated by finding the circle passing through
            path[i], path[i+1], and path[i+2] using perpendicular bisectors.
        """
        if not path or len(path) < 3:
            return

        path_data = []
        n = len(path)

        # Start at first point
        p0 = self._normalize_point(path[0])
        path_data.append(f"M {p0['x']},{p0['y']}")

        i = 0
        while i < n:
            next_i = (i + 1) % n
            next_next_i = (i + 2) % n

            p_current = self._normalize_point(path[i])
            p_next = self._normalize_point(path[next_i])

            # Check if next point defines an arc
            if path[next_i].get('arc', False) and i != n - 1:
                # Arc from path[i] through path[i+1] to path[i+2]
                p_next_next = self._normalize_point(path[next_next_i])

                # Calculate arc center and radius
                center = self._calculate_arc_center(p_current, p_next, p_next_next)

                if center:
                    radius = math.sqrt((p_current['x'] - center['x'])**2 +
                                     (p_current['y'] - center['y'])**2)

                    # Use sweep-flag=1 for proper arc direction with Y-flip transform
                    path_data.append(f"A {radius},{radius} 0 0 1 {p_next_next['x']},{p_next_next['y']}")

                    # Skip the next point since we've already drawn to next_next
                    i = next_next_i
                else:
                    # Collinear - treat as line
                    path_data.append(f"L {p_next_next['x']},{p_next_next['y']}")
                    i = next_next_i
            else:
                # Regular line segment
                if i < n - 1:
                    path_data.append(f"L {p_next['x']},{p_next['y']}")
                i = next_i

            # Break if we've wrapped around
            if i == 0:
                break

        path_data.append("Z")  # Close path
        path_string = " ".join(path_data)

        # Create path element
        glass_path = self.dwg.path(
            d=path_string,
            fill=fill,
            fill_opacity=fill_opacity,
            stroke=stroke,
            stroke_width=stroke_width
        )

        # Add simulation metadata if glass_obj is provided
        if glass_obj is not None:
            self._attach_scene_obj_metadata(glass_path, glass_obj, css_class='glass')

        self.layer_objects.add(glass_path)

        # Add label at center if provided
        if label:
            # Calculate centroid
            sum_x = sum(p['x'] for p in path)
            sum_y = sum(p['y'] for p in path)
            center_x = self._normalize_coord(sum_x / len(path))
            center_y = self._normalize_coord(sum_y / len(path))

            font_size = label_font_size
            vertical_offset = float(font_size.replace('px', '').replace('pt', '')) * 0.35  # Approximate vertical centering

            text = self.dwg.text(
                label,
                insert=(center_x, -center_y + vertical_offset),
                fill=stroke,
                font_size=font_size,
                font_family='sans-serif',
                text_anchor='middle',
                transform='scale(1, -1)'  # Flip text back to be readable
            )
            # Attach id from glass_obj if available
            if glass_obj is not None:
                obj_uuid = getattr(glass_obj, 'uuid', None)
                if obj_uuid:
                    text['id'] = f'label-glass-{obj_uuid}'
            self.layer_labels.add(text)

    # =========================================================================
    # PYTHON-SPECIFIC FEATURE: Edge Label Rendering
    # =========================================================================
    # Renders edge labels for glass objects near the center of each edge.
    # Works with the edge labeling feature in BaseGlass.
    # =========================================================================

    def draw_glass_edge_labels(self, glass, color='darkblue', font_size='6px',
                                offset_factor=0.15):
        """
        Draw edge labels for a glass object.

        Renders the short label for each edge near the center of that edge,
        positioned slightly outward from the glass centroid for readability.

        Args:
            glass: A Glass object with edge_labels property and path attribute.
            color (str): Text color for labels (default: 'darkblue')
            font_size (str): CSS font size (default: '10px')
            offset_factor (float): How far to offset labels from edge midpoint
                toward the outside of the glass, as a fraction of the distance
                from centroid to edge midpoint (default: 0.15)

        Note:
            This is a Python-specific feature for visualizing edge labels.
            The glass object must have:
            - path: List of points defining the glass boundary
            - edge_labels: Dict mapping edge index to (short_label, long_name)
        """
        if not hasattr(glass, 'path') or not glass.path:
            return

        if not hasattr(glass, 'edge_labels'):
            return

        path = glass.path
        n = len(path)

        # Calculate centroid for offset direction
        centroid = glass._get_centroid()

        for edge_index in range(n):
            label_tuple = glass.get_edge_label(edge_index)
            if not label_tuple:
                continue

            short_label = label_tuple[0]

            # Calculate edge midpoint
            midpoint = glass._get_edge_midpoint(edge_index)

            # Calculate offset direction (away from centroid)
            dx = midpoint[0] - centroid[0]
            dy = midpoint[1] - centroid[1]
            dist = math.sqrt(dx * dx + dy * dy)

            if dist > 1e-6:
                # Normalize and apply offset
                offset_x = (dx / dist) * dist * offset_factor
                offset_y = (dy / dist) * dist * offset_factor
            else:
                offset_x = 0
                offset_y = 0

            # Position label at midpoint with offset
            label_x = self._normalize_coord(midpoint[0] + offset_x)
            label_y = self._normalize_coord(midpoint[1] + offset_y)

            # Create text element
            # Note: The layer has a Y-flip transform (scale(1, -1)), so the text
            # would appear upside down. We add transform='scale(1, -1)' to the
            # text element itself to flip it back to readable orientation.
            # This means we need to negate the Y coordinate for proper positioning.
            # We also add a small vertical offset to approximately center the
            # text vertically (since dominant-baseline is not supported in SVG
            # tiny profile).
            # Parse font size to get numeric value for vertical offset
            font_size_num = float(font_size.replace('px', '').replace('pt', ''))
            vertical_offset = font_size_num * 0.35  # Approximate vertical centering

            text = self.dwg.text(
                short_label,
                insert=(label_x, -label_y + vertical_offset),
                fill=color,
                font_size=font_size,
                font_family='sans-serif',
                text_anchor='middle',
                transform='scale(1, -1)'  # Flip text back to be readable
            )
            self.layer_labels.add(text)

    def draw_glass_edge_overlays(self, glass_obj, stroke: str = 'none',
                                 stroke_width: float = 0) -> bool:
        """
        Add invisible overlay elements for each labeled edge of a glass object.

        These elements carry edge metadata (id, inkscape:label, data-* attributes)
        and can be selected in Inkscape to find specific edges. They are drawn
        with no visible stroke by default (purely for metadata), but can be made
        visible for debugging.

        Args:
            glass_obj: A Glass object with uuid, name, and edge_labels.
            stroke (str): Stroke color for overlays (default: 'none' = invisible).
            stroke_width (float): Stroke width for overlays (default: 0).

        Returns:
            bool: True on success.
        """
        from ..analysis.glass_geometry import get_edge_descriptions

        edges = get_edge_descriptions(glass_obj)
        obj_uuid = getattr(glass_obj, 'uuid', '')
        obj_name = (getattr(glass_obj, 'name', None)
                    or getattr(glass_obj, 'get_display_name', lambda: obj_uuid[:12])())

        edge_group = self.dwg.g(
            id=f'edges-{obj_uuid}',
        )
        edge_group['inkscape:label'] = f'Edges: {obj_name}'
        edge_group['class'] = 'glass-edges'

        for edge in edges:
            line = self.dwg.line(
                start=(edge.p1.x, edge.p1.y),
                end=(edge.p2.x, edge.p2.y),
                stroke=stroke,
                stroke_width=stroke_width,
            )
            line['id'] = f'{obj_uuid}-edge-{edge.index}'
            line['inkscape:label'] = edge.short_label or f'edge-{edge.index}'
            line['class'] = 'glass-edge'
            line['data-edge-index'] = str(edge.index)
            if edge.long_label:
                line['data-long-label'] = edge.long_label
            edge_group.add(line)

        self.layer_objects.add(edge_group)
        return True

    def draw_scene(self, scene, segments=None, draw_rays: bool = True,
                   draw_objects: bool = True, draw_obj_labels: bool = True,
                   draw_edge_labels: bool = True,
                   draw_edge_overlays: bool = True, ray_subsample: int = 1,
                   ray_subsample_seed=None, ray_stroke_width: float = 1.5,
                   edge_stroke_width: float = 2.0, object_label_font_size: str = '8px',
                   edge_label_font_size: str = '6px', **ray_kwargs) -> bool:
        """
        Draw all objects and rays from a scene with full metadata.

        This is a convenience method. For fine-grained control over appearance,
        use the individual draw_* methods directly.

        Args:
            scene: The Scene object (must have .objs attribute).
            segments: List of Ray segments to draw. Required if draw_rays=True.
            draw_rays (bool): Whether to draw ray segments (default: True).
            draw_objects (bool): Whether to draw scene objects (default: True).
            draw_obj_labels (bool): Whether to draw each object's
                display-name label (glass/lens/point/line objects).
                When False, the label is suppressed regardless of whether
                the object has a get_display_name() (default: True).
            draw_edge_labels (bool): Whether to draw edge labels on glass
                objects (default: True).
            draw_edge_overlays (bool): Whether to add invisible edge overlay
                elements for glass objects (default: True).
            ray_subsample (int): If > 1, draw only a random ~1/ray_subsample
                fraction of `segments` (e.g. 10 -> ~10% of rays). Lets the
                physics run at a high ray_density (for accurate detector/
                power readings) while keeping the rendered SVG small --
                the two were previously coupled through one ray_density.
                The subset is chosen randomly (via random.sample), not by a
                fixed stride, so it isn't visually biased toward one part of
                a ray fan. Default 1: draw every segment, unchanged behaviour.
            ray_subsample_seed: Optional seed for the random subsample, for a
                reproducible picture across re-renders. Default None
                (a different random subset each call).
            ray_stroke_width (float): Line width in pixels for ray segments
                (default: 1.5, matching draw_ray_with_scene_settings's own
                default -- unchanged rendering unless overridden).
            edge_stroke_width (float): Line width in pixels for scene object
                boundaries -- glass polygon edges (draw_glass_path) and
                line-based objects like mirrors/detectors (draw_line_segment)
                (default: 2.0, matching both methods' own defaults --
                unchanged rendering unless overridden). A device built from
                many short wall segments (e.g. DTIRCPrism's wall_segments)
                can look cluttered at the default width; thinning this down
                (e.g. 0.5-1.0) decutters the outline without touching rays.
            object_label_font_size (str): CSS font size for scene-object
                display-name labels -- glass/lens/line/point objects
                (default: '8px', matching each draw_* method's own default).
            edge_label_font_size (str): CSS font size for glass edge
                functional labels (draw_glass_edge_labels), only drawn when
                draw_edge_labels=True (default: '6px', matching that
                method's own default). A device with many short wall
                segments (e.g. DTIRCPrism's wall_segments) gets one label
                per edge -- shrinking this declutters without hiding labels
                entirely (see draw_edge_labels for that).
            **ray_kwargs: Additional keyword arguments passed to
                draw_ray_with_scene_settings (e.g. base_color).

        Returns:
            bool: True on success.
        """
        if draw_objects:
            for obj in scene.objs:
                # Glass objects: have path with >= 3 points
                if hasattr(obj, 'path') and hasattr(obj.path, '__len__') and len(obj.path) >= 3:
                    display_name = getattr(obj, 'get_display_name', lambda: None)() if draw_obj_labels else None
                    self.draw_glass_path(obj.path, label=display_name, glass_obj=obj,
                                         stroke_width=edge_stroke_width,
                                         label_font_size=object_label_font_size)
                    if draw_edge_overlays:
                        self.draw_glass_edge_overlays(obj)
                    if draw_edge_labels:
                        self.draw_glass_edge_labels(obj, font_size=edge_label_font_size)
                # Ideal lenses: have focalLength and p1/p2
                elif hasattr(obj, 'focalLength') and hasattr(obj, 'p1'):
                    display_name = getattr(obj, 'get_display_name', lambda: None)() if draw_obj_labels else None
                    self.draw_lens(obj.p1, obj.p2, obj.focalLength,
                                   label=display_name, scene_obj=obj,
                                   label_font_size=object_label_font_size)
                # Point sources: have x, y attributes and emit rays
                elif hasattr(obj, 'x') and hasattr(obj, 'y') and not hasattr(obj, 'p2'):
                    display_name = getattr(obj, 'get_display_name', lambda: None)() if draw_obj_labels else None
                    self.draw_point({'x': obj.x, 'y': obj.y},
                                    color='orange', radius=4,
                                    label=display_name, scene_obj=obj,
                                    label_font_size=object_label_font_size)
                # Line-based objects: have p1, p2 (mirrors, detectors, etc.)
                elif hasattr(obj, 'p1') and hasattr(obj, 'p2'):
                    display_name = getattr(obj, 'get_display_name', lambda: None)() if draw_obj_labels else None
                    self.draw_line_segment(obj.p1, obj.p2,
                                           label=display_name, scene_obj=obj,
                                           stroke_width=edge_stroke_width,
                                           label_font_size=object_label_font_size)

        if draw_rays and segments:
            draw_segments = segments
            if ray_subsample > 1 and len(segments) > 1:
                rng = random.Random(ray_subsample_seed)
                k = max(1, len(segments) // ray_subsample)
                draw_segments = rng.sample(list(segments), k)
            for seg in draw_segments:
                self.draw_ray_with_scene_settings(seg, scene, stroke_width=ray_stroke_width, **ray_kwargs)

        return True

    def _ensure_highlight_layer(self):
        """Create the Highlights layer on first use."""
        if not hasattr(self, 'layer_highlights'):
            self.layer_highlights = self.dwg.add(self.dwg.g(
                id='layer-highlights',
                transform='scale(1, -1)',
                **{'inkscape:groupmode': 'layer',
                   'inkscape:label': 'Highlights'}
            ))
        return self.layer_highlights

    def draw_scene_with_highlights(
        self,
        scene,
        segments,
        highlight_ray_uuids=None,
        highlight_edge_specs=None,
        highlight_glass_names=None,
        draw_rays: bool = True,
        draw_objects: bool = True,
        highlight_color: str = 'yellow',
        highlight_stroke_width: float = 3.0,
        dim_opacity: float = 0.15,
        base_ray_color: str = 'gray',
        base_stroke_width: float = 1.0,
        base_dasharray=None,
        highlight_dasharray=None,
        ray_stroke_width: float = 1.5,
        ray_subsample: int = 1,
        ray_subsample_seed=None,
        edge_highlight_color: str = 'lime',
        edge_highlight_width: float = 4.0,
        draw_obj_labels: bool = True,
        draw_edge_labels: bool = True,
        draw_edge_overlays: bool = True,
        object_label_font_size: str = '8px',
        edge_label_font_size: str = '6px',
        edge_stroke_width: float = 2.0,
        **ray_kwargs,
    ) -> bool:
        """
        Render a full scene with specific elements highlighted.

        Draws in multiple passes so that highlighted elements appear on top.
        Non-highlighted rays are dimmed; highlighted rays, edges, and glass
        objects are drawn vividly. Parameter names/defaults are aligned with
        draw_scene wherever the two methods do the same job, so switching
        between them only ever means adding/removing the highlight_*
        arguments -- everything about aesthetics (labels, stroke widths,
        subsampling) behaves the same way in both.

        Args:
            scene: The Scene object.
            segments: All ray segments from the simulation.
            highlight_ray_uuids: Set of ray uuids to highlight. If None, all
                rays are drawn normally (no dimming).
            highlight_edge_specs: List of (glass_name, edge_label) tuples.
                Matched edges are drawn with a vivid overlay.
            highlight_glass_names: List of glass object names to highlight
                (drawn with a stronger fill opacity).
            draw_rays (bool): Whether to draw ray segments at all (default:
                True, matching draw_scene's default).
            draw_objects (bool): Whether to draw scene objects at all
                (default: True, matching draw_scene's default).
            highlight_color (str): CSS color for highlighted rays.
            highlight_stroke_width (float): Stroke width for highlighted rays.
            dim_opacity (float): Opacity for non-highlighted rays.
            base_ray_color (str): Color for non-highlighted rays.
            base_stroke_width (float): Line width in pixels for non-highlighted
                rays when highlight_ray_uuids is given (default: 1.0, matching
                the previous hardcoded value -- unchanged rendering unless
                overridden). Widen this if a thin base ray gets fully hidden
                under an overlapping, wider highlighted ray drawn on top of it.
            base_dasharray (str or None): SVG stroke-dasharray for
                non-highlighted rays (e.g. '4,2'). None (default) draws solid,
                unchanged rendering unless overridden.
            highlight_dasharray (str or None): SVG stroke-dasharray for
                highlighted rays (e.g. '4,2'). None (default) draws solid.
                Since highlighted rays are drawn on top (Pass 3), dashing them
                is usually the more useful direction: a solid base ray shows
                through the gaps of an overlapping dashed highlighted one,
                instead of being fully occluded regardless of stroke width.
            ray_stroke_width (float): Line width in pixels for rays when
                highlight_ray_uuids is None -- i.e. the same "just draw
                everything normally" case draw_scene handles (default: 1.5,
                matching draw_scene's own default). Has no effect once
                highlight_ray_uuids is given; base_stroke_width /
                highlight_stroke_width take over for that case instead,
                since there are two ray populations to style independently.
            ray_subsample (int): If > 1, draw only a random ~1/ray_subsample
                fraction of the *non-highlighted* rays (default: 1, matching
                draw_scene's default -- unchanged rendering unless overridden).
                Every ray named in highlight_ray_uuids is always drawn in
                full, never subsampled -- an explicitly requested highlight
                must never silently vanish because of subsampling.
            ray_subsample_seed: Optional seed for the random subsample, for a
                reproducible picture across re-renders (default: None, a
                different random subset each call -- matches draw_scene).
            edge_highlight_color (str): Color for edges named in
                highlight_edge_specs (Pass 4). Has no visible effect unless
                highlight_edge_specs is also given -- there is nothing to
                colour otherwise.
            edge_highlight_width (float): Stroke width for edges named in
                highlight_edge_specs (Pass 4). Same caveat as
                edge_highlight_color: a no-op without highlight_edge_specs.
            draw_obj_labels (bool): Whether to draw each object's
                display-name label (glass/lens/point/line objects). When
                False, the label is suppressed regardless of whether the
                object has a get_display_name() (default: True, matching
                draw_scene's default -- unchanged rendering unless overridden).
            draw_edge_labels (bool): Whether to draw per-edge functional
                labels on glass objects (default: True, matching
                draw_scene's default).
            draw_edge_overlays (bool): Whether to add invisible edge overlay
                elements for glass objects -- draw_glass_edge_overlays draws
                them with stroke='none' by design (they exist for editor
                click-targets/metadata, not to be seen), so toggling this has
                **no visible effect either way**; that is expected, not a bug
                (default: True, matching draw_scene's default).
            object_label_font_size (str): CSS font size for scene-object
                display-name labels (default: '8px', matching each draw_*
                method's own default).
            edge_label_font_size (str): CSS font size for glass edge
                functional labels, only drawn when draw_edge_labels=True
                (default: '6px', matching draw_glass_edge_labels' own
                default). A scene with many small/named objects (e.g. a
                LinearSensor's internal blockers) can turn into unreadable
                label clutter at the defaults above -- set draw_obj_labels/
                draw_edge_labels to False, or shrink the font sizes, the same
                way draw_scene's own callers already do.
            edge_stroke_width (float): Line width in pixels for scene object
                boundaries -- glass polygon edges (draw_glass_path) and
                line-based objects like blockers/detectors (draw_line_segment)
                (default: 2.0, matching both methods' own defaults --
                unchanged rendering unless overridden). Does not apply to
                draw_lens, which hardcodes its own line width (matching
                draw_scene's identical scope).
            **ray_kwargs: Additional keyword arguments passed to
                draw_ray_with_scene_settings (e.g. base_color) when
                highlight_ray_uuids is None -- matching draw_scene's
                **ray_kwargs passthrough for that same case.

        Returns:
            bool: True on success.
        """
        from ..analysis.ray_geometry_queries import get_object_by_name, _resolve_edge

        highlight_set = set(highlight_ray_uuids) if highlight_ray_uuids else set()
        highlight_names = set(highlight_glass_names) if highlight_glass_names else set()

        # --- Pass 1: Draw all objects ---
        if draw_objects:
            for obj in scene.objs:
                if hasattr(obj, 'path') and hasattr(obj.path, '__len__') and len(obj.path) >= 3:
                    name = getattr(obj, 'name', None)
                    is_highlighted = name in highlight_names if name else False
                    fill_opacity = 0.5 if is_highlighted else 0.2
                    display_name = (getattr(obj, 'get_display_name', lambda: None)()
                                    if draw_obj_labels else None)
                    self.draw_glass_path(obj.path, fill_opacity=fill_opacity, glass_obj=obj,
                                        stroke_width=edge_stroke_width,
                                        label=display_name, label_font_size=object_label_font_size)
                    if draw_edge_labels:
                        self.draw_glass_edge_labels(obj, font_size=edge_label_font_size)
                    if draw_edge_overlays:
                        self.draw_glass_edge_overlays(obj)
                elif hasattr(obj, 'focalLength') and hasattr(obj, 'p1'):
                    display_name = (getattr(obj, 'get_display_name', lambda: None)()
                                    if draw_obj_labels else None)
                    self.draw_lens(obj.p1, obj.p2, obj.focalLength,
                                   label=display_name, scene_obj=obj,
                                   label_font_size=object_label_font_size)
                elif hasattr(obj, 'x') and hasattr(obj, 'y') and not hasattr(obj, 'p2'):
                    display_name = (getattr(obj, 'get_display_name', lambda: None)()
                                    if draw_obj_labels else None)
                    self.draw_point({'x': obj.x, 'y': obj.y},
                                    color='orange', radius=4,
                                    label=display_name, scene_obj=obj,
                                    label_font_size=object_label_font_size)
                elif hasattr(obj, 'p1') and hasattr(obj, 'p2'):
                    display_name = (getattr(obj, 'get_display_name', lambda: None)()
                                    if draw_obj_labels else None)
                    self.draw_line_segment(obj.p1, obj.p2,
                                           label=display_name, scene_obj=obj,
                                           label_font_size=object_label_font_size,
                                           stroke_width=edge_stroke_width)

        if draw_rays and segments:
            # Subsampling applies only to the non-highlighted population --
            # an explicitly highlighted ray must never be dropped by it.
            dim_pool = segments
            if ray_subsample > 1 and len(segments) > 1:
                rng = random.Random(ray_subsample_seed)
                k = max(1, len(segments) // ray_subsample)
                dim_pool = rng.sample(list(segments), k)

            # --- Pass 2: Draw non-highlighted rays (dimmed / subsampled) ---
            for seg in dim_pool:
                seg_uuid = getattr(seg, 'uuid', None)
                if highlight_set and seg_uuid and seg_uuid in highlight_set:
                    continue  # Skip — will be drawn in highlight pass
                if highlight_set:
                    # Dim non-highlighted rays
                    self.draw_ray_segment(seg, color=base_ray_color,
                                          opacity=dim_opacity, stroke_width=base_stroke_width,
                                          dasharray=base_dasharray)
                else:
                    # No highlights requested — draw all rays normally
                    self.draw_ray_with_scene_settings(seg, scene,
                                                      stroke_width=ray_stroke_width,
                                                      **ray_kwargs)

            # --- Pass 3: Draw highlighted rays on top (always the full,
            # unsampled set -- every explicitly named ray must appear) ---
            if highlight_set:
                hl_layer = self._ensure_highlight_layer()
                # Temporarily swap layer_rays to the highlight layer
                orig_layer = self.layer_rays
                self.layer_rays = hl_layer
                for seg in segments:
                    seg_uuid = getattr(seg, 'uuid', None)
                    if seg_uuid and seg_uuid in highlight_set:
                        self.draw_ray_segment(seg, color=highlight_color,
                                              opacity=1.0,
                                              stroke_width=highlight_stroke_width,
                                              dasharray=highlight_dasharray)
                self.layer_rays = orig_layer

        # --- Pass 4: Draw highlighted edges on top ---
        if highlight_edge_specs:
            hl_layer = self._ensure_highlight_layer()
            for glass_name, edge_label in highlight_edge_specs:
                glass = get_object_by_name(scene, glass_name)
                edge = _resolve_edge(glass, edge_label)
                line = self.dwg.line(
                    start=(edge.p1.x, edge.p1.y),
                    end=(edge.p2.x, edge.p2.y),
                    stroke=edge_highlight_color,
                    stroke_width=edge_highlight_width,
                    stroke_opacity=0.9,
                )
                line['inkscape:label'] = f'highlight: {glass_name} {edge_label}'
                line['class'] = 'highlight-edge'
                hl_layer.add(line)

        return True

    def _calculate_arc_center(self, pt1, pt2, pt3):
        """
        Calculate center of circle passing through three points.

        This matches the algorithm used in glass.py for arc interpretation.

        Args:
            pt1 (dict): First point with 'x', 'y' keys
            pt2 (dict): Second point with 'x', 'y' keys (on the arc)
            pt3 (dict): Third point with 'x', 'y' keys

        Returns:
            dict or None: Center point {'x': x, 'y': y} or None if collinear
        """
        # Perpendicular bisector of pt1→pt2
        mid_12_x = (pt1['x'] + pt2['x']) / 2
        mid_12_y = (pt1['y'] + pt2['y']) / 2
        dx_12 = pt2['x'] - pt1['x']
        dy_12 = pt2['y'] - pt1['y']

        # Perpendicular bisector of pt3→pt2
        mid_32_x = (pt3['x'] + pt2['x']) / 2
        mid_32_y = (pt3['y'] + pt2['y']) / 2
        dx_32 = pt2['x'] - pt3['x']
        dy_32 = pt2['y'] - pt3['y']

        # Intersection of perpendicular bisectors
        # Line 1: (mid_12_x, mid_12_y) + t1 * (-dy_12, dx_12)
        # Line 2: (mid_32_x, mid_32_y) + t2 * (-dy_32, dx_32)

        det = -dy_12 * dx_32 - (-dy_32) * dx_12
        if abs(det) < 1e-10:
            # Collinear points - no arc
            return None

        diff_x = mid_32_x - mid_12_x
        diff_y = mid_32_y - mid_12_y
        t1 = (diff_x * dx_32 - diff_y * (-dy_32)) / det

        center_x = mid_12_x + t1 * (-dy_12)
        center_y = mid_12_y + t1 * dx_12

        return {'x': center_x, 'y': center_y}

    def _clip_to_viewbox(self, p1, p2):
        """
        Clip a line segment to the viewbox boundaries.

        Uses Liang-Barsky algorithm to clip the line segment p1-p2 to the viewbox.

        Args:
            p1 (dict): Start point in Y-up coordinates
            p2 (dict): End point in Y-up coordinates

        Returns:
            tuple: (clipped_p1, clipped_p2) or (None, None) if completely outside
        """
        # Use user_viewbox which is in Y-up coordinates
        min_x, min_y, width, height = self.user_viewbox
        max_x = min_x + width
        max_y = min_y + height

        x1, y1 = p1['x'], p1['y']
        x2, y2 = p2['x'], p2['y']
        dx = x2 - x1
        dy = y2 - y1

        # Liang-Barsky algorithm
        t0, t1 = 0.0, 1.0

        # Check all four edges
        for edge in range(4):
            if edge == 0:   # Left edge
                p, q = -dx, x1 - min_x
            elif edge == 1: # Right edge
                p, q = dx, max_x - x1
            elif edge == 2: # Bottom edge
                p, q = -dy, y1 - min_y
            else:           # Top edge
                p, q = dy, max_y - y1

            if abs(p) < 1e-10:
                # Line is parallel to this edge
                if q < 0:
                    # Line is completely outside
                    return None, None
            else:
                t = q / p
                if p < 0:
                    # Entering the viewbox
                    t0 = max(t0, t)
                else:
                    # Leaving the viewbox
                    t1 = min(t1, t)

        if t0 > t1:
            # Line is completely outside
            return None, None

        # Calculate clipped points
        clipped_p1 = {'x': x1 + t0 * dx, 'y': y1 + t0 * dy}
        clipped_p2 = {'x': x1 + t1 * dx, 'y': y1 + t1 * dy}

        return clipped_p1, clipped_p2

    def _extend_to_edge(self, p1, p2):
        """
        Extend a ray from p1 through p2 to the edge of the viewbox.

        Args:
            p1 (dict): Start point in Y-up coordinates
            p2 (dict): Direction point in Y-up coordinates

        Returns:
            dict: Point at the edge of viewbox
        """
        dx = p2['x'] - p1['x']
        dy = p2['y'] - p1['y']

        if abs(dx) < 1e-10 and abs(dy) < 1e-10:
            return p2

        # Find intersection with viewbox edges (use user_viewbox for Y-up coordinates)
        min_x, min_y, width, height = self.user_viewbox
        max_x = min_x + width
        max_y = min_y + height

        # Calculate t values for each edge
        t_values = []

        if abs(dx) > 1e-10:
            t_left = (min_x - p1['x']) / dx
            t_right = (max_x - p1['x']) / dx
            if t_left > 0:
                t_values.append(t_left)
            if t_right > 0:
                t_values.append(t_right)

        if abs(dy) > 1e-10:
            t_top = (min_y - p1['y']) / dy
            t_bottom = (max_y - p1['y']) / dy
            if t_top > 0:
                t_values.append(t_top)
            if t_bottom > 0:
                t_values.append(t_bottom)

        if not t_values:
            return p2

        t = min(t_values)  # Use minimum t to get first edge intersection
        return {'x': p1['x'] + dx * t, 'y': p1['y'] + dy * t}

    def save(self, filename:str=None):
        """
        Save the SVG to a file.

        Args:
            filename (str): Output filename (e.g., 'output.svg')
        """
        if filename is None:
            filename = "output.svg"
        self.dwg.saveas(filename)

    def to_string(self):
        """
        Get the SVG as a string.

        Returns:
            str: SVG content as XML string
        """
        return self.dwg.tostring()


# Example usage and testing
if __name__ == "__main__":
    import os

    print("Testing SVGRenderer class...\n")

    # Test 1: Basic renderer creation
    print("Test 1: Create basic renderer")
    renderer = SVGRenderer(width=400, height=300)
    print(f"  Canvas size: {renderer.width}x{renderer.height}")
    print(f"  Viewbox: {renderer.viewbox}")
    print(f"  Layers created: objects, rays, labels")

    # Test 2: Custom viewbox
    print("\nTest 2: Custom viewbox")
    renderer2 = SVGRenderer(width=800, height=600, viewbox=(-100, -100, 400, 400))
    print(f"  Canvas size: {renderer2.width}x{renderer2.height}")
    print(f"  Custom viewbox: {renderer2.viewbox}")

    # Test 3: Draw points
    print("\nTest 3: Draw points")
    renderer.draw_point({'x': 50, 'y': 50}, color='red', radius=5, label='Point A')
    renderer.draw_point({'x': 150, 'y': 100}, color='blue', radius=3, label='Point B')
    renderer.draw_point({'x': 250, 'y': 150}, color='green', radius=4)
    print("  Drew 3 points: red (labeled), blue (labeled), green (unlabeled)")

    # Test 4: Draw line segments
    print("\nTest 4: Draw line segments")
    renderer.draw_line_segment(
        {'x': 50, 'y': 200},
        {'x': 250, 'y': 200},
        color='black',
        stroke_width=2,
        label='Screen'
    )
    renderer.draw_line_segment(
        {'x': 150, 'y': 50},
        {'x': 150, 'y': 250},
        color='gray',
        stroke_width=1
    )
    print("  Drew 2 line segments: black (labeled), gray (unlabeled)")

    # Test 5: Draw lenses
    print("\nTest 5: Draw lenses")
    # Converging lens
    renderer.draw_lens(
        {'x': 100, 'y': 50},
        {'x': 100, 'y': 150},
        focal_length=50,
        color='blue',
        label='Converging'
    )
    # Diverging lens
    renderer.draw_lens(
        {'x': 200, 'y': 50},
        {'x': 200, 'y': 150},
        focal_length=-50,
        color='purple',
        label='Diverging'
    )
    print("  Drew converging lens (f=50) and diverging lens (f=-50)")

    # Test 6: Draw ray segments
    print("\nTest 6: Draw ray segments")
    # Mock Ray class for testing
    class MockRay:
        _counter = 0
        def __init__(self, p1, p2, brightness_s=1.0, brightness_p=0.0, wavelength=None, gap=False):
            MockRay._counter += 1
            self.p1 = p1
            self.p2 = p2
            self.brightness_s = brightness_s
            self.brightness_p = brightness_p
            self.wavelength = wavelength
            self.gap = gap
            self.total_brightness = brightness_s + brightness_p
            self.uuid = f'mock-{MockRay._counter:04d}'
            self.interaction_type = 'source'
            self.parent_uuid = None

    # Normal ray
    ray1 = MockRay({'x': 10, 'y': 100}, {'x': 90, 'y': 100})
    renderer.draw_ray_segment(ray1, color='red', opacity=1.0, stroke_width=2)

    # Ray with wavelength
    ray2 = MockRay({'x': 10, 'y': 120}, {'x': 90, 'y': 120}, wavelength=650)
    renderer.draw_ray_segment(ray2, color='red', opacity=0.8, stroke_width=2)

    # Faint ray
    ray3 = MockRay({'x': 10, 'y': 140}, {'x': 90, 'y': 140}, brightness_s=0.3, brightness_p=0.2)
    renderer.draw_ray_segment(ray3, color='red', opacity=0.5, stroke_width=1)

    # Gap ray (should not be drawn)
    ray4 = MockRay({'x': 10, 'y': 160}, {'x': 90, 'y': 160}, gap=True)
    renderer.draw_ray_segment(ray4, color='red', opacity=1.0, stroke_width=2)

    ray5 = MockRay({'x': 0, 'y': 100}, {'x': 90, 'y': 110})
    renderer.draw_ray_segment(ray5, color='blue', opacity=1.0, stroke_width=2)

    print("  Drew 4 rays: normal, wavelength-specific, faint, gap (gap not drawn)")

    # Test 7: Invalid ray handling (NaN, Inf)
    print("\nTest 7: Invalid ray handling")
    ray_nan = MockRay({'x': float('nan'), 'y': 100}, {'x': 90, 'y': 100})
    ray_inf = MockRay({'x': 10, 'y': float('inf')}, {'x': 90, 'y': 100})
    renderer.draw_ray_segment(ray_nan, color='red')
    renderer.draw_ray_segment(ray_inf, color='red')
    print("  Attempted to draw NaN and Inf rays (skipped automatically)")
    
    # Test 8: Save to file
    print("\nTest 8: Save SVG to file")
    temp_dir = os.path.join(os.path.dirname(__file__), '..', 'developer_tests', 'temp_svg_tests')
    os.makedirs(temp_dir, exist_ok=True)
    output_file = os.path.join(temp_dir, 'test_renderer_output.svg')
    renderer.save(output_file)
    file_exists = os.path.exists(output_file)
    file_size = os.path.getsize(output_file) if file_exists else 0
    print(f"  Saved to: {output_file}")
    print(f"  File exists: {file_exists}")
    print(f"  File size: {file_size} bytes")

    # Test 9: SVG as string
    print("\nTest 9: Get SVG as string")
    svg_string = renderer.to_string()
    print(f"  SVG string length: {len(svg_string)} characters")
    objects_present = 'id="layer-objects"' in svg_string
    rays_present = 'id="layer-rays"' in svg_string
    labels_present = 'id="layer-labels"' in svg_string
    print(f"  Contains 'layer-objects' layer: {objects_present}")
    print(f"  Contains 'layer-rays' layer: {rays_present}")
    print(f"  Contains 'layer-labels' layer: {labels_present}")

    # Test 10: Complete example scene
    print("\nTest 10: Create a complete example scene")
    scene_renderer = SVGRenderer(width=600, height=400, viewbox=(0, 0, 300, 200))

    # Add a point source
    scene_renderer.draw_point({'x': 50, 'y': 100}, color='orange', radius=6, label='Source')

    # Add a lens
    scene_renderer.draw_lens(
        {'x': 150, 'y': 50},
        {'x': 150, 'y': 150},
        focal_length=50,
        color='blue',
        label='Lens (f=50)'
    )

    # Add a screen
    scene_renderer.draw_line_segment(
        {'x': 250, 'y': 30},
        {'x': 250, 'y': 170},
        color='black',
        stroke_width=3,
        label='Screen'
    )

    # Add some rays
    rays = [
        MockRay({'x': 50, 'y': 100}, {'x': 150, 'y': 80}),
        MockRay({'x': 150, 'y': 80}, {'x': 250, 'y': 100}),
        MockRay({'x': 50, 'y': 100}, {'x': 150, 'y': 100}),
        MockRay({'x': 150, 'y': 100}, {'x': 250, 'y': 100}),
        MockRay({'x': 50, 'y': 100}, {'x': 150, 'y': 120}),
        MockRay({'x': 150, 'y': 120}, {'x': 250, 'y': 100}),
    ]

    for ray in rays:
        scene_renderer.draw_ray_segment(ray, color='red', opacity=0.7, stroke_width=1.5)

    scene_output = os.path.join(temp_dir, 'test_complete_scene.svg')
    scene_renderer.save(scene_output)
    print(f"  Complete scene saved to: {scene_output}")
    print(f"  Scene contains: 1 source, 1 lens, 1 screen, {len(rays)} rays")

    # Test 11: Ray with arrows
    print("\nTest 11: Draw rays with direction arrows")
    arrow_renderer = SVGRenderer(width=400, height=200, viewbox=(0, 0, 200, 100))

    ray_arrow1 = MockRay({'x': 10, 'y': 50}, {'x': 90, 'y': 50})
    ray_arrow2 = MockRay({'x': 10, 'y': 70}, {'x': 90, 'y': 70})
    ray_arrow3 = MockRay({'x': 110, 'y': 30}, {'x': 190, 'y': 80})  # Diagonal

    arrow_renderer.draw_ray_segment(ray_arrow1, color='red', show_arrow=False)
    arrow_renderer.draw_ray_segment(ray_arrow2, color='blue', show_arrow=True)
    arrow_renderer.draw_ray_segment(ray_arrow3, color='green', show_arrow=True, arrow_size=8)

    arrow_output = os.path.join(temp_dir, 'test_ray_arrows.svg')
    arrow_renderer.save(arrow_output)
    print(f"  Saved ray arrows test to: {arrow_output}")
    print("  - Red ray without arrow")
    print("  - Blue ray with auto-sized arrow")
    print("  - Green diagonal ray with custom arrow size")

    # Test 12: Color mode functions
    print("\nTest 12: Test color mode functions")

    # Test wavelength_to_rgb
    test_wavelengths = [400, 450, 500, 550, 600, 650, 700]
    print("  Wavelength to RGB:")
    for wl in test_wavelengths:
        rgb = wavelength_to_rgb(wl)
        print(f"    {wl}nm -> RGB{rgb}")

    # Test brightness_to_opacity with different modes
    print("  Brightness to opacity (brightness=0.5):")
    for mode in ['default', 'linear', 'linearRGB', 'reinhard', 'colorizedIntensity']:
        opacity = brightness_to_opacity(0.5, mode)
        print(f"    {mode}: {opacity:.3f}")

    # Test brightness_to_color for colorizedIntensity
    print("  Brightness to color (colorizedIntensity mode):")
    for brightness in [0.001, 0.01, 0.1, 1.0, 10.0]:
        color = brightness_to_color(brightness, 'colorizedIntensity')
        print(f"    brightness={brightness}: {color}")

    # Test 13: Draw rays with scene settings
    print("\nTest 13: Draw rays with scene settings")

    # Create a mock scene class for testing
    class MockScene:
        def __init__(self):
            self.color_mode = 'default'
            self.show_ray_arrows = False
            self.simulate_colors = False

    settings_renderer = SVGRenderer(width=400, height=300, viewbox=(0, 0, 200, 150))
    mock_scene = MockScene()

    # Test different scene configurations
    ray1 = MockRay({'x': 10, 'y': 30}, {'x': 90, 'y': 30}, brightness_s=1.0)
    ray2 = MockRay({'x': 10, 'y': 60}, {'x': 90, 'y': 60}, brightness_s=0.5)
    ray3 = MockRay({'x': 10, 'y': 90}, {'x': 90, 'y': 90}, brightness_s=0.2)

    # Default mode
    mock_scene.color_mode = 'default'
    mock_scene.show_ray_arrows = False
    settings_renderer.draw_ray_with_scene_settings(ray1, mock_scene)
    settings_renderer.draw_ray_with_scene_settings(ray2, mock_scene)
    settings_renderer.draw_ray_with_scene_settings(ray3, mock_scene)
    print("  Drew 3 rays with default color mode (varying brightness -> varying opacity)")

    # With arrows
    ray4 = MockRay({'x': 110, 'y': 30}, {'x': 190, 'y': 30}, brightness_s=1.0)
    ray5 = MockRay({'x': 110, 'y': 60}, {'x': 190, 'y': 60}, brightness_s=0.5)
    mock_scene.show_ray_arrows = True
    settings_renderer.draw_ray_with_scene_settings(ray4, mock_scene, base_color=(0, 0, 255))
    settings_renderer.draw_ray_with_scene_settings(ray5, mock_scene, base_color=(0, 0, 255))
    print("  Drew 2 blue rays with arrows enabled")

    # With wavelength simulation
    ray6 = MockRay({'x': 110, 'y': 100}, {'x': 190, 'y': 100}, wavelength=650)
    ray7 = MockRay({'x': 110, 'y': 120}, {'x': 190, 'y': 120}, wavelength=500)
    mock_scene.simulate_colors = True
    mock_scene.show_ray_arrows = False
    settings_renderer.draw_ray_with_scene_settings(ray6, mock_scene)
    settings_renderer.draw_ray_with_scene_settings(ray7, mock_scene)
    print("  Drew 2 rays with wavelength simulation (650nm=red, 500nm=green)")

    settings_output = os.path.join(temp_dir, 'test_scene_settings.svg')
    settings_renderer.save(settings_output)
    print(f"  Saved scene settings test to: {settings_output}")

    print("\nSVGRenderer test completed successfully!")
    print(f"\nTest files created in: {temp_dir}")
    print(f"  - test_renderer_output.svg")
    print(f"  - test_complete_scene.svg")
    print(f"  - test_ray_arrows.svg")
    print(f"  - test_scene_settings.svg")
