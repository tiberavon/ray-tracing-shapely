"""
Python-specific module: edge bundles -- Map A, the optical path length spread of an SMS design's edge rays
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
PYTHON-SPECIFIC MODULE: edge bundles
===============================================================================
An SMS design is made so that the rays from one edge point of the source
reach one edge point of the receiver with one optical path length: for the RR
lens of Chaves (Ch. 9), the rays from E1 reach R2, and those from E2 reach R1.
An *edge bundle* is a fan of such rays, and *Map A* is how far each ray's S
is from the bundle's mean. One value across a bundle means the condition
holds; a gradient is an aberration, and its sign says which way to push.

**The fan.** A bundle is aimed from its source point at the designed entrance
surface: through each Hermite point of the spline edge (a *knot*, a designed
point) and at ``per_span - 1`` points between two knots, evenly in the
spline's parameter. An SMS design sends a ray through a knot of one surface
onto a knot of the other, so these rays also check that a line through a knot
to round-off meets the spline (`KW-CORE-03`, closed).

**S to the target.** A ray of the bundle is read along its designed route:
refracted by the entrance edge, then by the exit edge, nothing else. Its S is
summed to the exit point and completed to the target point:
``S = S(source -> exit) + n_target |exit - target|``, the reference sphere
centred on the target. A ray on another route (the rim, a corner, a partial
reflection) is off route and out of the map. Completing to a point does not
depend on where the ray goes after the exit, so S of a re-traced ray needs no
end-point correction (unlike a tube's arrival at a receiver,
`first_order.opl_at_old_end`).

**What S does not see.** Rays that leave through one point of the exit
surface (a corner the design's first fan aims at) have the same S to the
target whatever their direction. So each ray also carries its *miss*, the
signed distance from the target to its outgoing line: the transverse
aberration, which Map A alone does not show.

**Every index read, none assumed** (`C-SCULPT-05`). S is the sum of each
segment's ``medium_index`` times its length. A segment that carries no index
is not taken as 1: the ray is reported (``unindexed``), and left out of the
mean and the spread. A gradient-index glass is refused, as for the tubes.

**The first order** (`predict`): for a handle moved by delta, the change of a
bundle ray's S is ``(p_in - p_out) . dx`` at each of its hits on the moved
edge (`first_order`), where at the exit hit p_out is the momentum toward the
target, not the ray's own: the completion is a segment of the path. The slide
of the exit point along the exit surface enters only through the ray's own
aberration (its outgoing direction against the direction to the target).

Bundles, unlike tubes, are described by the design, not cut from a trace:
`rr_bundles` writes the RR lens's two from its recipe (E1 aimed at R2, E2 at
R1, entering by the N surface and leaving by the X surface). Another recipe's
bundles are added when they are written down and checked against its book
example.
===============================================================================
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .flux_tubes import FluxTubeError, RaySeed, Route, SurfaceHit, _copy, _direction, _unit, _walk

XY = Tuple[float, float]

#: An exit point this close to a knot of the exit edge, in its parameter, is at that knot.
_AT_KNOT = 1e-6


class EdgeBundleError(ValueError):
    """A bundle that cannot be aimed or read, with the reason."""


@dataclass(frozen=True)
class BundleSpec:
    """What the design asks of one edge bundle.

    Attributes:
        bundle_id: ``"E1->R2"``.
        glass: The designed glass's name.
        source: The edge point the rays leave from.
        target: The edge point they must reach.
        entrance: The edge they enter by (its index, as routes count edges).
        exit: The edge they leave by.
        target_index: The index of the medium the target is in.
    """

    bundle_id: str
    glass: str
    source: XY
    target: XY
    entrance: int
    exit: int
    target_index: float = 1.0


@dataclass(frozen=True)
class BundleSettings:
    """The numerical parameters of the bundles, apart from the design (`KC3`).

    Attributes:
        per_span: Rays per span of the entrance edge: one through its first knot, the rest
            between its knots. 1 aims at the knots only.
        max_rays: The trace's segment cap.
        min_brightness_exp: The weak-ray threshold, explicit, so every ray is traced on its own
            (as `flux_tubes.TubeSettings`).
    """

    per_span: int = 2
    max_rays: int = 200_000
    min_brightness_exp: int = 6

    def __post_init__(self) -> None:
        if self.per_span < 1:
            raise EdgeBundleError(f"per_span must be at least 1, got {self.per_span}")
        if self.max_rays < 1:
            raise EdgeBundleError(f"max_rays must be at least 1, got {self.max_rays}")


@dataclass(frozen=True)
class BundleRay:
    """One ray of a bundle, read along the designed route.

    Attributes:
        seed: Its index in the bundle's seeds.
        aim: The entrance edge's spline parameter it was aimed at.
        knot: Whether that is a designed point (a knot).
        route: The route it took, as tubes write them.
        on_route: Whether that is the designed route.
        opl: S from the source to the exit point, completed to the target; None off route or
            unindexed.
        miss: The signed distance from the target to its outgoing line (counter-clockwise of
            the direction positive); None off route.
        exit_knot: Whether it left by a knot of the exit edge.
        entry: Where it met the entrance edge.
        exit: Where it left by the exit edge.
        hits: Its optical events along the route, for the first-order estimate.
        unindexed: The positions in its path of segments that carry no medium index.
    """

    seed: int
    aim: float
    knot: bool
    route: Route
    on_route: bool
    opl: Optional[float]
    miss: Optional[float]
    exit_knot: bool = False
    entry: Optional[XY] = None
    exit: Optional[XY] = None
    hits: Tuple[SurfaceHit, ...] = ()
    unindexed: Tuple[int, ...] = ()


@dataclass(frozen=True)
class EdgeBundle:
    """A bundle traced: its seeds and its rays."""

    spec: BundleSpec
    seeds: Tuple[RaySeed, ...]
    rays: Tuple[BundleRay, ...]

    @property
    def bundle_id(self) -> str:
        return self.spec.bundle_id

    @property
    def counted(self) -> Tuple[BundleRay, ...]:
        """The rays in the map: on the designed route, every segment indexed."""
        return tuple(r for r in self.rays if r.opl is not None)

    @property
    def mean(self) -> Optional[float]:
        counted = self.counted
        return sum(r.opl for r in counted) / len(counted) if counted else None

    def deviations(self) -> Dict[int, float]:
        """Map A: per counted ray (by seed), its S minus the bundle's mean."""
        m = self.mean
        return {r.seed: r.opl - m for r in self.counted}

    @property
    def spread(self) -> Optional[float]:
        """Peak to valley of S over the counted rays."""
        counted = self.counted
        return max(r.opl for r in counted) - min(r.opl for r in counted) if counted else None

    @property
    def rms(self) -> Optional[float]:
        dev = list(self.deviations().values())
        return math.sqrt(sum(d * d for d in dev) / len(dev)) if dev else None


