"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Structural Path Signatures
===============================================================================
The PyLayers-inspired reduction from dev_doc/roadmap/proposed/
15_p2_bidirectional_ray_tracing_rational.md §2: a source->detector path in the
combined bidirectional graph (analysis.bidirectional), reduced to its
(surface_name, edge_index, interaction_type) tuple. A whole run reduces to a
signature_spectrum -- an energy-weighted signature -> {energy, count} map --
the device's structural fingerprint. Comparing two runs/designs is diffing
two spectra.

Sibling of analysis.bidirectional (Step C machinery) and analysis.
lineage_analysis (forward-tree-only analysis), not a growing section inside
either -- same reasoning as that existing module split.
===============================================================================
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING

from .bidirectional import extract_ranked_paths, _locate_on_surface, _surface_edges

if TYPE_CHECKING:
    from ..core.ray_lineage import RayLineage
    from ..core.scene import Scene
    from .bidirectional import BidirectionalResult


Signature = Tuple[Tuple[Any, Any, Any], ...]


def path_signature(path_dict: Dict[str, Any], graph: Any) -> Signature:
    """
    Reduce one extract_ranked_paths() entry to its structural signature.

    KNOWN CAVEAT, found while implementing estimate_role_transition (below):
    a segment's own `interaction_type` describes the event that *created*
    it -- i.e. what happened at its PARENT's hit_point -- not the event at
    its OWN hit_point/surface_name (confirmed directly against
    core/scene_objs/base_glass.py: `ray2.interaction_type = 'reflect'` /
    `ray3.interaction_type = 'refract'` are set on the newly-created output
    rays, whose p1 is the *incident* point, i.e. the parent's hit_point).
    So pairing one node's own `interaction_type` with its own
    `surface_name`/`edge_index` (as done here and in `_add_tree_to_graph`)
    is off by one hop: it pairs "how this segment began" with "where this
    segment is headed next", not "what happened where". The *sequence* of
    interaction_types along a path (`path_types` in extract_ranked_paths) is
    unaffected and correct; only the per-node (surface, interaction_type)
    *pairing* used here is approximate. estimate_role_transition below does
    NOT reuse this function -- it re-derives the correct parent/child
    pairing directly, precisely to avoid this. Left as a known limitation
    rather than fixed here: fixing it means re-deriving every node's pairing
    across the forward/backward/connection graph structure, which deserves
    its own dedicated pass, not a fix folded into an unrelated feature.

    Args:
        path_dict: One entry from extract_ranked_paths() -- must have
            'path_uuids' (node uuids from source to detector).
        graph: The combined nx.DiGraph the path was extracted from (its
            nodes must carry surface_name/edge_index/interaction_type --
            see bidirectional._add_tree_to_graph).

    Returns:
        A tuple of (surface_name, edge_index, interaction_type) tuples, one
        per node along the path.
    """
    return tuple(
        (
            graph.nodes[u].get('surface_name'),
            graph.nodes[u].get('edge_index'),
            graph.nodes[u].get('interaction_type'),
        )
        for u in path_dict['path_uuids']
    )


def signature_spectrum(
    result: 'BidirectionalResult',
    top_n: int = 10_000,
) -> Dict[Signature, Dict[str, float]]:
    """
    Energy-weighted signature -> {energy, count} map for one run -- the
    device's structural fingerprint.

    Args:
        result: A BidirectionalResult with a populated .combined graph.
        top_n: Maximum number of ranked paths to reduce (passed through to
            extract_ranked_paths).

    Returns:
        Dict mapping each distinct signature to {'energy': float (summed),
        'count': int}. Empty if result.combined has no source->detector path.
    """
    spectrum: Dict[Signature, Dict[str, float]] = {}
    if result.combined is None:
        return spectrum
    for path_dict in extract_ranked_paths(result.combined, top_n=top_n):
        sig = path_signature(path_dict, result.combined)
        entry = spectrum.setdefault(sig, {'energy': 0.0, 'count': 0})
        entry['energy'] += path_dict['energy']
        entry['count'] += 1
    return spectrum


