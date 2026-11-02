"""
Python-specific module: test nonimaging geometry
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
NONIMAGING GEOMETRY PRIMITIVE TESTS -- Nonimaging Optics Phase 1, Step 2
and the Chapter 21 Geometry Toolbox Extensions
===============================================================================
Tests isl/rfr/coptpt (optical_elements.prisms.nonimaging_geometry) against
the published intermediate values from Chaves, "Introduction to Nonimaging
Optics" ch. 3, Example 3.6 (the DTIRC) -- a rare case where the reference
material is also the test oracle. No prism class involved; pure functions
only.

Also tests the ch. 21 additions (coptsl, ccoptpt, dcoptpt, rfnrm, rfxnrm) --
these have no numeric worked example in the book to reproduce (unlike
isl/rfr/coptpt above), so they are checked instead against hand-derived
closed-form geometry, internal self-consistency with the already-verified
coptpt, and (for coptsl vs. coptpt) the physical far-field limit connecting
a point-focus target to a plane-wavefront target. See
dev_doc/architecture/components/nonimaging_design.md.

Run with:
    python developer_tests/test_nonimaging_geometry.py
Or with pytest:
    pytest developer_tests/test_nonimaging_geometry.py -v
===============================================================================
"""

import math
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

TOL = 1e-4  # book's own published values are rounded to ~6 significant figures


def assert_point_close(actual, expected, tol=TOL, msg=""):
    dx = actual[0] - expected[0]
    dy = actual[1] - expected[1]
    dist = math.hypot(dx, dy)
    if dist > tol:
        raise AssertionError(
            f"{msg}: expected {expected}, got {actual} (dist: {dist})"
        )


def test_isl_and_rfr_dtirc_example_3_6():
    """isl/rfr reproduce Chaves Ch. 3 Example 3.6's eqs. 3.38-3.42 chain."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import isl, rfr

    theta = math.radians(10.0)
    n = 1.5

    P1 = (math.cos(7 * math.pi / 9), math.sin(7 * math.pi / 9))
    P2 = (math.cos(2 * math.pi / 9), math.sin(2 * math.pi / 9))
    assert_point_close(P1, (-0.766044, 0.642788), msg="P1 (eq. 3.38)")
    assert_point_close(P2, (0.766044, 0.642788), msg="P2 (eq. 3.38)")

    # Edge ray direction, angle theta to vertical.
    v2 = (math.sin(theta), -math.cos(theta))
    W1 = (P1[0] - v2[0], P1[1] - v2[1])
    assert_point_close(W1, (-0.939693, 1.6276), msg="W1 (eq. 3.39)")

    v_W = (v2[1], -v2[0])  # wavefront direction, perpendicular to v2
    W2 = isl(W1, v_W, P2, v2)
    assert_point_close(W2, (0.546198, 1.8896), msg="W2 (eq. 3.40)")

    v1_prime = rfr((-v2[0], -v2[1]), (-P1[0], -P1[1]), 1.0, n)
    assert_point_close(v1_prime, (0.416693, -0.909047), msg="v1' (eq. 3.41)")

    R = math.hypot(P2[0] - P1[0], P2[1] - P1[1]) * math.sin(theta) / n
    assert abs(R - 0.177363) < TOL, f"R (eq. 3.42): expected 0.177363, got {R}"

    e2 = (0.0, 1.0)
    R2 = isl(P1, v1_prime, (R / 2, 0.0), e2)
    assert_point_close(R2, (0.0886815, -1.22186), msg="R2 (eq. 3.43)")
    print("  PASS: isl/rfr reproduce eqs. 3.38-3.43")
    return True


def test_coptpt_dtirc_example_3_6():
    """coptpt reproduces the sidewall point Q from eqs. 3.44-3.47."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import isl, rfr, coptpt

    theta = math.radians(10.0)
    n = 1.5

    P1 = (math.cos(7 * math.pi / 9), math.sin(7 * math.pi / 9))
    v2 = (math.sin(theta), -math.cos(theta))
    W1 = (P1[0] - v2[0], P1[1] - v2[1])
    v_W = (v2[1], -v2[0])

    R = 0.177363
    R2 = (0.0886815, -1.22186)
    R1 = (-R2[0], R2[1])
    S = math.hypot(P1[0] - W1[0], P1[1] - W1[1]) + n * math.hypot(P1[0] - R2[0], P1[1] - R2[1]) + n * R
    assert abs(S - 4.34286) < TOL, f"S (eq. 3.44): expected 4.34286, got {S}"

    phi = math.radians(-10.0)
    P = (math.cos(math.pi / 2 + phi), math.sin(math.pi / 2 + phi))
    assert_point_close(P, (0.173648, 0.984808), msg="P at phi=-10deg")

    W = isl(W1, v_W, P, v2)
    assert_point_close(W, (0.0301537, 1.79861), msg="W (eq. 3.45)")

    v_star = rfr((-v2[0], -v2[1]), (-P[0], -P[1]), 1.0, n)
    assert_point_close(v_star, (0.0554755, -0.99846), msg="v* (eq. 3.46)")

    S_param = S - math.hypot(P[0] - W[0], P[1] - W[1])
    Q = coptpt(P, v_star, R1, n, S_param)
    assert_point_close(Q, (0.273056, -0.804356), msg="Q (eq. 3.47)")
    print("  PASS: coptpt reproduces eq. 3.47's sidewall point Q")
    return True


