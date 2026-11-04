"""
Python-specific module: test tir analysis
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
TIR Analysis - Feature Verification
===============================================================================

Tests the tir_analysis pure-physics function and the tir_analysis_tool
agentic wrapper.

USAGE
-----
    python -m ray_tracing_shapely.developer_tests.test_tir_analysis

===============================================================================
"""

import sys
import os
import math

# Ensure the package is importable when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from ray_tracing_shapely.analysis.fresnel_utils import (
    tir_analysis,
    critical_angle,
    brewster_angle,
)
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.analysis.agentic_tools import (
    set_context,
    clear_context,
    tir_analysis_tool,
)


# =============================================================================
# Helpers
# =============================================================================

# All output keys that must be present in every tir_analysis result
_EXPECTED_KEYS = {
    'regime', 'near_tir', 'near_brewster', 'angle_provided',
    'n1', 'n2', 'theta_i_deg', 'tir_angle_deg', 'brewster_angle_deg',
    'delta_angle_deg',
    'T_s', 'T_p', 'R_s', 'R_p', 'ratio_Tp_Ts', 'theta_t_deg',
    'delta_s_deg', 'delta_p_deg', 'delta_relative_deg',
}


def build_two_glass_scene():
    """Build a scene with two adjacent glasses of different n."""
    scene = Scene()

    # Higher-n glass (n=1.72)
    glass_high = Glass(scene)
    glass_high.path = [
        {'x': 100, 'y': 50, 'arc': False},
        {'x': 200, 'y': 50, 'arc': False},
        {'x': 200, 'y': 150, 'arc': False},
        {'x': 100, 'y': 150, 'arc': False},
    ]
    glass_high.refIndex = 1.72
    glass_high.name = 'Flint Glass'
    scene.add_object(glass_high)

    # Lower-n glass (n=1.52)
    glass_low = Glass(scene)
    glass_low.path = [
        {'x': 200, 'y': 50, 'arc': False},
        {'x': 300, 'y': 50, 'arc': False},
        {'x': 300, 'y': 150, 'arc': False},
        {'x': 200, 'y': 150, 'arc': False},
    ]
    glass_low.refIndex = 1.52
    glass_low.name = 'Crown Glass'
    scene.add_object(glass_low)

    # A ray source to make the scene simulatable
    ray_src = SingleRay(scene)
    ray_src.p1 = {'x': 50, 'y': 100}
    ray_src.p2 = {'x': 150, 'y': 100}
    ray_src.brightness = 1.0
    scene.add_object(ray_src)

    glass_high.auto_label_cardinal()
    glass_low.auto_label_cardinal()

    return scene


# =============================================================================
# Fixtures -- the same objects main() passes as arguments, for pytest
# =============================================================================
# Unlike its siblings this module has no run_simulation() helper: main() drives
# the Simulator inline and takes the lineage off it, so the fixture does the
# same rather than inventing a helper the script route would not use.

@pytest.fixture(scope="module")
def _sim():
    scene = build_two_glass_scene()
    sim = Simulator(scene)
    segments = sim.run()
    return scene, segments, sim.lineage


@pytest.fixture(scope="module")
def scene(_sim):
    return _sim[0]


@pytest.fixture(scope="module")
def segments(_sim):
    return _sim[1]


@pytest.fixture(scope="module")
def lineage(_sim):
    return _sim[2]


@pytest.fixture(autouse=True)
def _context(scene, segments, lineage):
    """One test here clears the context on purpose to check the error path.

    main() restores it by hand afterwards -- "Restore context for remaining
    tests". Setting it per test makes that unnecessary.
    """
    set_context(scene, segments, lineage=lineage)
    yield


# =============================================================================
# Pure-physics tests (tir_analysis)
# =============================================================================

def test_tir_analysis_refraction_regime():
    """Test 1: Sub-critical angle produces refraction regime."""
    print("\nTest 1: tir_analysis refraction regime")
    result = tir_analysis(n1=1.72, n2=1.52, theta_i_deg=30.0)
    assert set(result.keys()) == _EXPECTED_KEYS, (
        f"Missing keys: {_EXPECTED_KEYS - set(result.keys())}"
    )
    assert result['regime'] == 'refraction'
    assert result['angle_provided'] is True
    assert result['T_s'] is not None
    assert result['T_p'] is not None
    assert result['theta_t_deg'] is not None
    # Energy conservation: T + R = 1
    assert abs(result['T_s'] + result['R_s'] - 1.0) < 1e-10, "T_s + R_s != 1"
    assert abs(result['T_p'] + result['R_p'] - 1.0) < 1e-10, "T_p + R_p != 1"
    print(f"  PASS: regime={result['regime']}, T_s={result['T_s']:.4f}, "
          f"delta_s={result['delta_s_deg']:.1f} deg")
    return True