def diff_signature_spectra(
    spec_a: Dict[Signature, Dict[str, float]],
    spec_b: Dict[Signature, Dict[str, float]],
) -> Dict[Signature, Dict[str, Any]]:
    """
    Set-diff + energy-delta of two signature spectra -- the CPC/design
    comparison tool (15_p2_bidirectional_ray_tracing_rational.md §3.5.1).

    Args:
        spec_a: signature_spectrum() output for run A.
        spec_b: signature_spectrum() output for run B.

    Returns:
        Dict mapping every signature seen in either spectrum to
        {'energy_a', 'energy_b', 'only_in'} -- 'only_in' is 'a', 'b', or
        None (present in both).
    """
    keys = set(spec_a) | set(spec_b)
    diff: Dict[Signature, Dict[str, Any]] = {}
    for sig in keys:
        in_a = sig in spec_a
        in_b = sig in spec_b
        diff[sig] = {
            'energy_a': spec_a.get(sig, {}).get('energy', 0.0),
            'energy_b': spec_b.get(sig, {}).get('energy', 0.0),
            'only_in': 'a' if not in_b else ('b' if not in_a else None),
        }
    return diff


def signature_spectrum_to_records(
    spectrum: Dict[Signature, Dict[str, float]],
) -> List[Dict[str, Any]]:
    """
    Serialize a signature_spectrum() result to a JSON-ready list of records.

    Signature tuples aren't valid JSON dict keys, so persist_run_artifacts()
    stores a list of {'signature': [...], 'energy': ..., 'count': ...}
    records instead of a {tuple: {...}} mapping. Pair with
    signature_spectrum_from_records() to reverse it.

    Args:
        spectrum: signature_spectrum() output.

    Returns:
        List of JSON-serializable record dicts.
    """
    return [
        {'signature': [list(node) for node in sig], **entry}
        for sig, entry in spectrum.items()
    ]


def signature_spectrum_from_records(
    records: List[Dict[str, Any]],
) -> Dict[Signature, Dict[str, float]]:
    """Reverse of signature_spectrum_to_records()."""
    return {
        tuple(tuple(node) for node in rec['signature']): {
            'energy': rec['energy'], 'count': rec['count'],
        }
        for rec in records
    }


def path_surfaces(path_dict: Dict[str, Any], graph: Any) -> List[Dict[str, Any]]:
    """
    Reduce one extract_ranked_paths() entry to its physical hop sequence,
    correctly pairing each hop's location with the interaction_type that
    actually happened there (15_p8_bidirectional_path_auditing.md item 2 --
    fixing the pairing path_signature's docstring documents as approximate).

    A tree edge always connects a lineage parent to its lineage child, and
    child.interaction_type describes the event at the PARENT's hit_point --
    not the child's own (see path_signature's KNOWN CAVEAT above). Graph
    edges already encode which end is which: 'forward'-kind edges point
    parent->child, 'backward'-kind edges point child->parent (reversed by
    _add_tree_to_graph so both trees read source->detector). So for each
    interior path node, the correct interaction_type comes from its
    NEIGHBOUR across a tree edge, not from its own graph attribute:
      - its outgoing edge is 'forward'-kind: this node is the parent -- use
        the NEXT node's own interaction_type.
      - its incoming edge is 'backward'-kind: this node is the parent -- use
        the PREVIOUS node's own interaction_type.

    Two hops are structurally unresolvable this way and come back with
    interaction_type=None: the last forward-tree node and the first
    backward-tree node, on either side of the 'connection' edge. That edge
    doesn't connect a lineage parent to a child -- it links two DIFFERENT
    segments (from two different trees) that connect_trees() matched as the
    same physical point -- so nothing in the tree structure records what
    happened there. path_physical_summary() (15_p8 item 4) resolves that one
    location correctly, using Connection.connecting_child_uuid (only
    available from the BidirectionalResult, not from the graph alone).

    The path's two endpoints (the source root and the detector root) keep
    their own sentinel interaction_type ('source', meaning "emission point,
    not a hit") rather than being resolved -- there is no hit event to pair
    them with.

    Args:
        path_dict: One entry from extract_ranked_paths() -- must have
            'path_uuids' (node uuids from source to detector).
        graph: The combined nx.DiGraph the path was extracted from (its
            nodes must carry surface_name/edge_index/arc_position/
            hit_point_x/hit_point_y/tree -- see bidirectional._add_tree_to_graph).

    Returns:
        List of per-hop dicts, one per node in path_dict['path_uuids'],
        each {'uuid', 'tree', 'surface_name', 'edge_index', 'arc_position',
        'hit_point_x', 'hit_point_y', 'interaction_type'} (interaction_type
        may be None at the two connection-adjacent hops, as above).
    """
    path_uuids = path_dict['path_uuids']
    n = len(path_uuids)
    hops = []
    for i, node in enumerate(path_uuids):
        data = graph.nodes[node]
        if i == 0 or i == n - 1:
            interaction_type = data.get('interaction_type')
        else:
            interaction_type = None
            nxt = path_uuids[i + 1]
            if graph.has_edge(node, nxt) and graph[node][nxt].get('kind') == 'forward':
                interaction_type = graph.nodes[nxt].get('interaction_type')
            else:
                prev = path_uuids[i - 1]
                if graph.has_edge(prev, node) and graph[prev][node].get('kind') == 'backward':
                    interaction_type = graph.nodes[prev].get('interaction_type')
        hops.append({
            'uuid': node,
            'tree': data.get('tree'),
            'surface_name': data.get('surface_name'),
            'edge_index': data.get('edge_index'),
            'arc_position': data.get('arc_position'),
            'hit_point_x': data.get('hit_point_x'),
            'hit_point_y': data.get('hit_point_y'),
            'interaction_type': interaction_type,
        })
    return hops


