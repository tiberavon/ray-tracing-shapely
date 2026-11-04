"""
Python-specific module: test phase2 schemas and lineage
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
PHASE 2: JSON Schema Definitions + Lineage Wrappers - Feature Verification
===============================================================================

Tests the Phase 2 additions:
1. input_schema on every tool in get_agentic_tools()
2. rank_paths_by_energy agentic wrapper
3. check_energy_conservation agentic wrapper
4. fresnel_transmittances_tool agentic wrapper, incl. C-AGENT-01's
   ill-typed-args-return-error-not-raise regression

USAGE
-----
    python -m ray_tracing_shapely.developer_tests.test_phase2_schemas_and_lineage

===============================================================================
"""

import sys
import os

# Ensure the package is importable when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.analysis.agentic_tools import (
    set_context,
    clear_context,
    rank_paths_by_energy,
    check_energy_conservation,
    fresnel_transmittances_tool,
)
from ray_tracing_shapely.analysis.tool_registry import (
    get_agentic_tools,
    list_available_tools,
)


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

    prism.auto_label_cardinal()

    return scene, prism


def run_simulation(scene):
    """Run the simulator and return (segments, lineage)."""
    sim = Simulator(scene)
    segments = sim.run()
    return segments, sim.lineage


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
def _run(scene):
    return run_simulation(scene)


@pytest.fixture(scope="module")
def segments(_run):
    return _run[0]


@pytest.fixture(scope="module")
def lineage(_run):
    return _run[1]


@pytest.fixture(autouse=True)
def _context(scene, segments, lineage):
    """With lineage, as main() does.

    Two tests here deliberately re-set a context *without* lineage to
    exercise the error path. They overwrite this one, which is why it is set
    per test rather than once per module.
    """
    set_context(scene, segments, lineage=lineage)
    yield


# =============================================================================
# Tests
# =============================================================================

def test_all_tools_have_input_schema():
    """Test 1: Every tool from get_agentic_tools() has input_schema."""
    print("\nTest 1: All tools have input_schema")
    tools = get_agentic_tools()
    for t in tools:
        assert 'input_schema' in t, f"Tool {t['name']} missing input_schema"
        schema = t['input_schema']
        assert 'type' in schema, f"Tool {t['name']} schema missing 'type'"
        assert schema['type'] == 'object', (
            f"Tool {t['name']} schema type is '{schema['type']}', expected 'object'"
        )
        assert 'properties' in schema, f"Tool {t['name']} schema missing 'properties'"
        assert 'required' in schema, f"Tool {t['name']} schema missing 'required'"
    print(f"  PASS: {len(tools)} tools all have valid input_schema")
    return True


def test_schema_properties_have_types():
    """Test 2: Each property in each schema has a 'type' key."""
    print("\nTest 2: Schema properties have types")
    tools = get_agentic_tools()
    for t in tools:
        schema = t['input_schema']
        for prop_name, prop_def in schema['properties'].items():
            assert 'type' in prop_def, (
                f"Tool {t['name']}, property '{prop_name}' missing 'type'"
            )
            assert 'description' in prop_def, (
                f"Tool {t['name']}, property '{prop_name}' missing 'description'"
            )
    print("  PASS: All properties have type and description")
    return True


def test_rank_paths_by_energy():
    """Test 3: rank_paths_by_energy returns correct structure."""
    print("\nTest 3: rank_paths_by_energy")
    result = rank_paths_by_energy()
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    paths = result['data']
    assert isinstance(paths, list), f"Expected list, got {type(paths)}"
    assert len(paths) > 0, "Expected at least one path"

    # Check first entry has all expected keys
    entry = paths[0]
    expected_keys = {'uuid', 'energy', 'energy_s', 'energy_p',
                     'path_length', 'path_types', 'path_uuids'}
    assert set(entry.keys()) == expected_keys, (
        f"Expected keys {expected_keys}, got {set(entry.keys())}"
    )

    # path_uuids should be list of strings (not Ray objects)
    assert isinstance(entry['path_uuids'], list), "path_uuids should be a list"
    if entry['path_uuids']:
        assert isinstance(entry['path_uuids'][0], str), (
            f"path_uuids entries should be strings, got {type(entry['path_uuids'][0])}"
        )

    # Results should be sorted by energy (descending)
    if len(paths) > 1:
        for i in range(len(paths) - 1):
            assert paths[i]['energy'] >= paths[i + 1]['energy'], (
                "Paths not sorted by energy descending"
            )

    print(f"  PASS: {len(paths)} paths, top energy={paths[0]['energy']:.4f}, "
          f"path_length={paths[0]['path_length']}")
    return True


