"""
Python-specific module: test svg renderer
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
SVG RENDERER TESTS -- ray_subsample
===============================================================================
Tests SVGRenderer.draw_scene()'s ray_subsample parameter: decouples the
physics ray_density (accurate detector/power readings) from the rendered
picture's size, since a scene traced at a high ray_density otherwise produces
an SVG with one path element per ray -- multi-MB for a few thousand segments.

Also tests ray_stroke_width/edge_stroke_width, which decouple ray and
scene-object (glass polygon / mirror / detector) line thickness -- a device
built from many short wall segments (e.g. DTIRCPrism's wall_segments) can
look cluttered at draw_glass_path's/draw_line_segment's own default width.

Also tests object_label_font_size/edge_label_font_size, which decouple
scene-object display-name label size from per-edge functional-label size --
the same declutter need, for text instead of line thickness.

Run with:
    python developer_tests/test_svg_renderer.py
Or with pytest:
    pytest developer_tests/test_svg_renderer.py -v
===============================================================================
"""

import sys
from pathlib import Path
from unittest.mock import patch

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class _FakeSeg:
    def __init__(self, i):
        self.p1 = {'x': 0, 'y': i}
        self.p2 = {'x': 1, 'y': i}
        self.brightness_s = 0.5
        self.brightness_p = 0.5
        self.wavelength = None
        self.gap = False


def test_ray_subsample_default_draws_everything():
    """ray_subsample's default (1) leaves existing behaviour unchanged."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer
    from ray_tracing_shapely.core.scene import Scene

    scene = Scene()
    segments = [_FakeSeg(i) for i in range(100)]
    renderer = SVGRenderer()
    with patch.object(renderer, 'draw_ray_with_scene_settings') as mock_draw:
        renderer.draw_scene(scene, segments, draw_objects=False)
        assert mock_draw.call_count == 100
    print("  PASS: ray_subsample=1 (default) draws every segment")
    return True


def test_ray_subsample_reduces_drawn_count():
    """ray_subsample=N draws ~1/N of the segments."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer
    from ray_tracing_shapely.core.scene import Scene

    scene = Scene()
    segments = [_FakeSeg(i) for i in range(100)]
    renderer = SVGRenderer()
    with patch.object(renderer, 'draw_ray_with_scene_settings') as mock_draw:
        renderer.draw_scene(scene, segments, draw_objects=False, ray_subsample=10)
        assert mock_draw.call_count == 10
    print("  PASS: ray_subsample=10 draws 100/10=10 segments")
    return True


def test_ray_subsample_seed_is_reproducible():
    """The same ray_subsample_seed picks the same subset across calls."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer
    from ray_tracing_shapely.core.scene import Scene

    scene = Scene()
    segments = [_FakeSeg(i) for i in range(100)]

    def _drawn_segments(seed):
        renderer = SVGRenderer()
        with patch.object(renderer, 'draw_ray_with_scene_settings') as mock_draw:
            renderer.draw_scene(scene, segments, draw_objects=False,
                                 ray_subsample=10, ray_subsample_seed=seed)
            return [c.args[0] for c in mock_draw.call_args_list]

    assert _drawn_segments(42) == _drawn_segments(42)
    print("  PASS: ray_subsample_seed reproduces the same random subset")
    return True


def test_ray_subsample_never_drops_to_zero():
    """A short segment list with a large subsample factor still draws >= 1."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer
    from ray_tracing_shapely.core.scene import Scene

    scene = Scene()
    renderer = SVGRenderer()
    with patch.object(renderer, 'draw_ray_with_scene_settings') as mock_draw:
        renderer.draw_scene(scene, [_FakeSeg(0)], draw_objects=False, ray_subsample=10)
        assert mock_draw.call_count == 1
    print("  PASS: ray_subsample never rounds a non-empty segment list down to 0")
    return True


