"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

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
PYTHON-SPECIFIC MODULE: Ray-Geometry Query Tools
===============================================================================
Functions for querying ray segments in relation to scene geometry (glass
boundaries, edges, etc.).  These are geometry-centric: they use Shapely
contains / intersects / normal computations.  They do NOT depend on the
lineage tree -- they operate on a flat List[Ray].

The two tool families (lineage-based and geometry-based) compose naturally
via uuid-based filtering.  See the roadmap document for examples.
===============================================================================
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple, Union, TYPE_CHECKING

from shapely.geometry import Point, LineString

from .glass_geometry import glass_to_polygon, get_edge_descriptions, describe_edges, EdgeDescription

if TYPE_CHECKING:
    from ..core.ray import Ray
    from ..core.scene import Scene
    from ..core.scene_objs.base_scene_obj import BaseSceneObj
    from ..core.scene_objs.base_glass import BaseGlass


# =============================================================================
# Phase 0 -- Scene object lookup utilities
# =============================================================================

def get_object_by_name(scene: 'Scene', name: str) -> 'BaseSceneObj':
    """
    Find a scene object by its user-defined name.

    Args:
        scene: The Scene to search.
        name: The exact name to match (case-sensitive).

    Returns:
        The matching BaseSceneObj.

    Raises:
        ValueError: If no object has that name or if multiple objects
            share the same name.
    """
    matches = [obj for obj in scene.objs if getattr(obj, 'name', None) == name]
    if len(matches) == 0:
        available = [
            getattr(obj, 'name', None)
            for obj in scene.objs
            if getattr(obj, 'name', None) is not None
        ]
        raise ValueError(
            f"No object named '{name}'. "
            f"Named objects: {available if available else '(none)'}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous: {len(matches)} objects are named '{name}'. "
            f"Use get_object_by_uuid() instead."
        )
    return matches[0]


def get_object_by_uuid(scene: 'Scene', uuid: str) -> 'BaseSceneObj':
    """
    Find a scene object by its UUID (exact or prefix match).

    Args:
        scene: The Scene to search.
        uuid: Full UUID or a prefix (e.g. first 8 characters).

    Returns:
        The matching BaseSceneObj.

    Raises:
        ValueError: If no object matches or if the prefix is ambiguous.
    """
    # Try exact match first
    for obj in scene.objs:
        obj_uuid = getattr(obj, 'uuid', None)
        if obj_uuid is not None and obj_uuid == uuid:
            return obj

    # Try prefix match
    matches = [
        obj for obj in scene.objs
        if getattr(obj, 'uuid', None) is not None
        and getattr(obj, 'uuid', '').startswith(uuid)
    ]
    if len(matches) == 0:
        raise ValueError(f"No object with UUID starting with '{uuid}'.")
    if len(matches) > 1:
        uuids = [getattr(m, 'uuid', '')[:12] + '...' for m in matches]
        raise ValueError(
            f"Ambiguous: {len(matches)} objects match prefix '{uuid}': {uuids}. "
            f"Provide a longer prefix."
        )
    return matches[0]


def get_objects_by_type(scene: 'Scene', type_name: str) -> List['BaseSceneObj']:
    """
    Find all scene objects of a given type.

    Args:
        scene: The Scene to search.
        type_name: The type string to match (e.g. 'Glass', 'Mirror',
            'PointSource'). Matches against the class-level ``type``
            attribute and falls back to ``__class__.__name__``.

    Returns:
        List of matching objects (empty if none found).
    """
    results = []
    for obj in scene.objs:
        obj_type = getattr(obj.__class__, 'type', None) or obj.__class__.__name__
        if obj_type == type_name:
            results.append(obj)
    return results


# =============================================================================
# Phase 1 -- Geometry-ray query functions
# =============================================================================

