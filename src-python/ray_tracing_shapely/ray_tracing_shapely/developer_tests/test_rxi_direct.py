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
RXIOPTICDIRECT TESTS: the complete RXI of Chaves Ch. 9, Figure 9.70
===============================================================================
The book gives section 9.7's construction but no worked example, so these tests
check what defines the design rather than published numbers: every surface keeps
the optical path it was built on, M is where R2's ray meets the top at the critical
angle, and the edge rays reach the receiver's edges in the simulator.

Run with:
    pytest developer_tests/test_rxi_direct.py -v
===============================================================================
"""

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import rfr
from ray_tracing_shapely.optical_elements.prisms.rxi_direct import RXIOpticDirect
from ray_tracing_shapely.optical_elements.prisms.sms_chain import RefractedEikonal, curve_through, reflect

R1, R2 = (-1.0, 0.0), (1.0, 0.0)
THETA = 10.0
N = 1.5


def _make(scene, **kw):
    return RXIOpticDirect(scene, R1, R2, theta_deg=THETA, n=N, **kw)


@pytest.fixture(scope="module")
def rxi():
    return _make(Scene())


def _unit(v):
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _refract(d, n, n1, n2):
    if _dot(d, n) < 0.0:
        n = (-n[0], -n[1])
    return rfr((-d[0], -d[1]), n, n1, n2)


def landings(starts, direction, receiver=(-1.5, 1.5)):
    """Where the brightest branch of each ray last meets the receiver's line: one RXI, one scene."""
    scene = Scene()
    scene.add_object(_make(scene))
    scene.add_object(Blocker(scene, {"p1": {"x": receiver[0], "y": R1[1]}, "p2": {"x": receiver[1], "y": R1[1]}}))
    for x, y in starts:
        scene.add_object(SingleRay(scene, {"p1": {"x": x, "y": y},
                                           "p2": {"x": x + direction[0], "y": y + direction[1]}}))
    segments = Simulator(scene, max_rays=20000).run_with_result(name="rxi landings").segments
    children = {}
    for g in segments:
        children.setdefault(g.parent_uuid, []).append(g)
    out = {}
    for root in children[None]:
        branch, g = [], root
        while True:
            branch.append(g)
            nxt = children.get(g.uuid)
            if not nxt:
                break
            g = max(nxt, key=lambda c: c.total_brightness)
        found = None
        for k, g in enumerate(branch):
            a, b = (g.p1["x"], g.p1["y"]), (g.p2["x"], g.p2["y"])
            if abs(b[1] - a[1]) < 1e-15:
                continue
            t = (R1[1] - a[1]) / (b[1] - a[1])
            if t >= -1e-12 and (t <= 1.0 + 1e-12 or k == len(branch) - 1):
                found = a[0] + t * (b[0] - a[0])
        out[round(root.p1["x"], 9)] = found
    return out


# ---------------------------------------------------------------------------
# The start (Figures 9.62-9.64)
# ---------------------------------------------------------------------------

def test_the_virtual_aperture_comes_from_etendue(rxi):
    assert _dist(rxi.Q, rxi.Q_star) * math.sin(math.radians(THETA)) == pytest.approx(_dist(R1, R2), abs=1e-12)
    # A lies on r2 (perpendicular to w2) through Q, above it; B on r1 through Q, on AC
    u = _unit((rxi.Q[0] - rxi.A[0], rxi.Q[1] - rxi.A[1]))
    assert u[0] == pytest.approx(rxi.v2[0], abs=1e-12) and u[1] == pytest.approx(rxi.v2[1], abs=1e-12)
    u = _unit((rxi.Q[0] - rxi.B[0], rxi.Q[1] - rxi.B[1]))
    assert u[0] == pytest.approx(rxi.v1[0], abs=1e-12) and u[1] == pytest.approx(rxi.v1[1], abs=1e-12)
    ac, ab = _unit((rxi.C[0] - rxi.A[0], rxi.C[1] - rxi.A[1])), _unit((rxi.B[0] - rxi.A[0], rxi.B[1] - rxi.A[1]))
    assert ac[0] * ab[1] - ac[1] * ab[0] == pytest.approx(0.0, abs=1e-12)