def test_ray_stroke_width_default_and_override():
    """ray_stroke_width defaults to draw_ray_with_scene_settings's own
    default (1.5, unchanged rendering) and is overridable."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer
    from ray_tracing_shapely.core.scene import Scene

    scene = Scene()
    segments = [_FakeSeg(0)]

    renderer = SVGRenderer()
    with patch.object(renderer, 'draw_ray_with_scene_settings') as mock_draw:
        renderer.draw_scene(scene, segments)
        assert mock_draw.call_args.kwargs.get('stroke_width') == 1.5

    renderer2 = SVGRenderer()
    with patch.object(renderer2, 'draw_ray_with_scene_settings') as mock_draw:
        renderer2.draw_scene(scene, segments, ray_stroke_width=0.4)
        assert mock_draw.call_args.kwargs.get('stroke_width') == 0.4
    print("  PASS: ray_stroke_width defaults to 1.5 (unchanged) and is overridable")
    return True


def test_edge_stroke_width_default_and_override():
    """edge_stroke_width defaults to draw_glass_path's/draw_line_segment's
    own default (2.0, unchanged rendering) and is overridable, applying to
    both glass polygons and line-based objects (mirrors/detectors)."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism

    scene = Scene()
    prism = DTIRCPrism(scene, theta_deg=10.0, n=1.5, size=30.0)
    scene.add_object(prism)
    mirror = Mirror(scene)
    mirror.p1 = {'x': 0, 'y': 0}
    mirror.p2 = {'x': 1, 'y': 1}
    scene.add_object(mirror)

    renderer = SVGRenderer()
    with patch.object(renderer, 'draw_glass_path') as mock_glass, \
         patch.object(renderer, 'draw_line_segment') as mock_line:
        renderer.draw_scene(scene, [])
        assert mock_glass.call_args.kwargs.get('stroke_width') == 2.0
        assert mock_line.call_args.kwargs.get('stroke_width') == 2.0

    renderer2 = SVGRenderer()
    with patch.object(renderer2, 'draw_glass_path') as mock_glass, \
         patch.object(renderer2, 'draw_line_segment') as mock_line:
        renderer2.draw_scene(scene, [], edge_stroke_width=0.7)
        assert mock_glass.call_args.kwargs.get('stroke_width') == 0.7
        assert mock_line.call_args.kwargs.get('stroke_width') == 0.7
    print("  PASS: edge_stroke_width defaults to 2.0 (unchanged) and applies to glass + line objects")
    return True


def test_font_size_default_and_override():
    """object_label_font_size/edge_label_font_size default to each draw_*
    method's own previous hardcoded value (8px objects, 6px edges -- unchanged
    rendering) and are independently overridable, applying to glass/lens/
    line/point object labels and per-edge functional labels respectively."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism

    scene = Scene()
    prism = DTIRCPrism(scene, theta_deg=10.0, n=1.5, size=30.0)
    prism.name = 'dtirc'
    scene.add_object(prism)
    mirror = Mirror(scene)
    mirror.p1 = {'x': 0, 'y': 0}
    mirror.p2 = {'x': 1, 'y': 1}
    mirror.name = 'm1'
    scene.add_object(mirror)

    renderer = SVGRenderer()
    with patch.object(renderer, 'draw_glass_path') as mock_glass, \
         patch.object(renderer, 'draw_glass_edge_labels') as mock_edge, \
         patch.object(renderer, 'draw_line_segment') as mock_line:
        renderer.draw_scene(scene, [])
        assert mock_glass.call_args.kwargs.get('label_font_size') == '8px'
        assert mock_edge.call_args.kwargs.get('font_size') == '6px'
        assert mock_line.call_args.kwargs.get('label_font_size') == '8px'

    renderer2 = SVGRenderer()
    with patch.object(renderer2, 'draw_glass_path') as mock_glass, \
         patch.object(renderer2, 'draw_glass_edge_labels') as mock_edge, \
         patch.object(renderer2, 'draw_line_segment') as mock_line:
        renderer2.draw_scene(scene, [], object_label_font_size='4px', edge_label_font_size='3px')
        assert mock_glass.call_args.kwargs.get('label_font_size') == '4px'
        assert mock_edge.call_args.kwargs.get('font_size') == '3px'
        assert mock_line.call_args.kwargs.get('label_font_size') == '4px'

    # End-to-end: actually renders (no exceptions), and the requested sizes
    # show up the expected number of times in the real SVG output.
    renderer3 = SVGRenderer()
    renderer3.draw_scene(scene, [], object_label_font_size='5px', edge_label_font_size='4px')
    svg = renderer3.to_string()
    assert svg.count('font-size="5px"') == 2   # 'dtirc' glass label + 'm1' line label
    assert svg.count('font-size="4px"') == len(prism.path)  # one edge label per edge
    print("  PASS: object_label_font_size/edge_label_font_size default correctly and override end to end")
    return True


def test_diagram_annotations_layer_is_topmost():
    """layer_diagram_annotations exists and paints last (over rays/labels)."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    ids = [getattr(el, 'attribs', {}).get('id') for el in renderer.dwg.elements]
    layer_ids = [i for i in ids if i and i.startswith('layer-')]
    assert layer_ids[-1] == 'layer-diagram-annotations', (
        f"expected layer-diagram-annotations last, got order {layer_ids}"
    )
    print("  PASS: layer_diagram_annotations is the last (topmost) layer")
    return True


