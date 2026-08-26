"""
===============================================================================
BIDIRECTIONAL TRACING -- Lineage backtracing Step C verification
===============================================================================

Incrementally landed alongside
dev_doc/roadmap/done/15_p1_ray_lineage_step_c_bidirectional_tracing.md.

Sub-problem C.1:
  - test_backward_source_emits_from_detector      backward roots lie on the
                                                  detector line, in the cone
  - test_backward_central_direction_reverses_forward
  - test_backward_lineage_valid_and_acyclic       backward tree interacts with
                                                  optics; get_full_path finishes
  - test_forward_state_preserved_after_backward   Step A records + sim state
                                                  survive the backward pass
  - test_backward_segments_carry_hit_records      Step B fields populated when
                                                  record_surface_hits=True
  - test_backward_source_geometric_fallback       no forward hits -> perpendicular
  - test_backward_source_param_validation         degenerate inputs raise

Sub-problem C.2 (reversed physics -- validates that refract() needs NO change):
  - test_reversed_snell_inverts_index_ratio       inside->air ray refracts with
                                                  the inverse ratio (glass angle
                                                  -> air angle)
  - test_two_surface_retrace_is_antiparallel      reversing a transmitted ray and
                                                  re-firing retraces the path and
                                                  emerges antiparallel (reciprocity)
  - test_backward_tir_bookkeeping                 a ray hitting a surface from
                                                  inside beyond critical TIRs
                                                  cleanly (tir flags/count sane)

Sub-problem C.3 (connecting the trees by parametric arc-length):
  - test_locate_on_surface_arc_length             hit_point -> (edge, arc-length)
  - test_connect_finds_shared_surface_connections antiparallel matches on the slab
  - test_connection_tolerance_monotonic           tol=0 -> none; looser -> >= ;
                                                  NN diagnostic well-formed
  - test_connect_requires_hit_records             no Step B records -> no connections
  - test_no_false_connections_across_surfaces     F and G of every connection sit
                                                  on the SAME surface

Sub-problem C.4 (NetworkX combined graph, energy, path extraction):
  - test_combined_graph_is_attributed             super terminals + stable labels
  - test_extract_ranked_paths_energy              sorted, in (0,1], = product of T
  - test_networkx_shortest_path_matches_best      Dijkstra weight == best path
  - test_no_path_without_connections              empty connections -> no paths

Sub-problem C.5 (agentic exposure -- rank_bidirectional_paths):
  - test_rank_bidirectional_paths_tool            structured dict, sorted by
                                                  energy, connections table
                                                  populated for query_rays()
  - test_bidirectional_tool_no_detector           structured error (never
                                                  raises) on missing context /
                                                  wrong detector_name; empty
                                                  (not error) with no
                                                  connections
  - test_mcp_exposes_bidirectional_tool           present in get_agentic_tools()
                                                  and mcp_server._EXPOSED_TOOLS

15_p8 item 1 (backward segments queryable in the rays SQL table):
  - test_backward_rays_in_table                   set_bidirectional_context
                                                  populates both trees, tagged
                                                  via the 'tree' column
  - test_populate_backward_rays_idempotent        re-running doesn't duplicate
                                                  backward rows

15_p8 items 2-4 (agentic exposure -- path_surfaces / audit_bidirectional_paths /
path_physical_summary):
  - test_path_surfaces_tool                       structured per-hop dict,
                                                  errors on unknown uuids /
                                                  missing context
  - test_audit_bidirectional_paths_tool           flags by expected_max_hops
                                                  and allowed_edges, JSON
                                                  [name, edge_index] conversion
  - test_path_physical_summary_tool               structured physical
                                                  summary, errors on a path
                                                  with no connection edge
  - test_mcp_exposes_path_auditing_tools           all three present in
                                                  get_agentic_tools() and
                                                  mcp_server._EXPOSED_TOOLS

Run with:
    python developer_tests/test_bidirectional.py

Or with pytest:
    pytest developer_tests/test_bidirectional.py -v
===============================================================================
"""

import sys
import math
from pathlib import Path

# Allow running as a script or with pytest
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.ray import Ray
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.scene_objs.light_source.backward_detector_source import (
    BackwardDetectorSource,
    backward_central_direction,
)
from ray_tracing_shapely.analysis.bidirectional import (
    connect_trees,
    nearest_neighbour_arc_distances,
    _locate_on_surface,
    build_combined_graph,
    extract_ranked_paths,
    prune_connections_best_per_forward,
    SUPER_SOURCE,
    SUPER_TARGET,
)
from ray_tracing_shapely.analysis.agentic_tools import (
    clear_context,
    set_context,
    set_bidirectional_context,
    rank_bidirectional_paths,
    path_surfaces_tool,
    audit_bidirectional_paths,
    path_physical_summary_tool,
    query_rays,
)