def test_de_reflects_every_ray_headed_to_q_onto_c(rxi):
    """Each ray headed to Q, refracted at AB and reflected at DE, reaches C with the path S_CQ."""
    for I, J in zip(rxi.AB_points, rxi.DE):
        v = _refract(_unit((rxi.Q[0] - I[0], rxi.Q[1] - I[1])), rxi.ac_normal, 1.0, N)
        assert _unit((J.p[0] - I[0], J.p[1] - I[1]))[0] == pytest.approx(v[0], abs=1e-9)
        out = reflect(v, J.n)
        to_c = _unit((rxi.C[0] - J.p[0], rxi.C[1] - J.p[1]))
        assert out[0] == pytest.approx(to_c[0], abs=1e-9) and out[1] == pytest.approx(to_c[1], abs=1e-9)
        path = N * _dist(rxi.C, J.p) + N * _dist(J.p, I) - _dist(I, rxi.Q)
        assert path == pytest.approx(rxi.S_CQ, abs=1e-9)
    assert rxi.DE[0].p == rxi.D and rxi.E[0] < rxi.D[0]


# ---------------------------------------------------------------------------
# The cavity (Figure 9.65)
# ---------------------------------------------------------------------------

def test_mn_takes_the_cone_reflected_at_c_to_r1(rxi):
    for q in rxi.MN:
        assert N * _dist(rxi.C, q.p) + _dist(q.p, R1) == pytest.approx(rxi.S_CR1, abs=1e-9)
        out = _refract(_unit((q.p[0] - rxi.C[0], q.p[1] - rxi.C[1])), q.n, N, 1.0)
        to_r1 = _unit((R1[0] - q.p[0], R1[1] - q.p[1]))
        assert out[0] == pytest.approx(to_r1[0], abs=1e-9) and out[1] == pytest.approx(to_r1[1], abs=1e-9)
    # M, MN's lower end, on the receiver's line; N above it, nearer the axis
    assert rxi.M_cav[1] == pytest.approx(R1[1], abs=1e-9)
    assert rxi.N[1] > rxi.M_cav[1] and 0.0 < rxi.N[0] < rxi.M_cav[0]
    # the cavity's two halves mirror each other, and through C it carries R1's path S_CR1
    assert rxi.w3(rxi.C, hint=rxi._s_N)[0] == pytest.approx(rxi.S_CR1, abs=1e-9)


# ---------------------------------------------------------------------------
# The chain (Figures 9.66-9.69)
# ---------------------------------------------------------------------------

def test_every_chain_point_keeps_its_optical_path_and_its_law(rxi):
    """Each top point: w2, through the top, reflected at the bottom point it was made from, then at
    the top point to R1 through the cavity, at the path S23. Each bottom point: w4 (from R2 through
    the cavity) reflected at the top point, then at the bottom point up through the top to w1,
    at S14. At each new point the normal reflects the one ray into the other."""
    top = rxi.top_points
    top_c = curve_through([q.p for q in top], [q.n for q in top])
    w2_in = RefractedEikonal(top_c, ("plane", rxi.v2), 1.0, N)
    w1_in = RefractedEikonal(top_c, ("plane", rxi.v1), 1.0, N)
    assert len(rxi.links) >= 4 * rxi.n_points
    for kind, K, P in rxi.links:
        if kind == "top":
            before, ray, _ = w2_in(K.p)
            after, back, _ = rxi.w3(P.p, hint=rxi._s1[P.p])
            S = rxi.S23
        else:
            before, ray, _ = rxi.w4(K.p, hint=rxi._s2[K.p])
            after, back, _ = w1_in(P.p)
            S = rxi.S14
        d = reflect(ray, K.n)
        along = _unit((P.p[0] - K.p[0], P.p[1] - K.p[1]))
        assert along[0] == pytest.approx(d[0], abs=1e-9) and along[1] == pytest.approx(d[1], abs=1e-9)
        assert before + N * _dist(K.p, P.p) + after == pytest.approx(S, abs=1e-9)
        out = reflect(d, P.n)
        assert out[0] == pytest.approx(-back[0], abs=1e-7) and out[1] == pytest.approx(-back[1], abs=1e-7)


def test_the_chain_grows_inward(rxi):
    xs = [q.p[0] for q in rxi.top_points]
    assert all(b < a for a, b in zip(xs, xs[1:]))
    assert xs[-1] < rxi.M[0]                               # the top reaches inside M
    assert rxi.bottom_points[0].p == rxi.D


# ---------------------------------------------------------------------------
# The mirrors (Figure 9.70)
# ---------------------------------------------------------------------------