def test_draw_annotation_marker_cross_style():
    """style='cross' adds two lines to layer_diagram_annotations, none to layer_objects."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    n_objects_before = len(renderer.layer_objects.elements)
    renderer.draw_annotation_marker({'x': 1.0, 'y': 2.0}, style='cross', size=0.05)
    assert len(renderer.layer_objects.elements) == n_objects_before
    assert len(renderer.layer_diagram_annotations.elements) == 2
    for el in renderer.layer_diagram_annotations.elements:
        assert el.elementname == 'line'
    print("  PASS: draw_annotation_marker(style='cross') draws two lines, only in the annotation layer")
    return True


def test_draw_annotation_marker_circle_style():
    """style='circle' adds a circle element to layer_diagram_annotations."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    renderer.draw_annotation_marker({'x': 0.0, 'y': 0.0}, style='circle', size=0.05)
    assert len(renderer.layer_diagram_annotations.elements) == 1
    assert renderer.layer_diagram_annotations.elements[0].elementname == 'circle'
    print("  PASS: draw_annotation_marker(style='circle') draws one circle")
    return True


def test_draw_annotation_marker_invalid_style_raises():
    """An unknown style raises ValueError rather than silently drawing nothing."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    try:
        renderer.draw_annotation_marker({'x': 0.0, 'y': 0.0}, style='triangle')
        raise AssertionError("expected ValueError, got a result")
    except ValueError:
        pass
    print("  PASS: draw_annotation_marker raises ValueError on an unknown style")
    return True


def test_draw_annotation_marker_label_in_same_layer():
    """The optional label lands in layer_diagram_annotations, not layer_labels."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    n_labels_before = len(renderer.layer_labels.elements)
    renderer.draw_annotation_marker({'x': 0.0, 'y': 0.0}, label='E', style='cross', size=0.05)
    assert len(renderer.layer_labels.elements) == n_labels_before
    texts = [el for el in renderer.layer_diagram_annotations.elements if el.elementname == 'text']
    assert len(texts) == 1
    print("  PASS: draw_annotation_marker's label stays in the annotation layer, not layer_labels")
    return True


def test_draw_annotation_vector_endpoint():
    """The shaft's far endpoint equals origin + length*normalize(direction)."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    origin = {'x': 0.0, 'y': 0.0}
    direction = (3.0, 4.0)  # magnitude 5 -- not axis-aligned, not pre-normalized
    length = 2.0
    renderer.draw_annotation_vector(origin, direction, length)

    lines = [el for el in renderer.layer_diagram_annotations.elements if el.elementname == 'line']
    assert len(lines) == 1
    shaft = lines[0].attribs
    expected_x2 = length * (3.0 / 5.0)
    expected_y2 = length * (4.0 / 5.0)
    assert abs(float(shaft['x2']) - expected_x2) < 1e-9
    assert abs(float(shaft['y2']) - expected_y2) < 1e-9
    print("  PASS: draw_annotation_vector's endpoint matches origin + length*normalize(direction)")
    return True


def test_draw_annotation_vector_arrowhead_present():
    """A polygon (arrowhead) is added near the tip."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    renderer.draw_annotation_vector({'x': 0.0, 'y': 0.0}, direction=(1.0, 0.0), length=1.0)
    polygons = [el for el in renderer.layer_diagram_annotations.elements if el.elementname == 'polygon']
    assert len(polygons) == 1
    print("  PASS: draw_annotation_vector adds one arrowhead polygon")
    return True


