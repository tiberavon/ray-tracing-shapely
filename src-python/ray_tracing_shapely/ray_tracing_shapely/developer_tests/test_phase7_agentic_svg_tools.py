"""
Python-specific module: test phase7 agentic svg tools
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
PHASE 7: Agentic SVG Tools - Feature Verification Test
===============================================================================

This script tests the Phase 7 agentic SVG rendering tools added to
agentic_tools.py. These tools compose ray-query functions with SVGRenderer
to save SVG/PNG files and return JSON-serializable descriptors with file
paths, dimensions, and text descriptions.

TOOLS TESTED
------------
1. render_scene_svg          -- baseline full-scene rendering
2. highlight_rays_inside_glass_svg  -- highlight rays inside a named glass
3. highlight_rays_crossing_edge_svg -- highlight rays crossing a named edge
4. highlight_rays_by_polarization_svg -- highlight rays by polarization
5. highlight_custom_rays_svg -- highlight arbitrary rays by uuid

HELPERS TESTED
--------------
- _compute_scene_bounds(scene) -- auto viewbox from scene objects
- _parse_viewbox(viewbox_str, scene) -- parse "auto" or "x,y,w,h"

REGISTRY
--------
- get_agentic_tools() includes all 5 SVG tools
- list_available_tools() includes all 5 SVG tools
- generate_tool_note_for_solveit_notebook() includes all 5 SVG tools

USAGE
-----
    python -m ray_tracing_shapely.developer_tests.test_phase7_agentic_svg_tools

===============================================================================
"""

import sys
import os
from pathlib import Path

# Ensure the package is importable when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.analysis.agentic_tools import (
    set_context,
    render_scene_svg,
    highlight_rays_inside_glass_svg,
    highlight_rays_crossing_edge_svg,
    highlight_rays_by_polarization_svg,
    highlight_custom_rays_svg,
    _compute_scene_bounds,
    _parse_viewbox,
)
from ray_tracing_shapely.analysis.glass_geometry import get_edge_descriptions
from ray_tracing_shapely.analysis.tool_registry import (
    get_agentic_tools,
    list_available_tools,
    generate_tool_note_for_solveit_notebook,
)


def _assert_descriptor(data: dict, label: str) -> None:
    """Shared assertions for render descriptor dicts."""
    assert isinstance(data, dict), f"{label}: data should be dict, got {type(data)}"
    assert 'svg_path' in data, f"{label}: missing svg_path"
    assert 'description' in data, f"{label}: missing description"
    assert 'width' in data, f"{label}: missing width"
    assert 'height' in data, f"{label}: missing height"
    assert 'png_available' in data, f"{label}: missing png_available"
    assert isinstance(data['description'], str), f"{label}: description not str"
    assert len(data['description']) > 0, f"{label}: description empty"
    assert isinstance(data['width'], int), f"{label}: width not int"
    assert isinstance(data['height'], int), f"{label}: height not int"
    assert isinstance(data['png_available'], bool), f"{label}: png_available not bool"
    # Verify SVG file exists and contains <svg
    svg_path = Path(data['svg_path'])
    assert svg_path.exists(), f"{label}: svg file not found: {svg_path}"
    svg_content = svg_path.read_text(encoding='utf-8')
    assert '<svg' in svg_content, f"{label}: SVG file missing <svg> tag"


def build_test_scene():
    """Build a minimal scene: one triangular prism + one single ray."""
    scene = Scene()

    prism = Glass(scene)
    prism.path = [
        {'x': 200, 'y': 50, 'arc': False},
        {'x': 250, 'y': 100, 'arc': False},
        {'x': 150, 'y': 100, 'arc': False},
    ]
    prism.refIndex = 1.5
    prism.name = 'test_prism'
    scene.add_object(prism)

    ray_src = SingleRay(scene)
    ray_src.p1 = {'x': 100, 'y': 80}
    ray_src.p2 = {'x': 250, 'y': 80}
    ray_src.brightness = 1.0
    scene.add_object(ray_src)

    # Label edges with cardinal directions
    prism.auto_label_cardinal()

    return scene, prism


def run_simulation(scene):
    """Run the simulator and return segments."""
    sim = Simulator(scene)
    segments = sim.run()
    return segments


# =============================================================================
# Fixtures -- the same objects main() passes as arguments, for pytest
# =============================================================================
# Scene-building and the simulation are module-scoped: they are the slow part
# and no test mutates them. The context is function-scoped, because it holds a
# live SQLite connection and because tests here open and close it on purpose.

@pytest.fixture(scope="module")
def _built():
    return build_test_scene()


@pytest.fixture(scope="module")
def scene(_built):
    return _built[0]


