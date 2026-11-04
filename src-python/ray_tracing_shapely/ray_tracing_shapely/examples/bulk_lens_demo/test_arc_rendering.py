"""
Python-specific module: test arc rendering
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

Test SVG Arc Rendering

This script creates various arc tests to understand why the lens arcs aren't rendering.
We'll test different arc parameters and approaches.
"""

import svgwrite

def test_basic_arcs():
    """Create a test SVG with various arc configurations."""

    dwg = svgwrite.Drawing('arc_test.svg', size=('800px', '600px'), viewBox='-50 -500 400 400')

    # Add a background grid for reference
    grid = dwg.add(dwg.g(id='grid', stroke='lightgray', stroke_width=0.5))
    for x in range(-50, 350, 50):
        grid.add(dwg.line((x, -500), (x, -100)))
    for y in range(-500, -100, 50):
        grid.add(dwg.line((-50, y), (350, y)))

    # Test 1: Simple arc with different sweep flags
    print("Test 1: Basic arcs with different sweep flags")

    # Arc sweeping clockwise (sweep=1)
    path1 = dwg.path(
        d="M 50,-200 A 50,50 0 0 1 100,-250",
        fill='none',
        stroke='red',
        stroke_width=2
    )
    dwg.add(path1)
    dwg.add(dwg.text('Arc sweep=1', insert=(75, -180), fill='red', font_size='12px'))

    # Arc sweeping counter-clockwise (sweep=0)
    path2 = dwg.path(
        d="M 150,-200 A 50,50 0 0 0 200,-250",
        fill='none',
        stroke='blue',
        stroke_width=2
    )
    dwg.add(path2)
    dwg.add(dwg.text('Arc sweep=0', insert=(175, -180), fill='blue', font_size='12px'))

    # Test 2: Lens-like shape using arcs (biconvex)
    print("Test 2: Biconvex lens shape")

    # Method 1: Using the exact coordinates from our lens
    lens_x_center = 100
    lens_y_top = -200
    lens_y_bottom = -400
    lens_half_width = 21.79
    arc_radius = 103.53

    # Left edge
    x_left = lens_x_center - lens_half_width
    x_right = lens_x_center + lens_half_width

    lens_path1 = dwg.path(
        d=f"M {x_right},{lens_y_top} L {x_left},{lens_y_top} A {arc_radius},{arc_radius} 0 0 0 {x_left},{lens_y_bottom} L {x_right},{lens_y_bottom} A {arc_radius},{arc_radius} 0 0 0 {x_right},{lens_y_top} Z",
        fill='cyan',
        fill_opacity=0.3,
        stroke='navy',
        stroke_width=2
    )
    dwg.add(lens_path1)
    dwg.add(dwg.text('Lens (sweep=0,0)', insert=(100, -280), fill='navy', font_size='12px', text_anchor='middle'))

    # Test 3: Same lens with sweep=1,1
    print("Test 3: Same lens with sweep=1,1")

    lens_path2 = dwg.path(
        d=f"M {x_right + 150},{lens_y_top} L {x_left + 150},{lens_y_top} A {arc_radius},{arc_radius} 0 0 1 {x_left + 150},{lens_y_bottom} L {x_right + 150},{lens_y_bottom} A {arc_radius},{arc_radius} 0 0 1 {x_right + 150},{lens_y_top} Z",
        fill='lime',
        fill_opacity=0.3,
        stroke='green',
        stroke_width=2
    )
    dwg.add(lens_path2)
    dwg.add(dwg.text('Lens (sweep=1,1)', insert=(250, -280), fill='green', font_size='12px', text_anchor='middle'))

    # Test 4: Complete circles for reference
    print("Test 4: Reference circles")

    dwg.add(dwg.circle((50, -450), r=30, fill='none', stroke='orange', stroke_width=1))
    dwg.add(dwg.text('Circle', insert=(50, -410), fill='orange', font_size='10px', text_anchor='middle'))

    # Test 5: Simple rectangle to verify rendering works
    print("Test 5: Reference rectangle")

    rect = dwg.rect((150, -470), (60, 40), fill='pink', fill_opacity=0.5, stroke='purple', stroke_width=2)
    dwg.add(rect)
    dwg.add(dwg.text('Rectangle', insert=(180, -410), fill='purple', font_size='10px', text_anchor='middle'))

    # Test 6: Try drawing lens using smaller arc radius
    print("Test 6: Lens with smaller arc radius")

    small_radius = 50
    lens_path3 = dwg.path(
        d=f"M {x_right},{lens_y_top - 100} L {x_left},{lens_y_top - 100} A {small_radius},{small_radius} 0 0 0 {x_left},{lens_y_bottom - 100} L {x_right},{lens_y_bottom - 100} A {small_radius},{small_radius} 0 0 0 {x_right},{lens_y_top - 100} Z",
        fill='yellow',
        fill_opacity=0.5,
        stroke='red',
        stroke_width=3
    )
    dwg.add(lens_path3)
    dwg.add(dwg.text('Small radius', insert=(100, -480), fill='red', font_size='12px', text_anchor='middle'))

    # Test 7: Draw markers at key points
    print("Test 7: Mark key points")

    # Mark the lens edge points
    for x, y, label in [
        (x_right, lens_y_top, 'TR'),
        (x_left, lens_y_top, 'TL'),
        (x_left, lens_y_bottom, 'BL'),
        (x_right, lens_y_bottom, 'BR')
    ]:
        dwg.add(dwg.circle((x, y), r=2, fill='red'))
        dwg.add(dwg.text(label, insert=(x + 5, y - 5), fill='red', font_size='8px'))

    dwg.save()
    print("\nTest SVG saved to: arc_test.svg")
    print("View this file in a browser or Inkscape to see which arcs render correctly.")


