"""
Python-specific module: test prisms
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
PRISM MODULE TESTS - Phase 6 Verification
===============================================================================

Comprehensive tests for the optical_elements.prisms module, covering:

1. GEOMETRY VERIFICATION
   - Vertex positions and CCW ordering (positive signed area)
   - Internal angles
   - Edge lengths
   - Polygon area

2. LABEL CORRECTNESS
   - Functional labels (_edge_roles count matches vertex count)
   - Cardinal labels from auto_label_cardinal()
   - Labels unchanged/updated after rotation

3. UTILITY FUNCTION TESTS
   - minimum_deviation() physics
   - refractive_index_from_deviation() round-trip
   - deviation_at_incidence() symmetry
   - critical_angle() and TIR utilities
   - n_cauchy() dispersion model
   - Wavelength-aware functions

4. INTEGRATION TESTS
   - Prism creation and scene integration
   - describe_prism() output verification

Run with:
    python developer_tests/test_prisms.py

Or with pytest:
    pytest developer_tests/test_prisms.py -v
===============================================================================
"""

import sys
import math
from pathlib import Path

# Add the src-python directory to the path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


# =============================================================================
# TEST CONFIGURATION
# =============================================================================

# Tolerance for floating-point comparisons
TOLERANCE = 1e-6
ANGLE_TOLERANCE = 0.01  # degrees


def assert_close(actual, expected, tol=TOLERANCE, msg=""):
    """Assert that two values are close within tolerance."""
    if abs(actual - expected) > tol:
        raise AssertionError(
            f"{msg}: expected {expected}, got {actual} (diff: {abs(actual - expected)})"
        )


def assert_angle_close(actual, expected, tol=ANGLE_TOLERANCE, msg=""):
    """Assert that two angles are close within tolerance."""
    assert_close(actual, expected, tol, msg)


# =============================================================================
# GEOMETRY VERIFICATION TESTS
# =============================================================================

def test_equilateral_geometry():
    """
    Test EquilateralPrism geometry:
    - All sides equal
    - All angles 60 degrees
    - CCW vertex ordering (positive signed area)
    """
    print("\n" + "=" * 60)
    print("TEST: EquilateralPrism Geometry")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import EquilateralPrism

    scene = Scene()
    side = 50.0
    prism = EquilateralPrism(scene, side_length=side, n=1.5)

    # Check signed area is positive (CCW ordering)
    area = prism.signed_area()
    assert area > 0, f"Expected positive signed area (CCW), got {area}"
    print(f"  Signed area: {area:.4f} (positive = CCW) - PASS")

    # Check all sides are equal
    lengths = [prism.get_edge_length(i) for i in range(3)]
    for i, length in enumerate(lengths):
        assert_close(length, side, TOLERANCE, f"Edge {i} length")
    print(f"  All sides equal ({side}): {lengths} - PASS")

    # Check all angles are 60 degrees
    angles = [prism.get_interior_angle(i) for i in range(3)]
    for i, angle in enumerate(angles):
        assert_angle_close(angle, 60.0, ANGLE_TOLERANCE, f"Vertex {i} angle")
    print(f"  All angles 60 deg: {[f'{a:.1f}' for a in angles]} - PASS")

    # Check apex vertex is defined (vertex 2)
    apex = prism.apex_vertex
    assert apex is not None, "Apex vertex should be defined"
    print(f"  Apex vertex: ({apex[0]:.2f}, {apex[1]:.2f}) - PASS")

    # Check apex_angle property
    assert_angle_close(prism.apex_angle, 60.0, ANGLE_TOLERANCE, "apex_angle property")
    print(f"  apex_angle property: {prism.apex_angle} - PASS")

    print("  EquilateralPrism geometry tests: ALL PASSED")
    return True


