"""
Python-specific module: Bidirectional Ray Tracing (Ray Lineage Step C)

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
PYTHON-SPECIFIC MODULE: Bidirectional Ray Tracing
===============================================================================
Container and (incrementally landed) machinery for tracing rays forward from
sources and backward from a detector, then connecting the two trees at shared
surfaces. See dev_doc/roadmap/done/15_p1_ray_lineage_step_c_bidirectional_tracing.md.

Landing order (each sub-step is independently testable):
  1. BackwardDetectorSource + Simulator._run_backward -> a valid backward
     lineage.  [DONE]
  2. Validate reversed-physics assumptions (C.2).  [DONE, in test_bidirectional]
  3. connect_trees() with parametric matching + diagnostics (C.3).  [DONE]
  4. NetworkX combined graph, energy, path extraction (C.4).  [DONE — this module]
  5. Agentic exposure: rank_bidirectional_paths (C.5).  [DONE — see
     analysis/agentic_tools.py's set_bidirectional_context/
     rank_bidirectional_paths, and agentic_db.py's connections table]
===============================================================================
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.ray import Ray
    from ..core.ray_lineage import RayLineage
    from ..core.scene import Scene


class BidirectionalResult:
    """Holds the forward and backward passes of a bidirectional run.

    Parallel to SimulationResult but purpose-built for Step C: it carries both
    lineages and their raw segments, plus (as later sub-steps land) the
    connections between the trees and the combined NetworkX graph.

    Attributes:
        forward_lineage: RayLineage from the forward (source-driven) pass.
        backward_lineage: RayLineage from the backward (detector-driven) pass.
        forward_segments: Raw forward ray segments.
        backward_segments: Raw backward ray segments.
        detector_name: Name of the detector the backward pass emitted from.
        connections: Forward<->backward surface connections (None until C.3).
        combined: Combined NetworkX DiGraph (None until C.4).
    """

    def __init__(
        self,
        forward_lineage: 'RayLineage',
        backward_lineage: 'RayLineage',
        forward_segments: List['Ray'],
        backward_segments: List['Ray'],
        *,
        detector_name: Optional[str] = None,
        connections: Optional[List[Any]] = None,
        combined: Optional[Any] = None,
    ) -> None:
        self.forward_lineage = forward_lineage
        self.backward_lineage = backward_lineage
        self.forward_segments = forward_segments
        self.backward_segments = backward_segments
        self.detector_name = detector_name
        self.connections = connections
        self.combined = combined

    def __repr__(self) -> str:
        conn = "None" if self.connections is None else str(len(self.connections))
        return (
            f"BidirectionalResult(detector={self.detector_name!r}, "
            f"forward_segments={len(self.forward_segments)}, "
            f"backward_segments={len(self.backward_segments)}, "
            f"connections={conn})"
        )


# ===========================================================================
# C.3 -- Connecting the forward and backward trees at shared surfaces
# ===========================================================================
#
# Two hits on the same surface are matched PARAMETRICALLY: each hit_point is
# projected onto the surface edge it lies on and reduced to a 1-D arc-length
# position along that edge, which is far more robust to discrete ray sampling
# than raw Euclidean point matching. A forward hit F and backward hit G connect
# when they land on the same (surface, edge) at ~the same arc-length AND F has a
# forward continuation that is antiparallel to G's arrival -- i.e. the two are
# the same physical ray traversed in opposite directions (see C.2 reciprocity).


class Connection:
    """A matched forward-hit / backward-hit pair on a shared surface.

    Attributes:
        forward_uuid: uuid of the forward segment arriving at the surface.
        backward_uuid: uuid of the backward segment arriving at the surface.
        connecting_child_uuid: uuid of F's outgoing continuation that lines up
            (antiparallel) with G -- the physical ray the connection represents.
        surface_uuid: uuid of the shared surface object.
        edge_index: index of the surface edge both hits lie on.
        arc_forward: arc-length of F's hit along the edge (from edge vertex 0).
        arc_backward: arc-length of G's hit along the edge.
        arc_distance: abs(arc_forward - arc_backward), the match residual.
        direction_dot: dot(F-continuation, G-arrival); ~ -1 for a clean match.
        point: the forward hit point {'x','y'} (the connection location).
    """

    __slots__ = (
        'forward_uuid', 'backward_uuid', 'connecting_child_uuid',
        'surface_uuid', 'edge_index', 'arc_forward', 'arc_backward',
        'arc_distance', 'direction_dot', 'point',
    )

    def __init__(
        self,
        forward_uuid: str,
        backward_uuid: str,
        connecting_child_uuid: Optional[str],
        surface_uuid: str,
        edge_index: int,
        arc_forward: float,
        arc_backward: float,
        direction_dot: float,
        point: Dict[str, float],
    ) -> None:
        self.forward_uuid = forward_uuid
        self.backward_uuid = backward_uuid
        self.connecting_child_uuid = connecting_child_uuid
        self.surface_uuid = surface_uuid
        self.edge_index = edge_index
        self.arc_forward = arc_forward
        self.arc_backward = arc_backward
        self.arc_distance = abs(arc_forward - arc_backward)
        self.direction_dot = direction_dot
        self.point = point

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable view (for the agentic layer, C.5)."""
        return {
            'forward_uuid': self.forward_uuid,
            'backward_uuid': self.backward_uuid,
            'connecting_child_uuid': self.connecting_child_uuid,
            'surface_uuid': self.surface_uuid,
            'edge_index': self.edge_index,
            'arc_forward': self.arc_forward,
            'arc_backward': self.arc_backward,
            'arc_distance': self.arc_distance,
            'direction_dot': self.direction_dot,
            'point': self.point,
        }

    def __repr__(self) -> str:
        return (
            f"Connection(surface={self.surface_uuid[:8]}..., edge={self.edge_index}, "
            f"arc_dist={self.arc_distance:.3e}, dot={self.direction_dot:.4f})"
        )


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _surface_edges(obj: Any) -> List[Tuple[int, Tuple[float, float], Tuple[float, float]]]:
    """Return the straight edges of a surface object as (index, a, b) tuples.

    Glass/prism polygons (``.path``) yield one edge per vertex pair, closed.
    Line objects (mirror, blocker, detector) with ``.p1``/``.p2`` yield one edge.
    Arc edges are approximated by their chord (a documented first-cut limitation).
    """
    path = getattr(obj, 'path', None)
    if path:
        pts = [(p['x'], p['y']) for p in path]
        n = len(pts)
        return [(i, pts[i], pts[(i + 1) % n]) for i in range(n)]
    p1 = getattr(obj, 'p1', None)
    p2 = getattr(obj, 'p2', None)
    if p1 and p2:
        return [(0, (p1['x'], p1['y']), (p2['x'], p2['y']))]
    return []


