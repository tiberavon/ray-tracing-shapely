"""
Python-specific module: test sms claims
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
What each SMS element claims, tested with rays
===============================================================================
An SMS design claims that its edge rays land on its receiver's edges: the RR
images E1 onto R2, and a concentrator takes a bundle tilted at +theta to one
receiver edge and the bundle at -theta to the other. Traced through the
simulator, the brightest branch of each ray, where it meets the receiver
line. Also, at each pair of chain points, the optical path from the wavefront
to the receiver edge equals the design's S: the construction's invariant.

The RR keeps its claim, and so does the RX of eq. 9.34, the tighter the
denser its seed (the book: "the higher the N_p, the more accurate will be
the focusing"). So does the XR of Example 9.2, its primary a spline mirror,
and every point of its primary keeps the XR's path length.
===============================================================================
"""

from __future__ import annotations

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.blocker.blocker import Blocker
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.prisms.nonimaging_geometry import isl, rfr
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens
from ray_tracing_shapely.optical_elements.prisms.rx_concentrator import RXConcentrator
from ray_tracing_shapely.optical_elements.prisms.xr_concentrator import XRConcentrator

RR = dict(e1=(-1.0, 2.0), e2=(1.0, 2.0), r1=(-0.5, -2.0), r2=(0.5, -2.0))
RX = dict(r1=(-0.5, 0.0), r2=(0.5, 0.0), theta_deg=2.0, n=1.5)


def _unit(v):
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


def _reflect(d, n):
    k = 2.0 * (d[0] * n[0] + d[1] * n[1])
    return (d[0] - k * n[0], d[1] - k * n[1])


def _refract(d, n, n1, n2):
    """d, the direction of travel, refracted from n1 into n2 (the normal's sign is free)."""
    if d[0] * n[0] + d[1] * n[1] < 0.0:
        n = (-n[0], -n[1])
    return rfr((-d[0], -d[1]), n, n1, n2)


def landing(make, start, direction, receiver_y, receiver=None, max_rays=2000):
    """Where the brightest branch of one ray last meets the line y = receiver_y.

    ``make(scene)`` returns the element. ``receiver``, (x_min, x_max), puts an
    absorbing segment there, so a ray that reaches the receiver ends on it.
    None if the branch never meets the line.
    """
    scene = Scene()
    scene.add_object(make(scene))
    if receiver is not None:
        scene.add_object(Blocker(scene, {"p1": {"x": receiver[0], "y": receiver_y},
                                         "p2": {"x": receiver[1], "y": receiver_y}}))
    scene.add_object(SingleRay(scene, {"p1": {"x": start[0], "y": start[1]},
                                       "p2": {"x": start[0] + direction[0], "y": start[1] + direction[1]}}))
    segments = Simulator(scene, max_rays=max_rays).run_with_result(name="landing").segments
    children = {}
    for g in segments:
        children.setdefault(g.parent_uuid, []).append(g)
    branch, g = [], children[None][0]
    while True:
        branch.append(g)
        nxt = children.get(g.uuid)
        if not nxt:
            break
        g = max(nxt, key=lambda c: c.total_brightness)
    found = None
    for k, g in enumerate(branch):
        a, b = (g.p1["x"], g.p1["y"]), (g.p2["x"], g.p2["y"])
        dy = b[1] - a[1]
        if abs(dy) < 1e-15:
            continue
        t = (receiver_y - a[1]) / dy
        last = k == len(branch) - 1
        if t >= -1e-12 and (t <= 1.0 + 1e-12 or last):   # the last segment is a ray: extended
            found = a[0] + t * (b[0] - a[0])
    return found


def edge_bundles(make, theta_deg, xs, start_y, receiver):
    """Landings of the two bundles tilted at +theta and -theta, travelling down."""
    th = math.radians(theta_deg)
    half = (receiver[1] - receiver[0]) / 2.0
    cx = (receiver[0] + receiver[1]) / 2.0
    out = {}
    for sign in (1.0, -1.0):
        d = (sign * math.sin(th), -math.cos(th))
        out[sign] = [landing(make, (x, start_y), d, receiver[2], receiver=(cx - 1.5 * half, cx + 1.5 * half))
                     for x in xs]
    return out