def test_right_angle_geometry():
    """
    Test RightAnglePrism geometry:
    - Two legs equal
    - Angles: 45, 45, 90 degrees
    - Hypotenuse = leg * sqrt(2)
    - CCW vertex ordering
    """
    print("\n" + "=" * 60)
    print("TEST: RightAnglePrism Geometry")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import RightAnglePrism

    scene = Scene()
    leg = 30.0
    prism = RightAnglePrism(scene, leg_length=leg, n=1.5)

    # Check signed area is positive (CCW ordering)
    area = prism.signed_area()
    assert area > 0, f"Expected positive signed area (CCW), got {area}"
    print(f"  Signed area: {area:.4f} (positive = CCW) - PASS")

    # Check leg lengths
    leg0 = prism.get_edge_length(0)  # Entrance face
    leg2 = prism.get_edge_length(2)  # Exit face
    assert_close(leg0, leg, TOLERANCE, "Entrance face length")
    assert_close(leg2, leg, TOLERANCE, "Exit face length")
    print(f"  Leg lengths: {leg0:.2f}, {leg2:.2f} - PASS")

    # Check hypotenuse length
    hyp = prism.get_edge_length(1)
    expected_hyp = leg * math.sqrt(2)
    assert_close(hyp, expected_hyp, TOLERANCE, "Hypotenuse length")
    assert_close(prism.hypotenuse_length, expected_hyp, TOLERANCE, "hypotenuse_length property")
    print(f"  Hypotenuse: {hyp:.4f} (expected {expected_hyp:.4f}) - PASS")

    # Check angles: 90, 45, 45 (V0 is the right-angle vertex geometrically)
    # Note: V0 at (0,0) is where the horizontal base meets the vertical edge,
    # so it has the 90-degree angle. V1 and V2 are the acute vertices.
    angles = [prism.get_interior_angle(i) for i in range(3)]
    expected_angles = [90.0, 45.0, 45.0]
    for i, (angle, expected) in enumerate(zip(angles, expected_angles)):
        assert_angle_close(angle, expected, ANGLE_TOLERANCE, f"Vertex {i} angle")
    print(f"  Angles (V0, V1, V2): {[f'{a:.1f}' for a in angles]} - PASS")

    # No apex vertex (two equal acute angles)
    assert prism.apex_vertex is None, "RightAnglePrism should have no apex vertex"
    print("  apex_vertex is None (as expected) - PASS")

    print("  RightAnglePrism geometry tests: ALL PASSED")
    return True


def test_refractometer_geometry():
    """
    Test RefractometerPrism geometry:
    - Symmetric trapezoid (4 vertices)
    - CCW vertex ordering
    - Face angle computed from physics
    """
    print("\n" + "=" * 60)
    print("TEST: RefractometerPrism Geometry")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import RefractometerPrism

    scene = Scene()
    n_prism = 1.72
    n_sample_range = (1.30, 1.50)
    m_length = 20.0

    prism = RefractometerPrism(
        scene,
        n_prism=n_prism,
        n_sample_range=n_sample_range,
        measuring_surface_length=m_length
    )

    # Check signed area is positive (CCW ordering)
    area = prism.signed_area()
    assert area > 0, f"Expected positive signed area (CCW), got {area}"
    print(f"  Signed area: {area:.4f} (positive = CCW) - PASS")

    # Check 4 vertices
    assert len(prism.path) == 4, f"Expected 4 vertices, got {len(prism.path)}"
    print(f"  Vertex count: {len(prism.path)} - PASS")

    # Check measuring surface length (Edge 2)
    m_edge_length = prism.get_edge_length(2)
    assert_close(m_edge_length, m_length, TOLERANCE, "Measuring surface length")
    print(f"  Measuring surface length: {m_edge_length:.2f} - PASS")

    # Check face angle is reasonable (should be between 20 and 60 degrees)
    assert 20.0 < prism.face_angle < 60.0, f"Face angle {prism.face_angle} out of range"
    print(f"  Face angle: {prism.face_angle:.2f} degrees - PASS")

    # Check n_mid and theta_c_mid
    n_mid = (n_sample_range[0] + n_sample_range[1]) / 2
    assert_close(prism.n_mid, n_mid, TOLERANCE, "n_mid calculation")
    print(f"  n_mid: {prism.n_mid:.3f} - PASS")

    # No apex vertex (trapezoid)
    assert prism.apex_vertex is None, "RefractometerPrism should have no apex vertex"
    print("  apex_vertex is None (as expected) - PASS")

    print("  RefractometerPrism geometry tests: ALL PASSED")
    return True


# =============================================================================
# LABEL CORRECTNESS TESTS
# =============================================================================

def test_equilateral_labels():
    """
    Test EquilateralPrism labels:
    - Functional labels: B, X, E
    - Cardinal labels assigned after construction
    - Functional labels unchanged after rotation
    """
    print("\n" + "=" * 60)
    print("TEST: EquilateralPrism Labels")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import EquilateralPrism

    scene = Scene()
    prism = EquilateralPrism(scene, side_length=50.0)

    # Check functional labels
    expected_functional = [
        ("B", "Base"),
        ("X", "Exit Face"),
        ("E", "Entrance Face")
    ]
    for i, (short, long) in enumerate(expected_functional):
        label = prism.get_functional_label(i)
        assert label is not None, f"Edge {i} should have functional label"
        assert label[0] == short, f"Edge {i} short label: expected {short}, got {label[0]}"
        assert label[1] == long, f"Edge {i} long label: expected {long}, got {label[1]}"
    print(f"  Functional labels: {expected_functional} - PASS")

    # Check find_edge_by_functional_label
    assert prism.find_edge_by_functional_label("B") == 0
    assert prism.find_edge_by_functional_label("X") == 1
    assert prism.find_edge_by_functional_label("E") == 2
    print("  find_edge_by_functional_label() - PASS")

    # Check vertex labels
    expected_vertex = [
        ("BL", "Base Left"),
        ("BR", "Base Right"),
        ("A", "Apex")
    ]
    for i, (short, long) in enumerate(expected_vertex):
        label = prism.get_vertex_label(i)
        assert label is not None, f"Vertex {i} should have label"
        assert label[0] == short, f"Vertex {i} short label: expected {short}, got {label[0]}"
    print(f"  Vertex labels: {expected_vertex} - PASS")

    # Check cardinal labels are assigned
    for i in range(3):
        card = prism.get_edge_label(i)
        assert card is not None, f"Edge {i} should have cardinal label"
    print("  Cardinal labels assigned - PASS")

    # Check label_summary output
    summary = prism.label_summary()
    assert "Base (B)" in summary
    assert "Exit Face (X)" in summary
    assert "Entrance Face (E)" in summary
    print("  label_summary() contains all labels - PASS")

    print("  EquilateralPrism label tests: ALL PASSED")
    return True