def test_rfr_returns_none_on_tir():
    """rfr returns None (not raises) past the critical angle."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import rfr

    # A ray inside n=1.5 hitting a flat surface near-grazing (89deg from
    # normal) trying to exit into air (n2=1) -- well past critical angle
    # (~41.8deg) -- must TIR.
    theta_i = math.radians(89.0)
    v_in = (-math.sin(theta_i), -math.cos(theta_i))  # back toward source
    n_surf = (0.0, 1.0)  # normal into the medium being entered (air)
    result = rfr(v_in, n_surf, 1.5, 1.0)
    assert result is None, f"expected TIR (None), got {result}"
    print("  PASS: rfr returns None on TIR")
    return True


def test_coptsl_matches_coptpt_when_wavefront_is_a_point_tangent():
    """
    coptsl (plane wavefront) reproduces coptpt (point focus) in the physical
    far-field limit: a point focus receding to distance R along the plane's
    own normal direction is exactly a plane wave in the R -> infinity limit
    (standard Fraunhofer/far-field fact). Checked here by fixing a coptsl
    solution P_plane, then confirming coptpt's solution -- for a point focus
    placed at increasing R beyond the same wavefront point Q, with S grown
    by the leading-order n*R term (NOT back-solved from P_plane) -- converges
    to P_plane at the expected O(1/R) rate, not merely "gets closer" by
    coincidence.
    """
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import coptpt, coptsl

    F = (0.0, 0.0)
    v = (0.6, 0.8)
    n = 1.5
    Q = (3.0, 1.0)
    u = (0.2, -0.98)
    mu = math.hypot(*u)
    u = (u[0] / mu, u[1] / mu)
    S_plane = 9.0

    P_plane = coptsl(F, v, Q, u, n, n, S_plane)

    def far_field_diff(R):
        G_R = (Q[0] + R * u[0], Q[1] + R * u[1])
        S_point_leading_order = n * R + S_plane  # no back-solving from P_plane
        P_check = coptpt(F, v, G_R, n, S_point_leading_order)
        return math.hypot(P_check[0] - P_plane[0], P_check[1] - P_plane[1])

    d_near = far_field_diff(100.0)
    d_far = far_field_diff(1.0e6)
    assert d_far < d_near / 1000.0, (
        f"expected far-field convergence: d_near={d_near}, d_far={d_far}"
    )
    assert d_far < 1e-6, f"expected near-exact match at R=1e6, got {d_far}"
    print("  PASS: coptsl matches coptpt's point-focus limit as R -> infinity")
    return True


def test_coptsl_known_geometry():
    """Hand-constructed case: horizontal wavefront, vertical ray, n1 != n2."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import coptsl

    F = (1.0, 1.0)
    v = (0.0, 1.0)
    Q = (0.0, 5.0)
    n_wave = (0.0, 1.0)
    n1, n2 = 1.0, 1.5
    S = 2.0

    qf_dot = (Q[0] - F[0]) * n_wave[0] + (Q[1] - F[1]) * n_wave[1]
    denom = n1 - n2 * (v[0] * n_wave[0] + v[1] * n_wave[1])
    t_expected = (S - n2 * qf_dot) / denom
    expected = (F[0] + t_expected * v[0], F[1] + t_expected * v[1])

    P = coptsl(F, v, Q, n_wave, n1, n2, S)
    assert_point_close(P, expected, tol=1e-9, msg="coptsl known geometry")
    print("  PASS: coptsl matches hand-derived closed form")
    return True


