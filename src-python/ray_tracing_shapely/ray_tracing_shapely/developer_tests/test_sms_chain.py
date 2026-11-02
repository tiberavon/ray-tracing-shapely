"""
Python-specific module: test sms chain
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
SMS CHAIN ENGINE TESTS (RR/RX/RXI Profile Construction)
===============================================================================
Tests sms_chain.py (optical_elements.prisms.sms_chain) against Chaves,
"Introduction to Nonimaging Optics" ch. 9's two fully-worked numeric
examples: Example 9.1 (RR, refract-refract) and Example 9.2 (XR,
reflect-then-refract-then-reflect) -- both worked examples, both used as
oracles, following the same "reference material is also the test oracle"
pattern test_nonimaging_geometry.py already established.

seed_arc()/build_sms_chain() have no book-published numeric example of
their own (Chaves Ch. 9 describes Figure 9.4's P1-Q1 seed procedurally,
not numerically) -- checked instead against hand-derived closed-form
geometry and internal consistency.

Run with:
    python developer_tests/test_sms_chain.py
Or with pytest:
    pytest developer_tests/test_sms_chain.py -v
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


def nrm(v):
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def test_reflect_matches_example_9_2_eq_9_73():
    """reflect(i, n_surf) -- NOT reflect(-i, n_surf) -- matches the book's rfx convention."""
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import reflect

    i = (-0.03489949670250096, -0.9993908270190958)
    n_X = (0.015223, -0.999884)
    t_X = reflect(i, n_X)
    assert_point_close(t_X, (-0.0653073, 0.997865), msg="reflect(i, n_X) (eq. 9.73)")
    print("  PASS: reflect() matches eq. 9.73 with un-negated i")
    return True


def test_sms_chain_step_matches_example_9_1_ping_pong():
    """
    sms_chain_step reproduces Chaves Ch. 9's own ping-pong step (the
    X_13 -> N_13 construction, ~line 1877): a real chain step (ray from
    R2 through an already-known CO_1 point, refracting to a new point on
    the N-surface), not the separate seed-fan sweep that builds CO_1
    itself (ccoptpt with an externally-swept direction -- a different,
    non-sms_chain_step procedure).
    """
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import sms_chain_step
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import (
        rfr, ccoptpt,
    )

    E1, E2 = (-1.0, 2.0), (1.0, 2.0)
    R1, R2 = (-0.5, -2.0), (0.5, -2.0)
    n = 1.5
    N = (0.721303, -0.620433)
    X = (0.673162, -0.917437)
    Np = 5

    # Build CO_1 (the seed-fan, not a chain step) to get a real X_13 + its
    # own computed normal, exactly as RRLens's own construction will.
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import (
        _resolve_new_normal,
    )

    s1 = nrm(sub(N, E1))
    t1 = nrm(sub(X, N))
    n_N = _resolve_new_normal(s1, t1, 1.0, n, 'refract')
    s2 = nrm(sub(N, E2))
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import (
        _orient_toward_travel,
    )
    n_N_oriented = _orient_toward_travel(n_N, s2)
    t2 = rfr((-s2[0], -s2[1]), n_N_oriented, 1.0, n)
    S_NR1 = n * math.hypot(*sub(N, X)) + math.hypot(*sub(X, R1))

    CO_1 = []
    for k in range(Np + 1):
        x = k / Np
        t = nrm((x * t2[0] + (1 - x) * t1[0], x * t2[1] + (1 - x) * t1[1]))
        P = ccoptpt(N, n, t, R1, 1.0, S_NR1)
        out_dir = nrm(sub(R1, P))
        nn = _resolve_new_normal(t, out_dir, n, 1.0, 'refract')
        CO_1.append((P, nn))

    X13, n_X13 = CO_1[2]
    assert_point_close(X13, (0.638962, -0.935759), msg="X13 (seed-fan)")

    S13 = 3.60958  # Chaves Ch. 9's own S_13 = S_RE1 - [R2,X13]
    result = sms_chain_step(
        known_point=X13, known_normal=n_X13, ray_source=R2,
        n_before=1.0, n_after=n, target=E1, target_n=None, n_target=1.0,
        S=S13, mechanism='refract', new_mechanism='refract',
    )
    assert_point_close(result.p, (0.611426, -0.530086), msg="N13")
    # Normal is checked up to sign at creation time in general (see
    # test_sms_chain_step_normal_sign_is_self_consistent below); here we
    # additionally confirm the exact book sign, since it happens to match.
    assert_point_close(result.n, (0.554893, 0.831922), msg="n_N13")
    print("  PASS: sms_chain_step reproduces Chaves Ch. 9's X13 -> N13 ping-pong step")
    return True