def test_tir_analysis_tir_regime():
    """Test 2: Super-critical angle produces TIR regime."""
    print("\nTest 2: tir_analysis TIR regime")
    result = tir_analysis(n1=1.72, n2=1.52, theta_i_deg=75.0)
    assert result['regime'] == 'tir'
    assert result['angle_provided'] is True
    assert result['T_s'] is None
    assert result['T_p'] is None
    assert result['R_s'] == 1.0
    assert result['R_p'] == 1.0
    assert result['ratio_Tp_Ts'] is None
    assert result['theta_t_deg'] is None
    # Phase shifts should be non-trivial (not 0 or 180)
    assert 0 < result['delta_s_deg'] < 180, (
        f"Expected non-trivial delta_s, got {result['delta_s_deg']}"
    )
    assert 0 < result['delta_p_deg'] < 180, (
        f"Expected non-trivial delta_p, got {result['delta_p_deg']}"
    )
    assert abs(result['delta_relative_deg'] -
               (result['delta_p_deg'] - result['delta_s_deg'])) < 1e-10
    print(f"  PASS: regime={result['regime']}, delta_s={result['delta_s_deg']:.2f}, "
          f"delta_p={result['delta_p_deg']:.2f}, "
          f"delta_rel={result['delta_relative_deg']:.2f}")
    return True


def test_tir_analysis_no_angle():
    """Test 3: No angle provided defaults to TIR + delta."""
    print("\nTest 3: tir_analysis no angle (defaults to TIR + delta)")
    result = tir_analysis(n1=1.5, n2=1.0, delta_angle_deg=2.0)
    tir_deg = critical_angle(1.5, 1.0)
    expected_angle = tir_deg + 2.0
    assert result['angle_provided'] is False
    assert abs(result['theta_i_deg'] - expected_angle) < 1e-10, (
        f"Expected angle {expected_angle}, got {result['theta_i_deg']}"
    )
    assert result['regime'] == 'tir'
    assert result['near_tir'] is True
    print(f"  PASS: angle_provided=False, theta_i={result['theta_i_deg']:.2f}, "
          f"regime={result['regime']}")
    return True


def test_tir_analysis_near_tir_flag():
    """Test 4: near_tir flag within delta_angle of critical angle."""
    print("\nTest 4: near_tir flag")
    tir_deg = critical_angle(1.5, 1.0)

    # Just below TIR
    result_near = tir_analysis(n1=1.5, n2=1.0,
                               theta_i_deg=tir_deg - 0.5,
                               delta_angle_deg=1.0)
    assert result_near['near_tir'] is True, "Should be near TIR"

    # Far from TIR
    result_far = tir_analysis(n1=1.5, n2=1.0,
                              theta_i_deg=20.0,
                              delta_angle_deg=1.0)
    assert result_far['near_tir'] is False, "Should NOT be near TIR"

    print(f"  PASS: near_tir=True at {tir_deg - 0.5:.2f} deg, "
          f"near_tir=False at 20.0 deg")
    return True


def test_tir_analysis_near_brewster_flag():
    """Test 5: near_brewster flag within delta_angle of Brewster's angle."""
    print("\nTest 5: near_brewster flag")
    brew_deg = brewster_angle(1.5, 1.0)

    result_near = tir_analysis(n1=1.5, n2=1.0,
                               theta_i_deg=brew_deg + 0.3,
                               delta_angle_deg=1.0)
    assert result_near['near_brewster'] is True, "Should be near Brewster"

    result_far = tir_analysis(n1=1.5, n2=1.0,
                              theta_i_deg=20.0,
                              delta_angle_deg=1.0)
    assert result_far['near_brewster'] is False, "Should NOT be near Brewster"

    print(f"  PASS: near_brewster=True at {brew_deg + 0.3:.2f} deg, "
          f"near_brewster=False at 20.0 deg")
    return True


def test_tir_analysis_n1_leq_n2():
    """Test 6: ValueError when n1 <= n2."""
    print("\nTest 6: ValueError when n1 <= n2")
    try:
        tir_analysis(n1=1.0, n2=1.5, theta_i_deg=30.0)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert 'n1' in str(e) and 'n2' in str(e)
    print("  PASS: ValueError raised for n1 <= n2")
    return True


