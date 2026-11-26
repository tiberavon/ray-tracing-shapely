"""
Python-specific module: flux tubes -- a source's light cut into bands of equal delivered power
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
PYTHON-SPECIFIC MODULE: flux tubes
===============================================================================
Where the light of a design goes, as a few bands instead of a cloud of rays.
`partition` traces the scene once and cuts each source's emitted rays, in the
order they were emitted, into K *tubes* that each deliver the same share of
the power the receiver (a detector) takes. Each tube keeps:

- its **seeds**: every emitted ray's start, unit direction and brightness, so
  the tube's rays can be traced again on their own (`replay`), whatever the
  scene's ray density;
- its two **boundary** rays, the first and the last of its rays to deliver;
- its **routes**: the sequences of (surface, event) its delivered light took,
  each with its share of the tube's delivered power, and the dominant one as
  the tube's ``signature``, the route an edit is expected to keep;
- its **arrivals**: for each crossing of the receiver, the seed it came from,
  its route, its optical path length S and the power it brought;
- the share of the source's emitted power it holds, and the share of that
  which reaches the receiver: Map B, where a pale tube is losing light.

**Which rays a tube holds.** The rays are taken in emission order (a point
source emits by angle; a beam by position). For a point source the order is
read round the circle starting just after its longest run of rays that
deliver nothing, so no tube straddles the dark side. A ray that delivers is
given to the tube its cumulative delivered power falls in. A ray that delivers
nothing but lies between two delivering rays of one tube belongs to that tube:
it left from within it, and its loss shows in Map B. A run of such rays
between two tubes is split between them, half each. The rays before the first
tube's first delivering ray or after the last tube's last one belong to no
tube: their share is the set's ``outside_fraction``.

**A route.** Each segment that ended on an optical surface contributes that
surface's name, the index of the edge it hit (in outline order, as
`P-SIGNATURE` counts them: `bidirectional._locate_on_surface`; None where the
surface has no edges to count) and the event that followed there, read from
the next segment's ``interaction_type`` (a segment's own type says how it began:
`signature_analysis.path_signature`'s caveat). A segment that ended on
nothing that recorded a hit is a crossing that left the ray unturned (a
detector) and is skipped; if it turned the ray, the surface is ``"?"``. The
route ends with ``(receiver, None, "arrive")``. The edge is what shows a tube
that moved from one face of a glass to another.

**Refused, loudly, before anything is cut:** a gradient-index glass in the
scene (its segments do not carry the index they travel in, so S would be
wrong; see the class); a trace stopped by ``max_rays``; a receiver that is not
a detector of the scene; a source whose light reaches the receiver too thinly
for K tubes of ``min_rays_per_tube`` delivering rays each; source rays whose s
and p brightnesses differ (a replayed ray is unpolarised); two objects with
one name (a replay finds the sources by name, `C-LABEL-01`).

**Every ray on its own.** Both traces run on a copy of the scene whose weak-ray
threshold is explicit (`TubeSettings.min_brightness_exp`, 10^-6 by default).
Under the automatic threshold the glass keeps only one dim ray in so many, *by
its index in the source's emission*, and amplifies it: upstream's adaptive
sampling. A ray's fate would then depend on its neighbours, and a tube
replayed alone could not give it back. With the explicit threshold every ray
is traced to it, whichever ray it is. The copy also leaves the caller's scene
and its detectors untouched.

K, the minimum count, the threshold and the cap are numerical parameters,
given apart from the scene (`TubeSettings`, `KC3`).

`replay` traces a tube set again: a copy of the scene, its sources replaced
by one `RaySetSource` per tube made from the seeds. On the scene the tubes were
cut from it gives back the same routes and S (`C-SCULPT-01`); on an edited
scene, what changed.
===============================================================================
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

Route = Tuple[Tuple[str, Optional[int], str], ...]

#: Two start points closer than this (scene units) are one point: the source is point-like.
_SAME_POINT = 1e-9
#: Two unit directions closer than this are one direction: the crossing left the ray unturned.
_SAME_DIRECTION = 1e-9
#: A hit farther than this from every edge of its surface has no edge (as `_locate_on_surface`).
_EDGE_TOLERANCE = 1e-4
#: A ray delivering less than this (in brightness) delivers nothing.
_NOTHING = 1e-12


class FluxTubeError(ValueError):
    """A scene, receiver or setting the tubes cannot be cut from, with the reason."""


@dataclass(frozen=True)
class TubeSettings:
    """The numerical parameters of a partition (`KC3`), apart from the physical scene.

    Attributes:
        tubes: K, the number of tubes per source.
        min_rays_per_tube: The fewest delivering rays a tube may hold; fewer is refused,
            with the advice to raise the ray density or lower K.
        max_rays: The segment cap of the analysis trace; reaching it is refused.
        min_brightness_exp: The traces' weak-ray threshold, 10^-exp: explicit, so that no
            ray's fate depends on its index (the module docstring).
    """

    tubes: int = 8
    min_rays_per_tube: int = 3
    max_rays: int = 200_000
    min_brightness_exp: int = 6

    def __post_init__(self) -> None:
        if not isinstance(self.tubes, int) or self.tubes < 1:
            raise FluxTubeError(f"tubes must be a whole number of at least 1, got {self.tubes!r}")
        if not isinstance(self.min_rays_per_tube, int) or self.min_rays_per_tube < 1:
            raise FluxTubeError(f"min_rays_per_tube must be a whole number of at least 1, got {self.min_rays_per_tube!r}")
        if not isinstance(self.max_rays, int) or self.max_rays < 1:
            raise FluxTubeError(f"max_rays must be a whole number of at least 1, got {self.max_rays!r}")
        if not isinstance(self.min_brightness_exp, int) or self.min_brightness_exp < 1:
            raise FluxTubeError(f"min_brightness_exp must be a whole number of at least 1, "
                                f"got {self.min_brightness_exp!r}")


@dataclass(frozen=True)
class RaySeed:
    """One emitted ray, replayable: start, unit direction, brightness (s + p), wavelength."""

    p: Tuple[float, float]
    d: Tuple[float, float]
    brightness: float
    wavelength: Optional[float] = None


@dataclass(frozen=True)
class SurfaceHit:
    """One optical event along an arrival's path, as the first-order estimate needs it.

    Attributes:
        surface: The surface's name; ``"?"`` where it recorded no hit but turned the ray.
        edge: The edge index (as in a route), or None.
        point: Where the ray met it.
        p_in: The optical momentum before: the incoming unit direction times its medium's index.
        p_out: The optical momentum after.
        event: What followed there: ``"refract"``, ``"reflect"``, ``"tir"``, ...
    """

    surface: str
    edge: Optional[int]
    point: Tuple[float, float]
    p_in: Tuple[float, float]
    p_out: Tuple[float, float]
    event: str


@dataclass(frozen=True)
class Arrival:
    """One crossing of the receiver: which seed, by which route, its S, the power it counted.

    Attributes:
        seed: The index of the seed in its tube.
        route: The (surface, edge, event) sequence it took.
        opl: Its optical path length S from the seed to the receiver.
        power: The power the receiver counted for it.
        point: Where it crossed the receiver.
        momentum: Its optical momentum there (unit direction times index): the gradient of S,
            so S at a nearby point of the receiver differs by ``momentum`` · (shift).
        hits: Its optical events in order, for the first-order estimate.
    """

    seed: int
    route: Route
    opl: float
    power: float
    point: Tuple[float, float] = (0.0, 0.0)
    momentum: Tuple[float, float] = (0.0, 0.0)
    hits: Tuple[SurfaceHit, ...] = ()


@dataclass(frozen=True)
class FluxTube:
    """A band of one source's rays delivering one K-th of its delivered power.

    Attributes:
        tube_id: ``"<source>/T<k>"``, k from 0 in emission order.
        source_label: The source's name.
        seeds: Every ray of the tube, in emission order.
        boundary: The indices in ``seeds`` of the first and the last delivering ray.
        power_fraction: The share of the source's emitted power the tube holds.
        delivered_fraction: The share of the tube's own emitted power that reaches the
            receiver (Map B).
        signature: The route carrying most of the tube's delivered power.
        routes: Every route, with its share of the tube's delivered power, largest first.
        arrivals: Every crossing of the receiver by the tube's light.
    """

    tube_id: str
    source_label: str
    seeds: Tuple[RaySeed, ...]
    boundary: Tuple[int, int]
    power_fraction: float
    delivered_fraction: float
    signature: Route
    routes: Tuple[Tuple[Route, float], ...]
    arrivals: Tuple[Arrival, ...]


@dataclass(frozen=True)
class TubeSet:
    """The tubes of every source, cut for one receiver.

    Attributes:
        receiver: The detector's name.
        settings: The numerical parameters they were cut with.
        tubes: Every source's tubes, source by source, each in emission order.
        outside_fraction: Per source, the share of its emitted power in no tube.
        brightness_scale: The factor the seeds' brightness was divided by to fit a replay
            source's (0, 1]; 1.0 when none was needed.
        trace_seconds: How long the analysis trace took.
    """

    receiver: str
    settings: TubeSettings
    tubes: Tuple[FluxTube, ...]
    outside_fraction: Dict[str, float]
    brightness_scale: float = 1.0
    trace_seconds: float = 0.0

    def tube(self, tube_id: str) -> FluxTube:
        for t in self.tubes:
            if t.tube_id == tube_id:
                return t
        raise KeyError(f"no tube {tube_id!r}; tubes: {', '.join(t.tube_id for t in self.tubes)}")

    def power_map(self) -> List[Dict[str, Any]]:
        """Map B: per tube, its share of the source's power and how much of it is delivered."""
        return [{"tube_id": t.tube_id, "source": t.source_label, "power_fraction": t.power_fraction,
                 "delivered_fraction": t.delivered_fraction, "rays": len(t.seeds),
                 "signature": route_text(t.signature)} for t in self.tubes]

    def to_dict(self) -> Dict[str, Any]:
        """The set as JSON-ready data (routes as lists); `from_dict` reads it back."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TubeSet":
        def route(r: Any) -> Route:
            return tuple((str(a), None if e is None else int(e), str(b)) for a, e, b in r)

        tubes = tuple(FluxTube(
            tube_id=t["tube_id"], source_label=t["source_label"],
            seeds=tuple(RaySeed(tuple(s["p"]), tuple(s["d"]), s["brightness"], s.get("wavelength"))
                        for s in t["seeds"]),
            boundary=tuple(t["boundary"]), power_fraction=t["power_fraction"],
            delivered_fraction=t["delivered_fraction"], signature=route(t["signature"]),
            routes=tuple((route(r), share) for r, share in t["routes"]),
            arrivals=tuple(Arrival(a["seed"], route(a["route"]), a["opl"], a["power"], tuple(a["point"]),
                                   tuple(a["momentum"]),
                                   tuple(SurfaceHit(h["surface"], h["edge"], tuple(h["point"]), tuple(h["p_in"]),
                                                    tuple(h["p_out"]), h["event"]) for h in a["hits"]))
                           for a in t["arrivals"]),
        ) for t in data["tubes"])
        return cls(receiver=data["receiver"], settings=TubeSettings(**data["settings"]), tubes=tubes,
                   outside_fraction=dict(data["outside_fraction"]),
                   brightness_scale=data.get("brightness_scale", 1.0), trace_seconds=data.get("trace_seconds", 0.0))


@dataclass
class ReplayedTube:
    """A tube traced again: its routes and arrivals on the scene it was replayed on."""

    tube_id: str
    delivered_fraction: float
    routes: Tuple[Tuple[Route, float], ...]
    arrivals: Tuple[Arrival, ...]
    signature: Optional[Route] = None


@dataclass
class Replay:
    """The result of `replay`: each tube again, and how long the trace took."""

    tubes: Dict[str, ReplayedTube] = field(default_factory=dict)
    trace_seconds: float = 0.0
    rays: int = 0


def route_text(route: Route) -> str:
    """A route in words: ``lens#0 refract → lens#2 refract → det arrive``."""
    return " → ".join(f"{name}{'' if edge is None else f'#{edge}'} {event}" for name, edge, event in route)