@dataclass
class BundleSet:
    """The bundles of one design, traced together."""

    settings: BundleSettings
    bundles: Tuple[EdgeBundle, ...]
    trace_seconds: float = 0.0

    def bundle(self, bundle_id: str) -> EdgeBundle:
        for b in self.bundles:
            if b.bundle_id == bundle_id:
                return b
        raise KeyError(f"no bundle {bundle_id!r}; bundles: {', '.join(b.bundle_id for b in self.bundles)}")

    def map_a(self) -> List[Dict[str, Any]]:
        """Per bundle: its mean S, spread, rms, the largest miss, and the rays counted, off route
        and reported for a missing index."""
        out = []
        for b in self.bundles:
            misses = [abs(r.miss) for r in b.counted if r.miss is not None]
            out.append({
                "bundle_id": b.bundle_id, "mean": b.mean, "spread": b.spread, "rms": b.rms,
                "max_miss": max(misses) if misses else None,
                "counted": len(b.counted),
                "off_route": [r.seed for r in b.rays if not r.on_route],
                "unindexed": [r.seed for r in b.rays if r.unindexed],
            })
        return out

    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BundleSet":
        def pair(v: Any) -> Optional[XY]:
            return None if v is None else (float(v[0]), float(v[1]))

        def route(v: Any) -> Route:
            return tuple((str(n), e, str(ev)) for n, e, ev in v)

        bundles = []
        for b in data["bundles"]:
            s = b["spec"]
            spec = BundleSpec(s["bundle_id"], s["glass"], pair(s["source"]), pair(s["target"]),
                              int(s["entrance"]), int(s["exit"]), float(s["target_index"]))
            seeds = tuple(RaySeed(pair(x["p"]), pair(x["d"]), float(x["brightness"]), x.get("wavelength"))
                          for x in b["seeds"])
            rays = tuple(BundleRay(
                r["seed"], r["aim"], r["knot"], route(r["route"]), r["on_route"], r["opl"], r["miss"],
                r["exit_knot"], pair(r["entry"]), pair(r["exit"]),
                tuple(SurfaceHit(h["surface"], h["edge"], pair(h["point"]), pair(h["p_in"]), pair(h["p_out"]),
                                 h["event"]) for h in r["hits"]),
                tuple(r["unindexed"])) for r in b["rays"])
            bundles.append(EdgeBundle(spec, seeds, rays))
        return cls(BundleSettings(**data["settings"]), tuple(bundles), data.get("trace_seconds", 0.0))


