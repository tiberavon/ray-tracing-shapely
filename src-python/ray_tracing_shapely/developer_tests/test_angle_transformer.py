"""
===============================================================================
ANGLE TRANSFORMER TESTS -- Nonimaging Optics Phase 2, Step 1
===============================================================================
Tests build_angle_transformer (optical_elements.prisms.angle_transformer)
against chapter_03.md Example 3.3's published numbers, the theta2->90deg
analytic CPC limit (15_p2_bidirectional_ray_tracing_rational.md §7.2/§7.3), and a
real Simulator smoke test.

Run with:
    python developer_tests/test_angle_transformer.py
Or with pytest:
    pytest developer_tests/test_angle_transformer.py -v
===============================================================================
"""

import math
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

TOL = 1e-4


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_angle_transformer_example_3_3():
    """P/Q match chapter_03.md Example 3.3 (theta1=30, theta2=70)."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.angle_transformer import build_angle_transformer

    scene = Scene()
    device = build_angle_transformer(scene, theta1_deg=30.0, theta2_deg=70.0)

    assert _dist(device['P'], (0.652704, 0.41955)) < TOL, f"P={device['P']}"
    assert _dist(device['Q'], (-0.652704, 0.41955)) < TOL, f"Q={device['Q']}"
    assert _dist(device['E'], (0.5, 0.0)) < TOL
    assert _dist(device['F'], (-0.5, 0.0)) < TOL

    # 4 mirrors: flat_right, arc_right_seg0, flat_left, arc_left_seg0 (n_arc_segments=1 default).
    assert len(device['mirrors']) == 4
    assert len(scene.objs) == 4
    names = {m.name for m in device['mirrors']}
    assert names == {
        'angle_xform_flat_right', 'angle_xform_arc_right_seg0',
        'angle_xform_flat_left', 'angle_xform_arc_left_seg0',
    }
    from ray_tracing_shapely.optical_elements.roles import Role
    assert all(m.role is Role.WALL for m in device['mirrors'])
    print("  PASS: P/Q/E/F match Example 3.3; 4 named, role-tagged mirrors")
    return True


def test_angle_transformer_theta2_to_90_limit():
    """As theta2 -> 90deg, the flat mirror segment [E,P] shrinks toward
    zero length -- the analytic CPC limit (Fig. 3.5 caption)."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.angle_transformer import build_angle_transformer

    lengths = []
    for theta2_deg in [70.0, 80.0, 85.0, 89.0, 89.9]:
        scene = Scene()
        device = build_angle_transformer(scene, theta1_deg=30.0, theta2_deg=theta2_deg)
        lengths.append(_dist(device['E'], device['P']))

    # Monotonically decreasing, and small near theta2=90.
    assert all(lengths[i] > lengths[i + 1] for i in range(len(lengths) - 1)), lengths
    assert lengths[-1] < 0.01, f"expected near-zero flat segment near theta2=90, got {lengths[-1]}"
    print(f"  PASS: flat segment length shrinks monotonically toward 0 ({lengths[0]:.4f} -> {lengths[-1]:.6f})")
    return True


def test_angle_transformer_parameter_validation():
    """Out-of-range parameters raise ValueError."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.angle_transformer import build_angle_transformer

    for kwargs in [
        dict(theta1_deg=0.0, theta2_deg=70.0),
        dict(theta1_deg=30.0, theta2_deg=0.0),
        dict(theta1_deg=30.0, theta2_deg=95.0),
        dict(theta1_deg=30.0, theta2_deg=70.0, n_arc_segments=0),
    ]:
        scene = Scene()
        try:
            build_angle_transformer(scene, **kwargs)
            raise AssertionError(f"expected ValueError for {kwargs}")
        except ValueError:
            pass
    print("  PASS: out-of-range parameters raise ValueError")
    return True


def test_angle_transformer_multi_segment_arc():
    """n_arc_segments > 1 produces distinctly-named Mirror objects tracing
    the same arc endpoints, each still reporting edge_index=0 (Mirror has
    no polyline) -- position lives in surface_name instead."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.angle_transformer import build_angle_transformer
    from ray_tracing_shapely.analysis.bidirectional import _surface_edges

    scene = Scene()
    device = build_angle_transformer(scene, theta1_deg=30.0, theta2_deg=70.0, n_arc_segments=4)

    arc_mirrors = [m for m in device['mirrors'] if 'arc_right' in m.name]
    assert len(arc_mirrors) == 4
    names = [m.name for m in arc_mirrors]
    assert names == [f'angle_xform_arc_right_seg{i}' for i in range(4)]

    for m in arc_mirrors:
        edges = _surface_edges(m)
        assert len(edges) == 1 and edges[0][0] == 0, "Mirror should always report edge_index=0"

    # Chained: seg_i's p2 should equal seg_{i+1}'s p1 (a continuous polyline).
    for i in range(3):
        p2 = arc_mirrors[i].p2
        p1_next = arc_mirrors[i + 1].p1
        assert abs(p2['x'] - p1_next['x']) < 1e-9 and abs(p2['y'] - p1_next['y']) < 1e-9

    # Last segment's p2 should be point A.
    last_p2 = arc_mirrors[-1].p2
    assert _dist((last_p2['x'], last_p2['y']), device['A']) < TOL
    print("  PASS: multi-segment arc is a continuous chain of distinctly-named Mirrors")
    return True


def test_angle_transformer_simulator_smoke():
    """A built device traces through the real Simulator without error."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
    from ray_tracing_shapely.core.simulator import Simulator
    from ray_tracing_shapely.optical_elements.prisms.angle_transformer import build_angle_transformer

    scene = Scene()
    scene.ray_density = 10
    device = build_angle_transformer(scene, theta1_deg=30.0, theta2_deg=70.0)

    ay = device['A'][1]
    source = AngleSource(scene)
    source.p1 = {'x': 0.0, 'y': ay + 3.0}
    source.p2 = {'x': 0.0, 'y': ay + 1.0}
    source.emis_angle = 50.0
    source.symmetric = True
    source.brightness = 1.0
    source.name = 'src'
    scene.add_object(source)

    sim = Simulator(scene, max_rays=2000)
    segments = sim.run()
    assert scene.error is None, f"scene error: {scene.error}"
    types = {s.interaction_type for s in segments}
    assert 'reflect' in types, f"expected at least one mirror reflection, got types={types}"
    print(f"  PASS: traced {len(segments)} segments, interaction types={types}")
    return True


def run_all_tests():
    tests = [
        ("Example 3.3 geometry (P/Q/E/F)", test_angle_transformer_example_3_3),
        ("theta2 -> 90deg CPC limit", test_angle_transformer_theta2_to_90_limit),
        ("Parameter validation", test_angle_transformer_parameter_validation),
        ("Multi-segment arc naming/chaining", test_angle_transformer_multi_segment_arc),
        ("Simulator smoke test", test_angle_transformer_simulator_smoke),
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