# --- the trace --------------------------------------------------------------------------


def _refuse_grin(scene: Any) -> None:
    from ..core.scene_objs.base_grin_glass import BaseGrinGlass  # noqa: PLC0415
    grin = [o.name for o in scene.objs if isinstance(o, BaseGrinGlass)]
    if grin:
        raise FluxTubeError(
            f"the scene holds a gradient-index glass ({', '.join(map(str, grin))}): its segments do not "
            f"carry the index they travel in, so an optical path length through it would be wrong")


def _receiver(scene: Any, name: str) -> Any:
    from ..core.scene_objs.other.detector import Detector  # noqa: PLC0415
    names = [o.name for o in scene.objs]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise FluxTubeError(f"two objects share a name ({', '.join(map(str, dup))}); tubes find their sources "
                            f"and the receiver by name, so every name must be one object's")
    found = [o for o in scene.objs if o.name == name]
    if not found:
        raise FluxTubeError(f"no object named {name!r}; objects: {', '.join(map(str, names))}")
    if not isinstance(found[0], Detector):
        raise FluxTubeError(f"{name!r} is a {type(found[0]).__name__}, not a detector: the receiver must count "
                            f"the light that reaches it")
    return found[0]


def _copy(scene: Any, settings: "TubeSettings") -> Any:
    """The scene through its scene file, with the explicit weak-ray threshold."""
    from . import scene_file as sf  # noqa: PLC0415
    _refuse_grin(scene)
    copy = sf.scene_from_dict(sf.scene_to_dict(scene))
    copy.min_brightness_exp = settings.min_brightness_exp
    return copy