def test_coptsl_raises_on_parallel_ray():
    """v parallel to the wavefront normal at matched indices: denom == 0."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import coptsl

    try:
        coptsl((0.0, 0.0), (0.0, 1.0), (0.0, 3.0), (0.0, 1.0), 1.5, 1.5, 10.0)
        raise AssertionError("expected ValueError, got a result")
    except ValueError:
        pass
    print("  PASS: coptsl raises ValueError when v is parallel to the wavefront")
    return True


def test_ccoptpt_matches_coptpt_when_n1_equals_n2():
    """ccoptpt(F, n, v, G, n, S) agrees with coptpt(F, v, G, n, S) exactly."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import coptpt, ccoptpt

    F = (0.0, 0.0)
    v = (0.6, 0.8)
    G = (3.0, 1.0)
    n = 1.5
    S = 9.0

    p_coptpt = coptpt(F, v, G, n, S)
    p_ccoptpt = ccoptpt(F, n, v, G, n, S)
    assert_point_close(p_ccoptpt, p_coptpt, tol=1e-9, msg="ccoptpt vs coptpt at n1==n2")
    print("  PASS: ccoptpt reduces exactly to coptpt when n1 == n2")
    return True


def test_ccoptpt_known_geometry():
    """Two-index converging case: result satisfies n1*[F,P]+n2*[P,G]==S and lies on the ray."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import ccoptpt

    F = (0.0, 0.0)
    v = (0.8, 0.6)
    n1 = 1.5
    G = (4.0, -1.0)
    n2 = 1.0
    S = 12.0

    P = ccoptpt(F, n1, v, G, n2, S)
    lhs = n1 * math.hypot(P[0] - F[0], P[1] - F[1]) + n2 * math.hypot(P[0] - G[0], P[1] - G[1])
    assert abs(lhs - S) < 1e-9, f"ccoptpt: expected S={S}, got {lhs}"
    t = (P[0] - F[0]) / v[0]
    assert abs((P[1] - F[1]) - t * v[1]) < 1e-9, "ccoptpt: P not on the ray from F"
    assert t > 0, "ccoptpt: t must be positive"
    print("  PASS: ccoptpt satisfies n1*[F,P]+n2*[P,G]==S and lies on the ray")
    return True


def test_dcoptpt_known_geometry():
    """Two-index diverging case: result satisfies n1*[F,P]-n2*[P,G]==S."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import dcoptpt

    F = (0.0, 0.0)
    v = (0.8, 0.6)
    n1 = 1.5
    G = (4.0, -1.0)
    n2 = 1.0
    S = 3.0

    P = dcoptpt(F, n1, v, G, n2, S)
    lhs = n1 * math.hypot(P[0] - F[0], P[1] - F[1]) - n2 * math.hypot(P[0] - G[0], P[1] - G[1])
    assert abs(lhs - S) < 1e-9, f"dcoptpt: expected S={S}, got {lhs}"
    t = (P[0] - F[0]) / v[0]
    assert abs((P[1] - F[1]) - t * v[1]) < 1e-9, "dcoptpt: P not on the ray from F"
    assert t > 0, "dcoptpt: t must be positive"
    print("  PASS: dcoptpt satisfies n1*[F,P]-n2*[P,G]==S and lies on the ray")
    return True