def test_r2s_ray_meets_the_top_at_m_at_the_critical_angle(rxi):
    """At M the ray from R2 (the book's r3) meets the top at the critical angle; R1's (r4) at a
    wider one; nearer the axis TIR fails, further out it holds."""
    def incidence(s, eikonal, hint):
        P = rxi.top_curve.point(s)
        d = rxi.top_curve.deriv(s)
        normal = _unit((-d[1], d[0]))
        _, ray, _ = eikonal(P, hint=hint)
        return math.acos(abs(_dot(ray, normal)))

    s = rxi.mirror_parameter
    h2, h1 = rxi._s2[rxi.top_points[int(s)].p], rxi._s1[rxi.top_points[int(s)].p]
    assert incidence(s, rxi.w4, h2) == pytest.approx(rxi.alpha_c, abs=1e-9)
    assert incidence(s, rxi.w3, h1) > rxi.alpha_c
    assert incidence(s + 0.5, rxi.w4, h2) < rxi.alpha_c < incidence(s - 0.5, rxi.w4, h2)


def test_the_labels_and_the_coatings(rxi):
    labels = [rxi.get_functional_label(s.index)[0] for s in rxi.spans]
    assert labels == ["TOP", "MT", "TOP", "RIM", "MB", "FOOT", "CAV", "FOOT", "MB", "RIM"]
    reflects = {lab: rxi.edge_reflects(s.path_indices[0]) for lab, s in zip(labels, rxi.spans)}
    assert reflects == {"TOP": False, "MT": True, "RIM": False, "MB": True, "FOOT": False, "CAV": False}
    # the top is one spline, cut at M and M*: three domains of the same curve
    top = [s for s, lab in zip(rxi.spans, labels) if lab in ("TOP", "MT")]
    assert len({str(rxi.path[s.path_indices[0]]["curve"]["points"]) for s in top}) == 1


def test_the_old_form_is_refused():
    for old in ({"c_height_fraction": 0.4}, {"n_stages": 2}, {"s_cr1_margin": 1.3}, {"n_points_de": 6}):
        with pytest.raises(TypeError):
            RXIOpticDirect(Scene(), R1, R2, theta_deg=THETA, **old)


# ---------------------------------------------------------------------------
# The edge rays, in the simulator
# ---------------------------------------------------------------------------

W2_ON_R1 = [0.65, 0.7, 0.75, 0.8, 0.9, 0.95]
W1_ON_R2 = [0.4, 0.5, 0.6, 0.7, 0.8]


def test_the_edge_rays_reach_the_receiver_edges(rxi):
    """The bundle perpendicular to w2 (toward -x) lands on R1, the one perpendicular to w1 on R2,
    over the aperture outside the central shadow and the start's portion."""
    half = rxi.half_aperture
    y = max(q.p[1] for q in rxi.top_points) + 1.0
    on_r1 = landings([(f * half, y) for f in W2_ON_R1], rxi.v2)
    on_r2 = landings([(f * half, y) for f in W1_ON_R2], rxi.v1)
    assert all(v is not None and abs(v - R1[0]) < 2e-3 for v in on_r1.values()), on_r1
    assert all(v is not None and abs(v - R2[0]) < 2e-3 for v in on_r2.values()), on_r2


def test_the_central_mirror_shades_the_centre(rxi):
    """Light arriving on m_T from outside is reflected away: nothing reaches the receiver."""
    half = rxi.half_aperture
    y = max(q.p[1] for q in rxi.top_points) + 1.0
    xs = [f * rxi.mirror_x for f in (0.2, 0.5, 0.8)]
    out = landings([(x, y) for x in xs], (0.0, -1.0))
    assert all(v is None or abs(v) > 1.5 for v in out.values()), out
    assert rxi.mirror_x < 0.5 * half


def test_the_rxi_accepts_inside_its_angle_and_not_outside(rxi):
    """Of a bundle filling the aperture, more than half reaches the receiver at 0 and at half the
    acceptance angle (m_T shades the central 36 %; 54 % and 56 % measured), and almost none at
    1.25 times it (none measured)."""
    rim = rxi.top_points[0].p
    y = max(q.p[1] for q in rxi.top_points) + 1.0
    xs = [-rim[0] + 2.0 * rim[0] * (k + 0.5) / 41 for k in range(41)]

    def reaching(factor):
        th = math.radians(factor * THETA)
        d = (math.sin(th), -math.cos(th))
        starts = [(x - (y - rim[1]) * math.tan(th), y) for x in xs]   # across the rim's width
        out = landings(starts, d)
        return sum(1 for v in out.values() if v is not None and R1[0] <= v <= R2[0]) / len(xs)

    assert reaching(0.0) > 0.5
    assert reaching(0.5) > 0.5
    assert reaching(1.25) < 0.05