# --- the design's bundles -----------------------------------------------------------------


def rr_bundles(lens: Any, glass: Optional[str] = None) -> List[BundleSpec]:
    """The RR lens's two edge bundles, from its recipe: E1 aimed at R2, E2 at R1.

    Args:
        lens: An `RRLens`.
        glass: The name of the glass in the scene the bundles are traced on (the lens's own,
            if not given; give it for a baked copy of the lens).
    """
    from ..optical_elements.prisms.rr_lens import RRLens  # noqa: PLC0415
    if not isinstance(lens, RRLens):
        raise EdgeBundleError(f"rr_bundles takes an RRLens, got a {type(lens).__name__}: its edge bundles are "
                              f"not written down")
    labels = {v[0]: k for k, v in lens._functional_labels.items() if v[0] in ("N", "X")}
    name = glass or lens.name
    pt = lambda p: (float(p[0]), float(p[1]))  # noqa: E731
    return [BundleSpec("E1->R2", name, pt(lens.e1), pt(lens.r2), labels["N"], labels["X"]),
            BundleSpec("E2->R1", name, pt(lens.e2), pt(lens.r1), labels["N"], labels["X"])]


# --- aiming and reading -------------------------------------------------------------------


def _glass(scene: Any, name: str) -> Any:
    found = [o for o in scene.objs if o.name == name]
    if not found:
        raise EdgeBundleError(f"no object named {name!r}")
    if not getattr(found[0], "path", None):
        raise EdgeBundleError(f"{name!r} is a {type(found[0]).__name__}, not a glass with an outline")
    return found[0]


def _spline(glass: Any, edge: int) -> Any:
    from ..core.glass_spans import glass_spans  # noqa: PLC0415
    spans = [s for s in glass_spans(glass.path) if s.index == edge]
    if not spans:
        raise EdgeBundleError(f"{glass.name!r} has no edge {edge}")
    if spans[0].kind != "spline":
        raise EdgeBundleError(f"edge {edge} of {glass.name!r} is a {spans[0].kind}, not a designed spline")
    return spans[0].shape


def _aims(curve: Any, per_span: int) -> List[Tuple[float, bool]]:
    """Spline parameters to aim at, each with whether it is a knot, in the curve's own order."""
    last = len(curve.points) - 1
    out: List[Tuple[float, bool]] = []
    for k in range(last + 1):
        out.append((float(k), True))
        if k < last:
            out.extend((k + j / per_span, False) for j in range(1, per_span))
    return out


