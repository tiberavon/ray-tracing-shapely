"""
Python-specific module: Ray Lineage Tracking

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Ray Lineage Tracker
===============================================================================
Tracks parent-child relationships for all ray segments in a simulation,
enabling post-hoc path analysis. Uses a lightweight dict-based tree
internally, with optional NetworkX export for graph visualization and
advanced algorithms.
===============================================================================
"""

from __future__ import annotations
from typing import Optional, List, Set, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .ray import Ray


class RayLineage:
    """
    Tracks parent-child relationships for all ray segments in a simulation.

    Internally maintains:
    - _parents: maps uuid -> parent_uuid (or None for roots)
    - _children: maps uuid -> list of child uuids
    - _segments: maps uuid -> Ray object
    - _interaction_types: maps uuid -> interaction type string

    All query methods return Ray objects, not uuids. For uuid-level access
    use the underlying dicts directly or get_subtree_uuids().

    Usage:
        lineage = RayLineage()
        for segment in simulation_segments:
            lineage.register(segment)

        # Query lineage
        path = lineage.get_full_path(some_ray.uuid)
        siblings = lineage.get_siblings(some_ray.uuid)
        tree = lineage.to_networkx()  # requires networkx
    """

    def __init__(self) -> None:
        self._parents: Dict[str, Optional[str]] = {}
        self._children: Dict[str, List[str]] = {}
        self._segments: Dict[str, 'Ray'] = {}
        self._interaction_types: Dict[str, str] = {}

    def register(self, segment: 'Ray') -> None:
        """
        Register a ray segment in the lineage tracker.

        Call this for every ray segment produced during simulation.

        Args:
            segment: A Ray object with uuid, parent_uuid, and interaction_type set.
        """
        self._segments[segment.uuid] = segment
        self._parents[segment.uuid] = segment.parent_uuid
        self._interaction_types[segment.uuid] = segment.interaction_type
        if segment.uuid not in self._children:
            self._children[segment.uuid] = []
        if segment.parent_uuid:
            self._children.setdefault(segment.parent_uuid, []).append(segment.uuid)

    @property
    def segment_count(self) -> int:
        """Total number of registered segments."""
        return len(self._segments)

    def get_segment(self, uuid: str) -> Optional['Ray']:
        """Get a segment by uuid, or None if not found."""
        return self._segments.get(uuid)

    # =========================================================================
    # Ancestor / descendant queries
    # =========================================================================

    def get_ancestors(self, uuid: str) -> List['Ray']:
        """
        All rays in the chain back to source, ordered root-first.

        Does not include the segment itself.

        Raises:
            RuntimeError: If the parent chain cycles back on itself. This
                should never happen (C-LINEAGE-01: single parent, fresh
                uuid per segment) -- raised rather than looping forever or
                silently truncating, so a regression that breaks the
                invariant is loud, not a hang or a plausible-looking wrong
                answer.
        """
        result = []
        visited: Set[str] = set()
        current = self._parents.get(uuid)
        while current is not None:
            if current in visited:
                raise RuntimeError(
                    f"RayLineage cycle detected: uuid {current!r} reappears "
                    f"in its own ancestor chain (starting from {uuid!r}). "
                    f"This violates C-LINEAGE-01."
                )
            visited.add(current)
            seg = self._segments.get(current)
            if seg is None:
                break  # parent not registered (shouldn't happen in a complete simulation)
            result.append(seg)
            current = self._parents.get(current)
        result.reverse()
        return result

    def get_full_path(self, uuid: str) -> List['Ray']:
        """
        Complete chain from source to this segment (inclusive).

        Returns a list ordered from root to the given segment.
        """
        seg = self._segments.get(uuid)
        if seg is None:
            return []
        return self.get_ancestors(uuid) + [seg]

    def get_children(self, uuid: str) -> List['Ray']:
        """Direct children of this segment."""
        return [self._segments[c] for c in self._children.get(uuid, [])
                if c in self._segments]

    def get_descendants(self, uuid: str) -> List['Ray']:
        """All segments spawned from this one (BFS order).

        Raises:
            RuntimeError: If the same uuid is reachable twice (a cycle, or a
                uuid reused as two segments' parent). Should never happen
                (C-LINEAGE-01) -- raised rather than looping forever or
                silently double-counting a shared branch.
        """
        result = []
        visited: Set[str] = set()
        queue = list(self._children.get(uuid, []))
        while queue:
            child = queue.pop(0)
            if child in visited:
                raise RuntimeError(
                    f"RayLineage cycle detected: uuid {child!r} is reachable "
                    f"twice while walking descendants of {uuid!r}. This "
                    f"violates C-LINEAGE-01."
                )
            visited.add(child)
            if child in self._segments:
                result.append(self._segments[child])
                queue.extend(self._children.get(child, []))
        return result

    def get_siblings(self, uuid: str) -> List['Ray']:
        """
        Other segments from the same parent.

        For example, at a glass surface this returns the reflected ray
        if you pass the refracted ray's uuid, and vice versa.
        """
        parent = self._parents.get(uuid)
        if parent is None:
            return []
        return [self._segments[c] for c in self._children.get(parent, [])
                if c != uuid and c in self._segments]

    # =========================================================================
    # Root / leaf / tree queries
    # =========================================================================

    def get_roots(self) -> List['Ray']:
        """All source segments (no parent)."""
        return [self._segments[u] for u, p in self._parents.items()
                if p is None]

    def get_leaves(self) -> List['Ray']:
        """All terminal segments (no children)."""
        return [self._segments[u] for u, children in self._children.items()
                if not children and u in self._segments]

    def get_subtree_uuids(self, uuid: str) -> Set[str]:
        """All uuids in the subtree rooted at uuid (inclusive).

        Raises:
            RuntimeError: If the same uuid is reachable twice -- see
                get_descendants(); should never happen (C-LINEAGE-01).
        """
        result = {uuid}
        queue = list(self._children.get(uuid, []))
        while queue:
            child = queue.pop(0)
            if child in result:
                raise RuntimeError(
                    f"RayLineage cycle detected: uuid {child!r} is reachable "
                    f"twice while walking the subtree rooted at {uuid!r}. "
                    f"This violates C-LINEAGE-01."
                )
            result.add(child)
            queue.extend(self._children.get(child, []))
        return result

    def get_tree_depth(self, uuid: str) -> int:
        """
        Depth of this segment in its tree (0 for roots).

        Raises:
            RuntimeError: If the parent chain cycles back on itself -- see
                get_ancestors(); should never happen (C-LINEAGE-01).
        """
        depth = 0
        visited: Set[str] = set()
        current = self._parents.get(uuid)
        while current is not None:
            if current in visited:
                raise RuntimeError(
                    f"RayLineage cycle detected: uuid {current!r} reappears "
                    f"while computing the depth of {uuid!r}. This violates "
                    f"C-LINEAGE-01."
                )
            visited.add(current)
            depth += 1
            current = self._parents.get(current)
        return depth

    # =========================================================================
    # Interaction type queries
    # =========================================================================

    def get_segments_by_type(self, interaction_type: str) -> List['Ray']:
        """Get all segments with a given interaction type."""
        return [self._segments[u] for u, t in self._interaction_types.items()
                if t == interaction_type and u in self._segments]

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_lineage_statistics(self) -> Dict[str, Any]:
        """
        Summary statistics for the lineage tree.

        Returns:
            Dict with keys:
            - segment_count: total registered segments
            - root_count: number of source rays
            - leaf_count: number of terminal segments
            - max_depth: deepest segment in any tree
            - interaction_counts: dict mapping interaction_type -> count
            - branching_factor_avg: average number of children per non-leaf
        """
        roots = [u for u, p in self._parents.items() if p is None]
        leaves = [u for u, children in self._children.items() if not children]

        # Max depth (sample all leaves)
        max_depth = 0
        for leaf in leaves:
            max_depth = max(max_depth, self.get_tree_depth(leaf))

        # Interaction type counts
        interaction_counts: Dict[str, int] = {}
        for t in self._interaction_types.values():
            interaction_counts[t] = interaction_counts.get(t, 0) + 1

        # Average branching factor (non-leaf nodes only)
        non_leaves = [u for u, children in self._children.items() if children]
        if non_leaves:
            total_children = sum(len(self._children[u]) for u in non_leaves)
            branching_avg = total_children / len(non_leaves)
        else:
            branching_avg = 0.0

        return {
            'segment_count': len(self._segments),
            'root_count': len(roots),
            'leaf_count': len(leaves),
            'max_depth': max_depth,
            'interaction_counts': interaction_counts,
            'branching_factor_avg': branching_avg,
        }

    # =========================================================================
    # NetworkX export (optional dependency)
    # =========================================================================

    def to_networkx(self) -> Any:
        """
        Export to a NetworkX DiGraph.

        Requires networkx to be installed. Each node is a ray uuid with
        'interaction' as a node attribute. Edges go from parent to child.

        Returns:
            nx.DiGraph

        Raises:
            ImportError: if networkx is not installed
        """
        import networkx as nx
        G = nx.DiGraph()
        for uuid, segment in self._segments.items():
            G.add_node(uuid, interaction=self._interaction_types.get(uuid, 'unknown'))
        for uuid, parent in self._parents.items():
            if parent is not None:
                G.add_edge(parent, uuid)
        return G

    def __repr__(self) -> str:
        stats = self.get_lineage_statistics()
        return (f"RayLineage(segments={stats['segment_count']}, "
                f"roots={stats['root_count']}, "
                f"leaves={stats['leaf_count']}, "
                f"max_depth={stats['max_depth']})")