def _trace(scene: Any, receiver: str, max_rays: int) -> Tuple[Any, Any, float]:
    """Trace a scene `_copy` made, recording the surface hits."""
    from ..core.simulator import Simulator  # noqa: PLC0415
    det = _receiver(scene, receiver)
    sim = Simulator(scene, max_rays=max_rays, record_surface_hits=True)
    t0 = time.perf_counter()
    sim.run()
    seconds = time.perf_counter() - t0
    if sim.processed_ray_count >= max_rays:
        raise FluxTubeError(f"the trace stopped at max_rays={max_rays} segments, so the light reaching "
                            f"{receiver!r} is not all counted; raise max_rays")
    return sim, det, seconds


def _unit(dx: float, dy: float) -> Tuple[float, float]:
    length = math.hypot(dx, dy)
    return (dx / length, dy / length) if length > 0 else (0.0, 0.0)


def _direction(seg: Any) -> Tuple[float, float]:
    return _unit(seg.p2["x"] - seg.p1["x"], seg.p2["y"] - seg.p1["y"])


def _edge(obj: Any, point: Optional[Dict[str, float]], spans: Dict[str, Any]) -> Optional[int]:
    """The index of the edge of ``obj`` nearest ``point``, as `P-SIGNATURE` counts them.

    `bidirectional._locate_on_surface`'s rule, with each object's spans built once per trace
    (``spans``): building them is the cost, and a trace has many hits on few surfaces.
    """
    from .bidirectional import _surface_spans  # noqa: PLC0415 -- the edge count signatures use
    if obj is None or point is None:
        return None
    if obj._uuid not in spans:
        try:
            spans[obj._uuid] = [sp for sp in _surface_spans(obj) if sp.length > 0.0]
        except (AttributeError, TypeError, ValueError):
            spans[obj._uuid] = []
    best = None
    for span in spans[obj._uuid]:
        dist, _ = span.locate((point["x"], point["y"]))
        if best is None or dist < best[0]:
            best = (dist, span.index)
    return None if best is None or best[0] > _EDGE_TOLERANCE else best[1]