def lands_on_opposite_edges(bundles, edge_a, edge_b, tol):
    """One bundle within tol of one edge, the other bundle of the other edge."""
    def near(values, edge):
        return all(v is not None and abs(v - edge) <= tol for v in values)
    return ((near(bundles[1.0], edge_a) and near(bundles[-1.0], edge_b))
            or (near(bundles[1.0], edge_b) and near(bundles[-1.0], edge_a)))


# ---------------------------------------------------------------------------
# The RR: rays from E1 land on R2 (the positive control)
# ---------------------------------------------------------------------------

def test_the_rr_images_e1_onto_r2():
    def make(sc):
        return RRLens(sc, RR["e1"], RR["e2"], RR["r1"], RR["r2"], seed_n_angle_deg=303.3, seed_x_angle_deg=42.7)

    lens = make(Scene())
    top = max(p["y"] for p in lens.path)
    lands = []
    for xt in (-0.6, -0.3, 0.0, 0.3, 0.6):
        d = _unit((xt - RR["e1"][0], top - RR["e1"][1]))
        lands.append(landing(make, RR["e1"], d, RR["r2"][1]))
    assert all(v is not None and abs(v - RR["r2"][0]) < 0.06 for v in lands), lands


# ---------------------------------------------------------------------------
# XRConcentrator: Example 9.2's chain
# ---------------------------------------------------------------------------

def _xr(scene, edges="spline"):
    xr = XRConcentrator(scene, RX["r1"], RX["r2"], theta_deg=RX["theta_deg"], p0=(0.0, -4.0), n0=(0.0, -1.0),
                        n=RX["n"], edges=edges)
    for mirror in xr.primary:
        scene.add_object(mirror)
    return xr


def test_every_primary_point_keeps_the_xr_path_length_and_its_laws():
    """At every point X of the primary (the axis point aside, which no chain computed), a ray of w2
    reflects to a point L of R, and refracts there to R1: [w2, X] + [X, L] + n[L, R1] = S."""
    xr = _xr(Scene())
    n, th = RX["n"], math.radians(RX["theta_deg"])
    v2 = (math.cos(-th), math.sin(-th))
    s2 = (-v2[1], v2[0])
    lens = [q for q in xr.lens_points] + [type(q)((-q.p[0], q.p[1]), (-q.n[0], q.n[1])) for q in xr.lens_points]
    worst_opl = worst_dir = 0.0
    for X in xr.mirror_points[1:]:
        out = _reflect((-s2[0], -s2[1]), X.n)
        on_ray = [L for L in lens if abs((L.p[0] - X.p[0]) * out[1] - (L.p[1] - X.p[1]) * out[0]) < 1e-7
                  and (L.p[0] - X.p[0]) * out[0] + (L.p[1] - X.p[1]) * out[1] > 0.0]
        assert on_ray, X.p
        L = min(on_ray, key=lambda L: math.dist(L.p, X.p))
        w = isl(X.p, s2, xr.W2, v2)
        opl = math.dist(X.p, w) + math.dist(X.p, L.p) + n * math.dist(L.p, RX["r1"])
        worst_opl = max(worst_opl, abs(opl - xr.S))
        inside = _refract(_unit((L.p[0] - X.p[0], L.p[1] - X.p[1])), L.n, 1.0, n)
        to_r1 = _unit((RX["r1"][0] - L.p[0], RX["r1"][1] - L.p[1]))
        worst_dir = max(worst_dir, abs(inside[0] * to_r1[1] - inside[1] * to_r1[0]))
    assert worst_opl < 1e-9, worst_opl
    assert worst_dir < 1e-9, worst_dir