def test_tir_analysis_phase_at_brewster():
    """Test 7: At Brewster angle, p-polarization phase flips to 0."""
    print("\nTest 7: Phase shift at Brewster angle")
    brew_deg = brewster_angle(1.5, 1.0)

    # Just below Brewster: delta_p should be 180 (pi)
    result_below = tir_analysis(n1=1.5, n2=1.0,
                                theta_i_deg=brew_deg - 2.0)
    assert result_below['delta_p_deg'] == 180.0, (
        f"Expected delta_p=180 below Brewster, got {result_below['delta_p_deg']}"
    )

    # Just above Brewster: delta_p should be 0
    result_above = tir_analysis(n1=1.5, n2=1.0,
                                theta_i_deg=brew_deg + 2.0)
    assert result_above['delta_p_deg'] == 0.0, (
        f"Expected delta_p=0 above Brewster, got {result_above['delta_p_deg']}"
    )

    # s-polarization should be 0 everywhere below TIR (for n1 > n2)
    assert result_below['delta_s_deg'] == 0.0
    assert result_above['delta_s_deg'] == 0.0

    print(f"  PASS: delta_p=180 below Brewster ({brew_deg - 2:.2f} deg), "
          f"delta_p=0 above Brewster ({brew_deg + 2:.2f} deg)")
    return True


def test_tir_analysis_continuity_at_critical():
    """Test 8: Phase shifts approach known limits near critical angle."""
    print("\nTest 8: Phase shift continuity near critical angle")
    tir_deg = critical_angle(1.5, 1.0)

    # Just above TIR: phase shifts should be small (close to 0)
    result = tir_analysis(n1=1.5, n2=1.0,
                          theta_i_deg=tir_deg + 0.01)
    assert result['regime'] == 'tir'
    assert result['delta_s_deg'] < 5.0, (
        f"Phase shift should be small near TIR, got {result['delta_s_deg']}"
    )

    # Well above TIR: phase shifts should be larger
    result_far = tir_analysis(n1=1.5, n2=1.0,
                              theta_i_deg=80.0)
    assert result_far['delta_s_deg'] > result['delta_s_deg'], (
        "Phase shift should increase with angle above TIR"
    )

    print(f"  PASS: delta_s={result['delta_s_deg']:.4f} near TIR, "
          f"delta_s={result_far['delta_s_deg']:.2f} at 80 deg")
    return True


def test_tir_analysis_known_values():
    """Test 9: Check against manually computed values for glass-air."""
    print("\nTest 9: Known values for glass-to-air (n=1.5)")
    # Critical angle for n1=1.5, n2=1.0 is arcsin(1/1.5) ≈ 41.81 deg
    tir_deg = critical_angle(1.5, 1.0)
    assert abs(tir_deg - math.degrees(math.asin(1.0 / 1.5))) < 1e-10

    # Brewster angle: arctan(1.0/1.5) ≈ 33.69 deg
    brew_deg = brewster_angle(1.5, 1.0)
    assert abs(brew_deg - math.degrees(math.atan(1.0 / 1.5))) < 1e-10

    result = tir_analysis(n1=1.5, n2=1.0, theta_i_deg=tir_deg + 1.0)
    assert result['regime'] == 'tir'
    assert abs(result['tir_angle_deg'] - tir_deg) < 1e-10
    assert abs(result['brewster_angle_deg'] - brew_deg) < 1e-10

    print(f"  PASS: TIR={tir_deg:.4f} deg, Brewster={brew_deg:.4f} deg")
    return True


# =============================================================================
# Agentic wrapper tests (tir_analysis_tool)
# =============================================================================

def test_tool_refraction(scene):
    """Test 10: tir_analysis_tool in refraction regime."""
    print("\nTest 10: tir_analysis_tool refraction regime")
    result = tir_analysis_tool(
        glass_name_high_n='Flint Glass',
        glass_name_low_n='Crown Glass',
        theta_i_deg=30.0,
    )
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    data = result['data']
    assert data['regime'] == 'refraction'
    assert data['glass_high_n'] == 'Flint Glass'
    assert data['glass_low_n'] == 'Crown Glass'
    assert data['n1'] == 1.72
    assert data['n2'] == 1.52
    print(f"  PASS: status=ok, regime={data['regime']}")
    return True


def test_tool_tir(scene):
    """Test 11: tir_analysis_tool in TIR regime."""
    print("\nTest 11: tir_analysis_tool TIR regime")
    result = tir_analysis_tool(
        glass_name_high_n='Flint Glass',
        glass_name_low_n='Crown Glass',
        theta_i_deg=75.0,
    )
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    data = result['data']
    assert data['regime'] == 'tir'
    assert data['R_s'] == 1.0
    assert data['T_s'] is None
    print(f"  PASS: regime=tir, delta_rel={data['delta_relative_deg']:.2f} deg")
    return True