def _momentum(seg: Any) -> Tuple[float, float]:
    d = _direction(seg)
    n = getattr(seg, "medium_index", 1.0)
    return (n * d[0], n * d[1])


def _walk(path: Sequence[Any], objects: Dict[str, Any], receiver: str,
          spans: Dict[str, Any]) -> Tuple[Route, Tuple[SurfaceHit, ...]]:
    """A path's route, and its optical events with their momenta."""
    route: List[Tuple[str, Optional[int], str]] = []
    hits: List[SurfaceHit] = []
    for seg, nxt in zip(path, path[1:]):
        event = str(nxt.interaction_type)
        if seg.hit_surface_uuid is not None:
            obj = objects.get(seg.hit_surface_uuid)
            name, edge = (obj.name if obj is not None else "?"), _edge(obj, seg.hit_point, spans)
            point = (seg.hit_point["x"], seg.hit_point["y"]) if seg.hit_point else (seg.p2["x"], seg.p2["y"])
        else:
            a, b = _direction(seg), _direction(nxt)
            if math.hypot(a[0] - b[0], a[1] - b[1]) <= _SAME_DIRECTION:
                continue                                   # a crossing that left it unturned: a detector
            name, edge, point = "?", None, (nxt.p1["x"], nxt.p1["y"])
        route.append((name, edge, event))
        hits.append(SurfaceHit(name, edge, point, _momentum(seg), _momentum(nxt), event))
    route.append((receiver, None, "arrive"))
    return tuple(route), tuple(hits)