# ---------------------------------------------------------------------------
# Scene builder: source (above) -> horizontal glass slab -> detector (below)
# ---------------------------------------------------------------------------

def _build_scene():
    """A vertical stack so forward rays travel -y and backward rays travel +y."""
    scene = Scene()
    scene.ray_density = 20
    scene.color_mode = 'linear'
    scene.min_brightness_exp = 3

    glass = Glass(scene, {
        'path': [
            {'x': -50, 'y': 0, 'arc': False},
            {'x': 50, 'y': 0, 'arc': False},
            {'x': 50, 'y': -40, 'arc': False},
            {'x': -50, 'y': -40, 'arc': False},
        ],
        'refIndex': 1.5,
    })
    glass.name = 'slab'
    scene.add_object(glass)

    source = AngleSource(scene)
    source.p1 = {'x': 0, 'y': 30}
    source.p2 = {'x': 0, 'y': 29}   # reference direction -y (into the slab)
    source.emis_angle = 40
    source.symmetric = True
    source.brightness = 1.0
    source.name = 'src'
    scene.add_object(source)

    det = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': -30, 'y': -60},
        'p2': {'x': 30, 'y': -60},
        'irrad_map': True,
        'bin_size': 2.0,
    })
    det.name = 'det'
    scene.add_object(det)
    return scene, det


def _run_bidirectional(record=True, **kwargs):
    scene, det = _build_scene()
    sim = Simulator(scene, max_rays=40000, record_surface_hits=record)
    params = dict(acceptance_angle_deg=30, origin_samples=15, direction_samples=11)
    params.update(kwargs)
    result = sim.run_bidirectional(det, **params)
    return sim, det, result


def _point_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ---------------------------------------------------------------------------
# C.1 tests
# ---------------------------------------------------------------------------

def test_backward_source_emits_from_detector():
    """Backward roots originate on the detector segment, inside the acceptance cone."""
    sim, det, result = _run_bidirectional()
    roots = result.backward_lineage.get_roots()
    assert len(roots) == 15 * 11, f"expected 165 backward roots, got {len(roots)}"

    central = backward_central_direction(det, result.forward_lineage)
    centre_ang = math.atan2(central[1], central[0])
    half = math.radians(30) / 2.0
    for r in roots:
        # On the detector line segment.
        d = _point_seg_dist(r.p1['x'], r.p1['y'],
                            det.p1['x'], det.p1['y'], det.p2['x'], det.p2['y'])
        assert d < 1e-9, f"root not on detector line: {r.p1} (dist {d})"
        # Root markers.
        assert r.interaction_type == 'source'
        assert r.parent_uuid is None
        assert getattr(r, 'direction', None) == 'backward'
        # Direction within +/- half-cone of the centre.
        dx, dy = r.p2['x'] - r.p1['x'], r.p2['y'] - r.p1['y']
        ang = math.atan2(dy, dx)
        delta = abs((ang - centre_ang + math.pi) % (2 * math.pi) - math.pi)
        assert delta <= half + 1e-9, f"ray outside cone: delta={math.degrees(delta):.2f}deg"


def test_backward_central_direction_reverses_forward():
    """The backward cone centre points back toward the source (+y here)."""
    sim, det, result = _run_bidirectional()
    central = backward_central_direction(det, result.forward_lineage)
    assert central is not None
    # Forward rays arrive travelling -y, so backward centre must be ~ +y.
    assert central[1] > 0.9, f"expected backward centre ~+y, got {central}"
    assert abs(central[0]) < 0.1, f"expected near-vertical centre, got {central}"


def test_backward_lineage_valid_and_acyclic():
    """Backward rays interact with the optics and every path terminates."""
    sim, det, result = _run_bidirectional()
    bl = result.backward_lineage
    stats = bl.get_lineage_statistics()
    assert stats['max_depth'] >= 1, "backward rays never interacted with an optic"
    # Backward rays refract/reflect through the slab.
    assert stats['interaction_counts'].get('refract', 0) > 0

    # get_full_path terminates for the deepest leaf (no parent_uuid==uuid cycle).
    leaves = bl.get_leaves()
    deepest = max(leaves, key=lambda s: bl.get_tree_depth(s.uuid))
    path = bl.get_full_path(deepest.uuid)
    assert len(path) == bl.get_tree_depth(deepest.uuid) + 1
    # No segment is its own parent.
    for s in result.backward_segments:
        assert s.parent_uuid != s.uuid