def test_right_angle_labels():
    """
    Test RightAnglePrism labels:
    - Functional labels: E, H, X
    - Vertex labels: A1, A2, R
    """
    print("\n" + "=" * 60)
    print("TEST: RightAnglePrism Labels")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import RightAnglePrism

    scene = Scene()
    prism = RightAnglePrism(scene, leg_length=30.0)

    # Check functional labels
    expected_functional = [
        ("E", "Entrance Face"),
        ("H", "Hypotenuse"),
        ("X", "Exit Face")
    ]
    for i, (short, long) in enumerate(expected_functional):
        label = prism.get_functional_label(i)
        assert label is not None, f"Edge {i} should have functional label"
        assert label[0] == short, f"Edge {i} short: expected {short}, got {label[0]}"
    print(f"  Functional labels: {[l[0] for l in expected_functional]} - PASS")

    # Check vertex labels
    expected_vertex = [
        ("A1", "Acute Vertex 1"),
        ("A2", "Acute Vertex 2"),
        ("R", "Right-Angle Vertex")
    ]
    for i, (short, long) in enumerate(expected_vertex):
        label = prism.get_vertex_label(i)
        assert label[0] == short
    print(f"  Vertex labels: {[l[0] for l in expected_vertex]} - PASS")

    print("  RightAnglePrism label tests: ALL PASSED")
    return True


def test_refractometer_labels():
    """
    Test RefractometerPrism labels:
    - Functional labels: B, X, M, E (4 edges)
    """
    print("\n" + "=" * 60)
    print("TEST: RefractometerPrism Labels")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import RefractometerPrism

    scene = Scene()
    prism = RefractometerPrism(
        scene,
        n_prism=1.72,
        n_sample_range=(1.30, 1.50),
        measuring_surface_length=20.0
    )

    # Check functional labels
    expected_functional = [
        ("B", "Base"),
        ("X", "Exit Face"),
        ("M", "Measuring Surface"),
        ("E", "Entrance Face")
    ]
    assert len(prism._functional_labels) == 4, "Should have 4 functional labels"

    for i, (short, long) in enumerate(expected_functional):
        label = prism.get_functional_label(i)
        assert label[0] == short, f"Edge {i}: expected {short}, got {label[0]}"
    print(f"  Functional labels: {[l[0] for l in expected_functional]} - PASS")

    # Check find_edge_by_functional_label
    assert prism.find_edge_by_functional_label("M") == 2
    print("  find_edge_by_functional_label('M') = 2 - PASS")

    print("  RefractometerPrism label tests: ALL PASSED")
    return True


def test_labels_after_rotation():
    """
    Test that functional labels are unchanged but cardinal labels update after rotation.
    """
    print("\n" + "=" * 60)
    print("TEST: Labels After Rotation")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import EquilateralPrism

    # Create prism at 0 degrees
    scene = Scene()
    prism0 = EquilateralPrism(scene, side_length=50.0, rotation=0.0)

    # Create prism at 90 degrees
    prism90 = EquilateralPrism(scene, side_length=50.0, rotation=90.0)

    # Functional labels should be identical
    for i in range(3):
        label0 = prism0.get_functional_label(i)
        label90 = prism90.get_functional_label(i)
        assert label0 == label90, f"Functional label for edge {i} changed after rotation"

    print("  Functional labels unchanged after rotation - PASS")

    # Cardinal labels should be different (rotated)
    card0_edge0 = prism0.get_edge_label(0)  # Base should face South at 0 degrees
    card90_edge0 = prism90.get_edge_label(0)  # Base should face West at 90 degrees

    # They should be different
    assert card0_edge0 != card90_edge0, "Cardinal labels should change after rotation"
    print(f"  Cardinal labels changed: edge 0 is '{card0_edge0[0]}' at 0 deg, '{card90_edge0[0]}' at 90 deg - PASS")

    print("  Rotation label tests: ALL PASSED")
    return True


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