def test_draw_annotation_vector_raises_on_zero_direction():
    """A zero-magnitude direction raises ValueError."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    try:
        renderer.draw_annotation_vector({'x': 0.0, 'y': 0.0}, direction=(0.0, 0.0), length=1.0)
        raise AssertionError("expected ValueError, got a result")
    except ValueError:
        pass
    print("  PASS: draw_annotation_vector raises ValueError on zero-magnitude direction")
    return True


def test_draw_annotation_angle_arc_endpoints():
    """The sampled arc's first/last points match center + radius*(cos, sin) at angle1/angle2."""
    import math
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    center = {'x': 1.0, 'y': -0.5}
    angle1, angle2, radius = 0.0, math.radians(8.0), 0.3
    renderer.draw_annotation_angle_arc(center, angle1, angle2, radius)

    paths = [el for el in renderer.layer_diagram_annotations.elements if el.elementname == 'path']
    assert len(paths) == 1
    # svgwrite's Path only materializes the 'd' attribute on serialization
    # (tostring()), not eagerly in .attribs at construction time.
    paths[0].tostring()
    d = paths[0].attribs['d']
    coord_strs = d.replace('M ', '').replace(' L ', ' ').split(' ')
    points = [tuple(float(v) for v in c.split(',')) for c in coord_strs]

    expected_start = (center['x'] + radius * math.cos(angle1), center['y'] + radius * math.sin(angle1))
    expected_end = (center['x'] + radius * math.cos(angle2), center['y'] + radius * math.sin(angle2))
    assert math.hypot(points[0][0] - expected_start[0], points[0][1] - expected_start[1]) < 1e-9
    assert math.hypot(points[-1][0] - expected_end[0], points[-1][1] - expected_end[1]) < 1e-9
    print("  PASS: draw_annotation_angle_arc's endpoints match center + radius*(cos, sin)")
    return True