def test_rank_paths_top_n():
    """Test 4: rank_paths_by_energy respects top_n."""
    print("\nTest 4: rank_paths_by_energy top_n")
    result = rank_paths_by_energy(top_n=2)
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    paths = result['data']
    assert len(paths) <= 2, f"Expected at most 2 paths, got {len(paths)}"
    print(f"  PASS: top_n=2 returned {len(paths)} paths")
    return True


def test_rank_paths_ill_typed_top_n():
    """Test 4b: C-AGENT-01 -- an ill-typed top_n returns an error dict, never raises.

    Regression test: top_n='x' used to raise an uncaught TypeError from the
    list slice (raw_results[:top_n]), instead of the agentic envelope's
    promised {"status": "error", "message": ...}. See
    dev_doc/architecture/contracts/C-AGENT-01.md.
    """
    print("\nTest 4b: rank_paths_by_energy with ill-typed top_n")
    result = rank_paths_by_energy(top_n='x')
    assert result['status'] == 'error', f"Expected error dict, got: {result}"
    assert 'message' in result
    print(f"  PASS: ill-typed top_n returns error dict: {result['message'][:60]}...")
    return True


def test_rank_paths_without_lineage(scene, segments):
    """Test 5: rank_paths_by_energy without lineage returns error."""
    print("\nTest 5: rank_paths_by_energy without lineage")
    clear_context()
    set_context(scene, segments)  # no lineage
    result = rank_paths_by_energy()
    assert result['status'] == 'error', f"Expected error, got: {result}"
    assert 'lineage' in result['message'].lower(), (
        f"Error message should mention lineage: {result['message']}"
    )
    print(f"  PASS: Returned error: {result['message'][:60]}...")
    return True


def test_check_energy_conservation():
    """Test 6: check_energy_conservation returns correct structure."""
    print("\nTest 6: check_energy_conservation")
    result = check_energy_conservation()
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    data = result['data']
    expected_keys = {'total_checks', 'violations', 'max_excess_ratio', 'is_valid'}
    assert set(data.keys()) == expected_keys, (
        f"Expected keys {expected_keys}, got {set(data.keys())}"
    )
    assert isinstance(data['is_valid'], bool), "is_valid should be bool"
    assert isinstance(data['violations'], list), "violations should be list"
    assert isinstance(data['total_checks'], int), "total_checks should be int"
    print(f"  PASS: is_valid={data['is_valid']}, "
          f"total_checks={data['total_checks']}, "
          f"violations={len(data['violations'])}")
    return True


def test_check_energy_without_lineage(scene, segments):
    """Test 7: check_energy_conservation without lineage returns error."""
    print("\nTest 7: check_energy_conservation without lineage")
    clear_context()
    set_context(scene, segments)  # no lineage
    result = check_energy_conservation()
    assert result['status'] == 'error', f"Expected error, got: {result}"
    assert 'lineage' in result['message'].lower(), (
        f"Error message should mention lineage: {result['message']}"
    )
    print(f"  PASS: Returned error: {result['message'][:60]}...")
    return True


def test_fresnel_transmittances_tool():
    """Test 8: fresnel_transmittances_tool returns Fresnel data."""
    print("\nTest 8: fresnel_transmittances_tool")
    result = fresnel_transmittances_tool(n1=1.0, n2=1.5, theta_i_deg=30.0)
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    data = result['data']
    expected_keys = {'T_s', 'T_p', 'R_s', 'R_p', 'ratio_Tp_Ts', 'theta_t_deg'}
    assert set(data.keys()) == expected_keys, (
        f"Expected keys {expected_keys}, got {set(data.keys())}"
    )
    # Transmittance + reflectance should sum to 1
    assert abs(data['T_s'] + data['R_s'] - 1.0) < 1e-10, "T_s + R_s != 1"
    assert abs(data['T_p'] + data['R_p'] - 1.0) < 1e-10, "T_p + R_p != 1"
    print(f"  PASS: T_s={data['T_s']:.4f}, T_p={data['T_p']:.4f}, "
          f"theta_t={data['theta_t_deg']:.2f} deg")
    return True


def test_fresnel_tir():
    """Test 9: fresnel_transmittances_tool returns error for TIR."""
    print("\nTest 9: fresnel_transmittances_tool TIR")
    # n1=1.5 > n2=1.0, theta_i=60 > critical angle ~41.8 deg
    result = fresnel_transmittances_tool(n1=1.5, n2=1.0, theta_i_deg=60.0)
    assert result['status'] == 'error', f"Expected error for TIR, got: {result}"
    assert 'total internal reflection' in result['message'].lower(), (
        f"Error message should mention TIR: {result['message']}"
    )
    print(f"  PASS: TIR error: {result['message'][:60]}...")
    return True