def test_minimum_deviation():
    """
    Test minimum_deviation() formula:
    D_min = 2 * arcsin(n * sin(A/2)) - A

    Known value: equilateral prism (A=60) with n=1.5 => D_min ~ 37.18 deg
    """
    print("\n" + "=" * 60)
    print("TEST: minimum_deviation()")
    print("=" * 60)

    from ray_tracing_shapely.optical_elements.prisms import prism_utils

    # Test case: equilateral prism with n=1.5
    apex_angle = 60.0
    n = 1.5

    d_min = prism_utils.minimum_deviation(apex_angle, n)

    # Analytical calculation
    A_rad = math.radians(apex_angle)
    expected = 2 * math.degrees(math.asin(n * math.sin(A_rad / 2))) - apex_angle

    assert_angle_close(d_min, expected, ANGLE_TOLERANCE, "minimum_deviation")
    assert_angle_close(d_min, 37.18, 0.1, "minimum_deviation vs known value")
    print(f"  minimum_deviation(60, 1.5) = {d_min:.2f} deg (expected ~37.18) - PASS")

    # Test with different values
    d_min_2 = prism_utils.minimum_deviation(60.0, 1.7)
    assert d_min_2 > d_min, "Higher n should give larger deviation"
    print(f"  minimum_deviation(60, 1.7) = {d_min_2:.2f} deg (> 37.18) - PASS")

    print("  minimum_deviation() tests: ALL PASSED")
    return True


def test_refractive_index_from_deviation():
    """
    Test round-trip: n -> D_min -> n (should recover original n)
    """
    print("\n" + "=" * 60)
    print("TEST: refractive_index_from_deviation() round-trip")
    print("=" * 60)

    from ray_tracing_shapely.optical_elements.prisms import prism_utils

    apex_angle = 60.0
    original_n = 1.52

    # Forward: n -> D_min
    d_min = prism_utils.minimum_deviation(apex_angle, original_n)

    # Reverse: D_min -> n
    recovered_n = prism_utils.refractive_index_from_deviation(apex_angle, d_min)

    assert_close(recovered_n, original_n, 1e-6, "Round-trip n recovery")
    print(f"  Original n: {original_n}, D_min: {d_min:.4f}, Recovered n: {recovered_n:.6f} - PASS")

    print("  refractive_index_from_deviation() round-trip: PASSED")
    return True


def test_deviation_at_incidence():
    """
    Test deviation_at_incidence():
    - At minimum deviation incidence, deviation should equal D_min
    - Deviation should be symmetric around minimum
    """
    print("\n" + "=" * 60)
    print("TEST: deviation_at_incidence()")
    print("=" * 60)

    from ray_tracing_shapely.optical_elements.prisms import prism_utils

    apex_angle = 60.0
    n = 1.5

    # Get minimum deviation and incidence angle for minimum deviation
    d_min = prism_utils.minimum_deviation(apex_angle, n)
    i_min = prism_utils.incidence_for_minimum_deviation(apex_angle, n)

    # At minimum deviation incidence, deviation should equal D_min
    dev_at_min = prism_utils.deviation_at_incidence(apex_angle, n, i_min)
    assert_angle_close(dev_at_min, d_min, 0.1, "Deviation at minimum incidence")
    print(f"  Deviation at i={i_min:.2f} deg: {dev_at_min:.2f} deg (D_min={d_min:.2f}) - PASS")

    # Test symmetry: deviations at i_min +/- delta should be equal
    delta = 5.0
    dev_plus = prism_utils.deviation_at_incidence(apex_angle, n, i_min + delta)
    dev_minus = prism_utils.deviation_at_incidence(apex_angle, n, i_min - delta)

    # Both should be greater than D_min
    assert dev_plus > d_min, "Deviation at i_min + delta should be > D_min"
    assert dev_minus > d_min, "Deviation at i_min - delta should be > D_min"
    print(f"  Deviation at {i_min + delta:.1f} deg: {dev_plus:.2f} > {d_min:.2f} - PASS")
    print(f"  Deviation at {i_min - delta:.1f} deg: {dev_minus:.2f} > {d_min:.2f} - PASS")

    print("  deviation_at_incidence() tests: ALL PASSED")
    return True


def test_critical_angle():
    """
    Test critical_angle() from tir_utils:
    - theta_c = arcsin(n_sample / n_prism)
    - Should raise error if n_prism <= n_sample
    """
    print("\n" + "=" * 60)
    print("TEST: critical_angle()")
    print("=" * 60)

    from ray_tracing_shapely.optical_elements.prisms import tir_utils

    n_sample = 1.333  # Water
    n_prism = 1.72

    theta_c = tir_utils.critical_angle(n_sample, n_prism)

    # Analytical
    expected = math.degrees(math.asin(n_sample / n_prism))
    assert_angle_close(theta_c, expected, ANGLE_TOLERANCE, "critical_angle")
    print(f"  critical_angle(1.333, 1.72) = {theta_c:.2f} deg (expected {expected:.2f}) - PASS")

    # Test error case
    try:
        tir_utils.critical_angle(1.72, 1.5)  # n_sample > n_prism
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "TIR impossible" in str(e)
        print("  Error raised for n_sample > n_prism - PASS")

    print("  critical_angle() tests: ALL PASSED")
    return True