def _locate_on_surface(
    obj: Any,
    point: Dict[str, float],
    tol: float = 1e-4,
) -> Optional[Tuple[int, float, float]]:
    """Locate a hit point on a surface as (edge_index, arc_length, edge_length).

    Picks the edge with the smallest perpendicular distance to the point; returns
    None if the closest edge is farther than ``tol`` (i.e. the point is not on
    this surface). arc_length is measured from the edge's first vertex.
    """
    px, py = point['x'], point['y']
    best: Optional[Tuple[float, int, float, float]] = None
    for idx, a, b in _surface_edges(obj):
        abx, aby = b[0] - a[0], b[1] - a[1]
        seg_len2 = abx * abx + aby * aby
        if seg_len2 == 0.0:
            continue
        t = ((px - a[0]) * abx + (py - a[1]) * aby) / seg_len2
        tc = max(0.0, min(1.0, t))
        cx, cy = a[0] + tc * abx, a[1] + tc * aby
        dist = math.hypot(px - cx, py - cy)
        seg_len = math.sqrt(seg_len2)
        if best is None or dist < best[0]:
            best = (dist, idx, tc * seg_len, seg_len)
    if best is None or best[0] > tol:
        return None
    return best[1], best[2], best[3]


def _direction(seg: 'Ray') -> Optional[Tuple[float, float]]:
    dx = seg.p2['x'] - seg.p1['x']
    dy = seg.p2['y'] - seg.p1['y']
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return None
    return dx / length, dy / length