def test_fresnel_no_context():
    """Test 10: fresnel_transmittances_tool works without set_context."""
    print("\nTest 10: fresnel_transmittances_tool without context")
    clear_context()
    result = fresnel_transmittances_tool(n1=1.0, n2=1.5, theta_i_deg=0.0)
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    # At normal incidence, T_s == T_p
    data = result['data']
    assert abs(data['T_s'] - data['T_p']) < 1e-10, (
        f"At normal incidence T_s should equal T_p: {data['T_s']} vs {data['T_p']}"
    )
    print(f"  PASS: Normal incidence T_s=T_p={data['T_s']:.6f}")
    return True


def test_fresnel_ill_typed_args():
    """Test 10b: C-AGENT-01 -- ill-typed args return an error dict, never raise.

    Regression test for a confirmed live counterexample: string arguments
    used to raise an uncaught TypeError (the except clause caught ValueError
    only), instead of the agentic envelope's promised {"status": "error",
    "message": ...}. See dev_doc/architecture/contracts/C-AGENT-01.md.
    """
    print("\nTest 10b: fresnel_transmittances_tool with ill-typed args")
    result = fresnel_transmittances_tool(n1='a', n2='b', theta_i_deg='c')
    assert result['status'] == 'error', f"Expected error dict, got: {result}"
    assert 'message' in result
    print(f"  PASS: ill-typed args return error dict: {result['message'][:60]}...")
    return True


def test_tool_registry_new_tools():
    """Test 11: Tool registry includes Phase 2 tools."""
    print("\nTest 11: Tool registry includes Phase 2 tools")
    tools = get_agentic_tools()
    names = [t['name'] for t in tools]
    assert 'rank_paths_by_energy' in names, "rank_paths_by_energy missing"
    assert 'check_energy_conservation' in names, "check_energy_conservation missing"
    assert 'fresnel_transmittances' in names, "fresnel_transmittances missing"
    print("  PASS: All 3 Phase 2 tools in registry")
    return True


def test_tool_registry_count():
    """Test 12: Total tool count is 22 (19 + path_surfaces/audit_bidirectional_paths/
    path_physical_summary -- bidirectional path auditing)."""
    print("\nTest 12: Tool count")
    tools = get_agentic_tools()
    expected = 22
    assert len(tools) == expected, (
        f"Expected {expected} tools, got {len(tools)}: "
        f"{[t['name'] for t in tools]}"
    )
    print(f"  PASS: {len(tools)} tools total")
    return True


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 70)
    print("Phase 2: JSON Schema + Lineage Wrappers - Feature Verification")
    print("=" * 70)

    # --- Setup ---
    print("\nSetup: Building scene and running simulation...")
    scene, prism = build_test_scene()
    segments, lineage = run_simulation(scene)
    print(f"  Scene has {len(scene.objs)} objects, "
          f"simulation produced {len(segments)} segments, "
          f"lineage has {lineage.segment_count} nodes")

    # Set context WITH lineage for most tests
    set_context(scene, segments, lineage=lineage)
    print("  Context set (with lineage).\n")

    # --- Run tests ---
    results = []
    results.append(("input_schema on all tools",    test_all_tools_have_input_schema()))
    results.append(("schema properties typed",       test_schema_properties_have_types()))
    results.append(("rank_paths_by_energy",          test_rank_paths_by_energy()))
    results.append(("rank_paths top_n",              test_rank_paths_top_n()))
    results.append(("rank_paths ill-typed top_n",     test_rank_paths_ill_typed_top_n()))

    # Tests 5 and 7 modify context -- run them, then restore
    results.append(("rank_paths no lineage",         test_rank_paths_without_lineage(scene, segments)))
    set_context(scene, segments, lineage=lineage)
    results.append(("check_energy_conservation",     test_check_energy_conservation()))
    results.append(("check_energy no lineage",       test_check_energy_without_lineage(scene, segments)))
    set_context(scene, segments, lineage=lineage)

    results.append(("fresnel_transmittances_tool",   test_fresnel_transmittances_tool()))
    results.append(("fresnel TIR error",             test_fresnel_tir()))
    results.append(("fresnel no context",            test_fresnel_no_context()))
    results.append(("fresnel ill-typed args",        test_fresnel_ill_typed_args()))

    # Restore context for registry tests
    set_context(scene, segments, lineage=lineage)
    results.append(("tool registry new tools",       test_tool_registry_new_tools()))
    results.append(("tool registry count",           test_tool_registry_count()))

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
        print("\nAll Phase 2 schema + lineage tools verified successfully!")
    else:
        print("\nSome tests failed.")
        sys.exit(1)


if __name__ == '__main__':
    main()