def test_forward_state_preserved_after_backward():
    """The backward pass must not corrupt forward Step A records or sim state."""
    sim, det, result = _run_bidirectional()
    # Forward detector hits still present.
    assert len(det.get_hit_uuids()) > 0
    # Detector hit_records reference forward segments, not backward ones.
    forward_uuids = {s.uuid for s in result.forward_segments}
    for rec in det.hit_records:
        assert rec['ray_uuid'] in forward_uuids
    # Simulator's live lineage/segments are the forward ones.
    assert sim.lineage is result.forward_lineage
    assert sim.ray_segments is result.forward_segments


def test_backward_segments_carry_hit_records():
    """With record_surface_hits=True, backward hits get Step B geometry (needed for C.3)."""
    sim, det, result = _run_bidirectional(record=True)
    recorded = [s for s in result.backward_segments if s.incident_angle is not None]
    assert recorded, "no backward segment recorded a surface hit"
    for s in recorded:
        assert s.hit_point is not None
        assert s.hit_normal is not None
        assert 0.0 <= s.incident_angle <= math.pi / 2 + 1e-9


def test_backward_source_geometric_fallback():
    """With no central_direction and no forward hits, fall back to the perpendicular."""
    scene, det = _build_scene()
    # Detector line is horizontal (p1->p2 = +x); perpendicular is +/- y.
    src = BackwardDetectorSource(det, central_direction=None,
                                 origin_samples=3, direction_samples=1)
    cx, cy = src.central_direction
    assert abs(cx) < 1e-9 and abs(cy) == 1.0, f"expected +/-y perpendicular, got {src.central_direction}"
    rays = src.emit_rays()
    assert len(rays) == 3


def test_backward_source_param_validation():
    """Degenerate detector or sample counts raise ValueError."""
    scene, det = _build_scene()

    class _Degenerate:
        p1 = {'x': 1.0, 'y': 1.0}
        p2 = {'x': 1.0, 'y': 1.0}
    raised = False
    try:
        BackwardDetectorSource(_Degenerate())
    except ValueError:
        raised = True
    assert raised, "coincident endpoints should raise ValueError"

    raised = False
    try:
        BackwardDetectorSource(det, origin_samples=0)
    except ValueError:
        raised = True
    assert raised, "origin_samples=0 should raise ValueError"


# ---------------------------------------------------------------------------
# C.2 tests -- reversed physics (single deterministic rays through a slab)
# ---------------------------------------------------------------------------

N_GLASS = 1.5


def _slab_scene(top=0.0, bottom=-40.0, n=N_GLASS):
    """A wide horizontal glass slab with a horizontal top/bottom face."""
    scene = Scene()
    scene.color_mode = 'linear'
    scene.min_brightness_exp = 3
    glass = Glass(scene, {'path': [
        {'x': -500, 'y': top, 'arc': False},
        {'x': 500, 'y': top, 'arc': False},
        {'x': 500, 'y': bottom, 'arc': False},
        {'x': -500, 'y': bottom, 'arc': False},
    ], 'refIndex': n})
    glass.name = 'slab'
    scene.add_object(glass)
    return scene, glass


def _fire(scene, ray, max_rays=50):
    """Trace a single ray with surface-hit recording; return the lineage."""
    sim = Simulator(scene, max_rays=max_rays, record_surface_hits=True)
    sim.add_ray(ray)
    sim.run()
    return sim.lineage


def _unit(dx, dy):
    length = math.hypot(dx, dy)
    return dx / length, dy / length


def _angle_from_vertical(seg):
    """Angle (deg) between the segment direction and the vertical (the slab normal)."""
    dx = seg.p2['x'] - seg.p1['x']
    dy = seg.p2['y'] - seg.p1['y']
    length = math.hypot(dx, dy)
    return math.degrees(math.acos(max(-1.0, min(1.0, abs(dy) / length))))


def _refract_child(lineage, seg):
    for child in lineage.get_children(seg.uuid):
        if child.interaction_type == 'refract':
            return child
    return None


