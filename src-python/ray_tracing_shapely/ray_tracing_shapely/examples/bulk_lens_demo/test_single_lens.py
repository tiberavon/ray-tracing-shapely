"""
Python-specific module: test single lens
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

Minimal test: Single lens with sweep=0,0

This script creates a minimal SVG with just the lens shape using the exact
coordinates from the bulk_lens_collimation_demo simulation.
"""

import svgwrite

def create_single_lens_test():
    """Create SVG with just one lens using actual simulation coordinates."""

    # Create SVG with same viewbox as main simulation
    dwg = svgwrite.Drawing('single_lens_test.svg', size=('800px', '600px'),
                          viewBox='-50 -500 400 400')

    # Add a simple grid for reference
    grid = dwg.add(dwg.g(id='grid', stroke='lightgray', stroke_width=0.5))
    for x in range(0, 350, 50):
        grid.add(dwg.line((x, -500), (x, -100)))
    for y in range(-500, -100, 50):
        grid.add(dwg.line((0, y), (350, y)))

    # Actual coordinates from simulation output
    # These are the 6 points from lens.path after Y-flip for SVG
    points = [
        (121.79, -200.00),  # p0 - top-right
        (78.21, -200.00),   # p1 - top-left
        (105.00, -300.00),  # p2 - arc center right
        (78.21, -400.00),   # p3 - bottom-left
        (121.79, -400.00),  # p4 - bottom-right
        (95.00, -300.00),   # p5 - arc center left
    ]

    # Mark all points for debugging
    for i, (x, y) in enumerate(points):
        dwg.add(dwg.circle((x, y), r=2, fill='red'))
        dwg.add(dwg.text(f'p{i}', insert=(x + 5, y - 5),
                        fill='red', font_size='10px'))

    # Draw the reference circles showing the arc radii
    radius = 103.53

    # Right arc center (p2)
    dwg.add(dwg.circle((points[2][0], points[2][1]), r=radius,
                      fill='none', stroke='lightblue', stroke_width=0.5,
                      stroke_dasharray='5,5'))
    dwg.add(dwg.text('right arc', insert=(points[2][0] + 5, points[2][1]),
                    fill='lightblue', font_size='10px'))

    # Left arc center (p5)
    dwg.add(dwg.circle((points[5][0], points[5][1]), r=radius,
                      fill='none', stroke='lightgreen', stroke_width=0.5,
                      stroke_dasharray='5,5'))
    dwg.add(dwg.text('left arc', insert=(points[5][0] - 50, points[5][1]),
                    fill='lightgreen', font_size='10px'))

    # Create the lens path with sweep=0,0
    # Path: Start at p0 (top-right) -> line to p1 (top-left) ->
    #       arc to p3 (bottom-left) -> line to p4 (bottom-right) ->
    #       arc to p0 (close)

    p0_x, p0_y = points[0]
    p1_x, p1_y = points[1]
    p3_x, p3_y = points[3]
    p4_x, p4_y = points[4]

    path_string = (
        f"M {p0_x},{p0_y} "                              # Move to top-right
        f"L {p1_x},{p1_y} "                              # Line to top-left
        f"A {radius},{radius} 0 0 0 {p3_x},{p3_y} "     # Arc to bottom-left (sweep=0)
        f"L {p4_x},{p4_y} "                              # Line to bottom-right
        f"A {radius},{radius} 0 0 0 {p0_x},{p0_y} "     # Arc to top-right (sweep=0)
        f"Z"                                             # Close path
    )

    print(f"Lens path string:\n{path_string}\n")

    # Draw the lens
    lens_path = dwg.path(
        d=path_string,
        fill='cyan',
        fill_opacity=0.6,
        stroke='navy',
        stroke_width=3
    )
    dwg.add(lens_path)

    # Add label
    dwg.add(dwg.text('Lens (sweep=0,0)',
                    insert=(100, -300),
                    fill='darkblue',
                    font_size='14px',
                    font_weight='bold',
                    text_anchor='middle'))

    # Add axis labels
    dwg.add(dwg.text('x=100', insert=(100, -480),
                    fill='black', font_size='10px', text_anchor='middle'))
    dwg.add(dwg.text('y=-200', insert=(10, -195),
                    fill='black', font_size='10px'))
    dwg.add(dwg.text('y=-400', insert=(10, -395),
                    fill='black', font_size='10px'))

    # Add dimensions
    dwg.add(dwg.line((78.21, -190), (121.79, -190),
                    stroke='orange', stroke_width=1))
    lens_width = 121.79 - 78.21
    dwg.add(dwg.text(f'width={lens_width:.1f}',
                    insert=(100, -175),
                    fill='orange', font_size='10px', text_anchor='middle'))

    dwg.save()
    print("Single lens test saved to: single_lens_test.svg")
    print(f"Lens width: {lens_width:.2f}")
    print("Lens height: 200.00")
    print(f"Arc radius: {radius:.2f}")


if __name__ == '__main__':
    print("Single Lens Test")
    print("=" * 60)
    create_single_lens_test()
    print("\nOpen single_lens_test.svg in Inkscape to verify the lens renders correctly.")