def test_the_xr_takes_its_edge_rays_to_the_receiver_edges():
    """Rays at +-theta passing beside the dielectric reflect off the primary and refract up through
    R onto the receiver's edges: with the splines, at the book's density, to 1e-4 out to 0.8 of the
    primary (5e-5 measured); the polyline far less closely (the book's "we will not get perfect
    focusing"). Toward the primary's rim the splines' miss grows (3e-3 at 0.98), and shrinks with
    the seed's density (1e-4 with 11 seed points): it is the interpolation's."""
    def landings(edges, fractions, n_seed=6):
        def make(scene):
            xr = XRConcentrator(scene, RX["r1"], RX["r2"], theta_deg=RX["theta_deg"], p0=(0.0, -4.0),
                                n0=(0.0, -1.0), n=RX["n"], edges=edges, n_points_on_seed_circle=n_seed)
            for mirror in xr.primary:
                scene.add_object(mirror)
            return xr
        xr = make(Scene())
        inner = max(abs(q.p[0]) for q in xr.lens_points)
        outer = abs(xr.mirror_points[-1].p[0])
        aperture = [s * (inner + f * (outer - inner)) for s in (-1.0, 1.0) for f in fractions]
        return edge_bundles(make, RX["theta_deg"], aperture, 1.0, (RX["r1"][0], RX["r2"][0], RX["r1"][1]))

    inside = (0.1, 0.3, 0.5, 0.7, 0.8)
    spline, polyline = landings("spline", inside), landings("polyline", inside)
    assert lands_on_opposite_edges(spline, RX["r1"][0], RX["r2"][0], tol=1e-4), spline
    assert _worst(spline) < _worst(polyline) / 100.0
    rim_coarse, rim_dense = landings("spline", (0.98,)), landings("spline", (0.98,), n_seed=11)
    assert _worst(rim_dense) < _worst(rim_coarse) / 10.0


def test_a_denser_xr_seed_builds():
    """With many seed points, some chains end where no lens point can be reached; such points lie
    beyond the primary, and are left out of it, not an error."""
    xr = XRConcentrator(Scene(), RX["r1"], RX["r2"], theta_deg=RX["theta_deg"], p0=(0.0, -4.0), n0=(0.0, -1.0),
                        n=RX["n"], n_points_on_seed_circle=21)
    assert len(xr.mirror_points) > 4 * 42 - 10 and abs(xr.mirror_points[-1].p[0]) == pytest.approx(21.42, abs=0.05)


# ---------------------------------------------------------------------------
# RXConcentrator: eq. 9.34
# ---------------------------------------------------------------------------

def _rx_landings(n_seed, edges="spline"):
    def make(scene):
        return RXConcentrator(scene, RX["r1"], RX["r2"], theta_deg=RX["theta_deg"], n=RX["n"], n_seed=n_seed,
                              edges=edges)

    rx = make(Scene())
    half = max(abs(q.p[0]) for q in rx.lens_points)
    top = max(q.p[1] for q in rx.lens_points)          # from the surface: a spline path keeps only its corners
    aperture = [s * f * half for s in (-1.0, 1.0) for f in (0.15, 0.3, 0.5, 0.7, 0.9)]
    return edge_bundles(make, RX["theta_deg"], aperture, top + 1.0, (RX["r1"][0], RX["r2"][0], RX["r1"][1]))


def _worst(bundles):
    return max(max(abs(v - RX["r2"][0]) for v in bundles[1.0]), max(abs(v - RX["r1"][0]) for v in bundles[-1.0]))


def test_the_rx_takes_its_edge_rays_to_the_receiver_edges():
    """The bundle travelling toward +x (perpendicular to w1) lands on R2, the other on R1: with the
    spline surfaces to 1e-4 (1.3e-5 measured), with the polyline far less closely."""
    spline, polyline = _rx_landings(6), _rx_landings(6, edges="polyline")
    assert lands_on_opposite_edges(spline, RX["r1"][0], RX["r2"][0], tol=1e-4), spline
    assert lands_on_opposite_edges(polyline, RX["r1"][0], RX["r2"][0], tol=0.2), polyline
    assert _worst(spline) < _worst(polyline) / 100.0


def test_the_rx_accepts_inside_its_angle_and_not_outside():
    """On-axis rays land at the receiver's centre, rays at half the angle halfway to its edge, and
    rays at 1.5 times the angle beyond it."""
    def make(scene):
        return RXConcentrator(scene, RX["r1"], RX["r2"], theta_deg=RX["theta_deg"], n=RX["n"])

    rx = make(Scene())
    half = max(abs(q.p[0]) for q in rx.lens_points)
    top = max(q.p[1] for q in rx.lens_points)
    xs = [s * f * half for s in (-1.0, 1.0) for f in (0.3, 0.6, 0.9)]

    def lands(factor):
        th = math.radians(factor * RX["theta_deg"])
        return [landing(make, (x, top + 1.0), (math.sin(th), -math.cos(th)), RX["r1"][1], receiver=(-0.75, 0.75))
                for x in xs]
    assert all(v is not None and abs(v) < 0.02 for v in lands(0.0))
    assert all(v is not None and abs(v - 0.25) < 0.02 for v in lands(0.5))
    assert all(v is None or v > RX["r2"][0] + 0.2 for v in lands(1.5))
