"""
Python-specific module: rxi direct
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

Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
RXI OPTIC (DIRECT METHOD) -- Chaves Ch. 9 Section 9.7, Figure 9.70
===============================================================================
The complete RXI of the book's direct method: one dielectric whose top refracts
the light in (R), whose mirrored bottom reflects it (X), whose top then reflects
it by total internal reflection (I) into a cavity over the receiver. The top's
centre, out to the point M, is mirrored, where TIR fails.

The book gives the construction (Figures 9.62-9.70) but no numbers: no worked
example exists for section 9.7. What is checked is what defines the design: its
edge rays reach the receiver's edges, the path lengths it was built on hold at
every point, and the ray from R2 meets the top at M at the critical angle.

Distinct from RXIOptic (rxi.py): a circular-arc dome with no edge-ray design.

See dev_doc/architecture/components/nonimaging_design.md
===============================================================================
"""

from __future__ import annotations

import math
from typing import ClassVar, Dict, List, Optional, Tuple, TYPE_CHECKING

from .base_prism import BasePrism
from .nonimaging_geometry import Point, ccoptpt, rfr
from .sms_chain import (
    RefractedEikonal,
    SMSPoint,
    _bisect,
    curve_through,
    eikonal_reflect_step,
    reflect,
)

if TYPE_CHECKING:
    from ...core.scene import Scene


def _nrm(v: Point) -> Point:
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m)


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point, s: float = 1.0) -> Point:
    return (a[0] + s * b[0], a[1] + s * b[1])


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _refract(d: Point, normal: Point, n1: float, n2: float) -> Optional[Point]:
    """d, the direction of travel, refracted from n1 into n2 (the normal's sign is free)."""
    if _dot(d, normal) < 0.0:
        normal = (-normal[0], -normal[1])
    return rfr((-d[0], -d[1]), normal, n1, n2)


def _snell_normal(d_in: Point, d_out: Point, n1: float, n2: float) -> Point:
    """The normal of the surface refracting d_in (in n1) into d_out (in n2)."""
    return _nrm((n2 * d_out[0] - n1 * d_in[0], n2 * d_out[1] - n1 * d_in[1]))


#: The designs built, by their parameters: the construction is deterministic and takes seconds,
#: and a design is rebuilt whenever a scene is (each trace of a test, each notebook cell). An
#: instance shares its design's points and curves, which are never changed after the build.
_DESIGNS: Dict[tuple, dict] = {}
_DESIGNS_KEPT = 8