def _arrivals(sim: Any, det: Any, objects: Dict[str, Any], receiver: str) -> Dict[str, List[Tuple[Any, ...]]]:
    """Per root uuid: (route, S, counted power, point, momentum, hits) of each crossing of the receiver."""
    from .lineage_analysis import optical_path_length  # noqa: PLC0415
    out: Dict[str, List[Tuple[Any, ...]]] = {}
    spans: Dict[str, Any] = {}
    for rec in det.get_hit_records():
        uuid = rec.get("ray_uuid")
        if uuid is None:
            continue
        path = sim.lineage.get_full_path(uuid)
        if not path:
            continue
        power = det._counted(rec["sign"]) * rec["brightness_total"]
        route, hits = _walk(path, objects, receiver, spans)
        point = rec.get("incident_point") or path[-1].p2
        out.setdefault(path[0].uuid, []).append(
            (route, optical_path_length(sim.lineage, uuid), power, (point["x"], point["y"]),
             _momentum(path[-1]), hits))
    return out


# --- the partition ----------------------------------------------------------------------


def _ordered(roots: List[Any], delivered: List[float]) -> List[int]:
    """Emission order; for a point-like source, read round from just after the longest dark run."""
    n = len(roots)
    p0 = roots[0].p1
    point_like = all(math.hypot(r.p1["x"] - p0["x"], r.p1["y"] - p0["y"]) <= _SAME_POINT for r in roots)
    lit = [d > _NOTHING for d in delivered]
    if not point_like or all(lit) or not any(lit):
        return list(range(n))
    best_len, best_end, run = -1, 0, 0
    for i in range(2 * n):                      # twice round, so a run across the wrap is seen whole
        if lit[i % n]:
            if run > best_len:
                best_len, best_end = run, i % n
            run = 0
        else:
            run += 1
    return [(best_end + k) % n for k in range(n)]


def _cut(order: List[int], delivered: List[float], k: int) -> Tuple[List[Optional[int]], int]:
    """The tube of each ray (None: outside every tube), and the tubes actually filled."""
    total = sum(max(delivered[i], 0.0) for i in order)
    tube_of: List[Optional[int]] = [None] * len(delivered)
    cum = 0.0
    lit_positions: List[int] = []
    for pos, i in enumerate(order):
        d = max(delivered[i], 0.0)
        if d > _NOTHING:
            tube_of[i] = min(k - 1, int(k * (cum + d / 2) / total))
            lit_positions.append(pos)
        cum += d
    for a, b in zip(lit_positions, lit_positions[1:]):        # dark runs between two delivering rays
        ta, tb = tube_of[order[a]], tube_of[order[b]]
        dark = list(range(a + 1, b))
        for j, pos in enumerate(dark):
            tube_of[order[pos]] = ta if (ta == tb or j < len(dark) / 2) else tb
    return tube_of, len({t for t in tube_of if t is not None})