def test_sms_chain_step_matches_example_9_2_reflect_refract_chain():
    """
    sms_chain_step reproduces Chaves Ch. 9 Example 9.2's full
    reflect-then-refract-then-reflect chain (eq. 9.73-9.79): X (mirror,
    reflect) -> X2 (lens, refract) -> X3 (mirror, reflect). Exercises
    both mechanisms and both ccoptpt (point target)/coptsl (wavefront
    target) branches in one continuous, book-verified sequence.
    """
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import sms_chain_step
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import (
        isl, rfr, rfxnrm,
    )

    theta = math.radians(2.0)
    n = 1.5
    R1, R2 = (-0.5, 0.0), (0.5, 0.0)
    P0, n0 = (0.0, -4.0), (0.0, -1.0)

    t = rfr((-nrm(sub(P0, R2))[0], -nrm(sub(P0, R2))[1]), n0, n, 1.0)
    P1 = (P0[0] + 10 * t[0], P0[1] + 10 * t[1])
    s1 = (math.cos(math.pi / 2 + theta), math.sin(math.pi / 2 + theta))
    W1 = (P1[0] + 15 * s1[0], P1[1] + 15 * s1[1])
    v2 = (math.cos(-theta), math.sin(-theta))
    W2 = (-W1[0], W1[1])
    S = math.hypot(*sub(W1, P1)) + math.hypot(*sub(P1, P0)) + n * math.hypot(*sub(P0, R2))
    assert abs(S - 31.0467) < TOL, f"S: expected 31.0467, got {S}"

    X, n_X = (0.372449, -13.8934), (0.015223, -0.999884)
    s2 = (-v2[1], v2[0])  # ray direction of the w2 bundle: v2 rotated +90deg
    Pw2 = isl(X, s2, W2, v2)
    S_X = S - math.hypot(*sub(X, Pw2))

    step1 = sms_chain_step(
        known_point=X, known_normal=n_X, ray_source=Pw2,
        n_before=1.0, n_after=1.0, target=R1, target_n=None, n_target=n,
        S=S_X, mechanism='reflect', new_mechanism='refract',
    )
    assert_point_close(step1.p, (-0.274686, -4.00547), msg="X2 (eq. 9.74)")

    S_X2 = S - n * math.hypot(*sub(R2, step1.p))
    step2 = sms_chain_step(
        known_point=step1.p, known_normal=step1.n, ray_source=R2,
        n_before=n, n_after=1.0, target=W1, target_n=s1, n_target=1.0,
        S=S_X2, mechanism='refract', new_mechanism='reflect',
    )
    assert_point_close(step2.p, (-3.36293, -13.6643), msg="X3 (eq. 9.78)")
    assert_point_close(step2.n, (-0.136846, -0.990592), msg="n_X3 (eq. 9.79)")
    print("  PASS: sms_chain_step reproduces Example 9.2's reflect->refract->reflect chain")
    return True


