"""
Python-specific module: test detector agentic tools
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
RAY LINEAGE STEP A -- AGENTIC EXPOSURE - Feature Verification
===============================================================================

Tests the agentic surface for detector-path analysis (closing the gap
described in dev_doc/concepts/KA7_a_tool_is_registered_in_three_places_or_it_is_unreachable.md).
Items 3-4 are part of C-AGENT-02's checked_by
(dev_doc/architecture/contracts/C-AGENT-02.md, the three-way tool
registration contract):

1. list_detectors() agentic wrapper
2. rank_detector_paths() agentic wrapper
3. Registration in tool_registry (get_agentic_tools, list_available_tools)
4. Exposure over MCP (mcp_server._EXPOSED_TOOLS)
5. detectors / detector_hits tables in the agentic SQLite database

USAGE
-----
    python -m ray_tracing_shapely.developer_tests.test_detector_agentic_tools

===============================================================================
"""

import sys
import os

# Ensure the package is importable when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.analysis.agentic_tools import (
    set_context,
    clear_context,
    list_detectors,
    rank_detector_paths,
    query_rays,
)
from ray_tracing_shapely.analysis.tool_registry import get_agentic_tools


def build_test_scene():
    """
    A source ray crossing a detector directly, plus an off-axis glass
    object (unused by the ray) to exercise the 'not a Detector' error path.
    """
    scene = Scene()

    # Off to the side -- the horizontal ray at y=80 never reaches it.
    prism = Glass(scene)
    prism.path = [
        {'x': 200, 'y': 150, 'arc': False},
        {'x': 250, 'y': 200, 'arc': False},
        {'x': 150, 'y': 200, 'arc': False},
    ]
    prism.refraction_index = 1.5
    prism.name = 'test_prism'
    scene.add_object(prism)

    ray_src = SingleRay(scene)
    ray_src.p1 = {'x': 100, 'y': 80}
    ray_src.p2 = {'x': 250, 'y': 80}
    ray_src.brightness = 1.0
    scene.add_object(ray_src)

    detector = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': 200, 'y': 0},
        'p2': {'x': 200, 'y': 160},
        'irrad_map': True,
        'bin_size': 10.0,
    })
    detector.name = 'test_detector'
    scene.add_object(detector)

    return scene, detector


def run_simulation(scene):
    """Run the simulator and return (segments, lineage)."""
    sim = Simulator(scene)
    segments = sim.run()
    return segments, sim.lineage


# =============================================================================
# Tests
# =============================================================================

def test_list_detectors():
    """Test 1: list_detectors reports the scene's detector and its hit count."""
    print("\nTest 1: list_detectors")
    result = list_detectors()
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    names = [d['name'] for d in result['data']]
    assert 'test_detector' in names, f"'test_detector' missing from {names}"
    entry = next(d for d in result['data'] if d['name'] == 'test_detector')
    assert entry['hit_count'] == 1, f"Expected 1 hit, got {entry['hit_count']}"
    print(f"  PASS: found {len(result['data'])} detector(s), "
          f"test_detector hit_count={entry['hit_count']}")
    return True


def test_rank_detector_paths_ok():
    """Test 2: rank_detector_paths ranks the path that reached the detector."""
    print("\nTest 2: rank_detector_paths ok")
    result = rank_detector_paths('test_detector')
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    paths = result['data']
    assert len(paths) == 1, f"Expected 1 path, got {len(paths)}"
    entry = paths[0]
    expected_keys = {'uuid', 'energy', 'energy_s', 'energy_p',
                     'path_length', 'path_types', 'path_uuids', 'bin_index'}
    assert set(entry.keys()) == expected_keys, (
        f"Expected keys {expected_keys}, got {set(entry.keys())}"
    )
    assert entry['path_types'] == ['source'], (
        f"Expected a bare source path, got {entry['path_types']}"
    )
    assert entry['bin_index'] == 8, f"Expected bin 8, got {entry['bin_index']}"
    print(f"  PASS: 1 path, energy={entry['energy']:.4f}, bin_index={entry['bin_index']}")
    return True


def test_rank_detector_paths_unknown_name():
    """Test 3: rank_detector_paths with an unknown name returns structured error."""
    print("\nTest 3: rank_detector_paths unknown name")
    result = rank_detector_paths('nonexistent_detector')
    assert result['status'] == 'error', f"Expected error, got: {result}"
    print(f"  PASS: Returned error: {result['message'][:60]}...")
    return True


def test_rank_detector_paths_not_a_detector():
    """Test 4: rank_detector_paths on a non-Detector object returns structured error."""
    print("\nTest 4: rank_detector_paths not a detector")
    result = rank_detector_paths('test_prism')
    assert result['status'] == 'error', f"Expected error, got: {result}"
    assert 'not a detector' in result['message'].lower(), (
        f"Error message should say 'not a Detector': {result['message']}"
    )
    print(f"  PASS: Returned error: {result['message'][:60]}...")
    return True


def test_rank_detector_paths_requires_lineage(scene, segments):
    """Test 5: rank_detector_paths without lineage returns structured error."""
    print("\nTest 5: rank_detector_paths without lineage")
    clear_context()
    set_context(scene, segments)  # no lineage
    result = rank_detector_paths('test_detector')
    assert result['status'] == 'error', f"Expected error, got: {result}"
    assert 'lineage' in result['message'].lower(), (
        f"Error message should mention lineage: {result['message']}"
    )
    print(f"  PASS: Returned error: {result['message'][:60]}...")
    return True