class _Hit:
    """A Step B surface hit reduced to its (surface, edge, arc) location."""
    __slots__ = ('seg', 'edge_index', 'arc', 'edge_len')

    def __init__(self, seg: 'Ray', edge_index: int, arc: float, edge_len: float) -> None:
        self.seg = seg
        self.edge_index = edge_index
        self.arc = arc
        self.edge_len = edge_len


def _hits_by_surface_edge(
    lineage: 'RayLineage',
    obj_by_uuid: Dict[str, Any],
) -> Dict[Tuple[str, int], List[_Hit]]:
    """Bucket a lineage's Step B hits by (surface_uuid, edge_index)."""
    buckets: Dict[Tuple[str, int], List[_Hit]] = {}
    for seg in lineage._segments.values():
        surface_uuid = getattr(seg, 'hit_surface_uuid', None)
        hit_point = getattr(seg, 'hit_point', None)
        if surface_uuid is None or hit_point is None:
            continue
        obj = obj_by_uuid.get(surface_uuid)
        if obj is None:
            continue
        located = _locate_on_surface(obj, hit_point)
        if located is None:
            continue
        edge_index, arc, edge_len = located
        buckets.setdefault((surface_uuid, edge_index), []).append(
            _Hit(seg, edge_index, arc, edge_len))
    return buckets


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def connect_trees(
    forward_lineage: 'RayLineage',
    backward_lineage: 'RayLineage',
    scene: 'Scene',
    *,
    spatial_tolerance: float = 1e-3,
    angular_tolerance_deg: float = 1.0,
) -> List[Connection]:
    """Match forward hits and backward hits at shared surfaces (C.3).

    Both lineages must have been produced with ``record_surface_hits=True``.

    Args:
        forward_lineage: Forward (source-driven) lineage.
        backward_lineage: Backward (detector-driven) lineage.
        scene: The scene, used to resolve hit_surface_uuid -> surface geometry.
        spatial_tolerance: Max along-edge arc-length difference for a match
            (scene units).
        angular_tolerance_deg: Max deviation from perfect antiparallelism between
            F's continuation and G's arrival.

    Returns:
        A list of Connection objects (possibly empty).
    """
    obj_by_uuid = {getattr(o, 'uuid', None): o for o in scene.objs}
    forward = _hits_by_surface_edge(forward_lineage, obj_by_uuid)
    backward = _hits_by_surface_edge(backward_lineage, obj_by_uuid)

    dot_threshold = -math.cos(math.radians(angular_tolerance_deg))
    connections: List[Connection] = []

    for key, f_hits in forward.items():
        g_hits = backward.get(key)
        if not g_hits:
            continue
        surface_uuid, edge_index = key
        for f in f_hits:
            f_children = forward_lineage.get_children(f.seg.uuid)
            for g in g_hits:
                if abs(f.arc - g.arc) > spatial_tolerance:
                    continue
                g_dir = _direction(g.seg)
                if g_dir is None:
                    continue
                # F must have a continuation antiparallel to G's arrival.
                best_child = None
                best_dot = 0.0
                for child in f_children:
                    c_dir = _direction(child)
                    if c_dir is None:
                        continue
                    dot = c_dir[0] * g_dir[0] + c_dir[1] * g_dir[1]
                    if dot <= dot_threshold and (best_child is None or dot < best_dot):
                        best_child = child
                        best_dot = dot
                if best_child is None:
                    continue
                connections.append(Connection(
                    forward_uuid=f.seg.uuid,
                    backward_uuid=g.seg.uuid,
                    connecting_child_uuid=best_child.uuid,
                    surface_uuid=surface_uuid,
                    edge_index=edge_index,
                    arc_forward=f.arc,
                    arc_backward=g.arc,
                    direction_dot=best_dot,
                    point={'x': f.seg.hit_point['x'], 'y': f.seg.hit_point['y']},
                ))
    return connections