def test_draw_annotation_angle_arc_raises_on_reversed_angles():
    """angle2 < angle1 raises ValueError rather than drawing a wrapped-around arc."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    renderer = SVGRenderer()
    try:
        renderer.draw_annotation_angle_arc({'x': 0.0, 'y': 0.0}, angle1=1.0, angle2=0.0, radius=0.3)
        raise AssertionError("expected ValueError, got a result")
    except ValueError:
        pass
    print("  PASS: draw_annotation_angle_arc raises ValueError when angle2 < angle1")
    return True


def test_annotation_default_stroke_width_scales_with_size():
    """
    Regression test: stroke_width must default to a fraction of the method's
    own size/arrowhead_size/radius, not a fixed number -- an earlier version
    defaulted to a flat 1.0, which rendered as ~1/3 of the canvas width on a
    2.9-unit-wide scene (fig9_1a.svg) and made changing `size` invisible,
    since the oversized stroke swamped any change to the marker's length.
    """
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    small = SVGRenderer()
    small.draw_annotation_marker({'x': 0.0, 'y': 0.0}, style='cross', size=0.05)
    small_stroke = float(small.layer_diagram_annotations.elements[0].attribs['stroke-width'])
    assert small_stroke < 0.05, (
        f"stroke_width ({small_stroke}) must be smaller than the marker's own "
        f"size (0.05), not a fixed value that could dwarf it"
    )

    big = SVGRenderer()
    big.draw_annotation_marker({'x': 0.0, 'y': 0.0}, style='cross', size=5.0)
    big_stroke = float(big.layer_diagram_annotations.elements[0].attribs['stroke-width'])
    assert big_stroke > small_stroke, (
        "stroke_width must scale up with size, not stay fixed"
    )
    print("  PASS: default stroke_width scales with size, not fixed")
    return True


def test_annotation_default_label_font_size_scales_with_size():
    """
    Regression test: label_font_size must default to a fraction of the
    method's own size/arrowhead_size/radius, not a fixed '8px' -- an
    earlier version defaulted to a flat '8px', which SVG resolves inside
    the (viewBox-scaled) user space, not real screen pixels: on a
    2.9-unit-wide scene this rendered ~3x the whole canvas, and its
    derived vertical_offset (font_size_num * 0.35) threw the label
    position far from the marker it was meant to label.
    """
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    small = SVGRenderer()
    small.draw_annotation_marker({'x': 0.0, 'y': 0.0}, label='E', style='cross', size=0.05)
    small_texts = [el for el in small.layer_diagram_annotations.elements if el.elementname == 'text']
    small_font = float(small_texts[0].attribs['font-size'].replace('px', ''))
    assert small_font < 1.0, (
        f"label_font_size ({small_font}px) must be smaller than the scene "
        f"itself for a small-scale marker (size=0.05), not a fixed '8px'"
    )

    big = SVGRenderer()
    big.draw_annotation_marker({'x': 0.0, 'y': 0.0}, label='E', style='cross', size=5.0)
    big_texts = [el for el in big.layer_diagram_annotations.elements if el.elementname == 'text']
    big_font = float(big_texts[0].attribs['font-size'].replace('px', ''))
    assert big_font > small_font, "label_font_size must scale up with size, not stay fixed"
    print("  PASS: default label_font_size scales with size, not fixed")
    return True


def test_annotation_sizes_are_user_space_not_pixels():
    """The same size produces identical absolute coordinate deltas regardless of viewbox scale."""
    from ray_tracing_shapely.core.svg_renderer import SVGRenderer

    small_scene = SVGRenderer(viewbox=(-1, -1, 2, 2))
    large_scene = SVGRenderer(viewbox=(-500, -500, 1000, 1000))

    small_scene.draw_annotation_marker({'x': 0.0, 'y': 0.0}, style='cross', size=0.05)
    large_scene.draw_annotation_marker({'x': 0.0, 'y': 0.0}, style='cross', size=0.05)

    small_line = small_scene.layer_diagram_annotations.elements[0].attribs
    large_line = large_scene.layer_diagram_annotations.elements[0].attribs
    assert small_line['x2'] == large_line['x2'] == 0.05
    print("  PASS: annotation sizes are absolute scene units, unaffected by viewbox scale")
    return True


def run_all_tests():
    tests = [
        ("ray_subsample=1 (default) draws everything", test_ray_subsample_default_draws_everything),
        ("ray_subsample=N reduces drawn count", test_ray_subsample_reduces_drawn_count),
        ("ray_subsample_seed is reproducible", test_ray_subsample_seed_is_reproducible),
        ("ray_subsample never drops to 0", test_ray_subsample_never_drops_to_zero),
        ("ray_stroke_width default + override", test_ray_stroke_width_default_and_override),
        ("edge_stroke_width default + override", test_edge_stroke_width_default_and_override),
        ("font sizes default + override", test_font_size_default_and_override),
        ("diagram annotations layer is topmost", test_diagram_annotations_layer_is_topmost),
        ("draw_annotation_marker cross style", test_draw_annotation_marker_cross_style),
        ("draw_annotation_marker circle style", test_draw_annotation_marker_circle_style),
        ("draw_annotation_marker invalid style raises", test_draw_annotation_marker_invalid_style_raises),
        ("draw_annotation_marker label in same layer", test_draw_annotation_marker_label_in_same_layer),
        ("draw_annotation_vector endpoint", test_draw_annotation_vector_endpoint),
        ("draw_annotation_vector arrowhead present", test_draw_annotation_vector_arrowhead_present),
        ("draw_annotation_vector raises on zero direction", test_draw_annotation_vector_raises_on_zero_direction),
        ("draw_annotation_angle_arc endpoints", test_draw_annotation_angle_arc_endpoints),
        ("draw_annotation_angle_arc raises on reversed angles", test_draw_annotation_angle_arc_raises_on_reversed_angles),
        ("annotation default stroke_width scales with size", test_annotation_default_stroke_width_scales_with_size),
        ("annotation default label_font_size scales with size", test_annotation_default_label_font_size_scales_with_size),
        ("annotation sizes are user-space, not pixels", test_annotation_sizes_are_user_space_not_pixels),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_func in tests:
        print(f"\nTEST: {name}")
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  FAILED: {name}")
            print(f"    Error: {e}")

    print("\n" + "=" * 78)
    print(f"SUMMARY: {passed}/{len(tests)} tests passed")
    print("=" * 78)

    if errors:
        print("\nFailed tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")
        return False

    print("\nAll tests passed!")
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