def test_tools_registered():
    """Test 6: list_detectors and rank_detector_paths are in get_agentic_tools()."""
    print("\nTest 6: tools registered")
    tools = get_agentic_tools()
    names = [t['name'] for t in tools]
    assert 'list_detectors' in names, "list_detectors missing from get_agentic_tools()"
    assert 'rank_detector_paths' in names, "rank_detector_paths missing from get_agentic_tools()"

    rdp = next(t for t in tools if t['name'] == 'rank_detector_paths')
    assert rdp['input_schema']['required'] == ['detector_name'], (
        f"Expected detector_name required, got {rdp['input_schema']['required']}"
    )
    print(f"  PASS: both tools present, rank_detector_paths requires detector_name")
    return True


def test_mcp_exposes_detector_tools():
    """Test 7: rank_detector_paths and list_detectors are exposed over MCP."""
    print("\nTest 7: MCP exposure")
    try:
        from ray_tracing_shapely.analysis import mcp_server
    except ImportError as e:
        print(f"  SKIP: mcp package not installed ({e})")
        return True

    exposed_names = [fn.__name__ for fn in mcp_server._EXPOSED_TOOLS]
    assert 'list_detectors' in exposed_names, "list_detectors missing from _EXPOSED_TOOLS"
    assert 'rank_detector_paths' in exposed_names, "rank_detector_paths missing from _EXPOSED_TOOLS"
    print(f"  PASS: {len(exposed_names)} MCP tools exposed, detector tools present")
    return True


def test_detector_hits_table(scene, segments, lineage):
    """Test 8: detectors / detector_hits tables are queryable via query_rays."""
    print("\nTest 8: detectors / detector_hits SQL tables")
    clear_context()
    set_context(scene, segments, lineage=lineage)

    result = query_rays("SELECT name, bin_size FROM detectors")
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    assert result['data']['row_count'] == 1, (
        f"Expected 1 detector row, got {result['data']['row_count']}"
    )

    result2 = query_rays(
        "SELECT dh.ray_uuid, dh.bin_index, r.brightness_total "
        "FROM detector_hits dh "
        "JOIN rays r ON r.uuid = dh.ray_uuid "
        "JOIN detectors d ON d.uuid = dh.detector_uuid "
        "WHERE d.name = 'test_detector'"
    )
    assert result2['status'] == 'ok', f"Expected ok, got: {result2}"
    assert result2['data']['row_count'] == 1, (
        f"Expected 1 joined hit row, got {result2['data']['row_count']}"
    )
    print(f"  PASS: 1 detector row, 1 detector_hits row joined to rays")
    return True


def test_detector_hits_table_empty_safe():
    """Test 9: detectors / detector_hits tables are empty-safe with no detector in scene."""
    print("\nTest 9: detectors table empty-safe")
    scene = Scene()
    ray_src = SingleRay(scene)
    ray_src.p1 = {'x': 0, 'y': 0}
    ray_src.p2 = {'x': 100, 'y': 0}
    ray_src.brightness = 1.0
    scene.add_object(ray_src)

    sim = Simulator(scene)
    segments = sim.run()

    clear_context()
    set_context(scene, segments, lineage=sim.lineage)
    result = query_rays("SELECT COUNT(*) as n FROM detectors")
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    assert result['data']['rows'][0][0] == 0, "Expected 0 detector rows"
    print(f"  PASS: empty detectors table does not error")
    return True


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 70)
    print("Ray Lineage Step A -- Agentic Exposure - Feature Verification")
    print("=" * 70)

    # --- Setup ---
    print("\nSetup: Building scene and running simulation...")
    scene, detector = build_test_scene()
    segments, lineage = run_simulation(scene)
    print(f"  Scene has {len(scene.objs)} objects, "
          f"simulation produced {len(segments)} segments, "
          f"detector hit_count={len(detector.get_hit_records())}")

    set_context(scene, segments, lineage=lineage)
    print("  Context set (with lineage).\n")

    # --- Run tests ---
    results = []
    results.append(("list_detectors",                 test_list_detectors()))
    results.append(("rank_detector_paths ok",          test_rank_detector_paths_ok()))
    results.append(("rank_detector_paths unknown",     test_rank_detector_paths_unknown_name()))
    results.append(("rank_detector_paths not-detector", test_rank_detector_paths_not_a_detector()))

    # Test 5 modifies context -- run it, then restore
    results.append(("rank_detector_paths no lineage",  test_rank_detector_paths_requires_lineage(scene, segments)))
    set_context(scene, segments, lineage=lineage)

    results.append(("tools registered",                test_tools_registered()))
    results.append(("MCP exposure",                    test_mcp_exposes_detector_tools()))
    results.append(("detector SQL tables",              test_detector_hits_table(scene, segments, lineage)))
    results.append(("detector SQL tables empty-safe",   test_detector_hits_table_empty_safe()))

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
        print("\nAll Step A agentic exposure tools verified successfully!")
    else:
        print("\nSome tests failed.")
        sys.exit(1)


if __name__ == '__main__':
    main()