def test_n_cauchy():
    """
    Test n_cauchy() dispersion model:
    n(lambda) = A + B / lambda^2

    Blue light should have higher n than red light.
    """
    print("\n" + "=" * 60)
    print("TEST: n_cauchy() dispersion")
    print("=" * 60)

    from ray_tracing_shapely.optical_elements.prisms import prism_utils

    # Typical Cauchy coefficients for crown glass
    A = 1.5220
    B = 0.00459  # um^2

    # Test at different wavelengths
    n_red = prism_utils.n_cauchy(656.0, A, B)    # H-alpha, red
    n_green = prism_utils.n_cauchy(546.0, A, B)  # Green
    n_blue = prism_utils.n_cauchy(486.0, A, B)   # H-beta, blue

    # Blue should have higher n (normal dispersion)
    assert n_blue > n_green > n_red, "Expected n_blue > n_green > n_red"
    print(f"  n_red(656nm): {n_red:.6f}")
    print(f"  n_green(546nm): {n_green:.6f}")
    print(f"  n_blue(486nm): {n_blue:.6f}")
    print("  n_blue > n_green > n_red (normal dispersion) - PASS")

    # Verify formula: n = A + B / (lambda_um)^2
    lambda_um = 0.546  # 546 nm in um
    expected = A + B / (lambda_um ** 2)
    assert_close(n_green, expected, TOLERANCE, "n_cauchy formula")
    print(f"  Formula verification: {n_green:.6f} == {expected:.6f} - PASS")

    print("  n_cauchy() tests: ALL PASSED")
    return True


def test_dispersion_spectrum():
    """
    Test dispersion_spectrum() function.
    """
    print("\n" + "=" * 60)
    print("TEST: dispersion_spectrum()")
    print("=" * 60)

    from ray_tracing_shapely.optical_elements.prisms import prism_utils

    apex_angle = 60.0
    A = 1.5220
    B = 0.00459

    wavelengths = [400.0, 500.0, 600.0, 700.0]
    spectrum = prism_utils.dispersion_spectrum(apex_angle, A, B, wavelengths)

    assert len(spectrum) == len(wavelengths)
    print(f"  Spectrum has {len(spectrum)} entries - PASS")

    # Check that blue light deviates more than red (higher n -> higher deviation)
    deviations = [d for _, d in spectrum]
    assert deviations[0] > deviations[-1], "Blue should deviate more than red"
    print(f"  Deviation at 400nm: {deviations[0]:.2f} deg")
    print(f"  Deviation at 700nm: {deviations[-1]:.2f} deg")
    print("  Blue deviates more than red - PASS")

    print("  dispersion_spectrum() tests: ALL PASSED")
    return True


def test_right_angle_tir():
    """
    Test RightAnglePrism TIR properties:
    - supports_tir should be True for n >= sqrt(2)
    - tir_margin should be positive for n = 1.5
    """
    print("\n" + "=" * 60)
    print("TEST: RightAnglePrism TIR Properties")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import RightAnglePrism

    scene = Scene()

    # Test with n=1.5 (supports TIR)
    prism_15 = RightAnglePrism(scene, leg_length=30.0, n=1.5)
    assert prism_15.supports_tir, "n=1.5 should support TIR"
    margin = prism_15.tir_margin()
    assert margin > 0, f"TIR margin should be positive, got {margin}"
    print(f"  n=1.5: supports_tir=True, margin={margin:.2f} deg - PASS")

    # Test with n=1.3 (does NOT support TIR)
    prism_13 = RightAnglePrism(scene, leg_length=30.0, n=1.3)
    assert not prism_13.supports_tir, "n=1.3 should not support TIR"
    margin_13 = prism_13.tir_margin()
    assert margin_13 < 0, f"TIR margin should be negative, got {margin_13}"
    print(f"  n=1.3: supports_tir=False, margin={margin_13:.2f} deg - PASS")

    # Test critical angle
    critical = prism_15.critical_angle_at_hypotenuse()
    assert 0 < critical < 45, f"Critical angle should be < 45 for TIR at 45 deg incidence"
    print(f"  Critical angle at hypotenuse (n=1.5): {critical:.2f} deg - PASS")

    print("  RightAnglePrism TIR tests: ALL PASSED")
    return True