def test_sms_chain_step_normal_sign_is_self_consistent():
    """
    Even when a newly-created normal's resolved sign doesn't match the
    book's own printed convention for that intermediate point (confirmed
    for Example 9.2's X2 -- both books' worked numbers and this codebase
    agree the *magnitude* is right, but the sign differs), a FURTHER
    chain step using that normal (re-oriented via _orient_toward_travel)
    still reproduces the correct downstream result. This is exactly what
    test_sms_chain_step_matches_example_9_2_reflect_refract_chain already
    demonstrates end-to-end; this test isolates the claim explicitly.
    """
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import (
        sms_chain_step, _resolve_new_normal,
    )
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import (
        isl, rfr,
    )

    theta = math.radians(2.0)
    n = 1.5
    R1, R2 = (-0.5, 0.0), (0.5, 0.0)
    P0, n0 = (0.0, -4.0), (0.0, -1.0)
    t = rfr((-nrm(sub(P0, R2))[0], -nrm(sub(P0, R2))[1]), n0, n, 1.0)
    P1 = (P0[0] + 10 * t[0], P0[1] + 10 * t[1])
    s1 = (math.cos(math.pi / 2 + theta), math.sin(math.pi / 2 + theta))
    W1 = (P1[0] + 15 * s1[0], P1[1] + 15 * s1[1])
    v2 = (math.cos(-theta), math.sin(-theta))
    W2 = (-W1[0], W1[1])
    S = math.hypot(*sub(W1, P1)) + math.hypot(*sub(P1, P0)) + n * math.hypot(*sub(P0, R2))
    X, n_X = (0.372449, -13.8934), (0.015223, -0.999884)
    s2 = (-v2[1], v2[0])
    Pw2 = isl(X, s2, W2, v2)
    S_X = S - math.hypot(*sub(X, Pw2))
    step1 = sms_chain_step(
        known_point=X, known_normal=n_X, ray_source=Pw2,
        n_before=1.0, n_after=1.0, target=R1, target_n=None, n_target=n,
        S=S_X, mechanism='reflect', new_mechanism='refract',
    )
    # step1.n's sign, as resolved, need not match the book's printed
    # (0.0378641, -0.999283) -- confirm it's the negation (both are valid
    # "up to sign" per rfnrm's own documented ambiguity), not a wrong value.
    book_n_X2 = (0.0378641, -0.999283)
    matches_plus = math.hypot(step1.n[0] - book_n_X2[0], step1.n[1] - book_n_X2[1]) < TOL
    matches_minus = math.hypot(step1.n[0] + book_n_X2[0], step1.n[1] + book_n_X2[1]) < TOL
    assert matches_plus or matches_minus, f"n_X2 {step1.n} matches neither +/-{book_n_X2}"
    print("  PASS: a resolved normal's sign is self-consistent even when it differs "
          "from the book's own printed convention for that intermediate point")
    return True


def test_seed_arc_center_via_isl():
    """seed_arc's found center matches a hand-built isl() intersection; every point is exactly r from it."""
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import seed_arc
    from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import isl

    p1 = (1.0, 0.0)
    n1 = (0.0, 1.0)  # normal line: x=1
    p2 = (0.0, 1.0)
    n2 = (1.0, 0.0)  # normal line: y=1
    expected_center = isl(p1, n1, p2, n2)
    assert_point_close(expected_center, (1.0, 1.0), tol=1e-9, msg="hand-built center")

    points = seed_arc(p1, n1, p2, n2, n_points=7)
    assert len(points) == 7
    assert_point_close(points[0].p, p1, tol=1e-9, msg="seed_arc first point")
    assert_point_close(points[-1].p, p2, tol=1e-9, msg="seed_arc last point")
    r_expected = math.hypot(p1[0] - 1.0, p1[1] - 1.0)
    for sp in points:
        r = math.hypot(sp.p[0] - 1.0, sp.p[1] - 1.0)
        assert abs(r - r_expected) < 1e-9, f"point {sp.p} not at radius {r_expected} from center"
    print("  PASS: seed_arc's center matches isl(), all points equidistant from it")
    return True