def partition(scene: Any, receiver: str, settings: Optional[TubeSettings] = None,
              sources: Optional[Sequence[str]] = None) -> TubeSet:
    """Trace the scene once and cut each source's light into flux tubes.

    Args:
        scene: The scene; a copy of it is traced (the module docstring), so it is not changed.
        receiver: The name of the detector whose delivered power is cut.
        settings: K, the minimum rays per tube and the trace's cap; the defaults if not given.
        sources: The names of the sources to cut; every source that emitted, if not given.

    Returns:
        The `TubeSet`.

    Raises:
        FluxTubeError: As the module docstring lists, with the reason.
    """
    settings = settings or TubeSettings()
    _receiver(scene, receiver)                       # refused on the caller's scene, by its names
    scene = _copy(scene, settings)
    sim, det, seconds = _trace(scene, receiver, settings.max_rays)
    objects = {o._uuid: o for o in scene.objs}
    arrivals = _arrivals(sim, det, objects, receiver)

    by_source: Dict[str, List[Any]] = {}
    for root in sim.lineage.get_roots():
        src = objects.get(root.source_uuid)
        by_source.setdefault(root.source_label or (src.name if src is not None else "?"), []).append(root)
    if sources is not None:
        missing = [s for s in sources if s not in by_source]
        if missing:
            raise FluxTubeError(f"no rays from {', '.join(missing)}; sources that emitted: {', '.join(by_source)}")
        by_source = {s: by_source[s] for s in sources}

    all_roots = [r for roots in by_source.values() for r in roots]
    for r in all_roots:
        if abs(r.brightness_s - r.brightness_p) > 1e-12 * max(1.0, abs(r.brightness_s)):
            raise FluxTubeError(f"a ray of {r.source_label!r} is polarised (s {r.brightness_s}, p {r.brightness_p}); "
                                f"a replayed ray is unpolarised, so its tubes could not be traced again faithfully")
    peak = max((r.brightness_s + r.brightness_p for r in all_roots), default=1.0)
    scale = max(1.0, peak)

    tubes: List[FluxTube] = []
    outside: Dict[str, float] = {}
    k = settings.tubes
    for label, roots in by_source.items():
        delivered = [sum(a[2] for a in arrivals.get(r.uuid, ())) for r in roots]
        emitted = [r.brightness_s + r.brightness_p for r in roots]
        lit = sum(1 for d in delivered if d > _NOTHING)
        if lit < k * settings.min_rays_per_tube:
            raise FluxTubeError(
                f"{label!r}: {lit} of its {len(roots)} rays reach {receiver!r}, fewer than {k} tubes of "
                f"{settings.min_rays_per_tube} each need; raise the scene's ray density or lower the tube count")
        order = _ordered(roots, delivered)
        tube_of, filled = _cut(order, delivered, k)
        source_power = sum(emitted)
        outside[label] = sum(emitted[i] for i in order if tube_of[i] is None) / source_power
        for t in range(k):
            members = [i for i in order if tube_of[i] == t]
            lit_members = [i for i in members if delivered[i] > _NOTHING]
            if len(lit_members) < settings.min_rays_per_tube:
                raise FluxTubeError(
                    f"{label!r}: tube {t} holds {len(lit_members)} delivering rays, fewer than "
                    f"{settings.min_rays_per_tube}; raise the scene's ray density or lower the tube count")
            seeds, tube_arrivals = [], []
            weights: Dict[Route, float] = {}
            for j, i in enumerate(members):
                r = roots[i]
                seeds.append(RaySeed((r.p1["x"], r.p1["y"]), _direction(r), emitted[i] / scale,
                                     getattr(r, "wavelength", None) if scene.simulate_colors else None))
                for route, opl, power, point, momentum, hits in arrivals.get(r.uuid, ()):
                    tube_arrivals.append(Arrival(j, route, opl, power, point, momentum, hits))
                    weights[route] = weights.get(route, 0.0) + power
            tube_emitted = sum(emitted[i] for i in members)
            tube_delivered = sum(delivered[i] for i in members)
            routes = tuple(sorted(((r, w / tube_delivered) for r, w in weights.items()), key=lambda x: -x[1]))
            tubes.append(FluxTube(
                tube_id=f"{label}/T{t}", source_label=label, seeds=tuple(seeds),
                boundary=(members.index(lit_members[0]), members.index(lit_members[-1])),
                power_fraction=tube_emitted / source_power, delivered_fraction=tube_delivered / tube_emitted,
                signature=routes[0][0], routes=routes, arrivals=tuple(tube_arrivals)))
    return TubeSet(receiver=receiver, settings=settings, tubes=tuple(tubes), outside_fraction=outside,
                   brightness_scale=scale, trace_seconds=seconds)