def test_reversed_snell_inverts_index_ratio():
    """A ray hitting a surface from *inside* the glass refracts with the inverse
    index ratio -- geometry-derived incident_type, so refract() needs no change."""
    theta1 = 30.0
    theta2 = math.degrees(math.asin(math.sin(math.radians(theta1)) / N_GLASS))

    scene, _ = _slab_scene()
    a = math.radians(theta2)
    # Start inside the slab (y=-5) heading up toward the top face at theta2.
    ray = Ray(p1={'x': 0.0, 'y': -5.0},
              p2={'x': math.sin(a), 'y': -5.0 + math.cos(a)},
              brightness_s=0.5, brightness_p=0.5)
    lineage = _fire(scene, ray)
    root = lineage.get_roots()[0]

    # Incidence recorded from inside == theta2.
    assert abs(math.degrees(root.incident_angle) - theta2) < 0.1
    child = _refract_child(lineage, root)
    assert child is not None, "expected a refracted ray to escape into air"
    # Exit angle in air == theta1 (inverse ratio applied).
    assert abs(_angle_from_vertical(child) - theta1) < 0.1


def test_two_surface_retrace_is_antiparallel():
    """Reversing a transmitted ray and re-firing retraces the path: the ray that
    emerges is antiparallel to the original incidence (reciprocity)."""
    theta1 = 30.0
    inc = math.radians(theta1)
    inc_dir = (math.sin(inc), -math.cos(inc))  # down-right

    scene, _ = _slab_scene(top=0.0, bottom=-40.0)
    ray = Ray(p1={'x': 0.0, 'y': 20.0},
              p2={'x': inc_dir[0], 'y': 20.0 + inc_dir[1]},
              brightness_s=0.5, brightness_p=0.5)
    lineage = _fire(scene, ray)
    root = lineage.get_roots()[0]
    into_glass = _refract_child(lineage, root)
    transmitted = _refract_child(lineage, into_glass)   # exits the bottom face
    assert transmitted is not None
    ex = _unit(transmitted.p2['x'] - transmitted.p1['x'],
               transmitted.p2['y'] - transmitted.p1['y'])

    # Reverse the transmitted ray and fire it back from below the slab.
    start = {'x': transmitted.p1['x'] + 10 * ex[0],
             'y': transmitted.p1['y'] + 10 * ex[1]}
    back = Ray(p1=start, p2={'x': start['x'] - ex[0], 'y': start['y'] - ex[1]},
               brightness_s=0.5, brightness_p=0.5)
    scene2, _ = _slab_scene(top=0.0, bottom=-40.0)
    lineage2 = _fire(scene2, back)
    broot = lineage2.get_roots()[0]
    b_into = _refract_child(lineage2, broot)
    b_out = _refract_child(lineage2, b_into)   # emerges from the top face
    assert b_out is not None
    fin = _unit(b_out.p2['x'] - b_out.p1['x'], b_out.p2['y'] - b_out.p1['y'])

    dot = fin[0] * inc_dir[0] + fin[1] * inc_dir[1]
    assert dot < -0.999, f"expected antiparallel (dot~-1), got {dot:.6f}"


def test_backward_tir_bookkeeping():
    """A ray hitting the top face from inside beyond the critical angle undergoes
    clean TIR: no refracted ray escapes, and tir flags/count are sane."""
    theta_c = math.degrees(math.asin(1.0 / N_GLASS))

    scene, _ = _slab_scene()
    a = math.radians(theta_c + 10.0)  # comfortably beyond critical
    ray = Ray(p1={'x': 0.0, 'y': -5.0},
              p2={'x': math.sin(a), 'y': -5.0 + math.cos(a)},
              brightness_s=0.5, brightness_p=0.5)
    lineage = _fire(scene, ray)
    root = lineage.get_roots()[0]
    assert math.degrees(root.incident_angle) > theta_c

    children = lineage.get_children(root.uuid)
    types = [c.interaction_type for c in children]
    assert 'tir' in types, "expected a TIR child beyond the critical angle"
    assert 'refract' not in types, "no refracted ray should escape beyond critical"
    tir_child = next(c for c in children if c.interaction_type == 'tir')
    assert tir_child.is_tir_result is True
    assert tir_child.tir_count >= 1


# ---------------------------------------------------------------------------
# C.3 tests -- connecting the trees by parametric arc-length
# ---------------------------------------------------------------------------