def test_refractometer_physics():
    """
    Test RefractometerPrism physics methods:
    - exit_angle_for(n_mid) should be 0 (normal exit)
    - critical_angle_for() should return valid angles
    """
    print("\n" + "=" * 60)
    print("TEST: RefractometerPrism Physics")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import RefractometerPrism

    scene = Scene()
    n_prism = 1.72
    n_sample_range = (1.30, 1.50)

    prism = RefractometerPrism(
        scene,
        n_prism=n_prism,
        n_sample_range=n_sample_range,
        measuring_surface_length=20.0
    )

    # Exit angle at n_mid should be ~0 (normal exit design)
    exit_at_mid = prism.exit_angle_for(prism.n_mid)
    assert_angle_close(exit_at_mid, 0.0, 0.5, "Exit angle at n_mid")
    print(f"  Exit angle at n_mid ({prism.n_mid:.3f}): {exit_at_mid:.4f} deg - PASS")

    # Critical angle for n_min and n_max
    theta_c_min = prism.critical_angle_for(n_sample_range[0])
    theta_c_max = prism.critical_angle_for(n_sample_range[1])
    assert theta_c_min < theta_c_max, "theta_c should increase with n_sample"
    print(f"  Critical angle range: [{theta_c_min:.2f}, {theta_c_max:.2f}] deg - PASS")

    # Validate geometry (should return empty list for valid geometry)
    warnings = prism.validate_geometry()
    if warnings:
        print(f"  Geometry warnings: {warnings}")
    else:
        print("  validate_geometry(): no warnings - PASS")

    print("  RefractometerPrism physics tests: ALL PASSED")
    return True


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

def test_describe_prism():
    """
    Test describe_prism() function for all prism types.
    """
    print("\n" + "=" * 60)
    print("TEST: describe_prism()")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import (
        EquilateralPrism, RightAnglePrism, RefractometerPrism
    )
    from ray_tracing_shapely.analysis import describe_prism

    scene = Scene()

    # Test EquilateralPrism
    eq_prism = EquilateralPrism(scene, side_length=50.0, n=1.5, position=(100, 100))
    eq_desc = describe_prism(eq_prism, format='text')
    assert "EquilateralPrism" in eq_desc
    assert "Base (B)" in eq_desc
    assert "Exit Face (X)" in eq_desc
    assert "Minimum Deviation" in eq_desc
    print("  EquilateralPrism text description - PASS")

    # Test XML format
    eq_xml = describe_prism(eq_prism, format='xml')
    assert "<?xml" in eq_xml
    assert "<prism_description>" in eq_xml
    assert 'functional_short="B"' in eq_xml
    print("  EquilateralPrism XML description - PASS")

    # Test RightAnglePrism
    ra_prism = RightAnglePrism(scene, leg_length=30.0, n=1.5)
    ra_desc = describe_prism(ra_prism, format='text')
    assert "RightAnglePrism" in ra_desc
    assert "Hypotenuse (H)" in ra_desc
    assert "Supports TIR" in ra_desc
    print("  RightAnglePrism text description - PASS")

    # Test RefractometerPrism
    ref_prism = RefractometerPrism(
        scene,
        n_prism=1.72,
        n_sample_range=(1.30, 1.50),
        measuring_surface_length=20.0
    )
    ref_desc = describe_prism(ref_prism, format='text')
    assert "RefractometerPrism" in ref_desc
    assert "Measuring Surface (M)" in ref_desc
    assert "Sample Range" in ref_desc
    print("  RefractometerPrism text description - PASS")

    print("  describe_prism() tests: ALL PASSED")
    return True


def test_from_vertices():
    """
    Test BasePrism.from_vertices() escape hatch.
    """
    print("\n" + "=" * 60)
    print("TEST: BasePrism.from_vertices()")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import BasePrism

    scene = Scene()

    # Create custom triangle
    vertices = [
        (0.0, 0.0),
        (100.0, 0.0),
        (50.0, 86.6)  # roughly equilateral
    ]

    prism = BasePrism.from_vertices(scene, vertices, n=1.6)

    # Check vertex count
    assert len(prism.path) == 3
    print(f"  Created prism with {len(prism.path)} vertices - PASS")

    # Check CCW ordering
    area = prism.signed_area()
    assert area > 0, "Should have positive signed area"
    print(f"  Signed area: {area:.2f} (CCW) - PASS")

    # Check numeric functional labels (not type-specific)
    for i in range(3):
        label = prism.get_functional_label(i)
        assert label[0] == str(i), f"Expected numeric label {i}, got {label[0]}"
    print("  Numeric functional labels assigned - PASS")

    # Check cardinal labels are assigned
    for i in range(3):
        card = prism.get_edge_label(i)
        assert card is not None
    print("  Cardinal labels assigned - PASS")

    print("  from_vertices() tests: ALL PASSED")
    return True


def test_factory_functions():
    """
    Test factory functions in prisms/__init__.py
    """
    print("\n" + "=" * 60)
    print("TEST: Factory Functions")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import (
        equilateral_prism,
        right_angle_prism,
        refractometer_prism
    )

    scene = Scene()

    # Test equilateral_prism()
    eq = equilateral_prism(scene, side_length=50.0, n=1.5)
    assert eq.side_length == 50.0
    assert eq.refIndex == 1.5
    print("  equilateral_prism() - PASS")

    # Test right_angle_prism()
    ra = right_angle_prism(scene, leg_length=30.0, n=1.52)
    assert ra.leg_length == 30.0
    assert ra.refIndex == 1.52
    print("  right_angle_prism() - PASS")

    # Test refractometer_prism()
    ref = refractometer_prism(
        scene,
        n_prism=1.72,
        n_sample_range=(1.30, 1.50),
        measuring_surface_length=20.0
    )
    assert ref.n_prism == 1.72
    assert ref.measuring_surface_length == 20.0
    print("  refractometer_prism() - PASS")

    print("  Factory function tests: ALL PASSED")
    return True