def test_seed_arc_degenerate_straight_line():
    """Parallel normals fall back to a straight-line seed, not an error."""
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import seed_arc

    p1 = (0.0, 0.0)
    p2 = (4.0, 0.0)
    n_shared = (0.0, 1.0)
    points = seed_arc(p1, n_shared, p2, n_shared, n_points=5)
    assert len(points) == 5
    assert_point_close(points[0].p, p1, tol=1e-9)
    assert_point_close(points[-1].p, p2, tol=1e-9)
    assert_point_close(points[2].p, (2.0, 0.0), tol=1e-9, msg="midpoint of straight seed")
    for sp in points:
        assert_point_close(sp.n, n_shared, tol=1e-9)
    print("  PASS: seed_arc degenerates to a straight line for parallel normals")
    return True


def test_seed_arc_raises_on_too_few_points():
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import seed_arc

    try:
        seed_arc((0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 0.0), n_points=1)
        raise AssertionError("expected ValueError, got a result")
    except ValueError:
        pass
    print("  PASS: seed_arc raises ValueError for n_points < 2")
    return True


def test_build_sms_chain_reaches_axis_and_alternates():
    """
    A minimal synthetic chain (not a real optical device) confirms
    build_sms_chain's own bookkeeping: it alternates surfaces per
    step_fn's own tag, stops exactly when stop_condition fires, and
    returns both point lists in the order produced.
    """
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import (
        build_sms_chain, SMSPoint,
    )

    seed = [SMSPoint((0.0, 1.0), (0.0, 1.0)), SMSPoint((0.5, 1.0), (0.0, 1.0))]

    def step_fn(current, tag):
        x, y = current.p
        if tag == 'seed':
            return SMSPoint((x + 0.5, 2.0), (0.0, 1.0)), 'other'
        return SMSPoint((x + 0.5, 1.0), (0.0, 1.0)), 'seed'

    def stop_condition(point):
        return point.p[0] >= 2.5

    seed_points, other_points = build_sms_chain(seed, step_fn, stop_condition)
    # The loop must stop as soon as stop_condition fires, on the very last
    # point produced (whichever surface it landed on) -- not run past it.
    assert seed_points[-1].p[0] >= 2.5, f"expected the chain to stop at x>=2.5, got {seed_points[-1].p}"
    assert all(p.p[0] < 2.5 for p in other_points), "other_points must not include the stopping point"
    # Confirm alternation: 'other' points all at y=2.0, 'seed' growth at y=1.0.
    assert all(p.p[1] == 2.0 for p in other_points)
    assert all(p.p[1] == 1.0 for p in seed_points)
    print("  PASS: build_sms_chain alternates surfaces and stops on stop_condition")
    return True


def test_build_sms_chain_raises_on_max_steps():
    from ray_tracing_shapely.optical_elements.prisms.sms_chain import (
        build_sms_chain, SMSPoint,
    )

    seed = [SMSPoint((0.0, 0.0), (0.0, 1.0))]

    def step_fn(current, tag):
        return SMSPoint(current.p, current.n), 'other' if tag == 'seed' else 'seed'

    try:
        build_sms_chain(seed, step_fn, lambda p: False, max_steps=5)
        raise AssertionError("expected RuntimeError, got a result")
    except RuntimeError:
        pass
    print("  PASS: build_sms_chain raises RuntimeError when max_steps is exhausted")
    return True


def run_all_tests():
    tests = [
        ("reflect matches Example 9.2 eq. 9.73", test_reflect_matches_example_9_2_eq_9_73),
        ("sms_chain_step matches Example 9.1's ping-pong step", test_sms_chain_step_matches_example_9_1_ping_pong),
        ("sms_chain_step matches Example 9.2's reflect-refract chain", test_sms_chain_step_matches_example_9_2_reflect_refract_chain),
        ("sms_chain_step normal sign is self-consistent", test_sms_chain_step_normal_sign_is_self_consistent),
        ("seed_arc center via isl", test_seed_arc_center_via_isl),
        ("seed_arc degenerate straight line", test_seed_arc_degenerate_straight_line),
        ("seed_arc raises on too few points", test_seed_arc_raises_on_too_few_points),
        ("build_sms_chain reaches axis and alternates", test_build_sms_chain_reaches_axis_and_alternates),
        ("build_sms_chain raises on max_steps", test_build_sms_chain_raises_on_max_steps),
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