def test_locate_on_surface_arc_length():
    """A hit point maps to (edge_index, arc-length) along that edge."""
    scene, glass = _slab_scene(top=0.0, bottom=-40.0)
    # The slab path starts at x=-500; the top edge (index 0) runs -500 -> +500.
    loc = _locate_on_surface(glass, {'x': 0.0, 'y': 0.0})
    assert loc is not None
    edge_index, arc, edge_len = loc
    assert edge_index == 0
    assert abs(arc - 500.0) < 1e-6     # 0.0 is 500 units from x=-500
    assert abs(edge_len - 1000.0) < 1e-6
    # A point far from every edge is not on the surface.
    assert _locate_on_surface(glass, {'x': 0.0, 'y': 5.0}) is None


def test_connect_finds_shared_surface_connections():
    """Forward and backward hits on the slab connect antiparallel at ~same arc."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    conns = result.connections
    assert conns, "expected connections on the shared slab surface"
    dot_threshold = -math.cos(math.radians(2.0))
    for c in conns:
        assert c.arc_distance <= 0.5 + 1e-9
        assert c.direction_dot <= dot_threshold      # antiparallel
        # Both endpoints of the connection sit on the same physical surface.
        f = result.forward_lineage.get_segment(c.forward_uuid)
        g = result.backward_lineage.get_segment(c.backward_uuid)
        assert f.hit_surface_uuid == c.surface_uuid
        assert g.hit_surface_uuid == c.surface_uuid


def test_connection_tolerance_monotonic():
    """Zero tolerance yields no connections; looser tolerance yields at least as
    many. The NN-distance diagnostic is well-formed."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    fwd, bwd = result.forward_lineage, result.backward_lineage

    tight = connect_trees(fwd, bwd, sim.scene, spatial_tolerance=0.0,
                          angular_tolerance_deg=2.0)
    loose = connect_trees(fwd, bwd, sim.scene, spatial_tolerance=2.0,
                          angular_tolerance_deg=3.0)
    assert len(tight) <= len(result.connections) <= len(loose)

    diag = nearest_neighbour_arc_distances(fwd, bwd, sim.scene)
    assert set(diag) == {'count', 'min', 'max', 'mean', 'median', 'distances'}
    assert diag['count'] == len(diag['distances'])
    assert diag['count'] > 0
    assert diag['min'] <= diag['median'] <= diag['max']


def test_connect_requires_hit_records():
    """Without record_surface_hits there is no geometry to match on."""
    scene, det = _build_scene()
    sim = Simulator(scene, max_rays=40000, record_surface_hits=False)
    result = sim.run_bidirectional(det, acceptance_angle_deg=30,
                                   origin_samples=15, direction_samples=11,
                                   spatial_tolerance=0.5)
    assert result.connections == []


def test_no_false_connections_across_surfaces():
    """Every connection pairs hits on one and the same surface object."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    for c in result.connections:
        f = result.forward_lineage.get_segment(c.forward_uuid)
        g = result.backward_lineage.get_segment(c.backward_uuid)
        assert f.hit_surface_uuid == g.hit_surface_uuid == c.surface_uuid


# ---------------------------------------------------------------------------
# C.4 tests -- NetworkX combined graph, energy, path extraction
# ---------------------------------------------------------------------------

def test_combined_graph_is_attributed():
    """The combined graph has super terminals and stable semantic labels."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    graph = result.combined
    assert graph is not None
    assert graph.has_node(SUPER_SOURCE) and graph.has_node(SUPER_TARGET)

    # Connection edges carry the surface's semantic labels.
    conn_edges = [(u, v, d) for u, v, d in graph.edges(data=True)
                  if d.get('kind') == 'connection']
    assert conn_edges, "expected connection edges in the combined graph"
    _, _, d = conn_edges[0]
    assert d['surface_name'] == 'slab'
    assert d['edge_index'] in (0, 2)

    # Segment nodes carry tree + interaction_type; some sit on the named surface.
    trees = {nd.get('tree') for _, nd in graph.nodes(data=True)}
    assert {'forward', 'backward'} <= trees
    assert any(nd.get('surface_name') == 'slab'
               for _, nd in graph.nodes(data=True))