def test_lens_from_actual_coords():
    """Create test using the exact coordinates from the simulation."""

    dwg = svgwrite.Drawing('lens_coords_test.svg', size=('800px', '600px'), viewBox='-50 -500 400 400')

    # Actual coordinates from simulation output
    points = [
        {'x': 121.79, 'y': -200.00, 'label': 'p0 (top-right)'},
        {'x': 78.21, 'y': -200.00, 'label': 'p1 (top-left)'},
        {'x': 105.00, 'y': -300.00, 'label': 'p2 (arc center right)'},
        {'x': 78.21, 'y': -400.00, 'label': 'p3 (bottom-left)'},
        {'x': 121.79, 'y': -400.00, 'label': 'p4 (bottom-right)'},
        {'x': 95.00, 'y': -300.00, 'label': 'p5 (arc center left)'},
    ]

    # Draw all points
    for i, p in enumerate(points):
        dwg.add(dwg.circle((p['x'], p['y']), r=3, fill='red'))
        dwg.add(dwg.text(f"[{i}] {p['label']}", insert=(p['x'] + 5, p['y'] - 5),
                        fill='darkred', font_size='10px'))

    # Draw the arc centers and their radii
    radius_right = 103.53
    radius_left = 103.53

    # Right arc center
    dwg.add(dwg.circle((points[2]['x'], points[2]['y']), r=radius_right,
                      fill='none', stroke='lightblue', stroke_width=0.5, stroke_dasharray='5,5'))

    # Left arc center
    dwg.add(dwg.circle((points[5]['x'], points[5]['y']), r=radius_left,
                      fill='none', stroke='lightgreen', stroke_width=0.5, stroke_dasharray='5,5'))

    # Test different path constructions
    tests = [
        {
            'name': 'Original (sweep 0,0)',
            'offset_x': 0,
            'path': "M 121.79,-200.0 L 78.21,-200.0 A 103.53,103.53 0 0 0 78.21,-400.0 L 121.79,-400.0 A 103.53,103.53 0 0 0 121.79,-200.0 Z",
            'color': 'cyan'
        },
        {
            'name': 'Test sweep 1,1',
            'offset_x': 150,
            'path': f"M {121.79+150},-200.0 L {78.21+150},-200.0 A 103.53,103.53 0 0 1 {78.21+150},-400.0 L {121.79+150},-400.0 A 103.53,103.53 0 0 1 {121.79+150},-200.0 Z",
            'color': 'lime'
        },
        {
            'name': 'Test large-arc 1,1',
            'offset_x': -150,
            'path': f"M {121.79-150},-200.0 L {78.21-150},-200.0 A 103.53,103.53 0 1 1 {78.21-150},-400.0 L {121.79-150},-400.0 A 103.53,103.53 0 1 1 {121.79-150},-200.0 Z",
            'color': 'orange'
        }
    ]

    for test in tests:
        path = dwg.path(
            d=test['path'],
            fill=test['color'],
            fill_opacity=0.4,
            stroke='black',
            stroke_width=2
        )
        dwg.add(path)
        dwg.add(dwg.text(test['name'],
                        insert=(100 + test['offset_x'], -450),
                        fill='black', font_size='12px', text_anchor='middle'))

    dwg.save()
    print("\nLens coordinates test saved to: lens_coords_test.svg")


if __name__ == '__main__':
    print("SVG Arc Rendering Tests")
    print("=" * 60)

    test_basic_arcs()
    test_lens_from_actual_coords()

    print("\nTests complete. Open the generated SVG files to see results:")
    print("  - arc_test.svg: Various arc configurations")
    print("  - lens_coords_test.svg: Tests using actual lens coordinates")