def nearest_neighbour_arc_distances(
    forward_lineage: 'RayLineage',
    backward_lineage: 'RayLineage',
    scene: 'Scene',
) -> Dict[str, Any]:
    """Diagnostic: distribution of forward->backward nearest arc-length gaps.

    For every forward hit that shares a (surface, edge) with at least one
    backward hit, report the arc-length distance to the nearest backward hit.
    Lets the user pick a sane ``spatial_tolerance`` for connect_trees before a
    single connection is attempted (mitigation for the discrete-sampling risk).

    Returns:
        {'count', 'min', 'max', 'mean', 'median', 'distances'} over all such
        forward hits (empty-safe: zeros and [] when there is no shared surface).
    """
    obj_by_uuid = {getattr(o, 'uuid', None): o for o in scene.objs}
    forward = _hits_by_surface_edge(forward_lineage, obj_by_uuid)
    backward = _hits_by_surface_edge(backward_lineage, obj_by_uuid)

    distances: List[float] = []
    for key, f_hits in forward.items():
        g_hits = backward.get(key)
        if not g_hits:
            continue
        g_arcs = [g.arc for g in g_hits]
        for f in f_hits:
            distances.append(min(abs(f.arc - g_arc) for g_arc in g_arcs))

    if not distances:
        return {'count': 0, 'min': 0.0, 'max': 0.0, 'mean': 0.0,
                'median': 0.0, 'distances': []}
    ordered = sorted(distances)
    mid = len(ordered) // 2
    median = (ordered[mid] if len(ordered) % 2
              else 0.5 * (ordered[mid - 1] + ordered[mid]))
    return {
        'count': len(distances),
        'min': ordered[0],
        'max': ordered[-1],
        'mean': sum(distances) / len(distances),
        'median': median,
        'distances': distances,
    }


# ===========================================================================
# C.4 -- Combined graph, energy, and path extraction (NetworkX)
# ===========================================================================
#
# The combined graph is an attributed nx.DiGraph:
#   * forward tree edges parent->child,
#   * backward tree edges reversed (child->parent) so a directed path runs
#     detector-root -> ... -> surface,
#   * a synthetic SUPER_SOURCE -> every forward root and every backward root ->
#     SUPER_TARGET (weight 0), reducing "any source to detector" to one shortest
#     path,
#   * C.3 connection edges F->G (weight 0; F's continuation *is* G reversed).
# Edge weight = -log(T), T = child.total_brightness / parent.total_brightness,
# so the shortest path is the maximum-energy source->detector route and its
# energy is exp(-total_weight) = T_forward x T_backward. Nodes/edges carry stable
# semantic labels (surface_name, edge_index, interaction_type, ...) for cross-run
# topological comparison. See the Step C roadmap for the full rationale.

SUPER_SOURCE = '__SOURCE__'
SUPER_TARGET = '__DETECTOR__'

# Weight used for an edge whose transmittance is unusable (<= 0): large but
# finite so the edge is a last resort rather than breaking shortest-path math.
_UNREACHABLE_WEIGHT = 1e9


def _segment_transmittance(child: 'Ray', parent: 'Ray') -> Optional[float]:
    """Branch transmittance child/parent by total brightness (clamped to (0,1])."""
    parent_b = parent.total_brightness
    child_b = child.total_brightness
    if parent_b <= 0.0 or child_b <= 0.0:
        return None
    return min(1.0, child_b / parent_b)