def test_extract_ranked_paths_energy():
    """Ranked paths are sorted by energy, in (0,1], and energy == product of T."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    paths = extract_ranked_paths(result.combined, top_n=5)
    assert paths, "expected at least one source->detector path"

    energies = [p['energy'] for p in paths]
    assert energies == sorted(energies, reverse=True)
    for e in energies:
        assert 0.0 < e <= 1.0 + 1e-9

    # Best path energy equals the product of edge transmittances along it.
    best = paths[0]
    assert best['connection_surface'] == 'slab'
    assert best['forward_len'] >= 1 and best['backward_len'] >= 1
    node_path = [SUPER_SOURCE] + best['path_uuids'] + [SUPER_TARGET]
    product_t = 1.0
    for a, b in zip(node_path[:-1], node_path[1:]):
        t = result.combined[a][b].get('transmittance')
        if t is not None:
            product_t *= t
    assert abs(best['energy'] - product_t) < 1e-9


def test_networkx_shortest_path_matches_best():
    """The min-loss Dijkstra weight equals the top-ranked path's weight."""
    import networkx as nx
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    graph = result.combined
    best = extract_ranked_paths(graph, top_n=1)[0]
    dijkstra_weight = nx.dijkstra_path_length(graph, SUPER_SOURCE, SUPER_TARGET,
                                              weight='weight')
    assert abs(best['weight'] - dijkstra_weight) < 1e-9


def test_no_path_without_connections():
    """With no Step B records there are no connections and hence no paths."""
    scene, det = _build_scene()
    sim = Simulator(scene, max_rays=40000, record_surface_hits=False)
    result = sim.run_bidirectional(det, acceptance_angle_deg=30,
                                   origin_samples=15, direction_samples=11,
                                   spatial_tolerance=0.5)
    assert result.connections == []
    assert extract_ranked_paths(result.combined, top_n=5) == []


# ---------------------------------------------------------------------------
# C.5 tests -- agentic exposure (rank_bidirectional_paths)
# ---------------------------------------------------------------------------

def test_rank_bidirectional_paths_tool():
    """C.5: the tool returns ranked connected paths as a structured dict whose
    path_uuids feed highlight_custom_rays_svg, and populates the connections
    table for query_rays()."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    clear_context()
    set_context(sim.scene, result.forward_segments, result.forward_lineage)
    set_bidirectional_context(result)

    response = rank_bidirectional_paths(top_n=5)
    assert response['status'] == 'ok'
    paths = response['data']
    assert paths, "expected at least one ranked path"

    energies = [p['energy'] for p in paths]
    assert energies == sorted(energies, reverse=True)

    top = paths[0]
    for key in ('uuid', 'energy', 'weight', 'path_length', 'path_types',
                'path_uuids', 'connection_surface', 'connection_edge_index',
                'forward_len', 'backward_len'):
        assert key in top, f"missing key {key!r} in {top}"
    assert top['uuid'] == top['path_uuids'][-1]
    assert top['path_length'] == len(top['path_uuids'])

    # detector_name is a sanity check, not a filter: right name passes,
    # wrong name errors.
    matching = rank_bidirectional_paths(detector_name=det.name, top_n=1)
    assert matching['status'] == 'ok'
    mismatched = rank_bidirectional_paths(detector_name='not_the_real_detector')
    assert mismatched['status'] == 'error'

    # connections table populated into the shared db (C.5, optional part).
    q = query_rays("SELECT COUNT(*) AS n FROM connections")
    assert q['status'] == 'ok'
    assert q['data']['rows'][0][0] == len(result.connections)

    clear_context()


def test_bidirectional_tool_no_detector():
    """C.5: structured error (never raises) with no bidirectional context or a
    mismatched detector_name; a legitimately empty (not erroring) result when
    the trace found no connections at all."""
    clear_context()
    no_context = rank_bidirectional_paths()
    assert no_context['status'] == 'error'
    assert 'bidirectional' in no_context['message'].lower()

    scene, det = _build_scene()
    sim = Simulator(scene, max_rays=40000, record_surface_hits=False)
    result = sim.run_bidirectional(det, acceptance_angle_deg=30,
                                   origin_samples=5, direction_samples=3,
                                   spatial_tolerance=0.5)
    set_context(scene, result.forward_segments, result.forward_lineage)
    set_bidirectional_context(result)

    mismatched = rank_bidirectional_paths(detector_name='not_det')
    assert mismatched['status'] == 'error'

    # No Step B records -> no connections -> legitimately empty, not an error.
    assert result.connections == []
    empty = rank_bidirectional_paths()
    assert empty['status'] == 'ok'
    assert empty['data'] == []

    clear_context()


def test_mcp_exposes_bidirectional_tool():
    """C.5: rank_bidirectional_paths is present in both the framework-agnostic
    tool registry (get_agentic_tools) and mcp_server's _EXPOSED_TOOLS."""
    from ray_tracing_shapely.analysis.tool_registry import get_agentic_tools

    names = [t['name'] for t in get_agentic_tools()]
    assert 'rank_bidirectional_paths' in names, (
        f"rank_bidirectional_paths missing from get_agentic_tools(): {names}"
    )

    try:
        from ray_tracing_shapely.analysis import mcp_server
    except ImportError:
        return  # mcp package not installed -- same skip as test_detector_agentic_tools

    exposed_names = [fn.__name__ for fn in mcp_server._EXPOSED_TOOLS]
    assert 'rank_bidirectional_paths' in exposed_names, (
        f"rank_bidirectional_paths missing from _EXPOSED_TOOLS: {exposed_names}"
    )