@pytest.fixture(scope="module")
def prism(_built):
    return _built[1]


@pytest.fixture(scope="module")
def segments(scene):
    return run_simulation(scene)


@pytest.fixture(autouse=True)
def _context(scene, segments):
    """main() sets this once; under pytest each test needs its own."""
    set_context(scene, segments)
    yield


def test_imports():
    """Test 1: All Phase 7 functions are importable."""
    print("Test 1: Imports")
    # If we got here, imports succeeded (done at module level)
    print("  PASS: All Phase 7 functions imported successfully")
    return True


def test_parse_viewbox_explicit():
    """Test 2: _parse_viewbox with explicit coordinates."""
    print("\nTest 2: _parse_viewbox (explicit)")
    vb = _parse_viewbox('10,20,400,300', None)
    assert vb == (10.0, 20.0, 400.0, 300.0), f"Expected (10,20,400,300), got {vb}"
    print(f"  PASS: _parse_viewbox('10,20,400,300') -> {vb}")
    return True


def test_compute_scene_bounds(scene):
    """Test 3: _compute_scene_bounds returns reasonable bounds."""
    print("\nTest 3: _compute_scene_bounds")
    bounds = _compute_scene_bounds(scene)
    min_x, min_y, w, h = bounds
    assert w > 0 and h > 0, f"Width/height must be positive, got w={w}, h={h}"
    assert min_x < 200 and min_y < 80, "min_x/min_y should be below object coords"
    print(f"  PASS: bounds = ({min_x:.1f}, {min_y:.1f}, {w:.1f}, {h:.1f})")
    return True


def test_render_scene_svg(segments):
    """Test 4: render_scene_svg returns a valid descriptor."""
    print("\nTest 4: render_scene_svg")
    result = render_scene_svg()
    assert result['status'] == 'ok', f"Expected status 'ok', got {result['status']}"
    data = result['data']
    _assert_descriptor(data, 'render_scene_svg')
    # Check SVG file has expected layers
    svg_content = Path(data['svg_path']).read_text(encoding='utf-8')
    assert 'layer-objects' in svg_content, "Missing layer-objects"
    assert 'layer-rays' in svg_content, "Missing layer-rays"
    print(f"  PASS: descriptor with svg_path={data['svg_path']}, "
          f"description='{data['description'][:50]}...'")
    return True


def test_render_scene_svg_explicit_viewbox():
    """Test 5: render_scene_svg with explicit viewbox."""
    print("\nTest 5: render_scene_svg (explicit viewbox)")
    result = render_scene_svg(width=600, height=400, viewbox='100,30,200,100')
    assert result['status'] == 'ok', f"Expected status 'ok', got {result['status']}"
    data = result['data']
    _assert_descriptor(data, 'render_scene_svg_viewbox')
    assert data['width'] == 600, f"Expected width=600, got {data['width']}"
    assert data['height'] == 400, f"Expected height=400, got {data['height']}"
    print(f"  PASS: descriptor width={data['width']}, height={data['height']}")
    return True


def test_highlight_rays_inside_glass_svg():
    """Test 6: highlight_rays_inside_glass_svg."""
    print("\nTest 6: highlight_rays_inside_glass_svg")
    result = highlight_rays_inside_glass_svg('test_prism')
    assert result['status'] == 'ok', f"Expected status 'ok', got {result['status']}"
    data = result['data']
    _assert_descriptor(data, 'highlight_inside')
    assert data['highlight_summary'] is not None, "Missing highlight_summary"
    assert data['highlight_summary']['filter'] == 'inside_glass', (
        f"Expected filter='inside_glass', got {data['highlight_summary']['filter']}"
    )
    print(f"  PASS: {data['highlight_summary']['highlighted_rays']} rays highlighted")
    return True


def test_highlight_rays_crossing_edge_svg(prism):
    """Test 7: highlight_rays_crossing_edge_svg."""
    print("\nTest 7: highlight_rays_crossing_edge_svg")
    edges = get_edge_descriptions(prism)
    labels = [e.short_label for e in edges if e.short_label]
    assert labels, "No edge labels found on prism"
    print(f"  Edge labels found: {labels}")

    result = highlight_rays_crossing_edge_svg('test_prism', labels[0])
    assert result['status'] == 'ok', f"Expected status 'ok', got {result['status']}"
    data = result['data']
    _assert_descriptor(data, 'highlight_edge')
    assert data['highlight_summary'] is not None, "Missing highlight_summary"
    assert data['highlight_summary']['filter'] == 'crossing_edge', (
        f"Expected filter='crossing_edge', got {data['highlight_summary']['filter']}"
    )
    print(f"  PASS: highlighted edge '{labels[0]}', "
          f"{data['highlight_summary']['highlighted_rays']} rays")
    return True