def _edge_weight(transmittance: Optional[float]) -> float:
    """-log(T) edge weight; unusable transmittance -> large finite weight."""
    if transmittance is None or transmittance <= 0.0:
        return _UNREACHABLE_WEIGHT
    return -math.log(transmittance)


def prune_connections_best_per_forward(connections: List[Connection]) -> List[Connection]:
    """Greedy 1-per-forward pruning of a many-to-many connection set.

    Discrete sampling yields many near-coincident forward hits matching many
    backward hits; keeping all of them makes ranked paths sampling duplicates.
    Keep, for each forward continuation, the single best connection (smallest
    arc-distance, then most antiparallel). Pragmatic stand-in for optimal
    weighted bipartite matching (a later refinement).
    """
    best: Dict[str, Connection] = {}
    for conn in connections:
        key = conn.connecting_child_uuid or conn.forward_uuid
        current = best.get(key)
        if current is None or (conn.arc_distance, conn.direction_dot) \
                < (current.arc_distance, current.direction_dot):
            best[key] = conn
    return list(best.values())


def _add_tree_to_graph(
    graph: Any,
    lineage: 'RayLineage',
    tree: str,
    name_by_uuid: Dict[str, Optional[str]],
    obj_by_uuid: Dict[str, Any],
    reverse: bool,
) -> None:
    """Add one lineage's nodes and (optionally reversed) weighted edges.

    Each node also carries edge_index/arc_position (position along the
    surface it hit), located via _locate_on_surface -- the same helper
    connect_trees() already uses. Needed for path_signature() (analysis
    .signature_analysis) to reduce a path to (surface_name, edge_index,
    interaction_type); previously only present on 'connection' edges, not
    on nodes at all.

    hit_point_x/hit_point_y (the raw scene-coordinate hit point, distinct
    from edge_index/arc_position) are also carried, so path_surfaces()
    (analysis.signature_analysis, 15_p8 item 2) can report each hop's
    physical location without re-deriving it from the ray segments.
    """
    for uuid, seg in lineage._segments.items():
        surface_uuid = getattr(seg, 'hit_surface_uuid', None)
        edge_index = None
        arc_position = None
        hit_point = getattr(seg, 'hit_point', None)
        if surface_uuid is not None and hit_point is not None:
            obj = obj_by_uuid.get(surface_uuid)
            if obj is not None:
                located = _locate_on_surface(obj, hit_point)
                if located is not None:
                    edge_index, arc_position, _edge_len = located
        graph.add_node(
            uuid,
            tree=tree,
            interaction_type=seg.interaction_type,
            surface_uuid=surface_uuid,
            surface_name=name_by_uuid.get(surface_uuid),
            edge_index=edge_index,
            arc_position=arc_position,
            brightness_total=seg.total_brightness,
            incident_angle=getattr(seg, 'incident_angle', None),
            hit_point_x=hit_point.get('x') if hit_point is not None else None,
            hit_point_y=hit_point.get('y') if hit_point is not None else None,
        )
    for uuid, seg in lineage._segments.items():
        parent_uuid = seg.parent_uuid
        if parent_uuid is None:
            continue
        parent = lineage._segments.get(parent_uuid)
        if parent is None:
            continue
        transmittance = _segment_transmittance(seg, parent)
        weight = _edge_weight(transmittance)
        if reverse:
            graph.add_edge(uuid, parent_uuid, kind=tree,
                           weight=weight, transmittance=transmittance)
        else:
            graph.add_edge(parent_uuid, uuid, kind=tree,
                           weight=weight, transmittance=transmittance)