def audit_paths(
    result: 'BidirectionalResult',
    *,
    top_n: int = 20,
    expected_max_hops: Optional[int] = None,
    allowed_edges: Optional[Iterable[Tuple[str, Optional[int]]]] = None,
) -> Dict[str, Any]:
    """
    Flag ranked source->detector paths that don't match an expected routing
    (15_p8_bidirectional_path_auditing.md item 3) -- e.g. path 17 in the
    Hamamatsu refractometer notebook: a source->detector route via a TIR on
    the sample's own far edge, outside the prism, contaminating the intended
    n_sample measurement.

    A path is flagged if EITHER:
      - expected_max_hops is given and the path has more hops than that, or
      - allowed_edges is given and the path touches a (surface_name,
        edge_index) not covered by it.

    Args:
        result: A BidirectionalResult with a populated .combined graph.
        top_n: Maximum number of ranked paths to audit (passed through to
            extract_ranked_paths).
        expected_max_hops: Optional. Paths with more than this many nodes
            (len(path_uuids)) are flagged. Omit to skip this check.
        allowed_edges: Optional iterable of (surface_name, edge_index)
            pairs the path is allowed to touch. edge_index=None means "any
            edge on this surface is allowed" (coarser than naming every
            edge_index individually -- e.g. an entire lens face). Nodes
            with surface_name=None (the source/detector roots) are never
            flagged. Omit to skip this check.

    Returns:
        {'total_paths', 'total_energy', 'flagged_paths', 'flagged_energy',
        'flagged_energy_fraction'}. flagged_paths entries are the ranked
        path dicts (as extract_ranked_paths returns, plus 'path_length' and
        'flag_reasons'). Empty/zeroed if result.combined has no path at all.
    """
    if result.combined is None:
        return {
            'total_paths': 0, 'total_energy': 0.0,
            'flagged_paths': [], 'flagged_energy': 0.0,
            'flagged_energy_fraction': 0.0,
        }

    allowed_set = set(allowed_edges) if allowed_edges is not None else None
    allowed_any_edge_surfaces = (
        {s for s, e in allowed_set if e is None} if allowed_set is not None else set()
    )

    paths = extract_ranked_paths(result.combined, top_n=top_n)
    total_energy = sum(p['energy'] for p in paths)

    flagged_paths = []
    flagged_energy = 0.0
    for path in paths:
        reasons: List[str] = []
        n_hops = len(path['path_uuids'])

        if expected_max_hops is not None and n_hops > expected_max_hops:
            reasons.append(
                f"path_length {n_hops} exceeds expected_max_hops {expected_max_hops}"
            )

        if allowed_set is not None:
            for u in path['path_uuids']:
                node = result.combined.nodes[u]
                surface_name = node.get('surface_name')
                if surface_name is None:
                    continue  # source/detector roots -- not a surface touch
                edge_index = node.get('edge_index')
                allowed = (
                    surface_name in allowed_any_edge_surfaces
                    or (surface_name, edge_index) in allowed_set
                )
                if not allowed:
                    reasons.append(
                        f"touches ({surface_name!r}, edge {edge_index}), not in allowed_edges"
                    )

        if reasons:
            entry = dict(path)
            entry['path_length'] = n_hops
            entry['flag_reasons'] = reasons
            flagged_paths.append(entry)
            flagged_energy += path['energy']

    return {
        'total_paths': len(paths),
        'total_energy': total_energy,
        'flagged_paths': flagged_paths,
        'flagged_energy': flagged_energy,
        'flagged_energy_fraction': (
            flagged_energy / total_energy if total_energy > 1e-10 else 0.0
        ),
    }


