"""
===============================================================================
NONIMAGING PRISM TESTS -- Nonimaging Optics Phase 1, Step 3
===============================================================================
Tests DTIRCPrism (optical_elements.prisms.dtirc), the first fixture from
15_p3_cpc_and_sms_optical_elements.md: geometry sanity (vertex count, CCW ordering,
closed-form invariants independently re-derived from Example 3.6's own
formulas) and _edge_roles/Role correctness.

Run with:
    python developer_tests/test_nonimaging_prisms.py
Or with pytest:
    pytest developer_tests/test_nonimaging_prisms.py -v
===============================================================================
"""

import math
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

TOL = 1e-6


def _path_point(prism, index):
    p = prism.path[index]
    return (p['x'], p['y'])


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_dtirc_default_construction():
    """A default DTIRCPrism builds without error and is CCW."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism

    scene = Scene()
    prism = DTIRCPrism(scene, theta_deg=10.0, n=1.5)

    expected_count = 2 * prism.wall_segments + prism.entrance_arc_segments + 1
    assert len(prism.path) == expected_count, (
        f"expected {expected_count} vertices, got {len(prism.path)}"
    )
    assert prism.signed_area() > 0, "DTIRCPrism should be CCW (positive signed area)"
    print(f"  PASS: default construction, {len(prism.path)} vertices, CCW")
    return True


def test_dtirc_closed_form_invariants():
    """Exit-aperture width and entrance-aperture chord match independently
    re-derived closed-form expressions from Example 3.6 (eqs. 3.37, 3.42)."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism

    scene = Scene()
    theta_deg, n, phi_edge_deg = 10.0, 1.5, 50.0
    prism = DTIRCPrism(scene, theta_deg=theta_deg, n=n, phi_edge_deg=phi_edge_deg,
                        wall_segments=16, entrance_arc_segments=8)

    theta = math.radians(theta_deg)
    phi_edge = math.radians(phi_edge_deg)

    # Entrance aperture chord [P1,P2] = 2*sin(phi_edge) at unit radius (eq. 3.37).
    expected_chord = 2 * math.sin(phi_edge)
    P2 = _path_point(prism, prism.wall_segments + 1)
    P1 = _path_point(prism, prism.wall_segments + prism.entrance_arc_segments + 1)
    actual_chord = _dist(P1, P2)
    assert abs(actual_chord - expected_chord) < TOL, (
        f"entrance chord: expected {expected_chord}, got {actual_chord}"
    )

    # Exit aperture width R = [P1,P2]*sin(theta)/n (eq. 3.42).
    expected_R = expected_chord * math.sin(theta) / n
    R1 = _path_point(prism, 0)
    R2 = _path_point(prism, 1)
    actual_R = _dist(R1, R2)
    assert abs(actual_R - expected_R) < TOL, (
        f"exit aperture width: expected {expected_R}, got {actual_R}"
    )
    print("  PASS: entrance chord and exit aperture width match closed-form")
    return True


def test_dtirc_edge_roles():
    """_edge_roles tags exit/wall/entrance edges with the right Role, per
    the CCW ordering R1->R2->[right wall]->P2->[entrance]->P1->[left wall]."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism
    from ray_tracing_shapely.optical_elements.roles import Role

    scene = Scene()
    prism = DTIRCPrism(scene, theta_deg=10.0, n=1.5, wall_segments=16, entrance_arc_segments=8)

    assert prism.get_edge_role(0) is Role.ABSORBER, "edge 0 (exit) should be ABSORBER"
    assert prism.get_functional_label(0)[0] == "EX"

    assert prism.get_edge_role(1) is Role.WALL, "first right-wall edge should be WALL"
    assert prism.get_edge_role(prism.wall_segments) is Role.WALL, "last right-wall edge should be WALL"

    first_entrance_edge = prism.wall_segments + 1
    last_entrance_edge = prism.wall_segments + prism.entrance_arc_segments
    assert prism.get_edge_role(first_entrance_edge) is Role.ENTRANCE
    assert prism.get_edge_role(last_entrance_edge) is Role.ENTRANCE
    assert prism.get_functional_label(first_entrance_edge)[0] == "EN"

    last_edge = 2 * prism.wall_segments + prism.entrance_arc_segments
    assert prism.get_edge_role(last_edge) is Role.WALL, "last left-wall edge should be WALL"

    # label_summary() should not raise (exercises the dual-labelling machinery end to end).
    summary = prism.label_summary()
    assert "Exit Aperture" in summary and "Entrance Aperture" in summary
    print("  PASS: _edge_roles / get_edge_role match the CCW edge layout")
    return True


def test_dtirc_minimum_wall_segments():
    """wall_segments=1 (no interior wall points) still builds a valid polygon."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism

    scene = Scene()
    prism = DTIRCPrism(scene, theta_deg=10.0, n=1.5, wall_segments=1, entrance_arc_segments=4)

    expected_count = 2 * 1 + 4 + 1
    assert len(prism.path) == expected_count
    assert prism.signed_area() > 0
    print("  PASS: wall_segments=1 minimum builds a valid CCW polygon")
    return True


def test_dtirc_parameter_validation():
    """Out-of-range parameters raise ValueError."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism

    scene = Scene()
    for kwargs in [
        dict(theta_deg=0.0, n=1.5),
        dict(theta_deg=95.0, n=1.5),
        dict(theta_deg=10.0, n=1.5, phi_edge_deg=0.0),
        dict(theta_deg=10.0, n=1.5, wall_segments=0),
        dict(theta_deg=10.0, n=1.5, entrance_arc_segments=0),
    ]:
        try:
            DTIRCPrism(scene, **kwargs)
            raise AssertionError(f"expected ValueError for {kwargs}")
        except ValueError:
            pass
    print("  PASS: out-of-range parameters raise ValueError")
    return True


def run_all_tests():
    tests = [
        ("Default construction (CCW, vertex count)", test_dtirc_default_construction),
        ("Closed-form invariants vs Example 3.6", test_dtirc_closed_form_invariants),
        ("_edge_roles / Role tagging", test_dtirc_edge_roles),
        ("Minimum wall_segments=1", test_dtirc_minimum_wall_segments),
        ("Parameter validation", test_dtirc_parameter_validation),
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