class RXIOpticDirect(BasePrism):
    """
    The RXI of Chaves Ch. 9 section 9.7, built as the book builds it (Figures 9.62-9.70).

    The right half is designed and mirrored. The bundle perpendicular to w2 travels toward -x
    and is sent to R1; the one perpendicular to w1, toward +x, to R2. The design grows from
    the rim inward:

    1. **The start** (Figures 9.62-9.64). The virtual aperture QQ*, from étendue,
       [Q, Q*] sin(theta) = [R1, R2]: Q lies ``q_depth`` below A, on the ray r2 (perpendicular
       to w2) through A, the rim. C lies on the top, at ``c_fraction`` of the half-aperture
       from the axis and ``c_rise`` above A; the top AC is straight. B is where r1
       (perpendicular to w1) headed to Q crosses AC. D lies ``d_extension`` along r2
       refracted at A. DE, of the bottom, reflects every ray headed to Q and refracted at AB
       to C: a Cartesian oval, ``ccoptpt(I, n, v, C, n, S_I)``.
    2. **The cavity** (Figure 9.65). MN takes the cone reflected at C to R1: a Cartesian
       oval from C (glass) to R1 (air), its optical path S_CR1 set so that M, its lower end,
       lies on the receiver's line (``s_cr1`` sets it instead). M*N* is its mirror image and
       NN* one cubic matching their normals at N and N*. The receiver is in air.
    3. **The chain** (Figures 9.66-9.69). w3 and w4, the wavefronts of R1 and R2 propagated
       out through the cavity, are carried as optical paths through it
       (``sms_chain.RefractedEikonal``). Rays from w2, refracted by the top built so far and
       reflected at the last bottom portion, give the next top portion at the optical path
       S23 of r2 (w2-A-D-C-R1). Rays of w4 reflected at that top portion give the next bottom
       portion at the path S14 of r1 (w1-B-E-C-R2). The portions alternate inward
       (``sms_chain.eikonal_reflect_step``) until the bottom reaches the cavity, the top the
       axis, or no ray solves a step.
    4. **The mirrors** (Figure 9.70). m_B, the whole bottom. m_T, the top from the axis out
       to M, where the ray from R2 through the cavity meets the top at the critical angle;
       nearer the axis TIR fails. Both are the glass's own coating
       (``BasePrism.edge_reflects``): a mirror reflects from either side, so m_T also shades
       the light arriving on it from outside.

    Where the chain stops short of the axis, one cubic joins the top's two halves across it;
    where the bottom stops short of the cavity, a straight foot joins them. Neither is
    designed.

    Edge labels: ``TOP`` (entrance, refracting; TIR on the way back), ``MT`` (the top's
    mirror), ``MB`` (the bottom mirror), ``CAV`` (the cavity, exit, refracting), ``RIM`` (A
    to D) and ``FOOT`` (the bottom's inner end to the cavity).

    Args:
        r1, r2: The receiver's edges, at one height, r1 left of r2.
        theta_deg: The half-acceptance angle.
        n: The dielectric's refractive index.
        aperture_height: A, the rim's top corner, above the receiver.
        q_depth: Q below A.
        c_fraction: C from the axis, as a fraction of the half-aperture [Q, Q*]/2.
        c_rise: C above A.
        d_extension: D from A, along r2 refracted at A.
        n_points: Points on each portion of the chain (DE has n_points + 1).
        s_cr1: The cavity's optical path from C to R1; None puts M on the receiver's line.
        max_stages: The most portions grown beyond DE.
        edges: ``"spline"`` (each surface an exact cubic Hermite spline through its points)
            or ``"polyline"``.

    Reference:
        Chaves, J., Introduction to Nonimaging Optics, 2nd ed., CRC Press, Ch. 9
        "Miñano-Benítez Design Method", section 9.7 "The RXI Optic: Direct Calculation",
        Figures 9.62-9.70.
    """

    _edge_roles: ClassVar[List[Tuple[str, str]]] = []
    _vertex_roles: ClassVar[List[Tuple[str, str]]] = []
    _apex_vertex_index: ClassVar[Optional[int]] = None
    _supports_refinement: ClassVar[bool] = False
    type = 'RXIOpticDirect'

    def __init__(
        self,
        scene: 'Scene',
        r1: Point,
        r2: Point,
        theta_deg: float,
        n: float = 1.5,
        aperture_height: float = 1.6,
        q_depth: float = 2.0,
        c_fraction: float = 0.7,
        c_rise: float = 0.0,
        d_extension: float = 0.6,
        n_points: int = 6,
        s_cr1: Optional[float] = None,
        max_stages: int = 40,
        name: Optional[str] = None,
        edges: str = "spline",
    ) -> None:
        if abs(r1[1] - r2[1]) > 1e-12 or r1[0] >= r2[0]:
            raise ValueError("RXIOpticDirect: r1 and r2 at one height, r1 left of r2")
        if not 0.0 < c_fraction < 1.0:
            raise ValueError("RXIOpticDirect: 0 < c_fraction < 1")
        if edges not in ("spline", "polyline"):
            raise ValueError(f"edges is 'spline' or 'polyline', got {edges!r}")
        self.r1, self.r2 = r1, r2
        self.theta_deg = theta_deg
        self.n_lens = n
        self.aperture_height = aperture_height
        self.q_depth = q_depth
        self.c_fraction = c_fraction
        self.c_rise = c_rise
        self.d_extension = d_extension
        self.n_points = n_points

        key = (tuple(r1), tuple(r2), theta_deg, n, aperture_height, q_depth, c_fraction, c_rise,
               d_extension, n_points, s_cr1, max_stages)
        design = _DESIGNS.get(key)
        if design is None:
            self._build_start()
            self._build_cavity(s_cr1)
            self._grow(max_stages)
            self._find_mirror_end()
            design = dict(self.__dict__)
            _DESIGNS[key] = design
            while len(_DESIGNS) > _DESIGNS_KEPT:
                _DESIGNS.pop(next(iter(_DESIGNS)))
        else:
            self.__dict__.update(design)

        from ...core.scene_objs.glass.glass import Glass
        Glass.__init__(self, scene, json_obj=None)
        self.size = 0.0
        self._position = (0.0, 0.0)
        self._rotation = 0.0
        self._anchor = 'centroid'
        self.refIndex = n
        self.edges = edges
        self._assemble(edges)
        self._vertex_labels = {i: (str(i), f"Vertex {i}") for i in range(len(self.path))}
        self.auto_label_cardinal()
        if name is not None:
            self.name = name
        self._mirrors: List[object] = []   # the coating is the glass's own: MT and MB reflect

    # ------------------------------------------------------------------
    # 1. The start: Q, A, C, B, AC, D, DE
    # ------------------------------------------------------------------
    def _build_start(self) -> None:
        r1, r2, n = self.r1, self.r2, self.n_lens
        th = math.radians(self.theta_deg)
        self.cx, self.cy = 0.5 * (r1[0] + r2[0]), r1[1]
        half = _dist(r1, r2) / (2.0 * math.sin(th))
        self.half_aperture = half
        # w2's rays travel toward -x (to R1), w1's toward +x (to R2)
        self.v2 = (-math.sin(th), -math.cos(th))
        self.v1 = (math.sin(th), -math.cos(th))
        v1, v2 = self.v1, self.v2

        self.Q = (self.cx + half, self.cy + self.aperture_height - self.q_depth)
        self.Q_star = (self.cx - half, self.Q[1])
        self.A = _add(self.Q, v2, -self.q_depth / math.cos(th))          # on r2, above Q
        self.C = (self.cx + self.c_fraction * half, self.A[1] + self.c_rise)
        A, C, Q = self.A, self.C, self.Q
        ac = _nrm(_sub(C, A))
        normal = (-ac[1], ac[0])
        self.ac_normal = normal if normal[1] > 0.0 else (-normal[0], -normal[1])
        # B: where r1, headed to Q, crosses AC
        along = ((Q[0] - A[0]) * v1[1] - (Q[1] - A[1]) * v1[0]) / (ac[0] * v1[1] - ac[1] * v1[0])
        self.B = _add(A, ac, along)
        if not 0.0 < along < _dist(A, C):
            raise ValueError("RXIOpticDirect: r1 headed to Q misses AC; deepen q_depth or move C")

        t_a = _refract(v2, self.ac_normal, 1.0, n)
        self.D = _add(A, t_a, self.d_extension)
        s_cq = n * _dist(C, self.D) + n * _dist(self.D, A) - _dist(A, Q)   # Q virtual: minus
        self.S_CQ = s_cq
        self.DE: List[SMSPoint] = []
        self.AB_points: List[Point] = []                 # where DE's ray, headed to Q, enters
        for k in range(self.n_points + 1):
            I = _add(A, _sub(self.B, A), k / self.n_points)
            v = _refract(_nrm(_sub(Q, I)), self.ac_normal, 1.0, n)
            J = ccoptpt(I, n, v, C, n, s_cq + _dist(I, Q))
            self.AB_points.append(I)
            self.DE.append(SMSPoint(J, _nrm(_sub(_nrm(_sub(C, J)), v))))
        self.E = self.DE[-1].p
        if self.E[0] >= self.D[0]:
            raise ValueError("RXIOpticDirect: E lies outside D, so the w2 rays reaching DE would "
                             "enter beyond the rim; deepen q_depth")

    # ------------------------------------------------------------------
    # 2. The cavity: MN, M*N*, NN*; the wavefronts w3 and w4 through it
    # ------------------------------------------------------------------
    def _build_cavity(self, s_cr1: Optional[float]) -> None:
        n, C, r1 = self.n_lens, self.C, self.r1
        c_d = reflect(_nrm(_sub(C, self.DE[0].p)), self.ac_normal)     # r2, reflected at C
        c_e = reflect(_nrm(_sub(C, self.DE[-1].p)), self.ac_normal)    # r1
        a_d, a_e = math.atan2(c_d[1], c_d[0]), math.atan2(c_e[1], c_e[0])
        m = 4 * self.n_points
        cone = [(math.cos(a_d + (a_e - a_d) * k / m), math.sin(a_d + (a_e - a_d) * k / m))
                for k in range(m + 1)]

        def oval(S: float) -> List[SMSPoint]:
            out = []
            for t in cone:
                P = ccoptpt(C, n, t, r1, 1.0, S)
                out.append(SMSPoint(P, _snell_normal(t, _nrm(_sub(r1, P)), n, 1.0)))
            return out

        if s_cr1 is None:
            # n t + [P, R1] rises along each ray of the cone from [C, R1] at t = 0
            s_cr1 = _bisect(lambda S: min(q.p[1] for q in oval(S)) - self.cy,
                            _dist(C, r1) * (1.0 + 1e-6), n * _dist(C, r1), tol=1e-13)
        self.S_CR1 = s_cr1
        mn = sorted(oval(s_cr1), key=lambda q: q.p[1])                  # M (low) .. N (high)
        self.MN = mn
        self.M_cav, self.N = mn[0].p, mn[-1].p
        # NN*: the cubic matching the normals at N* and N, carried as knots along it, so that
        # no one span of the cavity is long beside MN's short ones
        n_star = self._mirror(mn[-1])
        cubic = curve_through([n_star.p, mn[-1].p], [n_star.n, mn[-1].n])
        dome = []
        for k in range(1, self.n_points):
            u = k / self.n_points
            d = cubic.deriv(u)
            dome.append(SMSPoint(cubic.point(u), _nrm((-d[1], d[0]))))
        # traversed from M* over N*, N to M: the glass on its left
        left = [self._mirror(q) for q in mn]
        self.cavity_points = left + dome + list(reversed(mn))
        self.cavity = curve_through([q.p for q in self.cavity_points], [q.n for q in self.cavity_points])
        last = float(len(self.cavity_points) - 1)
        self._s_N, self._s_M = float(len(mn) + len(dome)), last
        right_half = (last / 2.0, last)
        self.w3 = RefractedEikonal(self.cavity, ("point", self.r1), 1.0, n, side=1.0, s_range=right_half)
        self.w4 = RefractedEikonal(self.cavity, ("point", self.r2), 1.0, n, side=1.0, s_range=right_half)

        A, B, D, E = self.A, self.B, self.D, self.E
        self.S23 = _dot(A, self.v2) + n * _dist(A, D) + n * _dist(D, C) + s_cr1
        self.S14 = _dot(B, self.v1) + n * _dist(B, E) + n * _dist(E, C) + self.w4(C, hint=self._s_M)[0]

    def _mirror(self, q: SMSPoint) -> SMSPoint:
        """A point of the right half and its normal, mirrored to the left."""
        return SMSPoint((2.0 * self.cx - q.p[0], q.p[1]), (-q.n[0], q.n[1]))

    # ------------------------------------------------------------------
    # 3. The chain, portion by portion, inward
    # ------------------------------------------------------------------
    def _grow(self, max_stages: int) -> None:
        n = self.n_lens
        t_max = 4.0 * self.half_aperture
        top: List[SMSPoint] = [SMSPoint(self.A, self.ac_normal), SMSPoint(self.C, self.ac_normal)]
        bottom: List[SMSPoint] = list(self.DE)
        portion = list(self.DE)
        s1: Dict[Point, float] = {self.C: self._s_N}      # where R1's ray to a top point crosses the cavity
        s2: Dict[Point, float] = {self.C: self._s_M}      # and R2's
        on_bottom, stages = True, 0
        self.stop_reason = "max_stages"
        self.links: List[Tuple[str, SMSPoint, SMSPoint]] = []   # (the new point's surface, from, new)
        while stages < max_stages:
            stages += 1
            top_curve = curve_through([q.p for q in top], [q.n for q in top])
            w2_in = RefractedEikonal(top_curve, ("plane", self.v2), 1.0, n, side=1.0)
            w1_in = RefractedEikonal(top_curve, ("plane", self.v1), 1.0, n, side=1.0)
            new: List[SMSPoint] = []
            hint = s1[top[-1].p] if on_bottom else s2[portion[0].p]
            for K in portion[1:]:
                try:
                    if on_bottom:
                        # w2 through the top, reflected at the bottom point K, to a new top
                        # point, reflected there to R1 through the cavity: S23
                        path, ray, _ = w2_in(K.p)
                        P, hint = eikonal_reflect_step(
                            K.p, K.n, ray, path, lambda X, h=hint: self.w3(X, hint=h), self.S23, n, t_max)
                        s1[P.p] = hint
                    else:
                        # w4 (from R2 through the cavity), reflected at the top point K, to a
                        # new bottom point, reflected there up through the top to w1: S14
                        path, ray, hint = self.w4(K.p, hint=hint)
                        s2[K.p] = hint
                        P, _ = eikonal_reflect_step(K.p, K.n, ray, path, w1_in, self.S14, n, t_max)
                except ValueError:
                    self.stop_reason = "no ray solves the next step"
                    break
                new.append(P)
                self.links.append(("top" if on_bottom else "bottom", K, P))
            if not new:
                break
            if on_bottom:
                portion = [top[-1]] + new
                top.extend(new)
                done = new[-1].p[0] <= self.cx
            else:
                portion = [bottom[-1]] + new
                bottom.extend(new)
                done = new[-1].p[0] <= self.M_cav[0]
            on_bottom = not on_bottom
            if done:
                self.stop_reason = "reached the axis" if not on_bottom else "reached the cavity"
                break
            if len(new) < self.n_points:
                break
        self.stages = stages
        # the top to the axis, the bottom to the cavity; each in order along its surface
        self.top_points = [q for q in top if q.p[0] > self.cx + 1e-9]
        self.bottom_points = [q for q in bottom if q.p[0] >= self.M_cav[0]]
        self._s1, self._s2 = s1, s2

    # ------------------------------------------------------------------
    # 4. m_T: out to M, where R2's ray meets the top at the critical angle
    # ------------------------------------------------------------------
    def _find_mirror_end(self) -> None:
        n = self.n_lens
        self.alpha_c = math.asin(1.0 / n)
        pts = self.top_points
        self.top_curve = curve_through([q.p for q in pts], [q.n for q in pts])
        def normal(s: float) -> Point:
            d = self.top_curve.deriv(s)
            return _nrm((-d[1], d[0]))

        def margin(s: float, hint: float) -> Tuple[float, float]:
            _, ray, h = self.w4(self.top_curve.point(s), hint=hint)
            return math.acos(min(1.0, abs(_dot(ray, normal(s))))) - self.alpha_c, h

        hint = self._s_M
        prev = None
        self.mirror_parameter = None
        for k in range(1, len(pts)):           # C onward: from the rim toward the axis
            try:
                g, hint = margin(float(k), hint)
            except ValueError:
                continue
            if prev is not None and prev[1] > 0.0 >= g:
                h0 = hint
                self.mirror_parameter = _bisect(lambda s: margin(s, h0)[0], prev[0], float(k))
                break
            prev = (float(k), g)
        if self.mirror_parameter is None:
            raise ValueError("RXIOpticDirect: R2's ray never meets the top under the critical "
                             "angle, so there is no M; the design does not close")
        self.M = self.top_curve.point(self.mirror_parameter)
        self.mirror_x = self.M[0] - self.cx

    # ------------------------------------------------------------------
    # The outline
    # ------------------------------------------------------------------
    def _assemble(self, edges: str) -> None:
        from ..roles import Mechanism, Role

        mirror = self._mirror
        top = self.top_points                                  # A, C, ... toward the axis
        top_full = top + [mirror(q) for q in reversed(top)]
        bottom = self.bottom_points                            # D, E, ... toward the cavity
        cav = self.cavity_points                               # M*, ..., N*, N, ..., M
        A, D = top[0].p, bottom[0].p
        A_, D_ = mirror(top[0]).p, mirror(bottom[0]).p
        b_end, b_end_ = bottom[-1].p, mirror(bottom[-1]).p

        top_c = curve_through([q.p for q in top_full], [q.n for q in top_full])
        k_m = self.mirror_parameter
        k_m_ = float(len(top_full) - 1) - k_m                  # M*, by symmetry
        last_top = float(len(top_full) - 1)
        bottom_left = [mirror(q) for q in bottom]
        bottom_right = list(reversed(bottom))
        bl_c = curve_through([q.p for q in bottom_left], [q.n for q in bottom_left])
        br_c = curve_through([q.p for q in bottom_right], [q.n for q in bottom_right])
        M_star = top_c.point(k_m_)

        # (start, curve or None, curve domain, label)
        pieces = [
            (A, top_c, (0.0, k_m), "TOP"),
            (self.M, top_c, (k_m, k_m_), "MT"),
            (M_star, top_c, (k_m_, last_top), "TOP"),
            (A_, None, None, "RIM"),
            (D_, bl_c, (0.0, float(len(bottom_left) - 1)), "MB"),
            (b_end_, None, None, "FOOT"),
            (cav[0].p, self.cavity, (0.0, float(len(cav) - 1)), "CAV"),
            (cav[-1].p, None, None, "FOOT"),
            (b_end, br_c, (0.0, float(len(bottom_right) - 1)), "MB"),
            (D, None, None, "RIM"),
        ]
        names = {
            "TOP": ("Top (refracting; TIR on the way back)", Role.ENTRANCE, Mechanism.REFRACT),
            "MT": ("Top mirror m_T (mirror-coated)", Role.WALL, Mechanism.REFLECT),
            "MB": ("Bottom mirror m_B (mirror-coated)", Role.WALL, Mechanism.REFLECT),
            "CAV": ("Receiver cavity (refracting)", Role.EXIT, Mechanism.REFRACT),
            "RIM": ("Rim", None, Mechanism.REFRACT),
            "FOOT": ("Foot, joining the bottom to the cavity", None, Mechanism.REFRACT),
        }
        path, labels = [], []
        for start, curve, domain, label in pieces:
            if curve is None:
                path.append({'x': float(start[0]), 'y': float(start[1]), 'arc': False})
                labels.append(label)
            elif edges == "spline":
                desc = curve.descriptor()
                desc["domain"] = [domain[0], domain[1]]
                path.append({'x': float(start[0]), 'y': float(start[1]), 'arc': False, 'curve': desc})
                labels.append(label)
            else:
                lo, hi = domain
                knots = [lo] + [float(k) for k in range(math.floor(lo) + 1, math.ceil(hi))] + [hi]
                for p in knots[:-1]:
                    x, y = curve.point(p)
                    path.append({'x': float(x), 'y': float(y), 'arc': False})
                    labels.append(label)
        self.path = path
        self.polyline_vertices = [(v['x'], v['y']) for v in path]
        self._functional_labels, self._edge_role_tags, self._edge_mechanisms = {}, {}, {}
        for i, label in enumerate(labels):
            long, role, mechanism = names[label]
            self._functional_labels[i] = (label, long)
            if role is not None:
                self._edge_role_tags[i] = role
            self._edge_mechanisms[label] = mechanism


__all__ = ['RXIOpticDirect']