def build_combined_graph(
    forward_lineage: 'RayLineage',
    backward_lineage: 'RayLineage',
    connections: List[Connection],
    scene: 'Scene',
) -> Any:
    """Build the attributed combined nx.DiGraph (C.4).

    Args:
        forward_lineage: Forward lineage.
        backward_lineage: Backward lineage.
        connections: Surface connections (typically pruned; pass the raw set to
            retain the full many-to-many structure for topological analysis).
        scene: Scene, to resolve surface names for the semantic labels.

    Returns:
        An nx.DiGraph with SUPER_SOURCE / SUPER_TARGET terminals.
    """
    import networkx as nx

    name_by_uuid = {getattr(o, 'uuid', None): getattr(o, 'name', None)
                    for o in scene.objs}
    obj_by_uuid = {getattr(o, 'uuid', None): o for o in scene.objs}

    graph = nx.DiGraph()
    _add_tree_to_graph(graph, forward_lineage, 'forward', name_by_uuid, obj_by_uuid, reverse=False)
    _add_tree_to_graph(graph, backward_lineage, 'backward', name_by_uuid, obj_by_uuid, reverse=True)

    graph.add_node(SUPER_SOURCE, role='super_source')
    for root in forward_lineage.get_roots():
        graph.add_edge(SUPER_SOURCE, root.uuid, kind='source_link', weight=0.0)

    graph.add_node(SUPER_TARGET, role='super_target')
    for root in backward_lineage.get_roots():
        graph.add_edge(root.uuid, SUPER_TARGET, kind='target_link', weight=0.0)

    for conn in connections:
        if not (graph.has_node(conn.forward_uuid) and graph.has_node(conn.backward_uuid)):
            continue
        graph.add_edge(
            conn.forward_uuid, conn.backward_uuid,
            kind='connection', weight=0.0,
            surface_uuid=conn.surface_uuid,
            surface_name=name_by_uuid.get(conn.surface_uuid),
            edge_index=conn.edge_index,
            arc_distance=conn.arc_distance,
            direction_dot=conn.direction_dot,
        )
    return graph


def _summarise_path(graph: Any, path: List[str]) -> Dict[str, Any]:
    """Reduce a SUPER_SOURCE..SUPER_TARGET node path to a structured summary."""
    total_weight = 0.0
    connection_surface = None
    connection_edge_index = None
    for u, v in zip(path[:-1], path[1:]):
        data = graph[u][v]
        total_weight += data.get('weight', 0.0)
        if data.get('kind') == 'connection':
            connection_surface = data.get('surface_name')
            connection_edge_index = data.get('edge_index')

    inner = [n for n in path if n not in (SUPER_SOURCE, SUPER_TARGET)]
    path_types = [graph.nodes[n].get('interaction_type') for n in inner]
    trees = [graph.nodes[n].get('tree') for n in inner]
    return {
        'energy': math.exp(-total_weight),
        'weight': total_weight,
        'path_uuids': inner,
        'path_types': path_types,
        'connection_surface': connection_surface,
        'connection_edge_index': connection_edge_index,
        'forward_len': sum(1 for t in trees if t == 'forward'),
        'backward_len': sum(1 for t in trees if t == 'backward'),
    }


def extract_ranked_paths(graph: Any, top_n: int = 10) -> List[Dict[str, Any]]:
    """Rank distinct source->detector paths by energy (C.4).

    Uses Yen's algorithm (nx.shortest_simple_paths) over the combined graph from
    SUPER_SOURCE to SUPER_TARGET, weighted by -log(T). Returns up to ``top_n``
    structured path dicts, highest-energy first. Empty if no path exists (e.g. no
    connections). Best run on a de-duplicated graph (see
    prune_connections_best_per_forward) so results are physically distinct.
    """
    import networkx as nx
    from itertools import islice

    if not (graph.has_node(SUPER_SOURCE) and graph.has_node(SUPER_TARGET)):
        return []
    if not nx.has_path(graph, SUPER_SOURCE, SUPER_TARGET):
        return []
    generator = nx.shortest_simple_paths(graph, SUPER_SOURCE, SUPER_TARGET,
                                         weight='weight')
    return [_summarise_path(graph, path) for path in islice(generator, top_n)]
