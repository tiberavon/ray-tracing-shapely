"""
Python-specific module: test phase3 render result
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
PHASE 3: RenderResult Layer - Feature Verification
===============================================================================

Tests the Phase 3 additions:
1. save_render() saves SVG to file and returns descriptor dict
2. _svg_to_png() optional conversion (graceful fallback if no cairosvg)
3. reset_render_counter() resets the module-level counter
4. set_context() creates render_dir in _CONTEXT
5. clear_context() resets the render counter
6. SVG tools return descriptor dicts (not raw SVG strings)
7. Descriptor dict is JSON-serializable

USAGE
-----
    python -m ray_tracing_shapely.developer_tests.test_phase3_render_result

===============================================================================
"""

import sys
import os
import json
import tempfile
from pathlib import Path

# Ensure the package is importable when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.analysis.render_result import (
    save_render,
    reset_render_counter,
)
from ray_tracing_shapely.analysis.agentic_tools import (
    set_context,
    clear_context,
    get_context,
    render_scene_svg,
    highlight_rays_inside_glass_svg,
    highlight_rays_crossing_edge_svg,
    highlight_rays_by_polarization_svg,
    highlight_custom_rays_svg,
)


MINIMAL_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100"/></svg>'


def build_test_scene():
    """Build a minimal scene: one triangular prism + one single ray."""
    scene = Scene()

    prism = Glass(scene)
    prism.path = [
        {'x': 200, 'y': 50, 'arc': False},
        {'x': 250, 'y': 100, 'arc': False},
        {'x': 150, 'y': 100, 'arc': False},
    ]
    prism.refraction_index = 1.5
    prism.name = 'test_prism'
    scene.add_object(prism)

    ray_src = SingleRay(scene)
    ray_src.p1 = {'x': 100, 'y': 80}
    ray_src.p2 = {'x': 250, 'y': 80}
    ray_src.brightness = 1.0
    scene.add_object(ray_src)

    prism.auto_label_cardinal()

    return scene, prism


def run_simulation(scene):
    """Run the simulator and return segments."""
    sim = Simulator(scene)
    segments = sim.run()
    return segments


# =============================================================================
# Tests
# =============================================================================

def test_save_render_creates_svg_file():
    """Test 1: save_render writes SVG file to disk."""
    print("\nTest 1: save_render creates SVG file")
    reset_render_counter()
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        result = save_render(
            svg_string=MINIMAL_SVG,
            render_dir=tmpdir,
            prefix='test',
            width=100,
            height=100,
            description='Test render.',
        )
        svg_path = Path(result['svg_path'])
        assert svg_path.exists(), f"SVG file not found: {svg_path}"
        content = svg_path.read_text(encoding='utf-8')
        assert '<svg' in content, "SVG file missing <svg> tag"
    print(f"  PASS: SVG file created at {result['svg_path']}")
    return True


def test_save_render_descriptor_keys():
    """Test 2: save_render returns all expected keys."""
    print("\nTest 2: save_render descriptor keys")
    reset_render_counter()
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        result = save_render(
            svg_string=MINIMAL_SVG,
            render_dir=tmpdir,
            prefix='test',
            width=800,
            height=600,
            description='All keys test.',
        )
        expected_keys = {'svg_path', 'png_path', 'png_available', 'width',
                         'height', 'description', 'highlight_summary'}
        assert set(result.keys()) == expected_keys, (
            f"Expected keys {expected_keys}, got {set(result.keys())}"
        )
        assert result['width'] == 800
        assert result['height'] == 600
        assert result['description'] == 'All keys test.'
        assert result['highlight_summary'] is None
        assert isinstance(result['png_available'], bool)
    print(f"  PASS: All {len(expected_keys)} keys present, values correct")
    return True