def test_ccoptpt_raises_on_unreachable_S():
    """A negative/unreachable S raises ValueError, matching coptpt's convention."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import ccoptpt

    F = (0.0, 0.0)
    v = (0.8, 0.6)
    G = (4.0, -1.0)
    try:
        ccoptpt(F, 1.5, v, G, 1.0, -100.0)
        raise AssertionError("expected ValueError, got a result")
    except ValueError:
        pass
    print("  PASS: ccoptpt raises ValueError on unreachable S")
    return True


def test_rfnrm_recovers_known_normal():
    """rfnrm(i, r, n1, n2) recovers n_surf (up to sign) from rfr's own output."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import rfr, rfnrm

    n_surf = (0.0, 1.0)
    n1, n2 = 1.0, 1.5
    v = (0.3, -0.95)
    mv = math.hypot(*v)
    v = (v[0] / mv, v[1] / mv)

    r = rfr(v, n_surf, n1, n2)
    assert r is not None, "test setup error: unexpected TIR"
    i = (-v[0], -v[1])
    recovered = rfnrm(i, r, n1, n2)

    matches_plus = math.hypot(recovered[0] - n_surf[0], recovered[1] - n_surf[1]) < 1e-9
    matches_minus = math.hypot(recovered[0] + n_surf[0], recovered[1] + n_surf[1]) < 1e-9
    assert matches_plus or matches_minus, (
        f"rfnrm: expected +/-{n_surf}, got {recovered}"
    )
    print("  PASS: rfnrm recovers n_surf (up to sign) from rfr's own output")
    return True


def test_rfxnrm_matches_rfnrm_at_equal_indices():
    """rfxnrm(i, r) == rfnrm(i, r, 1.0, 1.0) exactly (delegation, not reimplementation)."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import rfnrm, rfxnrm

    i = (1.0, 0.0)
    r = (0.5, 0.5)
    assert rfxnrm(i, r) == rfnrm(i, r, 1.0, 1.0), "rfxnrm must delegate to rfnrm(i, r, 1.0, 1.0)"
    print("  PASS: rfxnrm delegates to rfnrm(i, r, 1.0, 1.0)")
    return True


def test_rfnrm_raises_on_inconsistent_rays():
    """i == r at n1 == n2: n1*i - n2*r is exactly zero, no real surface normal."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import rfnrm

    try:
        rfnrm((1.0, 0.0), (1.0, 0.0), 1.0, 1.0)
        raise AssertionError("expected ValueError, got a result")
    except ValueError:
        pass
    print("  PASS: rfnrm raises ValueError on inconsistent i/r/n1/n2")
    return True


def test_hyp_matches_example_9_1():
    """hyp(E1,E2,U,1) / hyp(R1,R2,U,1) at Example 9.1's own phi reproduce N/X exactly."""
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import hyp

    E1, E2 = (-1.0, 2.0), (1.0, 2.0)
    R1, R2 = (-0.5, -2.0), (0.5, -2.0)
    U = 1.0

    h_E = hyp(E1, E2, U, 1.0)
    h_R = hyp(R1, R2, U, 1.0)

    N = h_E(math.radians(303.3))
    X = h_R(math.radians(42.7))
    assert_point_close(N, (0.721303, -0.620433), msg="hyp(E1,E2,U,1)(303.3deg) -> N")
    assert_point_close(X, (0.673162, -0.917437), msg="hyp(R1,R2,U,1)(42.7deg) -> X")
    print("  PASS: hyp() reproduces Example 9.1's N and X exactly")
    return True


def run_all_tests():
    tests = [
        ("isl/rfr vs Example 3.6 (eqs. 3.38-3.43)", test_isl_and_rfr_dtirc_example_3_6),
        ("coptpt vs Example 3.6 (eqs. 3.44-3.47)", test_coptpt_dtirc_example_3_6),
        ("rfr TIR -> None", test_rfr_returns_none_on_tir),
        ("coptsl matches coptpt's far-field limit", test_coptsl_matches_coptpt_when_wavefront_is_a_point_tangent),
        ("coptsl known geometry", test_coptsl_known_geometry),
        ("coptsl raises on parallel ray", test_coptsl_raises_on_parallel_ray),
        ("ccoptpt matches coptpt at n1==n2", test_ccoptpt_matches_coptpt_when_n1_equals_n2),
        ("ccoptpt known geometry", test_ccoptpt_known_geometry),
        ("dcoptpt known geometry", test_dcoptpt_known_geometry),
        ("ccoptpt raises on unreachable S", test_ccoptpt_raises_on_unreachable_S),
        ("rfnrm recovers known normal", test_rfnrm_recovers_known_normal),
        ("rfxnrm matches rfnrm at equal indices", test_rfxnrm_matches_rfnrm_at_equal_indices),
        ("rfnrm raises on inconsistent rays", test_rfnrm_raises_on_inconsistent_rays),
        ("hyp matches Example 9.1's N and X", test_hyp_matches_example_9_1),
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