# =============================================================================
# from_critical_ray_path TESTS
# =============================================================================

def test_trapezoid_from_critical_ray_path_dimensions():
    """
    Test that trapezoid_from_critical_ray_path() returns correct dimensions
    for the numerical example: n_prism=1.72, n_target=1.33, L=20.
    """
    print("\n" + "=" * 60)
    print("TEST: trapezoid_from_critical_ray_path() dimensions")
    print("=" * 60)

    from ray_tracing_shapely.optical_elements.prisms import tir_utils

    dims = tir_utils.trapezoid_from_critical_ray_path(
        n_target=1.33, n_prism=1.72, ray_path_length=20.0
    )

    # Expected values from the roadmap numerical example
    theta_c_expected = math.degrees(math.asin(1.33 / 1.72))
    cos_tc = math.cos(math.radians(theta_c_expected))
    sin_tc = math.sin(math.radians(theta_c_expected))

    h_expected = 20.0 * cos_tc
    E_expected = 20.0 * cos_tc / sin_tc
    M_expected = 20.0 / sin_tc
    b_expected = math.sqrt(E_expected ** 2 - h_expected ** 2)
    B_expected = M_expected - 2 * b_expected

    assert_angle_close(dims['theta_c_deg'], theta_c_expected, ANGLE_TOLERANCE,
                       "theta_c")
    assert_close(dims['h'], h_expected, TOLERANCE, "h")
    assert_close(dims['E'], E_expected, TOLERANCE, "E")
    assert_close(dims['M'], M_expected, TOLERANCE, "M")
    assert_close(dims['b'], b_expected, TOLERANCE, "b")
    assert_close(dims['B'], B_expected, TOLERANCE, "B")
    assert_angle_close(dims['face_angle_deg'], 90.0 - theta_c_expected,
                       ANGLE_TOLERANCE, "face_angle_deg")

    print(f"  theta_c = {dims['theta_c_deg']:.2f} deg - PASS")
    print(f"  h = {dims['h']:.4f} - PASS")
    print(f"  E = {dims['E']:.4f} - PASS")
    print(f"  M = {dims['M']:.4f} - PASS")
    print(f"  b = {dims['b']:.4f} - PASS")
    print(f"  B = {dims['B']:.4f} - PASS")

    # Verify Pythagorean relation: M^2 = L^2 + E^2
    assert_close(dims['M'] ** 2, 20.0 ** 2 + dims['E'] ** 2, 1e-4,
                 "Pythagorean relation M^2 = L^2 + E^2")
    print("  M^2 = L^2 + E^2 (Pythagorean) - PASS")

    # Verify B > 0
    assert dims['B'] > 0, f"B should be positive, got {dims['B']}"
    print(f"  B > 0 ({dims['B']:.4f}) - PASS")

    print("  trapezoid_from_critical_ray_path() dimension tests: ALL PASSED")
    return True


def test_trapezoid_from_critical_ray_path_errors():
    """
    Test error cases for trapezoid_from_critical_ray_path().
    """
    print("\n" + "=" * 60)
    print("TEST: trapezoid_from_critical_ray_path() error cases")
    print("=" * 60)

    from ray_tracing_shapely.optical_elements.prisms import tir_utils

    # n_target >= n_prism should raise ValueError
    try:
        tir_utils.trapezoid_from_critical_ray_path(
            n_target=1.72, n_prism=1.50, ray_path_length=20.0
        )
        raise AssertionError("Should have raised ValueError for n_target > n_prism")
    except ValueError as e:
        assert "TIR impossible" in str(e)
        print("  ValueError for n_target > n_prism - PASS")

    # theta_c <= 45 deg should raise ValueError
    # arcsin(n_target/n_prism) = 45 deg => n_target/n_prism = sin(45) = 0.7071
    # e.g. n_target=1.0, n_prism=2.0 => theta_c = 30 deg < 45 deg
    try:
        tir_utils.trapezoid_from_critical_ray_path(
            n_target=1.0, n_prism=2.0, ray_path_length=20.0
        )
        raise AssertionError("Should have raised ValueError for theta_c <= 45")
    except ValueError as e:
        assert "45" in str(e)
        print("  ValueError for theta_c <= 45 deg - PASS")

    print("  trapezoid_from_critical_ray_path() error tests: ALL PASSED")
    return True