def _seeds(scene: Any, spec: BundleSpec, settings: BundleSettings) -> Tuple[Tuple[RaySeed, ...], List[Tuple[float, bool]]]:
    curve = _spline(_glass(scene, spec.glass), spec.entrance)
    aims = _aims(curve, settings.per_span)
    seeds = []
    for p, _ in aims:
        q = curve.point(p)
        d = _unit(q[0] - spec.source[0], q[1] - spec.source[1])
        if d == (0.0, 0.0):
            raise EdgeBundleError(f"bundle {spec.bundle_id}: its source lies on the entrance edge")
        seeds.append(RaySeed(spec.source, d, 1.0))
    return tuple(seeds), aims


def _strict_opl(path: Sequence[Any], upto: int) -> Tuple[float, Tuple[int, ...]]:
    """S over ``path[:upto + 1]``, and the positions of the segments that carry no index."""
    total, missing = 0.0, []
    for i, seg in enumerate(path[:upto + 1]):
        n = getattr(seg, "medium_index", None)
        if n is None:
            missing.append(i)
            continue
        total += n * math.hypot(seg.p2["x"] - seg.p1["x"], seg.p2["y"] - seg.p1["y"])
    return total, tuple(missing)


def _sources(scene: Any) -> List[Any]:
    from ..core.scene_objs.light_source.angle_source import AngleSource  # noqa: PLC0415
    from ..core.scene_objs.light_source.beam import Beam  # noqa: PLC0415
    from ..core.scene_objs.light_source.point_source import PointSource  # noqa: PLC0415
    from ..core.scene_objs.light_source.single_ray import SingleRay  # noqa: PLC0415
    from ..optical_elements.sources.ray_set_source import RaySetSource  # noqa: PLC0415
    return [o for o in scene.objs if isinstance(o, (AngleSource, Beam, PointSource, SingleRay, RaySetSource))]


def _bundle_scene(scene: Any, specs: Sequence[BundleSpec], seeds: Sequence[Sequence[RaySeed]],
                  settings: BundleSettings) -> Any:
    """A copy of the scene, its sources replaced by one `RaySetSource` per bundle."""
    from ..optical_elements.sources.ray_set_source import RaySetSource  # noqa: PLC0415
    copy = _copy(scene, settings)
    for obj in _sources(copy):
        copy.remove_object(obj)
    names = {o.name for o in copy.objs}
    for spec, ss in zip(specs, seeds):
        if spec.bundle_id in names:
            raise EdgeBundleError(f"the scene has an object named {spec.bundle_id!r}, the bundle's own name")
        src = RaySetSource.from_rays(copy, [s.p for s in ss], [s.d for s in ss], [s.brightness for s in ss])
        src.name = spec.bundle_id
        copy.add_object(src)
    return copy


def _read(sim: Any, objects: Dict[str, Any], spec: BundleSpec, aims: Sequence[Tuple[float, bool]],
          roots: Sequence[Any], leaves: Dict[str, List[List[Any]]], exit_curve: Any) -> Tuple[BundleRay, ...]:
    """Each seed's ray along the designed route, from the trace's leaves under its root."""
    designed = ((spec.glass, spec.entrance, "refract"), (spec.glass, spec.exit, "refract"))
    spans: Dict[str, Any] = {}
    out = []
    for j, root in enumerate(roots):
        aim, knot = aims[j]
        best = None
        for path in leaves.get(root.uuid, []):
            route, hits = _walk(path, objects, "", spans)
            route = route[:-1]
            if route == designed:
                best = (path, route, hits)
                break
            if best is None or path[-1].brightness_s + path[-1].brightness_p > \
                    best[0][-1].brightness_s + best[0][-1].brightness_p:
                best = (path, route, hits)
        if best is None:
            out.append(BundleRay(j, aim, knot, (), False, None, None))
            continue
        path, route, hits = best
        if route != designed:
            out.append(BundleRay(j, aim, knot, route, False, None, None, hits=hits))
            continue
        last = max(i for i, seg in enumerate(path) if seg.hit_surface_uuid is not None)
        s, missing = _strict_opl(path, last)
        ex = hits[-1].point
        d = _direction(path[last + 1])
        to = (spec.target[0] - ex[0], spec.target[1] - ex[1])
        miss = d[0] * to[1] - d[1] * to[0]
        _, p = exit_curve.nearest(ex)
        opl = None if missing else s + spec.target_index * math.hypot(*to)
        out.append(BundleRay(j, aim, knot, route, True, opl, miss, abs(p - round(p)) <= _AT_KNOT,
                             hits[0].point, ex, hits, missing))
    return tuple(out)