def _resolve_edge(glass: 'BaseGlass', edge_label: str) -> EdgeDescription:
    """
    Resolve an edge label to an EdgeDescription.

    Matches against short_label first, then long_label, then numeric
    index as a string.

    Raises:
        ValueError: If the label doesn't match any edge.
    """
    edges = get_edge_descriptions(glass)
    if not edges:
        raise ValueError("Glass object has no edges (empty path).")

    # Try short_label
    for e in edges:
        if e.short_label == edge_label:
            return e

    # Try long_label
    for e in edges:
        if e.long_label == edge_label:
            return e

    # Try numeric index
    for e in edges:
        if str(e.index) == edge_label:
            return e

    available = [e.short_label for e in edges]
    raise ValueError(
        f"No edge matching '{edge_label}'. Available labels: {available}"
    )


def _edge_to_linestring(edge: EdgeDescription) -> LineString:
    """Convert an EdgeDescription to a Shapely LineString."""
    return LineString([(edge.p1.x, edge.p1.y), (edge.p2.x, edge.p2.y)])


def _edge_outward_normal(edge: EdgeDescription, glass: 'BaseGlass') -> tuple:
    """
    Compute the outward-pointing unit normal of an edge.

    The edge direction is p1->p2.  The two candidate normals are
    (-dy, dx) and (dy, -dx).  We pick the one that points away from
    the glass centroid.

    Returns:
        (nx, ny) unit normal pointing outward.
    """
    dx = edge.p2.x - edge.p1.x
    dy = edge.p2.y - edge.p1.y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-12:
        return (0.0, 0.0)

    # Two candidate normals
    n1 = (-dy / length, dx / length)
    n2 = (dy / length, -dx / length)

    # Pick the one pointing away from the glass centroid
    poly = glass_to_polygon(glass)
    cx, cy = poly.centroid.x, poly.centroid.y

    # Vector from edge midpoint to centroid
    mx, my = edge.midpoint.x, edge.midpoint.y
    to_centroid_x = cx - mx
    to_centroid_y = cy - my

    # The outward normal has negative dot product with to-centroid vector
    dot1 = n1[0] * to_centroid_x + n1[1] * to_centroid_y
    if dot1 < 0:
        return n1
    return n2


def _ray_endpoints(ray: 'Ray') -> tuple:
    """Extract (p1x, p1y, p2x, p2y) handling both dict and Point."""
    p1 = ray.p1
    p2 = ray.p2
    p1x = p1['x'] if isinstance(p1, dict) else p1.x
    p1y = p1['y'] if isinstance(p1, dict) else p1.y
    p2x = p2['x'] if isinstance(p2, dict) else p2.x
    p2y = p2['y'] if isinstance(p2, dict) else p2.y
    return p1x, p1y, p2x, p2y


def find_rays_inside_glass(
    segments: List['Ray'],
    glass_obj: 'BaseGlass'
) -> List['Ray']:
    """
    Return rays whose midpoint is inside the given glass object.

    Uses ``glass_to_polygon()`` to get the Shapely polygon, then tests
    whether the midpoint of each segment ``(p1+p2)/2`` is contained.

    A ray crossing a glass boundary will have its midpoint inside only
    if the segment is mostly interior. For boundary-crossing rays, use
    ``find_rays_crossing_edge()`` instead.

    Args:
        segments: List of Ray objects to search.
        glass_obj: A BaseGlass object.

    Returns:
        List of Ray objects whose midpoint lies inside the glass.
    """
    poly = glass_to_polygon(glass_obj)
    result = []
    for ray in segments:
        p1x, p1y, p2x, p2y = _ray_endpoints(ray)
        mid = Point((p1x + p2x) / 2, (p1y + p2y) / 2)
        if poly.contains(mid):
            result.append(ray)
    return result


def find_rays_crossing_edge(
    segments: List['Ray'],
    glass_obj: 'BaseGlass',
    edge_label: str
) -> List['Ray']:
    """
    Return rays that cross (intersect) the specified edge of a glass object.

    Uses Shapely ``LineString.intersects()`` between each ray segment
    ``(p1->p2)`` and the edge geometry resolved from ``edge_label``.

    Args:
        segments: List of Ray objects to search.
        glass_obj: A BaseGlass object with labeled edges.
        edge_label: Label of the edge to test against. Matches
            short_label, long_label, or numeric index string.

    Returns:
        List of Ray objects that geometrically intersect the edge.

    Raises:
        ValueError: If ``edge_label`` doesn't match any edge.
    """
    edge = _resolve_edge(glass_obj, edge_label)
    edge_line = _edge_to_linestring(edge)

    result = []
    for ray in segments:
        p1x, p1y, p2x, p2y = _ray_endpoints(ray)
        ray_line = LineString([(p1x, p1y), (p2x, p2y)])
        if ray_line.intersects(edge_line):
            result.append(ray)
    return result