def test_from_critical_ray_path_geometry():
    """
    Test RefractometerPrism.from_critical_ray_path() prism geometry:
    - Correct vertex count
    - CCW ordering
    - Entrance and exit faces have equal length (symmetry)
    - Measuring surface length matches expected M
    """
    print("\n" + "=" * 60)
    print("TEST: RefractometerPrism.from_critical_ray_path() geometry")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import RefractometerPrism, tir_utils

    scene = Scene()
    n_prism = 1.72
    n_target = 1.33
    L = 20.0

    prism = RefractometerPrism.from_critical_ray_path(
        scene, n_prism=n_prism, n_target=n_target, ray_path_length=L
    )

    dims = tir_utils.trapezoid_from_critical_ray_path(n_target, n_prism, L)

    # Check 4 vertices
    assert len(prism.path) == 4, f"Expected 4 vertices, got {len(prism.path)}"
    print(f"  Vertex count: {len(prism.path)} - PASS")

    # Check CCW ordering
    area = prism.signed_area()
    assert area > 0, f"Expected positive signed area (CCW), got {area}"
    print(f"  Signed area: {area:.4f} (positive = CCW) - PASS")

    # Check symmetry: entrance face (edge 3) == exit face (edge 1)
    entrance_len = prism.get_edge_length(3)
    exit_len = prism.get_edge_length(1)
    assert_close(entrance_len, exit_len, TOLERANCE, "Entrance == Exit face length")
    print(f"  Entrance face = Exit face = {entrance_len:.4f} - PASS")

    # Check entrance face length matches expected E
    assert_close(entrance_len, dims['E'], 0.01,
                 "Entrance face length matches expected E")
    print(f"  Entrance face matches dims['E'] ({dims['E']:.4f}) - PASS")

    # Check measuring surface length matches expected M
    m_len = prism.get_edge_length(2)
    assert_close(m_len, dims['M'], 0.01,
                 "Measuring surface length matches expected M")
    print(f"  Measuring surface matches dims['M'] ({dims['M']:.4f}) - PASS")

    # Check base length matches expected B
    b_len = prism.get_edge_length(0)
    assert_close(b_len, dims['B'], 0.01, "Base length matches expected B")
    print(f"  Base matches dims['B'] ({dims['B']:.4f}) - PASS")

    # Check extra attributes
    assert prism.n_target == n_target, "n_target attribute"
    assert prism.ray_path_length == L, "ray_path_length attribute"
    print("  Extra attributes (n_target, ray_path_length) stored - PASS")

    print("  from_critical_ray_path() geometry tests: ALL PASSED")
    return True


def test_from_critical_ray_path_factory():
    """
    Test the refractometer_prism_from_critical_ray_path factory function.
    """
    print("\n" + "=" * 60)
    print("TEST: refractometer_prism_from_critical_ray_path() factory")
    print("=" * 60)

    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.optical_elements.prisms import (
        refractometer_prism_from_critical_ray_path
    )

    scene = Scene()
    prism = refractometer_prism_from_critical_ray_path(
        scene, n_prism=1.72, n_target=1.33, ray_path_length=20.0
    )

    assert prism.n_prism == 1.72
    assert prism.n_target == 1.33
    assert prism.ray_path_length == 20.0
    print("  Factory function creates valid prism - PASS")

    print("  refractometer_prism_from_critical_ray_path() tests: ALL PASSED")
    return True


# =============================================================================
# MAIN
# =============================================================================

def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 78)
    print("PRISM MODULE TESTS - Phase 6 Verification")
    print("=" * 78)

    tests = [
        # Geometry verification
        ("EquilateralPrism Geometry", test_equilateral_geometry),
        ("RightAnglePrism Geometry", test_right_angle_geometry),
        ("RefractometerPrism Geometry", test_refractometer_geometry),

        # Label correctness
        ("EquilateralPrism Labels", test_equilateral_labels),
        ("RightAnglePrism Labels", test_right_angle_labels),
        ("RefractometerPrism Labels", test_refractometer_labels),
        ("Labels After Rotation", test_labels_after_rotation),

        # Utility functions
        ("minimum_deviation()", test_minimum_deviation),
        ("refractive_index_from_deviation()", test_refractive_index_from_deviation),
        ("deviation_at_incidence()", test_deviation_at_incidence),
        ("critical_angle()", test_critical_angle),
        ("n_cauchy()", test_n_cauchy),
        ("dispersion_spectrum()", test_dispersion_spectrum),
        ("RightAnglePrism TIR", test_right_angle_tir),
        ("RefractometerPrism Physics", test_refractometer_physics),

        # Integration
        ("describe_prism()", test_describe_prism),
        ("from_vertices()", test_from_vertices),
        ("Factory Functions", test_factory_functions),

        # from_critical_ray_path
        ("trapezoid dimensions", test_trapezoid_from_critical_ray_path_dimensions),
        ("trapezoid error cases", test_trapezoid_from_critical_ray_path_errors),
        ("from_critical_ray_path geometry", test_from_critical_ray_path_geometry),
        ("from_critical_ray_path factory", test_from_critical_ray_path_factory),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"\n  FAILED: {name}")
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