def test_highlight_rays_by_polarization_svg():
    """Test 8: highlight_rays_by_polarization_svg."""
    print("\nTest 8: highlight_rays_by_polarization_svg")
    result = highlight_rays_by_polarization_svg(min_dop=0.0, max_dop=1.0)
    assert result['status'] == 'ok', f"Expected status 'ok', got {result['status']}"
    data = result['data']
    _assert_descriptor(data, 'highlight_polar')
    assert data['highlight_summary'] is not None, "Missing highlight_summary"
    assert data['highlight_summary']['filter'] == 'polarization', (
        f"Expected filter='polarization', got {data['highlight_summary']['filter']}"
    )
    print(f"  PASS: {data['highlight_summary']['highlighted_rays']} rays highlighted")
    return True


def test_highlight_custom_rays_svg(segments):
    """Test 9: highlight_custom_rays_svg with comma-separated uuids."""
    print("\nTest 9: highlight_custom_rays_svg")
    if not segments:
        print("  SKIP: no segments available")
        return True
    uuids = [s.uuid for s in segments[:2]]
    csv_str = ','.join(uuids)
    result = highlight_custom_rays_svg(csv_str, highlight_color='red')
    assert result['status'] == 'ok', f"Expected status 'ok', got {result['status']}"
    data = result['data']
    _assert_descriptor(data, 'highlight_custom')
    assert data['highlight_summary'] is not None, "Missing highlight_summary"
    assert data['highlight_summary']['filter'] == 'custom', (
        f"Expected filter='custom', got {data['highlight_summary']['filter']}"
    )
    print(f"  PASS: highlighted {len(uuids)} rays, "
          f"svg_path={data['svg_path']}")
    return True


def test_tool_registry():
    """Test 10: Tool registry includes all Phase 7 tools."""
    print("\nTest 10: Tool registry")
    tools = get_agentic_tools()
    names = [t['name'] for t in tools]

    expected_svg_tools = [
        'render_scene_svg',
        'highlight_rays_inside_glass_svg',
        'highlight_rays_crossing_edge_svg',
        'highlight_rays_by_polarization_svg',
        'highlight_custom_rays_svg',
    ]

    for name in expected_svg_tools:
        assert name in names, f"{name} missing from get_agentic_tools()"

    print(f"  PASS: All 5 SVG tools in get_agentic_tools() (total: {len(tools)} tools)")

    # Check list_available_tools text output
    text = list_available_tools()
    for name in expected_svg_tools:
        assert name in text, f"{name} missing from list_available_tools()"
    print("  PASS: All 5 SVG tools in list_available_tools()")

    # Check solveit notebook helper
    note = generate_tool_note_for_solveit_notebook()
    for name in expected_svg_tools:
        assert name in note, f"{name} missing from solveit notebook note"
    print("  PASS: All 5 SVG tools in generate_tool_note_for_solveit_notebook()")

    return True


def main():
    print("=" * 70)
    print("Phase 7: Agentic SVG Tools - Feature Verification")
    print("=" * 70)

    # --- Setup ---
    print("\nSetup: Building scene and running simulation...")
    scene, prism = build_test_scene()
    segments = run_simulation(scene)
    print(f"  Scene has {len(scene.objs)} objects, simulation produced {len(segments)} segments")

    set_context(scene, segments)
    print("  Context set.\n")

    # --- Run tests ---
    results = []
    results.append(("Imports",                    test_imports()))
    results.append(("_parse_viewbox explicit",    test_parse_viewbox_explicit()))
    results.append(("_compute_scene_bounds",      test_compute_scene_bounds(scene)))
    results.append(("render_scene_svg",           test_render_scene_svg(segments)))
    results.append(("render_scene_svg (viewbox)", test_render_scene_svg_explicit_viewbox()))
    results.append(("highlight inside glass",     test_highlight_rays_inside_glass_svg()))
    results.append(("highlight crossing edge",    test_highlight_rays_crossing_edge_svg(prism)))
    results.append(("highlight by polarization",  test_highlight_rays_by_polarization_svg()))
    results.append(("highlight custom uuids",     test_highlight_custom_rays_svg(segments)))
    results.append(("tool registry",              test_tool_registry()))

    # --- Summary ---
    print("\n" + "=" * 70)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print("=" * 70)

    if passed == total:
        print("\nAll Phase 7 agentic SVG tools verified successfully!")
    else:
        print("\nSome tests failed.")
        sys.exit(1)


if __name__ == '__main__':
    main()