def path_physical_summary(
    path_dict: Dict[str, Any],
    result: 'BidirectionalResult',
) -> Dict[str, Any]:
    """
    Reconstruct one bidirectional path's physical characteristics at the
    detector -- polarization and total geometric length
    (15_p8_bidirectional_path_auditing.md item 4).

    Reciprocity argument: Fresnel Rs/Rp/Ts/Tp are identical regardless of
    propagation direction, so a backward segment's brightness RELATIVE TO
    ITS OWN ROOT's brightness is a valid transfer function for [connection
    point -> detector], per polarization -- even though
    BackwardDetectorSource.emit_rays() seeds backward roots with an
    arbitrary 50/50 s/p split, not this path's true polarization (the ratio
    cancels that arbitrariness out). Combined with F' -- the forward
    segment's TRUE post-connection continuation, Connection
    .connecting_child_uuid, NOT the raw forward hit segment -- this gives
    the path's actual brightness_s/brightness_p at the detector.

    Args:
        path_dict: One entry from extract_ranked_paths() -- must have
            'path_uuids' (node uuids from source to detector, spanning
            exactly one 'connection' edge in result.combined).
        result: The BidirectionalResult the path was extracted from
            (.combined, .connections, .forward_lineage, .backward_lineage
            all required).

    Returns:
        {'total_length', 'brightness_s_at_detector', 'brightness_p_at_detector',
        'degree_of_polarization_at_detector', 'polarization_ratio_at_detector',
        'adaptive_sampling_warning'}.

    Raises:
        ValueError: If the path has no 'connection' edge, or no matching
            Connection (with a connecting_child_uuid) is found in
            result.connections -- both indicate path_dict didn't actually
            come from this result's extract_ranked_paths(result.combined).
    """
    graph = result.combined
    if graph is None:
        raise ValueError("result has no combined graph -- nothing to summarise")
    path_uuids = path_dict['path_uuids']

    forward_uuid = None
    backward_uuid = None
    for u, v in zip(path_uuids[:-1], path_uuids[1:]):
        if graph.has_edge(u, v) and graph[u][v].get('kind') == 'connection':
            forward_uuid, backward_uuid = u, v
            break
    if forward_uuid is None:
        raise ValueError(
            "path has no 'connection' edge -- not a valid bidirectional "
            "source->detector path (path_uuids should come from "
            "extract_ranked_paths(result.combined))"
        )

    conn = next(
        (c for c in result.connections
         if c.forward_uuid == forward_uuid and c.backward_uuid == backward_uuid),
        None,
    )
    if conn is None or conn.connecting_child_uuid is None:
        raise ValueError(
            f"no Connection with a connecting_child_uuid matches the graph's "
            f"connection edge ({forward_uuid}, {backward_uuid}) in result.connections"
        )

    forward_segments = result.forward_lineage._segments
    backward_segments = result.backward_lineage._segments

    f_prime = forward_segments.get(conn.connecting_child_uuid)
    if f_prime is None:
        raise ValueError(
            f"connecting_child_uuid {conn.connecting_child_uuid!r} not found "
            f"in result.forward_lineage"
        )
    backward_seg = backward_segments.get(backward_uuid)
    if backward_seg is None:
        raise ValueError(f"backward segment {backward_uuid!r} not found in result.backward_lineage")

    backward_root = backward_seg
    while backward_root.parent_uuid is not None:
        parent = backward_segments.get(backward_root.parent_uuid)
        if parent is None:
            break
        backward_root = parent

    ts_bwd = (backward_seg.brightness_s / backward_root.brightness_s
              if backward_root.brightness_s > 1e-10 else 0.0)
    tp_bwd = (backward_seg.brightness_p / backward_root.brightness_p
              if backward_root.brightness_p > 1e-10 else 0.0)

    brightness_s = f_prime.brightness_s * ts_bwd
    brightness_p = f_prime.brightness_p * tp_bwd
    total = brightness_s + brightness_p
    dop = abs(brightness_p - brightness_s) / total if total > 1e-10 else 0.0
    polarization_ratio = (brightness_p / brightness_s) if brightness_s > 1e-10 else float('inf')

    all_segments = {**forward_segments, **backward_segments}
    total_length = 0.0
    for u in path_uuids:
        seg = all_segments.get(u)
        if seg is None:
            continue
        total_length += math.hypot(seg.p2['x'] - seg.p1['x'], seg.p2['y'] - seg.p1['y'])

    adaptive_sampling_warning = (
        "Backward roots are seeded with an arbitrary 50/50 s/p brightness "
        "split (BackwardDetectorSource.emit_rays()), not this path's true "
        "polarization -- the s/p transfer functions used here (each backward "
        "segment's brightness relative to its OWN root's brightness) are "
        "valid under Fresnel reciprocity regardless of that split, but if "
        "this path belongs to a rare ray class (e.g. an unintended TIR "
        "route like path 17 in the Hamamatsu notebook), few forward/backward "
        "rays may have actually traced it, so this estimate can be noisy. "
        "See 15_p9_targeted_resimulation_and_importance_sampling.md for "
        "increasing this path class's sampling probability."
    )

    return {
        'total_length': total_length,
        'brightness_s_at_detector': brightness_s,
        'brightness_p_at_detector': brightness_p,
        'degree_of_polarization_at_detector': dop,
        'polarization_ratio_at_detector': polarization_ratio,
        'adaptive_sampling_warning': adaptive_sampling_warning,
    }