# ---------------------------------------------------------------------------
# 15_p8 item 1 tests -- backward segments queryable in the rays table
# ---------------------------------------------------------------------------

def test_backward_rays_in_table():
    """15_p8 item 1: set_bidirectional_context() populates the rays table with
    both trees, tagged via the 'tree' column, so a bidirectional path is
    queryable end to end (not just its forward half)."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    clear_context()
    set_context(sim.scene, result.forward_segments, result.forward_lineage)
    set_bidirectional_context(result)

    q = query_rays("SELECT tree, COUNT(*) AS n FROM rays GROUP BY tree")
    assert q['status'] == 'ok'
    counts = {row[0]: row[1] for row in q['data']['rows']}
    assert counts.get('forward') == len(result.forward_segments), (
        f"expected {len(result.forward_segments)} forward rows, got {counts.get('forward')}"
    )
    assert counts.get('backward') == len(result.backward_segments), (
        f"expected {len(result.backward_segments)} backward rows, got {counts.get('backward')}"
    )

    clear_context()


def test_populate_backward_rays_idempotent():
    """15_p8 item 1: calling set_bidirectional_context() twice on the same
    result does not duplicate backward rows (populate_backward_rays deletes
    any previously-inserted backward rows before re-inserting)."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    clear_context()
    set_context(sim.scene, result.forward_segments, result.forward_lineage)
    set_bidirectional_context(result)
    set_bidirectional_context(result)

    q = query_rays("SELECT COUNT(*) AS n FROM rays WHERE tree = 'backward'")
    assert q['status'] == 'ok'
    assert q['data']['rows'][0][0] == len(result.backward_segments)

    clear_context()


# ---------------------------------------------------------------------------
# 15_p8 items 2-4 tests -- path_surfaces / audit_bidirectional_paths /
# path_physical_summary agentic exposure
# ---------------------------------------------------------------------------

def test_path_surfaces_tool():
    """15_p8 item 2: path_surfaces_tool returns one structured hop per
    path_uuid, and errors (never raises) on unknown uuids or missing context."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    clear_context()
    set_context(sim.scene, result.forward_segments, result.forward_lineage)
    set_bidirectional_context(result)

    ranked = rank_bidirectional_paths(top_n=5)
    assert ranked['status'] == 'ok' and ranked['data'], "expected at least one ranked path"
    path_uuids = ranked['data'][0]['path_uuids']

    response = path_surfaces_tool(path_uuids)
    assert response['status'] == 'ok'
    hops = response['data']
    assert len(hops) == len(path_uuids)
    for key in ('uuid', 'tree', 'surface_name', 'edge_index', 'arc_position',
                'hit_point_x', 'hit_point_y', 'interaction_type'):
        assert key in hops[0], f"missing key {key!r} in {hops[0]}"
    assert [h['uuid'] for h in hops] == path_uuids

    bad = path_surfaces_tool(['not-a-real-uuid'])
    assert bad['status'] == 'error'

    clear_context()
    no_context = path_surfaces_tool(path_uuids)
    assert no_context['status'] == 'error'

    clear_context()


def test_audit_bidirectional_paths_tool():
    """15_p8 item 3: audit_bidirectional_paths_tool flags by expected_max_hops
    and by allowed_edges (JSON [name, edge_index_or_null] pairs), and errors
    (never raises) with no bidirectional context."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    clear_context()
    set_context(sim.scene, result.forward_segments, result.forward_lineage)
    set_bidirectional_context(result)

    unconstrained = audit_bidirectional_paths(top_n=10)
    assert unconstrained['status'] == 'ok'
    assert unconstrained['data']['flagged_paths'] == []
    assert unconstrained['data']['total_paths'] > 0

    strict = audit_bidirectional_paths(top_n=10, expected_max_hops=0)
    assert strict['status'] == 'ok'
    assert len(strict['data']['flagged_paths']) == strict['data']['total_paths']

    # allowed_edges as JSON-friendly [name, edge_index_or_null] pairs.
    allowed_real_surface = audit_bidirectional_paths(
        top_n=10, allowed_edges=[['slab', None]],
    )
    assert allowed_real_surface['status'] == 'ok'
    assert allowed_real_surface['data']['flagged_paths'] == []

    disallow_everything = audit_bidirectional_paths(
        top_n=10, allowed_edges=[['not_a_real_surface', None]],
    )
    assert disallow_everything['status'] == 'ok'
    assert len(disallow_everything['data']['flagged_paths']) == disallow_everything['data']['total_paths']

    clear_context()
    no_context = audit_bidirectional_paths()
    assert no_context['status'] == 'error'

    clear_context()