def test_save_render_counter_increments():
    """Test 3: save_render increments the counter for unique filenames."""
    print("\nTest 3: Counter increments")
    reset_render_counter()
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        r1 = save_render(MINIMAL_SVG, tmpdir, 'test', 100, 100, 'First')
        r2 = save_render(MINIMAL_SVG, tmpdir, 'test', 100, 100, 'Second')
        assert r1['svg_path'] != r2['svg_path'], "Filenames should differ"
        assert '_001.' in r1['svg_path'], f"Expected _001 in {r1['svg_path']}"
        assert '_002.' in r2['svg_path'], f"Expected _002 in {r2['svg_path']}"
    print(f"  PASS: {r1['svg_path']} -> {r2['svg_path']}")
    return True


def test_reset_render_counter():
    """Test 4: reset_render_counter resets counter to 0."""
    print("\nTest 4: reset_render_counter")
    reset_render_counter()
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        save_render(MINIMAL_SVG, tmpdir, 'test', 100, 100, 'Before reset')
        save_render(MINIMAL_SVG, tmpdir, 'test', 100, 100, 'Before reset 2')
        reset_render_counter()
        r3 = save_render(MINIMAL_SVG, tmpdir, 'after', 100, 100, 'After reset')
        assert '_001.' in r3['svg_path'], (
            f"Expected _001 after reset, got {r3['svg_path']}"
        )
    print(f"  PASS: Counter reset, next file: {r3['svg_path']}")
    return True


def test_save_render_with_highlight_summary():
    """Test 5: save_render passes highlight_summary through."""
    print("\nTest 5: highlight_summary pass-through")
    reset_render_counter()
    hl = {'highlighted_rays': 3, 'total_rays': 10, 'filter': 'inside_glass'}
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        result = save_render(
            MINIMAL_SVG, tmpdir, 'hl', 100, 100, 'With highlights',
            highlight_summary=hl,
        )
        assert result['highlight_summary'] == hl
    print(f"  PASS: highlight_summary preserved")
    return True


def test_save_render_json_serializable():
    """Test 6: save_render output is fully JSON-serializable."""
    print("\nTest 6: JSON serializable")
    reset_render_counter()
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        result = save_render(
            MINIMAL_SVG, tmpdir, 'json', 100, 100, 'Serializable test',
            highlight_summary={'filter': 'test', 'count': 5},
        )
        try:
            json_str = json.dumps(result)
            assert len(json_str) > 0
        except (TypeError, ValueError) as e:
            assert False, f"Descriptor not JSON-serializable: {e}"
    print(f"  PASS: json.dumps() succeeded")
    return True


def test_png_fallback():
    """Test 7: png_available is bool, png_path is str or None."""
    print("\nTest 7: PNG fallback")
    reset_render_counter()
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        result = save_render(MINIMAL_SVG, tmpdir, 'png', 100, 100, 'PNG test')
        assert isinstance(result['png_available'], bool)
        if result['png_available']:
            assert result['png_path'] is not None
            assert Path(result['png_path']).exists()
            print(f"  PASS: cairosvg available, PNG at {result['png_path']}")
        else:
            assert result['png_path'] is None
            print(f"  PASS: cairosvg not installed, png_path=None")
    return True


def test_set_context_creates_render_dir():
    """Test 8: set_context() creates a render_dir in _CONTEXT."""
    print("\nTest 8: set_context creates render_dir")
    scene, _prism = build_test_scene()
    segments = run_simulation(scene)
    clear_context()
    set_context(scene, segments)
    ctx = get_context()
    assert 'render_dir' in ctx, "render_dir missing from context"
    render_dir = Path(ctx['render_dir'])
    assert render_dir.exists(), f"render_dir does not exist: {render_dir}"
    print(f"  PASS: render_dir = {render_dir}")
    return True


