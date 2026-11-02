"""
Python-specific module: test corrected lens
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

Corrected Lens Rendering Test

This script uses the correct path interpretation for the spherical lens.
"""

import svgwrite

def create_corrected_lens():
    """Create SVG with correctly interpreted lens path."""

    dwg = svgwrite.Drawing('corrected_lens_test.svg', size=('800px', '600px'),
                          viewBox='-50 -500 400 400')

    # Grid
    grid = dwg.add(dwg.g(id='grid', stroke='lightgray', stroke_width=0.5))
    for x in range(0, 350, 50):
        grid.add(dwg.line((x, -500), (x, -100)))
    for y in range(-500, -100, 50):
        grid.add(dwg.line((0, y), (350, y)))

    # Actual coordinates from simulation (Y already flipped for SVG)
    points = [
        (121.79, -200.00),  # p0 - top-left (actually top-right in original coords)
        (78.21, -200.00),   # p1 - top-right (actually top-left in original coords)
        (105.00, -300.00),  # p2 - arc center right (actually left in original)
        (78.21, -400.00),   # p3 - bottom-right (actually bottom-left in original)
        (121.79, -400.00),  # p4 - bottom-left (actually bottom-right in original)
        (95.00, -300.00),   # p5 - arc center left (actually right in original)
    ]

    # Mark all points
    labels = ['p0 (TL)', 'p1 (TR)', 'p2 (arc R)', 'p3 (BR)', 'p4 (BL)', 'p5 (arc L)']
    for i, ((x, y), label) in enumerate(zip(points, labels)):
        dwg.add(dwg.circle((x, y), r=2, fill='red'))
        dwg.add(dwg.text(label, insert=(x + 5, y - 5),
                        fill='red', font_size='9px'))

    radius = 103.53

    # Draw reference circles
    dwg.add(dwg.circle((points[2][0], points[2][1]), r=radius,
                      fill='none', stroke='lightblue', stroke_width=0.5,
                      stroke_dasharray='5,5'))
    dwg.add(dwg.circle((points[5][0], points[5][1]), r=radius,
                      fill='none', stroke='lightgreen', stroke_width=0.5,
                      stroke_dasharray='5,5'))

    # CORRECT path interpretation based on spherical_lens.py lines 299-306:
    # Start at path[0] (top-left)
    # Arc from path[0] to path[4] using path[5] as center (left surface)
    # Line from path[4] to path[3] (bottom edge)
    # Arc from path[3] to path[1] using path[2] as center (right surface)
    # Line from path[1] to path[0] (top edge)

    p0_x, p0_y = points[0]
    p1_x, p1_y = points[1]
    p3_x, p3_y = points[3]
    p4_x, p4_y = points[4]

    path_string = (
        f"M {p0_x},{p0_y} "                              # Move to top-left (p0)
        f"A {radius},{radius} 0 0 0 {p4_x},{p4_y} "     # Arc to bottom-left (p4) via p5 center
        f"L {p3_x},{p3_y} "                              # Line to bottom-right (p3)
        f"A {radius},{radius} 0 0 0 {p1_x},{p1_y} "     # Arc to top-right (p1) via p2 center
        f"L {p0_x},{p0_y} "                              # Line back to top-left (p0)
        f"Z"                                             # Close path
    )

    print(f"Corrected lens path:\n{path_string}\n")

    # Draw the lens
    lens_path = dwg.path(
        d=path_string,
        fill='cyan',
        fill_opacity=0.6,
        stroke='navy',
        stroke_width=3
    )
    dwg.add(lens_path)

    # Add labels outside the lens
    center_x = (p0_x + p1_x) / 2
    center_y = (p0_y + p4_y) / 2

    # Calculate and show dimensions
    width = abs(p1_x - p0_x)
    height = abs(p4_y - p0_y)

    # Place title above the lens (Y decreases going up in SVG coords)
    dwg.add(dwg.text('Corrected Lens',
                    insert=(center_x, p0_y - 25),
                    fill='darkblue',
                    font_size='14px',
                    font_weight='bold',
                    text_anchor='middle'))

    # Place dimensions below the lens (Y increases going down in SVG coords)
    dwg.add(dwg.text(f'Width at edge: {width:.1f}',
                    insert=(center_x, p4_y + 25),
                    fill='orange', font_size='10px', text_anchor='middle'))
    dwg.add(dwg.text(f'Height: {height:.1f}',
                    insert=(center_x, p4_y + 40),
                    fill='orange', font_size='10px', text_anchor='middle'))

    dwg.save()
    print(f"Corrected lens test saved to: corrected_lens_test.svg")
    print(f"Width at edges: {width:.2f}")
    print(f"Height: {height:.2f}")
    print(f"Arc radius: {radius:.2f}")
    print(f"\nPath structure:")
    print(f"  p0 ({p0_x:.2f}, {p0_y:.2f}) - top-left")
    print(f"  --> arc via p5 (left surface) -->")
    print(f"  p4 ({p4_x:.2f}, {p4_y:.2f}) - bottom-left")
    print(f"  --> line -->")
    print(f"  p3 ({p3_x:.2f}, {p3_y:.2f}) - bottom-right")
    print(f"  --> arc via p2 (right surface) -->")
    print(f"  p1 ({p1_x:.2f}, {p1_y:.2f}) - top-right")
    print(f"  --> line back to p0")


if __name__ == '__main__':
    print("Corrected Lens Rendering Test")
    print("=" * 60)
    create_corrected_lens()
    print("\nOpen corrected_lens_test.svg to see the result.")