def find_rays_by_angle_to_edge(
    segments: List['Ray'],
    glass_obj: 'BaseGlass',
    edge_label: str,
    min_angle: float = 0.0,
    max_angle: float = 90.0,
    proximity: Optional[float] = None
) -> List['Ray']:
    """
    Return rays within an angle range relative to a specified edge.

    Computes the angle between each ray's direction vector and the
    edge's outward normal. Only rays whose midpoint is within
    ``proximity`` of the edge are considered (to avoid matching rays
    on the far side of the glass).

    Angles are in degrees, measured from the edge normal:
    - 0 = perpendicular to edge (head-on incidence)
    - 90 = parallel to edge (grazing incidence)

    Args:
        segments: List of Ray objects to search.
        glass_obj: A BaseGlass object with labeled edges.
        edge_label: Label of the reference edge.
        min_angle: Minimum angle in degrees (default: 0).
        max_angle: Maximum angle in degrees (default: 90).
        proximity: Maximum distance from ray midpoint to edge line for
            a ray to be considered.  If None, defaults to 2x the edge
            length (generous default).

    Returns:
        List of Ray objects within the angle range and proximity.

    Raises:
        ValueError: If ``edge_label`` doesn't match any edge.
    """
    edge = _resolve_edge(glass_obj, edge_label)
    edge_line = _edge_to_linestring(edge)
    normal = _edge_outward_normal(edge, glass_obj)

    if proximity is None:
        proximity = edge.length * 2.0

    result = []
    for ray in segments:
        p1x, p1y, p2x, p2y = _ray_endpoints(ray)

        # Check proximity: midpoint distance to edge line
        mid = Point((p1x + p2x) / 2, (p1y + p2y) / 2)
        dist = edge_line.distance(mid)
        if dist > proximity:
            continue

        # Ray direction (unit vector)
        rdx = p2x - p1x
        rdy = p2y - p1y
        ray_len = math.sqrt(rdx * rdx + rdy * rdy)
        if ray_len < 1e-12:
            continue
        rdx /= ray_len
        rdy /= ray_len

        # Angle between ray direction and edge normal
        # Use absolute dot product because we care about the angle magnitude,
        # not the sign (a ray going either way relative to the normal)
        dot = abs(rdx * normal[0] + rdy * normal[1])
        # dot = cos(angle_from_normal), clamp for numerical safety
        dot = max(0.0, min(1.0, dot))
        angle_deg = math.degrees(math.acos(dot))

        if min_angle <= angle_deg <= max_angle:
            result.append(ray)

    return result


def find_rays_by_polarization(
    segments: List['Ray'],
    min_dop: float = 0.0,
    max_dop: float = 1.0
) -> List['Ray']:
    """
    Filter rays by degree of polarization.

    Uses ``Ray.degree_of_polarization`` (0 = unpolarized, 1 = fully
    polarized).

    This function is not geometry-dependent -- it is a pure filter on
    ray properties, similar to ``filter_tir_rays`` and
    ``filter_grazing_rays`` in ``saving.py``.  It is placed here to
    keep the query toolkit self-contained for agents.

    Args:
        segments: List of Ray objects to filter.
        min_dop: Minimum degree of polarization (inclusive, default: 0).
        max_dop: Maximum degree of polarization (inclusive, default: 1).

    Returns:
        List of Ray objects within the specified DoP range.
    """
    return [
        ray for ray in segments
        if min_dop <= ray.degree_of_polarization <= max_dop
    ]


# =============================================================================
# Phase 2 -- Geometry convenience utilities
# =============================================================================

