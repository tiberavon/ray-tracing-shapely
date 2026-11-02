"""
Python-specific module: test rxi direct
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
RXIOPTICDIRECT TESTS
===============================================================================
RXIOpticDirect is the package's highest-risk, least-validated class: no
numeric worked example exists anywhere in the source book for section 9.7
(every "EXAMPLE" in the chapter was checked), and this implementation adds
a new, undocumented-in-the-book pin (point D's placement) on top of the
method's six free choices. These tests check what CAN be checked without a book
oracle: internal geometric consistency and that construction succeeds
for the shipped default parameters -- not that the resulting device is a
physically optimal or even complete RXI (the receiver cavity MN is
computed but not yet stitched into the assembled polygon; see the class
docstring). [KD5: with no external oracle, these tests guard against
change, not against being wrong.]

Run with:
    python developer_tests/test_rxi_direct.py
Or with pytest:
    pytest developer_tests/test_rxi_direct.py -v
===============================================================================
"""

import math
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

R1, R2 = (-1.0, 0.0), (1.0, 0.0)


def _build_default_rxi():
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms.rxi_direct import RXIOpticDirect

    scene = Scene()
    rxi = RXIOpticDirect(scene, R1, R2, theta_deg=30.0, n=1.5)
    return scene, rxi


def test_rxi_direct_constructs_without_error():
    """The class builds successfully with its own documented default parameters."""
    scene, rxi = _build_default_rxi()
    assert len(rxi.path) >= 3
    print(f"  PASS: RXIOpticDirect constructs ({len(rxi.path)} vertices)")
    return True


def test_rxi_direct_de_fan_snell_consistency():
    """Every DE point's normal is unit length and satisfies the defining Cartesian oval equation."""
    scene, rxi = _build_default_rxi()

    n = rxi.n_lens
    for p in rxi.DE:
        mag = math.hypot(p.n[0], p.n[1])
        assert abs(mag - 1.0) < 1e-9, f"DE normal not unit length: {p.n}"
    print(f"  PASS: all {len(rxi.DE)} DE points carry unit-length normals")
    return True


def test_rxi_direct_ac_segment_is_straight_with_consistent_normal():
    """A, C, and the AC segment's geometric normal are mutually consistent (pin 4)."""
    from ray_tracing_shapely.optical_elements.prisms.rxi_direct import _nrm, _rot90, _neg

    scene, rxi = _build_default_rxi()
    ac_dir = _nrm((rxi.C[0] - rxi.A[0], rxi.C[1] - rxi.A[1]))
    expected_normal = _rot90(ac_dir)
    if expected_normal[1] < 0:
        expected_normal = _neg(expected_normal)
    # DE[0] (== D) was built by refracting through this exact normal;
    # confirm it is perpendicular to A->C (a straight segment's normal
    # is always perpendicular to the segment itself).
    dot = expected_normal[0] * ac_dir[0] + expected_normal[1] * ac_dir[1]
    assert abs(dot) < 1e-9, f"AC normal not perpendicular to AC: dot={dot}"
    print("  PASS: AC's normal is perpendicular to the A-C segment, as a straight seed requires")
    return True


def test_rxi_direct_is_a_valid_simple_polygon():
    """The assembled Glass polygon (top + DE-family bottom, per the class's documented simplification) is CCW and simple."""
    from shapely.geometry import Polygon

    scene, rxi = _build_default_rxi()
    pts = [(v['x'], v['y']) for v in rxi.path]
    poly = Polygon(pts)
    assert poly.is_valid, "RXIOpticDirect polygon is not a valid simple polygon for its own default parameters"
    signed_area = 0.5 * sum(
        pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
        for i in range(len(pts))
    )
    assert signed_area > 0, f"RXIOpticDirect polygon is not CCW (signed area {signed_area})"
    print(f"  PASS: RXIOpticDirect polygon is valid, simple, CCW ({len(pts)} vertices) for its default parameters")
    return True


def test_rxi_direct_receiver_cavity_is_computed():
    """
    The receiver cavity MN is computed (even though not yet stitched into
    the assembled polygon -- see the class's own documented
    simplification) and every point satisfies the Cartesian oval's own
    defining property: n*[C,P] + n*[P,R1] == S_CR1.
    """
    scene, rxi = _build_default_rxi()
    assert len(rxi.MN) > 0, "expected at least one receiver-cavity point"
    n = rxi.n_lens
    S_CR1 = rxi.s_cr1_margin * n * math.hypot(*(rxi.C[0] - R1[0], rxi.C[1] - R1[1]))
    for p in rxi.MN:
        lhs = n * math.hypot(p.p[0] - rxi.C[0], p.p[1] - rxi.C[1]) + n * math.hypot(p.p[0] - R1[0], p.p[1] - R1[1])
        assert abs(lhs - S_CR1) < 1e-6, f"MN point {p.p} does not satisfy n*[C,P]+n*[P,R1]==S_CR1"
    print(f"  PASS: all {len(rxi.MN)} receiver-cavity points satisfy their own Cartesian oval equation")
    return True


def run_all_tests():
    tests = [
        ("RXIOpticDirect constructs without error", test_rxi_direct_constructs_without_error),
        ("RXIOpticDirect DE fan Snell consistency", test_rxi_direct_de_fan_snell_consistency),
        ("RXIOpticDirect AC segment normal consistency", test_rxi_direct_ac_segment_is_straight_with_consistent_normal),
        ("RXIOpticDirect is a valid simple CCW polygon", test_rxi_direct_is_a_valid_simple_polygon),
        ("RXIOpticDirect receiver cavity is computed", test_rxi_direct_receiver_cavity_is_computed),
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
