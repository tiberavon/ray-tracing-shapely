"""
Python-specific module: Post-hoc Path Analysis

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Post-hoc Lineage Analysis
===============================================================================
Analysis utilities that operate on a completed simulation's RayLineage to
extract path energy rankings, branching statistics, TIR trap detection, and
angular importance distributions.

All functions take a RayLineage (and optionally the segment list) as input
and return plain dicts/lists -- no side effects.

These tools are all topology-centric: they navigate the tree structure via 
parent_uuid / children, and their spatial awareness is limited 
to the source emission angle. They don't know about scene geometry at all 
-- no glass boundaries, no edge labels, no surface normals
===============================================================================
"""

from __future__ import annotations
import math
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.ray_lineage import RayLineage


# =============================================================================
# Energy path ranking
# =============================================================================

def rank_paths_by_energy(
    lineage: 'RayLineage',
    leaf_uuids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Rank optical paths by terminal segment brightness.

    For each leaf (terminal segment with no children), computes the full
    path from source and reports the terminal brightness. Results are
    sorted highest-energy first.

    Args:
        lineage: A populated RayLineage from a completed simulation.
        leaf_uuids: Optional list of specific leaf uuids to analyze.
            If None, all leaves in the lineage are used.

    Returns:
        List of dicts, each containing:
        - 'uuid': terminal segment uuid
        - 'energy': total brightness (brightness_s + brightness_p)
        - 'energy_s': s-polarization brightness
        - 'energy_p': p-polarization brightness
        - 'path_length': number of segments in the path
        - 'path_types': list of interaction_type strings along the path
        - 'path': list of Ray objects from source to leaf
    """
    if leaf_uuids is None:
        leaves = lineage.get_leaves()
    else:
        leaves = [lineage.get_segment(u) for u in leaf_uuids]
        leaves = [s for s in leaves if s is not None]

    results = []
    for leaf in leaves:
        path = lineage.get_full_path(leaf.uuid)
        results.append({
            'uuid': leaf.uuid,
            'energy': leaf.brightness_s + leaf.brightness_p,
            'energy_s': leaf.brightness_s,
            'energy_p': leaf.brightness_p,
            'path_length': len(path),
            'path_types': [s.interaction_type for s in path],
            'path': path,
        })

    results.sort(key=lambda x: x['energy'], reverse=True)
    return results


# =============================================================================
# Branching statistics
# =============================================================================

def get_branching_statistics(lineage: 'RayLineage') -> Dict[str, Any]:
    """
    Analyze ray tree branching patterns.

    Examines how rays split at optical surfaces. A parent with 2 children
    indicates a Fresnel split (reflected + refracted). A parent with 1 child
    indicates a single-path interaction (mirror reflection, TIR, or a
    Fresnel split where one branch was too dim and was culled).

    Args:
        lineage: A populated RayLineage from a completed simulation.

    Returns:
        Dict with:
        - 'total_segments': total segments in simulation
        - 'roots': number of source rays
        - 'leaves': number of terminal segments
        - 'internal_nodes': segments that have at least one child
        - 'splits': segments with 2+ children (Fresnel splits)
        - 'single_path': segments with exactly 1 child (TIR, mirror, or culled split)
        - 'max_children': maximum children of any single segment
        - 'energy_budget': dict showing energy distribution by interaction type
        - 'split_details': list of dicts for each split point with child info
    """
    roots = lineage.get_roots()
    leaves = lineage.get_leaves()

    splits = []
    single_path = []
    max_children = 0

    # Energy budget by interaction type
    energy_by_type: Dict[str, float] = {}
    count_by_type: Dict[str, int] = {}

    for uuid, seg in lineage._segments.items():
        itype = seg.interaction_type
        energy = seg.brightness_s + seg.brightness_p
        energy_by_type[itype] = energy_by_type.get(itype, 0.0) + energy
        count_by_type[itype] = count_by_type.get(itype, 0) + 1

    # Analyze branching at each non-leaf
    for uuid in lineage._children:
        children = lineage._children[uuid]
        n = len(children)
        if n == 0:
            continue
        max_children = max(max_children, n)
        if n >= 2:
            parent_seg = lineage.get_segment(uuid)
            child_segs = lineage.get_children(uuid)
            splits.append({
                'parent_uuid': uuid,
                'parent_energy': parent_seg.brightness_s + parent_seg.brightness_p if parent_seg else 0,
                'child_count': n,
                'children': [
                    {
                        'uuid': c.uuid,
                        'interaction_type': c.interaction_type,
                        'energy': c.brightness_s + c.brightness_p,
                    }
                    for c in child_segs
                ],
            })
        elif n == 1:
            single_path.append(uuid)

    internal_count = len(splits) + len(single_path)

    return {
        'total_segments': lineage.segment_count,
        'roots': len(roots),
        'leaves': len(leaves),
        'internal_nodes': internal_count,
        'splits': len(splits),
        'single_path': len(single_path),
        'max_children': max_children,
        'energy_budget': {
            itype: {
                'total_energy': energy_by_type.get(itype, 0.0),
                'segment_count': count_by_type.get(itype, 0),
            }
            for itype in sorted(set(list(energy_by_type.keys()) + list(count_by_type.keys())))
        },
        'split_details': splits,
    }


# =============================================================================
# TIR trap detection
# =============================================================================

def detect_tir_traps(
    lineage: 'RayLineage',
    min_tir_count: int = 2
) -> List[Dict[str, Any]]:
    """
    Find ray subtrees where rays are trapped by repeated TIR.

    A TIR trap is a sequence of consecutive TIR events in a ray's lineage,
    indicating a ray bouncing inside a glass body. This identifies
    geometries that act as light traps.

    Args:
        lineage: A populated RayLineage from a completed simulation.
        min_tir_count: Minimum consecutive TIR events to report (default: 2).

    Returns:
        List of dicts, each containing:
        - 'entry_uuid': uuid of the first TIR segment in the chain
        - 'tir_chain': list of consecutive TIR Ray objects
        - 'tir_count': number of TIR events in the chain
        - 'max_tir_count_in_lineage': highest tir_count value in the chain
        - 'escaped': True if the chain ends with a non-TIR event (ray escaped)
        - 'exit_type': interaction_type of the first non-TIR child, or None
        - 'energy_at_entry': brightness at start of TIR chain
        - 'energy_at_exit': brightness at end of TIR chain (last TIR segment)
    """
    traps = []
    visited: set = set()

    # Find all TIR segments
    tir_segments = lineage.get_segments_by_type('tir')

    for seg in tir_segments:
        if seg.uuid in visited:
            continue

        # Walk back to find the start of this TIR chain
        chain_start = seg
        current = seg
        while True:
            parent_uuid = lineage._parents.get(current.uuid)
            if parent_uuid is None:
                break
            parent = lineage.get_segment(parent_uuid)
            if parent is None or parent.interaction_type != 'tir':
                break
            chain_start = parent
            current = parent

        # Walk forward to build the full TIR chain
        chain = [chain_start]
        visited.add(chain_start.uuid)
        current = chain_start

        while True:
            children = lineage.get_children(current.uuid)
            tir_child = None
            for c in children:
                if c.interaction_type == 'tir':
                    tir_child = c
                    break
            if tir_child is None:
                break
            chain.append(tir_child)
            visited.add(tir_child.uuid)
            current = tir_child

        if len(chain) < min_tir_count:
            continue

        # Check if the ray escaped (last TIR segment has non-TIR children)
        last_tir = chain[-1]
        exit_children = lineage.get_children(last_tir.uuid)
        non_tir_children = [c for c in exit_children if c.interaction_type != 'tir']
        escaped = len(non_tir_children) > 0
        exit_type = non_tir_children[0].interaction_type if non_tir_children else None

        traps.append({
            'entry_uuid': chain_start.uuid,
            'tir_chain': chain,
            'tir_count': len(chain),
            'max_tir_count_in_lineage': max(getattr(s, 'tir_count', 0) for s in chain),
            'escaped': escaped,
            'exit_type': exit_type,
            'energy_at_entry': chain[0].brightness_s + chain[0].brightness_p,
            'energy_at_exit': last_tir.brightness_s + last_tir.brightness_p,
        })

    traps.sort(key=lambda x: x['tir_count'], reverse=True)
    return traps


# =============================================================================
# Angular importance distribution
# =============================================================================

def extract_angular_distribution(
    lineage: 'RayLineage',
    leaf_uuids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    For each leaf ray, trace back to its source and compute the emission angle.

    The emission angle is the direction from p1 to p2 of the root (source)
    segment, measured counter-clockwise from the positive x-axis. This can be
    used to build an angular importance distribution for importance sampling.

    Args:
        lineage: A populated RayLineage from a completed simulation.
        leaf_uuids: Optional list of specific leaf uuids to analyze.
            If None, all leaves in the lineage are used.

    Returns:
        List of dicts, each containing:
        - 'leaf_uuid': uuid of the terminal segment
        - 'source_uuid': uuid of the root (source) segment
        - 'emission_angle_rad': angle in radians [-pi, pi]
        - 'emission_angle_deg': angle in degrees [-180, 180]
        - 'source_point': {'x': float, 'y': float} of the source position
        - 'leaf_energy': terminal brightness
        - 'leaf_energy_s': s-polarization brightness
        - 'leaf_energy_p': p-polarization brightness
        - 'path_length': number of segments from source to leaf
    """
    if leaf_uuids is None:
        leaves = lineage.get_leaves()
    else:
        leaves = [lineage.get_segment(u) for u in leaf_uuids]
        leaves = [s for s in leaves if s is not None]

    results = []
    for leaf in leaves:
        path = lineage.get_full_path(leaf.uuid)
        if not path:
            continue

        root = path[0]
        # Compute emission angle from root segment direction
        dx = root.p2['x'] - root.p1['x']
        dy = root.p2['y'] - root.p1['y']
        angle_rad = math.atan2(dy, dx)

        results.append({
            'leaf_uuid': leaf.uuid,
            'source_uuid': root.uuid,
            'emission_angle_rad': angle_rad,
            'emission_angle_deg': math.degrees(angle_rad),
            'source_point': {'x': root.p1['x'], 'y': root.p1['y']},
            'leaf_energy': leaf.brightness_s + leaf.brightness_p,
            'leaf_energy_s': leaf.brightness_s,
            'leaf_energy_p': leaf.brightness_p,
            'path_length': len(path),
        })

    return results


def build_angular_histogram(
    angular_data: List[Dict[str, Any]],
    n_bins: int = 36,
    weight_by_energy: bool = True
) -> Dict[str, Any]:
    """
    Build a histogram of emission angles from angular distribution data.

    Args:
        angular_data: Output of extract_angular_distribution().
        n_bins: Number of angular bins (default: 36, i.e. 10 degrees each).
        weight_by_energy: If True, weight by leaf energy. If False, count rays.

    Returns:
        Dict with:
        - 'bin_edges_deg': list of bin edge angles in degrees (length n_bins + 1)
        - 'bin_centers_deg': list of bin center angles in degrees (length n_bins)
        - 'counts': list of (weighted) counts per bin
        - 'total': sum of all counts
        - 'peak_bin_center_deg': angle of the highest bin
        - 'peak_value': value of the highest bin
    """
    bin_width = 360.0 / n_bins
    bin_edges = [-180.0 + i * bin_width for i in range(n_bins + 1)]
    bin_centers = [-180.0 + (i + 0.5) * bin_width for i in range(n_bins)]
    counts = [0.0] * n_bins

    for entry in angular_data:
        angle = entry['emission_angle_deg']
        weight = entry['leaf_energy'] if weight_by_energy else 1.0

        # Find bin index
        bin_idx = int((angle + 180.0) / bin_width)
        bin_idx = max(0, min(n_bins - 1, bin_idx))
        counts[bin_idx] += weight

    total = sum(counts)
    peak_idx = counts.index(max(counts)) if counts else 0
    peak_value = counts[peak_idx] if counts else 0.0

    return {
        'bin_edges_deg': bin_edges,
        'bin_centers_deg': bin_centers,
        'counts': counts,
        'total': total,
        'peak_bin_center_deg': bin_centers[peak_idx] if bin_centers else 0.0,
        'peak_value': peak_value,
    }


# =============================================================================
# Path energy conservation check
# =============================================================================

def check_energy_conservation(lineage: 'RayLineage') -> Dict[str, Any]:
    """
    Verify energy conservation at each branching point.

    At each non-leaf segment, the sum of children's brightness should not
    exceed the parent's brightness (energy is conserved or lost, never
    gained). This is a diagnostic tool for verifying simulation correctness.

    Args:
        lineage: A populated RayLineage from a completed simulation.

    Returns:
        Dict with:
        - 'total_checks': number of branching points checked
        - 'violations': list of dicts for any violations found
        - 'max_excess_ratio': worst violation as ratio (child_sum / parent)
        - 'is_valid': True if no violations found
    """
    violations = []
    max_excess = 0.0
    total_checks = 0

    for uuid in lineage._children:
        children_uuids = lineage._children[uuid]
        if not children_uuids:
            continue

        parent = lineage.get_segment(uuid)
        if parent is None:
            continue

        parent_energy = parent.brightness_s + parent.brightness_p
        if parent_energy < 1e-12:
            continue

        children = lineage.get_children(uuid)
        child_energy = sum(c.brightness_s + c.brightness_p for c in children)

        total_checks += 1
        ratio = child_energy / parent_energy

        # Allow small numerical tolerance (1e-6 relative)
        if ratio > 1.0 + 1e-6:
            violations.append({
                'parent_uuid': uuid,
                'parent_energy': parent_energy,
                'child_energy_sum': child_energy,
                'excess_ratio': ratio,
                'child_types': [c.interaction_type for c in children],
            })
            max_excess = max(max_excess, ratio)

    return {
        'total_checks': total_checks,
        'violations': violations,
        'max_excess_ratio': max_excess if violations else 1.0,
        'is_valid': len(violations) == 0,
    }


# =============================================================================
# Path length (see dev_doc/architecture/components/analysis_lineage.md)
# =============================================================================
# Deliberately NOT named `path_length` -- rank_paths_by_energy's result dict
# already uses that key for segment COUNT (see above), not a distance.

def geometric_path_length(lineage: 'RayLineage', uuid: str) -> float:
    """
    Sum of Euclidean segment lengths over the full path from source to `uuid`.

    Args:
        lineage: A populated RayLineage from a completed simulation.
        uuid: A segment uuid (typically a detector hit record's `ray_uuid`).

    Returns:
        Total geometric distance travelled, inclusive of every segment on
        the path from the root source ray to `uuid`.
    """
    path = lineage.get_full_path(uuid)
    return sum(
        math.hypot(s.p2['x'] - s.p1['x'], s.p2['y'] - s.p1['y'])
        for s in path
    )


def optical_path_length(lineage: 'RayLineage', uuid: str) -> float:
    """
    Sum of medium_index * segment length over the full path from source to
    `uuid` (Ray.medium_index, part of P-RAY-LINEAGE --
    dev_doc/architecture/components/core_simulator.md).

    Args:
        lineage: A populated RayLineage from a completed simulation.
        uuid: A segment uuid (typically a detector hit record's `ray_uuid`).

    Returns:
        Total optical path length (sum of n*d per segment). Segments that
        predate the Ray.medium_index attribute -- or any Ray subclass/
        mock that doesn't carry it -- default to 1.0 via getattr, silently
        degrading to the geometric length for that segment.
    """
    path = lineage.get_full_path(uuid)
    return sum(
        getattr(s, 'medium_index', 1.0) *
        math.hypot(s.p2['x'] - s.p1['x'], s.p2['y'] - s.p1['y'])
        for s in path
    )