def interpolate_along_edge(
    glass_obj: 'BaseGlass',
    edge_label: str,
    fraction: float = 0.5,
    as_point: bool = False,
) -> Union[Tuple[float, float], Point]:
    """
    Get the (x, y) coordinates at a fractional position along a glass edge.

    Uses ``get_edge_descriptions()`` to resolve the edge, then Shapely's
    ``LineString.interpolate()`` for the computation.

    Args:
        glass_obj: A BaseGlass object with labeled edges.
        edge_label: Label of the edge (short_label, long_label, or index
            string).
        fraction: Position along the edge, 0.0 = start (p1), 1.0 = end
            (p2). Default: 0.5 (midpoint).
        as_point: If True, return a ``shapely.geometry.Point`` instead of
            an (x, y) tuple. Default: False.

    Returns:
        (x, y) tuple, or a ``shapely.geometry.Point`` if *as_point* is True.

    Raises:
        ValueError: If ``edge_label`` doesn't match any edge.

    Example:
        >>> x, y = interpolate_along_edge(prism, 'S', 3/4)
        >>> pt = interpolate_along_edge(prism, 'S', 3/4, as_point=True)
    """
    edge = _resolve_edge(glass_obj, edge_label)
    edge_line = _edge_to_linestring(edge)
    point = edge_line.interpolate(fraction, normalized=True)
    if as_point:
        return point
    return (point.x, point.y)


def normal_along_edge(
    glass_obj: 'BaseGlass',
    edge_label: str,
    fraction: float = 0.5,
    length: float = 1.0,
    as_point: bool = False,
) -> Tuple[
    Union[Tuple[float, float], Point],
    Union[Tuple[float, float], Point],
]:
    """
    Get two points defining the outward normal to a glass edge.

    The first point (base) sits on the edge at the given *fraction*.
    The second point (tip) is offset from the base along the outward-pointing
    unit normal by *length* scene units.

    Args:
        glass_obj: A BaseGlass object with labeled edges.
        edge_label: Label of the edge (short_label, long_label, or index
            string).
        fraction: Position along the edge where the normal originates,
            0.0 = start (p1), 1.0 = end (p2). Default: 0.5 (midpoint).
        length: Length of the normal segment in scene units. Default: 1.0.
        as_point: If True, return ``shapely.geometry.Point`` objects instead
            of (x, y) tuples. Default: False.

    Returns:
        (base, tip) — two points defining the normal direction.
        *base* lies on the edge, *tip* is *length* units outward.

    Raises:
        ValueError: If ``edge_label`` doesn't match any edge.

    Example:
        >>> base, tip = normal_along_edge(prism, 'S', 0.5, length=10.0)
        >>> base_pt, tip_pt = normal_along_edge(prism, 'S', 0.5, as_point=True)
    """
    edge = _resolve_edge(glass_obj, edge_label)

    # Base point on the edge
    edge_line = _edge_to_linestring(edge)
    base_shapely = edge_line.interpolate(fraction, normalized=True)
    bx, by = base_shapely.x, base_shapely.y

    # Outward unit normal
    nx, ny = _edge_outward_normal(edge, glass_obj)

    # Tip point
    tx = bx + nx * length
    ty = by + ny * length

    if as_point:
        return (Point(bx, by), Point(tx, ty))
    return ((bx, by), (tx, ty))


def describe_all_glass_edges(
    scene: 'Scene',
    format: str = 'text'
) -> str:
    """
    Describe all edges of all glass objects in a scene.

    Iterates over all BaseGlass subclass objects in the scene and
    concatenates their edge descriptions.

    Args:
        scene: The Scene to describe.
        format: Output format ('text' or 'xml'). Default: 'text'.

    Returns:
        Concatenated edge descriptions for all glass objects.
    """
    from ..core.scene_objs.base_glass import BaseGlass

    parts = []
    for obj in scene.objs:
        if not isinstance(obj, BaseGlass):
            continue
        name = getattr(obj, 'name', None) or getattr(obj, 'uuid', 'unknown')[:12]
        if format == 'xml':
            parts.append(describe_edges(obj, format='xml', show_coordinates=True))
        else:
            header = f"=== {name} ==="
            parts.append(header)
            parts.append(describe_edges(obj, format='text', show_coordinates=True))
            parts.append('')

    return '\n'.join(parts)