def _cumulative_arc_to_edge_start(obj: Any, edge_index: int) -> float:
    """Arc length from the surface's first vertex to the start of edge_index."""
    total = 0.0
    for idx, a, b in _surface_edges(obj):
        if idx == edge_index:
            return total
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    raise ValueError(f"edge_index {edge_index} not found on surface")


def estimate_role_transition(
    lineages: Iterable['RayLineage'],
    scene: 'Scene',
    surface_name: str,
    from_type: str,
    to_type: str,
    search_range: Optional[Tuple[float, float]] = None,
) -> Dict[str, float]:
    """
    Locate where a surface's dominant interaction_type flips from from_type
    to to_type, walking edges by edge_index (15_p7_mesh_refinement_and_convergence.md
    §4.2).

    Correctly pairs each PARENT segment's hit location (hit_surface_uuid,
    hit_point -- where it landed on `surface_name`) with its CHILD segments'
    interaction_type (what happened there) -- see the caveat on
    path_signature() above for why this is not simply
    "seg.interaction_type at seg.hit_point".

    Args:
        lineages: RayLineage objects to scan (e.g. [sim.lineage] for a
            forward-only pass, or [result.forward_lineage,
            result.backward_lineage] for a bidirectional one). Does NOT
            need the edge_index/arc_position combined-graph node fix
            (15_p2_bidirectional_ray_tracing_rational.md §11.1) -- this works
            directly off lineage-level hits.
        scene: Scene, to resolve surface_name -> object + edge geometry.
        surface_name: Name of the surface to analyze.
        from_type: Interaction type expected on one side of the transition
            ('refract', 'reflect', or 'tir').
        to_type: Interaction type expected on the other side.
        search_range: Optional (arc_start, arc_end) restricting which edges
            are considered, in cumulative arc-length units (the same units
            `arc_position` is returned in). Found necessary in practice, not
            speculative: a symmetric surface (e.g. RXIOptic's dome) can have
            more than one from_type->to_type flip, and -- exactly the
            instability flagged in 15_p7_mesh_refinement_and_convergence.md §6 --
            `edge_index` renumbers across refinement levels as edges are
            inserted, so a driver loop refining around one specific
            transition must re-lock onto it by arc-length position each
            level, not assume the first ascending match is still the same
            physical location. Omit to search the whole surface (the
            original, still-correct behaviour when there is only one
            transition of interest).

    Returns:
        {'arc_position': float, 'uncertainty': float, 'edge_index': int} --
        arc_position is the cumulative arc-length (from the surface's first
        vertex) of the boundary where the flip occurs; uncertainty is the
        arc-length of the coarsest segment straddling it (the mesh's
        current resolution there, not a statistical confidence interval).

    Raises:
        ValueError: If surface_name isn't found in scene, or no
            from_type->to_type transition exists in the traced data (within
            search_range, if given).
    """
    obj_by_uuid = {getattr(o, 'uuid', None): o for o in scene.objs}
    name_by_uuid = {getattr(o, 'uuid', None): getattr(o, 'name', None) for o in scene.objs}
    surface_uuid = next((u for u, n in name_by_uuid.items() if n == surface_name), None)
    if surface_uuid is None:
        raise ValueError(f"no surface named {surface_name!r} in scene")
    surface_obj = obj_by_uuid[surface_uuid]

    energy_by_edge_type: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    edge_len_by_edge: Dict[int, float] = {}

    for lineage in lineages:
        if lineage is None:
            continue
        for uuid, seg in lineage._segments.items():
            if getattr(seg, 'hit_surface_uuid', None) != surface_uuid:
                continue
            hit_point = getattr(seg, 'hit_point', None)
            if hit_point is None:
                continue
            located = _locate_on_surface(surface_obj, hit_point)
            if located is None:
                continue
            edge_index, _arc, edge_len = located
            edge_len_by_edge[edge_index] = edge_len
            for child in lineage.get_children(uuid):
                energy_by_edge_type[edge_index][child.interaction_type] += child.total_brightness

    dominant = {
        edge_index: max(types, key=types.get)
        for edge_index, types in energy_by_edge_type.items()
    }

    if search_range is not None:
        lo, hi = min(search_range), max(search_range)

        def _fully_inside(edge_index: int) -> bool:
            start = _cumulative_arc_to_edge_start(surface_obj, edge_index)
            end = start + edge_len_by_edge[edge_index]
            # Require the whole edge inside [lo, hi], not just its start --
            # a wide, unrelated edge whose start happens to fall just inside
            # the window (but mostly extends outside it) must not be picked
            # up just because one endpoint is technically in range.
            return lo <= start and end <= hi

        dominant = {
            edge_index: t for edge_index, t in dominant.items()
            if _fully_inside(edge_index)
        }

    ordered = sorted(dominant)
    for a, b in zip(ordered, ordered[1:]):
        if dominant[a] == from_type and dominant[b] == to_type:
            return {
                'arc_position': _cumulative_arc_to_edge_start(surface_obj, b),
                'uncertainty': edge_len_by_edge[a] + edge_len_by_edge[b],
                'edge_index': b,
                'from_edge_index': a,
            }
    raise ValueError(
        f"no {from_type}->{to_type} transition found on {surface_name!r} "
        f"within search_range={search_range} "
        f"(dominant types by edge_index: {dominant})"
    )


__all__ = [
    'path_signature',
    'path_surfaces',
    'audit_paths',
    'path_physical_summary',
    'signature_spectrum',
    'diff_signature_spectra',
    'signature_spectrum_to_records',
    'signature_spectrum_from_records',
    'estimate_role_transition',
]