def _trace(scene: Any, specs: Sequence[BundleSpec], seeds: Sequence[Tuple[RaySeed, ...]],
           aims: Sequence[List[Tuple[float, bool]]], settings: BundleSettings) -> BundleSet:
    from ..core.simulator import Simulator  # noqa: PLC0415
    copy = _bundle_scene(scene, specs, seeds, settings)
    sim = Simulator(copy, max_rays=settings.max_rays, record_surface_hits=True)
    t0 = time.perf_counter()
    sim.run()
    seconds = time.perf_counter() - t0
    if sim.processed_ray_count >= settings.max_rays:
        raise EdgeBundleError(f"the trace stopped at max_rays={settings.max_rays} segments; raise max_rays")
    objects = {o._uuid: o for o in copy.objs}
    leaves: Dict[str, List[List[Any]]] = {}
    for leaf in sim.lineage.get_leaves():
        path = sim.lineage.get_full_path(leaf.uuid)
        leaves.setdefault(path[0].uuid, []).append(path)
    roots_of: Dict[str, List[Any]] = {}
    for root in sim.lineage.get_roots():         # a RaySetSource emits its seeds in order
        roots_of.setdefault(root.source_label, []).append(root)
    bundles = []
    for spec, ss, aa in zip(specs, seeds, aims):
        roots = roots_of.get(spec.bundle_id, [])
        if len(roots) != len(ss):
            raise EdgeBundleError(f"bundle {spec.bundle_id}: {len(ss)} seeds, but {len(roots)} rays were emitted")
        exit_curve = _spline(_glass(copy, spec.glass), spec.exit)
        bundles.append(EdgeBundle(spec, tuple(ss), _read(sim, objects, spec, aa, roots, leaves, exit_curve)))
    return BundleSet(settings, tuple(bundles), seconds)


def edge_bundles(scene: Any, specs: Sequence[BundleSpec], settings: Optional[BundleSettings] = None) -> BundleSet:
    """Aim each bundle at its entrance edge and trace them, on a copy of the scene.

    The scene's own sources are left out of the copy; its other objects stay (a blocker in the
    way puts the rays it stops off route).

    Raises:
        EdgeBundleError: An unknown glass, an entrance or exit edge that is not a spline, a source
            on the entrance edge, a name taken, or the trace's cap reached.
        FluxTubeError: A gradient-index glass in the scene.
    """
    settings = settings or BundleSettings()
    if len({s.bundle_id for s in specs}) != len(specs):
        raise EdgeBundleError("two bundles share an id")
    for spec in specs:
        _spline(_glass(scene, spec.glass), spec.exit)
    made = [_seeds(scene, spec, settings) for spec in specs]
    return _trace(scene, specs, [m[0] for m in made], [m[1] for m in made], settings)


def trace_bundles(scene: Any, bundle_set: BundleSet) -> BundleSet:
    """Trace a bundle set's seeds again on ``scene`` (the design, or an edit of it).

    The seeds are not re-aimed: the same rays, so the change of each one's S is the edit's.
    """
    specs = [b.spec for b in bundle_set.bundles]
    aims = [[(r.aim, r.knot) for r in b.rays] for b in bundle_set.bundles]
    return _trace(scene, specs, [b.seeds for b in bundle_set.bundles], aims, bundle_set.settings)


# --- the first order ----------------------------------------------------------------------