# --- the replay -------------------------------------------------------------------------


def tube_scene(scene: Any, tube_set: TubeSet, tubes: Optional[Sequence[str]] = None) -> Any:
    """A copy of the scene with its tubes' sources replaced by one `RaySetSource` per tube.

    Each replay source is named by its tube id. The scene is copied through the scene file
    (`analysis.scene_file`), with the tube set's weak-ray threshold, so the original is not
    touched.
    """
    from ..optical_elements.sources.ray_set_source import RaySetSource  # noqa: PLC0415
    copy = _copy(scene, tube_set.settings)
    chosen = [tube_set.tube(t) for t in tubes] if tubes is not None else list(tube_set.tubes)
    labels = {t.source_label for t in tube_set.tubes}
    for obj in [o for o in copy.objs if o.name in labels]:
        copy.remove_object(obj)
    for t in chosen:
        src = RaySetSource.from_rays(copy, [s.p for s in t.seeds], [s.d for s in t.seeds],
                                     [s.brightness for s in t.seeds])
        if copy.simulate_colors:
            for ray, s in zip(src.rays, t.seeds):
                if s.wavelength is not None:
                    ray["wavelength"] = s.wavelength
        src.name = t.tube_id
        copy.add_object(src)
    return copy


def replay(scene: Any, tube_set: TubeSet, tubes: Optional[Sequence[str]] = None,
           max_rays: Optional[int] = None) -> Replay:
    """Trace the tubes' seeds again on ``scene`` (the scene they were cut from, or an edit of it).

    Args:
        scene: The scene to replay on; it is copied, not changed.
        tube_set: The tubes, from `partition`.
        tubes: The ids of the tubes to replay; all, if not given.
        max_rays: The trace's segment cap; the tube set's, if not given.

    Returns:
        A `Replay`: per tube, its delivered fraction, routes and arrivals, with powers in
        the original source's brightness (the seeds' scale undone).
    """
    copy = tube_scene(scene, tube_set, tubes)
    sim, det, seconds = _trace(copy, tube_set.receiver, max_rays or tube_set.settings.max_rays)
    arrivals = _arrivals(sim, det, {o._uuid: o for o in copy.objs}, tube_set.receiver)
    seed_of: Dict[str, Tuple[str, int]] = {}
    counters: Dict[str, int] = {}
    for root in sim.lineage.get_roots():          # a RaySetSource emits its seeds in order
        j = counters.get(root.source_label, 0)
        counters[root.source_label] = j + 1
        seed_of[root.uuid] = (root.source_label, j)
    out = Replay(trace_seconds=seconds, rays=sum(counters.values()))
    by_tube: Dict[str, List[Arrival]] = {}
    for uuid, items in arrivals.items():
        tube_id, j = seed_of[uuid]
        for route, opl, power, point, momentum, hits in items:
            by_tube.setdefault(tube_id, []).append(
                Arrival(j, route, opl, power * tube_set.brightness_scale, point, momentum, hits))
    for tube_id in counters:
        t = tube_set.tube(tube_id)
        got = by_tube.get(tube_id, [])
        weights: Dict[Route, float] = {}
        for a in got:
            weights[a.route] = weights.get(a.route, 0.0) + a.power
        delivered = sum(weights.values())
        emitted = sum(s.brightness for s in t.seeds) * tube_set.brightness_scale
        routes = tuple(sorted(((r, w / delivered) for r, w in weights.items()), key=lambda x: -x[1])) \
            if delivered > _NOTHING else ()
        out.tubes[tube_id] = ReplayedTube(tube_id, delivered / emitted, routes, tuple(got),
                                          routes[0][0] if routes else None)
    return out


__all__ = ["Arrival", "SurfaceHit", "FluxTube", "FluxTubeError", "Replay", "ReplayedTube", "RaySeed", "Route", "TubeSet",
           "TubeSettings", "partition", "replay", "route_text", "tube_scene"]