def test_path_physical_summary_tool():
    """15_p8 item 4: path_physical_summary_tool returns structured
    polarization/length data, and errors (never raises) on a path with no
    surface connection or missing context."""
    sim, det, result = _run_bidirectional(spatial_tolerance=0.5,
                                          angular_tolerance_deg=2.0)
    clear_context()
    set_context(sim.scene, result.forward_segments, result.forward_lineage)
    set_bidirectional_context(result)

    ranked = rank_bidirectional_paths(top_n=5)
    assert ranked['status'] == 'ok' and ranked['data'], "expected at least one ranked path"
    path_uuids = ranked['data'][0]['path_uuids']

    response = path_physical_summary_tool(path_uuids)
    assert response['status'] == 'ok'
    summary = response['data']
    for key in ('total_length', 'brightness_s_at_detector', 'brightness_p_at_detector',
                'degree_of_polarization_at_detector', 'polarization_ratio_at_detector',
                'adaptive_sampling_warning'):
        assert key in summary, f"missing key {key!r} in {summary}"
    assert summary['total_length'] > 0.0

    no_connection = path_physical_summary_tool([path_uuids[0]])
    assert no_connection['status'] == 'error'

    clear_context()
    no_context = path_physical_summary_tool(path_uuids)
    assert no_context['status'] == 'error'

    clear_context()


def test_mcp_exposes_path_auditing_tools():
    """15_p8 items 2-4: path_surfaces/audit_bidirectional_paths/
    path_physical_summary are present in both the framework-agnostic tool
    registry (get_agentic_tools) and mcp_server's _EXPOSED_TOOLS."""
    from ray_tracing_shapely.analysis.tool_registry import get_agentic_tools

    names = [t['name'] for t in get_agentic_tools()]
    for expected in ('path_surfaces', 'audit_bidirectional_paths', 'path_physical_summary'):
        assert expected in names, f"{expected} missing from get_agentic_tools(): {names}"

    try:
        from ray_tracing_shapely.analysis import mcp_server
    except ImportError:
        return  # mcp package not installed -- same skip as test_detector_agentic_tools

    exposed_names = [fn.__name__ for fn in mcp_server._EXPOSED_TOOLS]
    for expected in ('path_surfaces_tool', 'audit_bidirectional_paths', 'path_physical_summary_tool'):
        assert expected in exposed_names, f"{expected} missing from _EXPOSED_TOOLS: {exposed_names}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_backward_source_emits_from_detector,
        test_backward_central_direction_reverses_forward,
        test_backward_lineage_valid_and_acyclic,
        test_forward_state_preserved_after_backward,
        test_backward_segments_carry_hit_records,
        test_backward_source_geometric_fallback,
        test_backward_source_param_validation,
        test_reversed_snell_inverts_index_ratio,
        test_two_surface_retrace_is_antiparallel,
        test_backward_tir_bookkeeping,
        test_locate_on_surface_arc_length,
        test_connect_finds_shared_surface_connections,
        test_connection_tolerance_monotonic,
        test_connect_requires_hit_records,
        test_no_false_connections_across_surfaces,
        test_combined_graph_is_attributed,
        test_extract_ranked_paths_energy,
        test_networkx_shortest_path_matches_best,
        test_no_path_without_connections,
        test_rank_bidirectional_paths_tool,
        test_bidirectional_tool_no_detector,
        test_mcp_exposes_bidirectional_tool,
        test_backward_rays_in_table,
        test_populate_backward_rays_idempotent,
        test_path_surfaces_tool,
        test_audit_bidirectional_paths_tool,
        test_path_physical_summary_tool,
        test_mcp_exposes_path_auditing_tools,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface unexpected errors
            failures += 1
            print(f"  ERROR {test.__name__}: {exc!r}")

    if failures:
        print(f"\n{failures} test(s) failed.")
    else:
        print("\nAll bidirectional (Step C.1 + C.2 + C.3 + C.4 + C.5) tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