def _dot(a: XY, b: XY) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _normal(curve: Any, point: XY) -> XY:
    _, p = curve.nearest(point)
    d = curve.deriv(p)
    m = math.hypot(*d)
    return (-d[1] / m, d[0] / m)


def _ray_change(field: Any, exit_curve: Any, spec: BundleSpec, ray: BundleRay,
                entrance_moved: bool, exit_moved: bool) -> float:
    """The first-order change of one bundle ray's S to the target, per unit of the handle's move.

    S = S(source -> exit) + n_t |exit - target|, a path whose last segment is the completion. At
    the entry, Snell's law holds, so only the surface's own move counts: ``(p_in - p_out) . dx``.
    At the exit the completion is not the ray's outgoing direction (by the ray's aberration), so
    the exit point's whole movement counts: ``(p_glass - p_t) . dx_exit``, where the exit point
    moves because the inside ray moved (the entry shifted, its direction turned), the exit
    surface moved, or both.
    """
    entry, out = ray.hits[0], ray.hits[-1]
    total = 0.0
    shift, turn = 0.0, 0.0                       # the inside ray: its perpendicular shift at the entry, its turn
    n_glass = math.hypot(*entry.p_out)
    d = (entry.p_out[0] / n_glass, entry.p_out[1] / n_glass)
    perp = (-d[1], d[0])
    if entrance_moved:
        ch = field.at(entry.point, entry.p_in, entry.p_out, entry.event)
        total += ch.dopl
        nrm = _normal(field.base, entry.point)
        n_in = math.hypot(*entry.p_in)
        d_in = (entry.p_in[0] / n_in, entry.p_in[1] / n_in)
        dt = _dot(ch.displacement, nrm) / _dot(d_in, nrm)  # the new entry is on the incoming line
        shift, turn = dt * _dot(perp, d_in), ch.dtheta
    length = math.hypot(out.point[0] - entry.point[0], out.point[1] - entry.point[1])
    across = shift + length * turn               # how far the inside ray moved, across itself, at the exit
    n_x = _normal(exit_curve, out.point)
    normal_move = 0.0
    if exit_moved:
        normal_move = _dot(field.at(out.point, out.p_in, out.p_out, out.event).displacement, n_x)
    along = (normal_move - across * _dot(perp, n_x)) / _dot(d, n_x)
    dx_exit = (along * d[0] + across * perp[0], along * d[1] + across * perp[1])
    u = _unit(spec.target[0] - out.point[0], spec.target[1] - out.point[1])
    p_t = (spec.target_index * u[0], spec.target_index * u[1])
    return total + _dot((out.p_in[0] - p_t[0], out.p_in[1] - p_t[1]), dx_exit)


def predict(scene: Any, bundle_set: BundleSet, handle: Any, delta: float) -> Dict[str, Dict[int, float]]:
    """Per bundle, per counted ray (by seed), the first-order change of its S to the target for the
    move ``delta`` of ``handle`` (a `first_order.Handle`); nothing traced.

    A handle on neither the entrance nor the exit edge changes nothing (to first order: a ray on
    the designed route meets no other edge).
    """
    from .first_order import _Field  # noqa: PLC0415
    field = _Field(scene, handle)
    out: Dict[str, Dict[int, float]] = {}
    for b in bundle_set.bundles:
        spec = b.spec
        mine = handle.glass == spec.glass
        entrance_moved, exit_moved = mine and handle.edge == spec.entrance, mine and handle.edge == spec.exit
        if not (entrance_moved or exit_moved):
            out[spec.bundle_id] = {r.seed: 0.0 for r in b.counted}
            continue
        exit_curve = _spline(_glass(scene, spec.glass), spec.exit)
        out[spec.bundle_id] = {r.seed: delta * _ray_change(field, exit_curve, spec, r, entrance_moved, exit_moved)
                               for r in b.counted}
    return out


__all__ = ["BundleRay", "BundleSet", "BundleSettings", "BundleSpec", "EdgeBundle", "EdgeBundleError",
           "FluxTubeError", "edge_bundles", "predict", "rr_bundles", "trace_bundles"]