def test_tool_wrong_order(scene):
    """Test 12: Error when glasses are in wrong order."""
    print("\nTest 12: tir_analysis_tool wrong glass order")
    result = tir_analysis_tool(
        glass_name_high_n='Crown Glass',
        glass_name_low_n='Flint Glass',
    )
    assert result['status'] == 'error', f"Expected error, got: {result}"
    assert 'swap' in result['message'].lower(), (
        f"Error should suggest swapping: {result['message']}"
    )
    print(f"  PASS: Error with swap hint: {result['message'][:80]}...")
    return True


def test_tool_glass_not_found(scene):
    """Test 13: Error when glass name doesn't exist."""
    print("\nTest 13: tir_analysis_tool glass not found")
    result = tir_analysis_tool(
        glass_name_high_n='Nonexistent',
        glass_name_low_n='Crown Glass',
    )
    assert result['status'] == 'error', f"Expected error, got: {result}"
    assert 'nonexistent' in result['message'].lower() or \
           'no object' in result['message'].lower(), (
        f"Error should mention missing name: {result['message']}"
    )
    print(f"  PASS: Error: {result['message'][:80]}...")
    return True


def test_tool_no_context():
    """Test 14: Error when context is not set."""
    print("\nTest 14: tir_analysis_tool without context")
    clear_context()
    result = tir_analysis_tool(
        glass_name_high_n='Flint Glass',
        glass_name_low_n='Crown Glass',
    )
    assert result['status'] == 'error', f"Expected error, got: {result}"
    assert 'context' in result['message'].lower(), (
        f"Error should mention context: {result['message']}"
    )
    print(f"  PASS: Error: {result['message'][:60]}...")
    return True


def test_tool_no_angle(scene):
    """Test 15: tir_analysis_tool defaults when no angle is provided."""
    print("\nTest 15: tir_analysis_tool no angle provided")
    result = tir_analysis_tool(
        glass_name_high_n='Flint Glass',
        glass_name_low_n='Crown Glass',
    )
    assert result['status'] == 'ok', f"Expected ok, got: {result}"
    data = result['data']
    assert data['angle_provided'] is False
    assert data['regime'] == 'tir'
    assert data['near_tir'] is True
    print(f"  PASS: angle_provided=False, theta_i={data['theta_i_deg']:.2f} deg")
    return True


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 70)
    print("TIR Analysis - Feature Verification")
    print("=" * 70)

    results = []

    # --- Pure-physics tests ---
    print("\n--- Pure-physics tests (tir_analysis) ---")
    results.append(("refraction regime",        test_tir_analysis_refraction_regime()))
    results.append(("TIR regime",               test_tir_analysis_tir_regime()))
    results.append(("no angle default",          test_tir_analysis_no_angle()))
    results.append(("near_tir flag",             test_tir_analysis_near_tir_flag()))
    results.append(("near_brewster flag",        test_tir_analysis_near_brewster_flag()))
    results.append(("n1 <= n2 error",            test_tir_analysis_n1_leq_n2()))
    results.append(("phase at Brewster",         test_tir_analysis_phase_at_brewster()))
    results.append(("continuity at critical",    test_tir_analysis_continuity_at_critical()))
    results.append(("known values",              test_tir_analysis_known_values()))

    # --- Agentic wrapper tests ---
    print("\n--- Agentic wrapper tests (tir_analysis_tool) ---")

    scene = build_two_glass_scene()
    sim = Simulator(scene)
    segments = sim.run()
    set_context(scene, segments, lineage=sim.lineage)
    print(f"\nSetup: scene with {len(scene.objs)} objects, "
          f"{len(segments)} ray segments")

    results.append(("tool refraction",           test_tool_refraction(scene)))
    results.append(("tool TIR",                  test_tool_tir(scene)))
    results.append(("tool wrong order",          test_tool_wrong_order(scene)))
    results.append(("tool glass not found",      test_tool_glass_not_found(scene)))
    results.append(("tool no context",           test_tool_no_context()))

    # Restore context for remaining tests
    set_context(scene, segments, lineage=sim.lineage)
    results.append(("tool no angle",             test_tool_no_angle(scene)))

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
        print("\nAll TIR analysis tests passed!")
    else:
        print("\nSome tests failed.")
        sys.exit(1)


if __name__ == '__main__':
    main()