def test_clear_context_resets_counter():
    """Test 9: clear_context() resets the render counter."""
    print("\nTest 9: clear_context resets render counter")
    reset_render_counter()
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        save_render(MINIMAL_SVG, tmpdir, 'pre', 100, 100, 'Pre-clear')
        save_render(MINIMAL_SVG, tmpdir, 'pre', 100, 100, 'Pre-clear 2')
        # clear_context should reset the counter
        clear_context()
        r = save_render(MINIMAL_SVG, tmpdir, 'post', 100, 100, 'Post-clear')
        assert '_001.' in r['svg_path'], (
            f"Expected _001 after clear_context, got {r['svg_path']}"
        )
    print(f"  PASS: Counter reset after clear_context()")
    return True


def test_render_scene_svg_returns_descriptor():
    """Test 10: render_scene_svg returns descriptor (not SVG string)."""
    print("\nTest 10: render_scene_svg descriptor")
    scene, _prism = build_test_scene()
    segments = run_simulation(scene)
    set_context(scene, segments)

    result = render_scene_svg()
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    data = result['data']
    assert isinstance(data, dict), f"Expected dict, got {type(data)}"
    assert 'svg_path' in data, "Missing svg_path"
    assert 'description' in data, "Missing description"
    assert Path(data['svg_path']).exists(), f"SVG file not found: {data['svg_path']}"
    print(f"  PASS: descriptor with description='{data['description'][:50]}...'")
    return True


def test_highlight_tool_returns_descriptor_with_summary():
    """Test 11: highlight tool returns descriptor with highlight_summary."""
    print("\nTest 11: highlight tool descriptor + summary")
    scene, _prism = build_test_scene()
    segments = run_simulation(scene)
    set_context(scene, segments)

    result = highlight_rays_inside_glass_svg('test_prism')
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    data = result['data']
    assert isinstance(data, dict), f"Expected dict, got {type(data)}"
    assert data['highlight_summary'] is not None, "Missing highlight_summary"
    hs = data['highlight_summary']
    assert 'highlighted_rays' in hs, "Missing highlighted_rays"
    assert 'total_rays' in hs, "Missing total_rays"
    assert hs['filter'] == 'inside_glass', f"Expected inside_glass, got {hs['filter']}"
    print(f"  PASS: {hs['highlighted_rays']} of {hs['total_rays']} rays highlighted")
    return True


def test_render_dir_prefix():
    """Test 12: save_render uses the correct prefix in filenames."""
    print("\nTest 12: Filename prefix")
    reset_render_counter()
    with tempfile.TemporaryDirectory(prefix='test_render_') as tmpdir:
        r = save_render(MINIMAL_SVG, tmpdir, 'scene', 100, 100, 'Prefix test')
        filename = Path(r['svg_path']).name
        assert filename.startswith('scene_'), (
            f"Expected filename starting with 'scene_', got '{filename}'"
        )
    print(f"  PASS: filename = {filename}")
    return True


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 70)
    print("Phase 3: RenderResult Layer - Feature Verification")
    print("=" * 70)

    results = []
    results.append(("save_render creates SVG file",   test_save_render_creates_svg_file()))
    results.append(("descriptor keys",                 test_save_render_descriptor_keys()))
    results.append(("counter increments",              test_save_render_counter_increments()))
    results.append(("reset_render_counter",            test_reset_render_counter()))
    results.append(("highlight_summary pass-through",  test_save_render_with_highlight_summary()))
    results.append(("JSON serializable",               test_save_render_json_serializable()))
    results.append(("PNG fallback",                    test_png_fallback()))
    results.append(("set_context render_dir",          test_set_context_creates_render_dir()))
    results.append(("clear_context resets counter",    test_clear_context_resets_counter()))
    results.append(("render_scene_svg descriptor",     test_render_scene_svg_returns_descriptor()))
    results.append(("highlight tool descriptor",       test_highlight_tool_returns_descriptor_with_summary()))
    results.append(("filename prefix",                 test_render_dir_prefix()))

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
        print("\nAll Phase 3 render result tests verified successfully!")
    else:
        print("\nSome tests failed.")
        sys.exit(1)


if __name__ == '__main__':
    main()
