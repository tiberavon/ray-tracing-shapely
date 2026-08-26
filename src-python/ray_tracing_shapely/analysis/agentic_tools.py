"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Agentic Tool Wrappers (JSON-Serializable)
===============================================================================
String-in / string-out wrappers around the analysis tools, designed for use
with LLM tool-use APIs (Claude API, claudette, lisette, langchain, etc.)
where inputs and outputs must be JSON-serializable.

Each wrapper:
- Accepts only JSON-serializable parameters (strings, numbers)
- Resolves live Python objects from a pre-registered module-level context
- Delegates to the original analysis function
- Returns results as XML strings via rays_to_xml()

Usage:
    # After running a simulation:
    from ray_tracing_shapely.analysis.agentic_tools import (
        set_context_from_result,
        find_rays_inside_glass_xml,
    )
    set_context_from_result(scene=scene, result=result)

    # Pass tools to an LLM framework:
    chat = Chat(model, tools=[find_rays_inside_glass_xml])
===============================================================================
"""

from __future__ import annotations

import sqlite3
import tempfile
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING

from .ray_geometry_queries import (
    get_object_by_name,
    get_objects_by_type,
    find_rays_inside_glass,
    find_rays_crossing_edge,
    find_rays_by_angle_to_edge,
    find_rays_by_polarization,
)
from .saving import rays_to_xml

if TYPE_CHECKING:
    from ..core.scene import Scene
    from ..core.ray import Ray
    from ..core.ray_lineage import RayLineage
    from .simulation_result import SimulationResult
    from .bidirectional import BidirectionalResult


# =============================================================================
# Structured error response helpers
# =============================================================================

def _ok(data: Any) -> Dict[str, Any]:
    """Wrap a successful result in the standard agentic response envelope."""
    return {"status": "ok", "data": data}


def _error(message: str) -> Dict[str, str]:
    """Wrap an error message in the standard agentic response envelope."""
    return {"status": "error", "message": message}


# =============================================================================
# Context management
# =============================================================================

_CONTEXT: Dict[str, Any] = {}

_NO_CONTEXT_MSG = (
    "No context set. Call set_context() or set_context_from_result() "
    "before using agentic tools."
)


def set_context(
    scene: 'Scene',
    segments: List['Ray'],
    lineage: Optional['RayLineage'] = None,
) -> None:
    """
    Register simulation objects for use by agentic tool wrappers.

    Must be called before any agentic tool is invoked. Also creates an
    in-memory SQLite database with precomputed spatial relationships
    for use by query_rays() and describe_schema().

    Args:
        scene: The Scene object (needed to resolve glass names via
            get_object_by_name).
        segments: The ray segments from the simulation.
        lineage: Optional RayLineage for lineage-based tools.
    """
    from .agentic_db import create_database
    from .render_result import reset_render_counter

    _CONTEXT['scene'] = scene
    _CONTEXT['segments'] = segments
    _CONTEXT['lineage'] = lineage
    _CONTEXT['db'] = create_database(scene, segments)
    _CONTEXT['render_dir'] = tempfile.mkdtemp(prefix='ray_sim_')
    reset_render_counter()


def set_context_from_result(
    scene: 'Scene',
    result: 'SimulationResult',
) -> None:
    """
    Convenience: populate context from a SimulationResult.

    Note: SimulationResult stores a SceneSnapshot (flat summary), not
    the live Scene.  The caller must pass the original Scene separately.

    Args:
        scene: The live Scene object used in the simulation.
        result: The SimulationResult returned by run_with_result().
    """
    set_context(
        scene=scene,
        segments=result.segments,
        lineage=result.lineage,
    )


def set_bidirectional_context(result: 'BidirectionalResult') -> None:
    """
    Register a BidirectionalResult (ray-lineage Step C) for
    rank_bidirectional_paths().

    Additive to the existing forward context, not a replacement for it: call
    set_context() or set_context_from_result() first (for scene/segments/
    lineage/db), then this, for the backward pass + combined graph. If a
    database connection already exists in context, this also:
    - creates/populates a `connections` table in it (surface, edge,
      arc-distance, direction_dot per matched forward/backward pair) so
      query_rays() can SQL over connection quality -- silently skipped, not
      an error, if set_context() hasn't been called yet or the result has no
      connections;
    - inserts result.backward_segments into the existing `rays` table
      (tagged tree='backward'; forward rows stay tree='forward') so a whole
      bidirectional path -- not just its forward half -- is queryable by SQL
      (dev_doc/roadmap/proposed/15_p8_bidirectional_path_auditing.md item 1).

    Args:
        result: The BidirectionalResult from Simulator.run_bidirectional().
    """
    _CONTEXT['bidirectional'] = result

    db = _CONTEXT.get('db')
    if db is not None and result.connections:
        from .agentic_db import populate_connections_table

        scene = _CONTEXT.get('scene')
        name_by_uuid = (
            {getattr(o, 'uuid', None): getattr(o, 'name', None) for o in scene.objs}
            if scene is not None else None
        )
        populate_connections_table(db, result.connections, name_by_uuid=name_by_uuid)

    if db is not None:
        from .agentic_db import populate_backward_rays

        populate_backward_rays(db, result.backward_segments)


def get_context() -> Dict[str, Any]:
    """Return a copy of the current context dict (for inspection/debugging)."""
    return dict(_CONTEXT)


def clear_context() -> None:
    """Clear the context (e.g. between simulation runs)."""
    from .render_result import reset_render_counter

    db = _CONTEXT.get('db')
    if db is not None:
        db.close()
    reset_render_counter()
    _CONTEXT.clear()


def _require_context() -> tuple:
    """
    Return (scene, segments) from context, or raise RuntimeError.

    Returns:
        (scene, segments) tuple.

    Raises:
        RuntimeError: If set_context() has not been called.
    """
    if 'scene' not in _CONTEXT or 'segments' not in _CONTEXT:
        raise RuntimeError(_NO_CONTEXT_MSG)
    return _CONTEXT['scene'], _CONTEXT['segments']


def _require_db() -> sqlite3.Connection:
    """
    Return the SQLite connection from context, or raise RuntimeError.

    Returns:
        The sqlite3.Connection.

    Raises:
        RuntimeError: If set_context() has not been called or DB is missing.
    """
    if 'db' not in _CONTEXT:
        raise RuntimeError(_NO_CONTEXT_MSG)
    return _CONTEXT['db']


def _require_lineage() -> 'RayLineage':
    """
    Return the RayLineage from context, or raise RuntimeError.

    Returns:
        The RayLineage object.

    Raises:
        RuntimeError: If no lineage is available in the context.
    """
    if 'lineage' not in _CONTEXT or _CONTEXT['lineage'] is None:
        raise RuntimeError(
            "No lineage available. Pass lineage to set_context() "
            "or use set_context_from_result()."
        )
    return _CONTEXT['lineage']


def _require_bidirectional() -> 'BidirectionalResult':
    """
    Return the BidirectionalResult from context, or raise RuntimeError.

    Returns:
        The BidirectionalResult object.

    Raises:
        RuntimeError: If set_bidirectional_context() has not been called.
    """
    if 'bidirectional' not in _CONTEXT or _CONTEXT['bidirectional'] is None:
        raise RuntimeError(
            "No bidirectional result available. Call set_bidirectional_context"
            "(result) with the result of Simulator.run_bidirectional(...) first."
        )
    return _CONTEXT['bidirectional']


# =============================================================================
# SQL query tools (Phase 1)
# =============================================================================

def query_rays(sql: str) -> Dict[str, Any]:
    """
    Run a read-only SQL query against the simulation database.

    The database contains seven tables:
    - rays: One row per ray segment with all properties
    - glass_objects: One row per glass object in the scene
    - edges: One row per edge of each glass object
    - ray_glass_membership: Join table (ray_uuid, glass_uuid) for rays inside glass
    - ray_edge_crossing: Join table for rays crossing glass edges
    - detectors: One row per Detector object (including a LinearSensor's
      internal detector)
    - detector_hits: One row per ray that crossed a detector, joinable to
      rays.uuid via ray_uuid -- lets you filter rays.* by which detector
      (and which bin) they hit

    Use describe_schema() to see full table definitions.

    Only SELECT statements are allowed. Results are limited to 200 rows
    by default -- use LIMIT or more specific WHERE conditions for large results.

    Args:
        sql: A SQL SELECT query string.

    Returns:
        Structured dict with status and query results, or error message.
        On success, data contains 'columns', 'rows', and 'row_count'.

    Example queries:
        "SELECT COUNT(*) as n, AVG(brightness_total) as avg_b FROM rays"
        "SELECT r.uuid, r.brightness_total FROM rays r
         JOIN ray_glass_membership m ON r.uuid = m.ray_uuid
         WHERE m.glass_name = 'Main Prism'"
        "SELECT DISTINCT glass_name FROM ray_glass_membership"
    """
    try:
        from .agentic_db import execute_query
        db = _require_db()
        result = execute_query(db, sql)
        return _ok(result)
    except ValueError as e:
        return _error(str(e))
    except sqlite3.OperationalError as e:
        return _error(f"SQL error: {e}")
    except RuntimeError as e:
        return _error(str(e))


def describe_schema() -> Dict[str, Any]:
    """
    Return the schema of the simulation database.

    Lists all tables, their columns (with types and descriptions),
    and current row counts. Use this to discover what data is available
    before writing SQL queries with query_rays().

    Returns:
        Structured dict with table definitions and row counts.
    """
    try:
        from .agentic_db import get_schema_description
        db = _require_db()
        schema = get_schema_description(db)
        return _ok({"tables": schema})
    except RuntimeError as e:
        return _error(str(e))


# =============================================================================
# Lineage + Fresnel tools (Phase 2)
# =============================================================================

def rank_paths_by_energy(top_n: int = 10) -> Dict[str, Any]:
    """
    Rank optical paths by terminal segment brightness, highest-energy first.

    Returns a list of path summaries with uuid, energy, path_length,
    path_types, and path_uuids (for use with highlight_custom_rays_svg).

    Requires lineage: call set_context(scene, segments, lineage) or
    set_context_from_result() first.

    Args:
        top_n: Maximum number of paths to return (default: 10).

    Returns:
        Structured dict with status and ranked path data, or error message.
    """
    try:
        from .lineage_analysis import rank_paths_by_energy as _rank_paths

        lineage = _require_lineage()
        raw_results = _rank_paths(lineage)

        # Convert to JSON-serializable: replace 'path' (Ray objects) with
        # 'path_uuids' (string list) for use with highlight_custom_rays_svg
        serializable = []
        for entry in raw_results[:top_n]:
            serializable.append({
                'uuid': entry['uuid'],
                'energy': entry['energy'],
                'energy_s': entry['energy_s'],
                'energy_p': entry['energy_p'],
                'path_length': entry['path_length'],
                'path_types': entry['path_types'],
                'path_uuids': [r.uuid for r in entry['path']],
            })

        return _ok(serializable)
    except (ValueError, RuntimeError) as e:
        return _error(str(e))


def check_energy_conservation() -> Dict[str, Any]:
    """
    Verify energy conservation at each branching point in the ray tree.

    At each non-leaf segment, the sum of children's brightness should not
    exceed the parent's brightness. Returns a diagnostic report.

    Requires lineage: call set_context(scene, segments, lineage) or
    set_context_from_result() first.

    Returns:
        Structured dict with status and conservation report, or error message.
        On success, data contains 'is_valid', 'total_checks', 'violations',
        'max_excess_ratio'.
    """
    try:
        from .lineage_analysis import check_energy_conservation as _check_energy

        lineage = _require_lineage()
        result = _check_energy(lineage)
        return _ok(result)
    except RuntimeError as e:
        return _error(str(e))


# =============================================================================
# Detector-path tools (ray-lineage Step A agentic exposure)
# =============================================================================

def list_detectors() -> Dict[str, Any]:
    """
    List all Detector objects in the scene, including a LinearSensor's
    internal detector (named '<sensor_name>_detector').

    Use this to discover valid detector_name values for
    rank_detector_paths() without guessing.

    Requires context: call set_context() or set_context_from_result() first.

    Returns:
        Structured dict with status and a list of detector summaries
        (name, uuid, p1, p2, length, bin_size, hit_count), or error message.
    """
    try:
        scene, _segments = _require_context()
        detectors = get_objects_by_type(scene, 'Detector')

        summaries = []
        for det in detectors:
            hit_records = det.get_hit_records() if hasattr(det, 'get_hit_records') else []
            summaries.append({
                'name': det.name,
                'uuid': det.uuid,
                'p1': det.p1,
                'p2': det.p2,
                'length': det.length,
                'bin_size': det.bin_size,
                'hit_count': len(hit_records),
            })
        return _ok(summaries)
    except RuntimeError as e:
        return _error(str(e))


def rank_detector_paths(detector_name: str, top_n: int = 10) -> Dict[str, Any]:
    """
    Rank the optical paths that actually reached a named detector,
    highest-energy first.

    This is the detector-scoped counterpart to rank_paths_by_energy(): it
    filters the lineage tree to the rays that crossed the named detector
    (via Detector.get_hit_uuids()), so the ranking reflects what the
    detector actually measured -- not every leaf in the scene.

    Requires scene + lineage context: call set_context(scene, segments, lineage)
    or set_context_from_result() first. Use list_detectors() to discover
    valid detector_name values.

    Args:
        detector_name: Name of the Detector (or a LinearSensor's internal
            detector, named '<sensor_name>_detector') in the scene.
        top_n: Maximum number of paths to return (default: 10).

    Returns:
        Structured dict with status and ranked path data, or error message.
        Each entry has uuid, energy, energy_s, energy_p, path_length,
        path_types, path_uuids (for use with highlight_custom_rays_svg),
        and bin_index (the irradiance bin the ray landed in, or None).
    """
    try:
        from .lineage_analysis import rank_paths_by_energy as _rank_paths

        scene, _segments = _require_context()
        lineage = _require_lineage()

        detector = get_object_by_name(scene, detector_name)
        if not hasattr(detector, 'get_hit_uuids'):
            return _error(
                f"'{detector_name}' is not a Detector (no hit records). "
                f"Use list_detectors() to see valid names."
            )

        leaf_uuids = detector.get_hit_uuids()

        # Map each uuid to the bin it landed in (first occurrence), so the
        # agent can talk about pixel/bin position, not just energy.
        bin_by_uuid: Dict[str, Optional[int]] = {}
        for record in detector.get_hit_records():
            u = record['ray_uuid']
            if u is not None and u not in bin_by_uuid:
                bin_by_uuid[u] = record['bin_index']

        raw_results = _rank_paths(lineage, leaf_uuids=leaf_uuids)

        serializable = []
        for entry in raw_results[:top_n]:
            serializable.append({
                'uuid': entry['uuid'],
                'energy': entry['energy'],
                'energy_s': entry['energy_s'],
                'energy_p': entry['energy_p'],
                'path_length': entry['path_length'],
                'path_types': entry['path_types'],
                'path_uuids': [r.uuid for r in entry['path']],
                'bin_index': bin_by_uuid.get(entry['uuid']),
            })

        return _ok(serializable)
    except (ValueError, RuntimeError) as e:
        return _error(str(e))


def paths_by_incidence_angle(
    min_deg: float,
    max_deg: float,
    surface_name: Optional[str] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """
    Rank ray segments whose angle of incidence falls in [min_deg, max_deg],
    highest-brightness first.

    This surfaces the Step B surface-hit geometry: a segment carries an
    incident_angle only when the simulation was run with
    Simulator(record_surface_hits=True) AND the segment struck a surface that
    computes a normal (glass, mirror). Combine with rank_detector_paths() to
    answer compound questions like "of the paths that reached the sensor, which
    hit the entry face above the critical angle?".

    Requires context: call set_context() or set_context_from_result() first.

    Args:
        min_deg: Lower bound of the incidence-angle window, in DEGREES.
        max_deg: Upper bound of the incidence-angle window, in DEGREES.
        surface_name: Optional. Restrict to hits on a named object (glass,
            mirror, detector). Use list_detectors() / query the glass_objects
            table to discover names.
        top_n: Maximum number of segments to return (default: 10).

    Returns:
        Structured dict with status and a list of segments (each: uuid,
        interaction_type, incident_angle_deg, incident_angle_rad,
        hit_surface_uuid, hit_point, brightness_s/p/total), or error message.
        An empty list means no segment matched -- either the window is empty or
        the run did not record surface hits.
    """
    try:
        import math

        scene, _segments = _require_context()
        db = _require_db()

        surface_uuid: Optional[str] = None
        if surface_name is not None:
            # Raises ValueError with the list of valid names if unknown.
            obj = get_object_by_name(scene, surface_name)
            surface_uuid = getattr(obj, 'uuid', None)

        min_rad = math.radians(min_deg)
        max_rad = math.radians(max_deg)

        sql = (
            "SELECT uuid, interaction_type, incident_angle, hit_surface_uuid, "
            "hit_point_x, hit_point_y, brightness_s, brightness_p, brightness_total "
            "FROM rays WHERE incident_angle IS NOT NULL "
            "AND incident_angle >= ? AND incident_angle <= ?"
        )
        params: List[Any] = [min_rad, max_rad]
        if surface_uuid is not None:
            sql += " AND hit_surface_uuid = ?"
            params.append(surface_uuid)
        sql += " ORDER BY brightness_total DESC LIMIT ?"
        params.append(int(top_n))

        rows = db.execute(sql, params).fetchall()

        results = []
        for r in rows:
            results.append({
                'uuid': r[0],
                'interaction_type': r[1],
                'incident_angle_rad': r[2],
                'incident_angle_deg': math.degrees(r[2]),
                'hit_surface_uuid': r[3],
                'hit_point': ({'x': r[4], 'y': r[5]} if r[4] is not None else None),
                'brightness_s': r[6],
                'brightness_p': r[7],
                'brightness_total': r[8],
            })

        return _ok(results)
    except (ValueError, RuntimeError) as e:
        return _error(str(e))


# =============================================================================
# Bidirectional-path tools (ray-lineage Step C agentic exposure, C.5)
# =============================================================================

def rank_bidirectional_paths(
    detector_name: Optional[str] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """
    Rank source->detector paths from a bidirectional (Step C) trace, by
    end-to-end energy.

    Unlike rank_paths_by_energy()/rank_detector_paths() (forward-only
    ranking by terminal segment brightness), this ranks whole
    source -> ... -> connection -> ... -> detector paths extracted from the
    combined forward/backward graph (Simulator.run_bidirectional()), so the
    ranking reflects light that actually made it from a source to the
    detector through a matched surface connection, not just how bright a
    forward ray happened to end up.

    Requires a bidirectional context: call set_bidirectional_context(result)
    with the BidirectionalResult from Simulator.run_bidirectional() first.

    Args:
        detector_name: Optional sanity check, not a filter. A
            BidirectionalResult already belongs to exactly one detector (the
            one Simulator.run_bidirectional() was called with) -- unlike
            rank_detector_paths(), which filters a single forward context by
            any of several detectors. If given, must match
            BidirectionalResult.detector_name; use list_detectors() first if
            unsure, or omit to skip the check.
        top_n: Maximum number of paths to return (default: 10).

    Returns:
        Structured dict with status and ranked path data, or error message.
        Each entry: uuid (the path's detector-side terminal segment uuid,
        the natural per-path identifier here), energy, weight
        (-log(energy)), path_length, path_types, path_uuids (source
        ->detector node order, for use with highlight_custom_rays_svg),
        connection_surface, connection_edge_index, forward_len, backward_len.
        Empty list if the trace has no source->detector path (e.g. no
        connections were found).
    """
    try:
        from .bidirectional import extract_ranked_paths

        bidir = _require_bidirectional()
        if (detector_name is not None and bidir.detector_name is not None
                and detector_name != bidir.detector_name):
            return _error(
                f"This bidirectional result was traced from detector "
                f"'{bidir.detector_name}', not '{detector_name}'. Re-run "
                f"Simulator.run_bidirectional() against the detector you "
                f"want, or omit detector_name to skip this check."
            )
        if bidir.combined is None:
            return _error(
                "This bidirectional result has no combined graph (traced "
                "with connect=False or build_graph=False). Re-run "
                "Simulator.run_bidirectional(detector, connect=True, "
                "build_graph=True)."
            )

        raw = extract_ranked_paths(bidir.combined, top_n=top_n)

        serializable = []
        for entry in raw:
            path_uuids = entry['path_uuids']
            serializable.append({
                'uuid': path_uuids[-1] if path_uuids else None,
                'energy': entry['energy'],
                'weight': entry['weight'],
                'path_length': len(path_uuids),
                'path_types': entry['path_types'],
                'path_uuids': path_uuids,
                'connection_surface': entry['connection_surface'],
                'connection_edge_index': entry['connection_edge_index'],
                'forward_len': entry['forward_len'],
                'backward_len': entry['backward_len'],
            })

        return _ok(serializable)
    except RuntimeError as e:
        return _error(str(e))


def path_surfaces_tool(path_uuids: List[str]) -> Dict[str, Any]:
    """
    Reduce a bidirectional path to its physical hop sequence -- each node's
    surface_name/edge_index/arc_position/hit_point plus the interaction_type
    that actually happened there.

    This is the corrected counterpart to path_uuids/path_types (as returned
    by rank_bidirectional_paths): a segment's own interaction_type describes
    what happened at its PARENT's hit_point, not its own, so reading
    path_types node-by-node pairs each surface with the wrong event. This
    tool re-derives the correct pairing from the tree structure. Two hops
    -- immediately either side of the path's surface connection -- come
    back with interaction_type=None; use path_physical_summary_tool() to
    reason about that specific location instead.

    Requires a bidirectional context: call set_bidirectional_context(result)
    first. Get path_uuids from rank_bidirectional_paths().

    Args:
        path_uuids: The 'path_uuids' list from one rank_bidirectional_paths()
            entry (source->detector node order).

    Returns:
        Structured dict with status and a list of per-hop dicts (uuid, tree,
        surface_name, edge_index, arc_position, hit_point_x, hit_point_y,
        interaction_type), or error message.
    """
    try:
        from .signature_analysis import path_surfaces as _path_surfaces

        bidir = _require_bidirectional()
        if bidir.combined is None:
            return _error(
                "This bidirectional result has no combined graph (traced "
                "with connect=False or build_graph=False). Re-run "
                "Simulator.run_bidirectional(detector, connect=True, "
                "build_graph=True)."
            )
        missing = [u for u in path_uuids if not bidir.combined.has_node(u)]
        if missing:
            return _error(f"uuid(s) not found in the combined graph: {missing}")

        hops = _path_surfaces({'path_uuids': path_uuids}, bidir.combined)
        return _ok(hops)
    except RuntimeError as e:
        return _error(str(e))


def audit_bidirectional_paths(
    top_n: int = 20,
    expected_max_hops: Optional[int] = None,
    allowed_edges: Optional[List[List[Any]]] = None,
) -> Dict[str, Any]:
    """
    Flag ranked source->detector paths that don't match an expected routing
    -- e.g. an unintended TIR route that contaminates a measurement (path 17
    in the Hamamatsu refractometer notebook: a source->detector path via a
    TIR on the sample's own far edge, outside the prism).

    A path is flagged if it has more hops than expected_max_hops, OR if it
    touches a (surface_name, edge_index) not covered by allowed_edges.
    Omitting both just ranks and totals paths without flagging any.

    Requires a bidirectional context: call set_bidirectional_context(result)
    first.

    Args:
        top_n: Maximum number of ranked paths to audit (default: 20).
        expected_max_hops: Optional. Paths with more nodes than this are
            flagged.
        allowed_edges: Optional list of [surface_name, edge_index_or_null]
            pairs (JSON-friendly form of the (str, Optional[int]) tuples
            audit_paths() takes) -- edge_index=null means "any edge on this
            surface is allowed". A path touching a (surface_name,
            edge_index) not covered by this list is flagged. Nodes with no
            surface_name (the source/detector roots) are never flagged.

    Returns:
        Structured dict with status and {'total_paths', 'total_energy',
        'flagged_paths', 'flagged_energy', 'flagged_energy_fraction'}, or
        error message. flagged_paths entries carry 'flag_reasons'.
    """
    try:
        from .signature_analysis import audit_paths as _audit_paths

        bidir = _require_bidirectional()
        if bidir.combined is None:
            return _error(
                "This bidirectional result has no combined graph (traced "
                "with connect=False or build_graph=False). Re-run "
                "Simulator.run_bidirectional(detector, connect=True, "
                "build_graph=True)."
            )
        edges_arg = None
        if allowed_edges is not None:
            edges_arg = [(pair[0], pair[1]) for pair in allowed_edges]

        report = _audit_paths(
            bidir, top_n=top_n,
            expected_max_hops=expected_max_hops,
            allowed_edges=edges_arg,
        )
        return _ok(report)
    except RuntimeError as e:
        return _error(str(e))


def path_physical_summary_tool(path_uuids: List[str]) -> Dict[str, Any]:
    """
    Reconstruct one bidirectional path's polarization and total geometric
    length at the detector.

    Uses Connection.connecting_child_uuid (the forward ray's TRUE
    post-connection continuation) combined with the backward segment's
    brightness relative to its own root's brightness (a valid transfer
    function under Fresnel reciprocity, robust to the backward root's
    arbitrary 50/50 s/p seeding) -- see path_physical_summary()'s docstring
    for the full reasoning.

    Requires a bidirectional context: call set_bidirectional_context(result)
    first. Get path_uuids from rank_bidirectional_paths().

    Args:
        path_uuids: The 'path_uuids' list from one rank_bidirectional_paths()
            entry (source->detector node order, spanning exactly one surface
            connection).

    Returns:
        Structured dict with status and {'total_length',
        'brightness_s_at_detector', 'brightness_p_at_detector',
        'degree_of_polarization_at_detector', 'polarization_ratio_at_detector',
        'adaptive_sampling_warning'}, or error message.
    """
    try:
        from .signature_analysis import path_physical_summary as _path_physical_summary

        bidir = _require_bidirectional()
        if bidir.combined is None:
            return _error(
                "This bidirectional result has no combined graph (traced "
                "with connect=False or build_graph=False). Re-run "
                "Simulator.run_bidirectional(detector, connect=True, "
                "build_graph=True)."
            )
        missing = [u for u in path_uuids if not bidir.combined.has_node(u)]
        if missing:
            return _error(f"uuid(s) not found in the combined graph: {missing}")

        summary = _path_physical_summary({'path_uuids': path_uuids}, bidir)
        return _ok(summary)
    except (RuntimeError, ValueError) as e:
        return _error(str(e))


def fresnel_transmittances_tool(
    n1: float,
    n2: float,
    theta_i_deg: float,
) -> Dict[str, Any]:
    """
    Compute Fresnel power transmittances and reflectances at an interface.

    Standalone calculation — does not require set_context().

    Args:
        n1: Refractive index of the incident medium.
        n2: Refractive index of the transmitting medium.
        theta_i_deg: Angle of incidence in degrees (from normal).

    Returns:
        Structured dict with status and Fresnel data (T_s, T_p, R_s, R_p,
        ratio_Tp_Ts, theta_t_deg), or error message if TIR occurs.
    """
    try:
        from .fresnel_utils import fresnel_transmittances as _fresnel

        result = _fresnel(n1, n2, theta_i_deg)
        return _ok(result)
    except ValueError as e:
        return _error(str(e))


def tir_analysis_tool(
    glass_name_high_n: str,
    glass_name_low_n: str,
    theta_i_deg: Optional[float] = None,
    delta_angle_deg: float = 1.0,
) -> Dict[str, Any]:
    """
    Compute TIR critical angle, Brewster angle, Fresnel reflectances,
    and phase shifts between two named glasses.

    The first glass must have the higher refractive index.  Optionally
    provide an angle of incidence; if omitted, defaults to
    ``critical_angle + delta_angle_deg``.

    Requires context: call set_context() or set_context_from_result()
    before using this tool.

    Args:
        glass_name_high_n: Name of the glass with the higher refractive
            index.
        glass_name_low_n: Name of the glass with the lower refractive
            index.
        theta_i_deg: Angle of incidence in degrees (from normal).
            If omitted, defaults to critical_angle + delta_angle_deg.
        delta_angle_deg: Proximity threshold in degrees for near-TIR and
            near-Brewster flags.  Also used as the offset from TIR when
            no angle is provided.  Default 1.0.

    Returns:
        Structured dict with status and TIR analysis data, or error
        message.
    """
    try:
        from .fresnel_utils import tir_analysis as _tir_analysis

        scene, _segments = _require_context()

        glass_high = get_object_by_name(scene, glass_name_high_n)
        glass_low = get_object_by_name(scene, glass_name_low_n)

        n1 = getattr(glass_high, 'refIndex', None)
        n2 = getattr(glass_low, 'refIndex', None)
        if n1 is None or n2 is None:
            missing = []
            if n1 is None:
                missing.append(f"'{glass_name_high_n}'")
            if n2 is None:
                missing.append(f"'{glass_name_low_n}'")
            return _error(
                f"Object(s) {', '.join(missing)} have no refIndex attribute. "
                f"Are they Glass objects?"
            )

        if n1 <= n2:
            return _error(
                f"First glass must have higher refractive index. "
                f"'{glass_name_high_n}' has n={n1} but "
                f"'{glass_name_low_n}' has n={n2}. "
                f"Swap the arguments: tir_analysis("
                f"glass_name_high_n='{glass_name_low_n}', "
                f"glass_name_low_n='{glass_name_high_n}', ...)"
            )

        result = _tir_analysis(n1, n2, theta_i_deg, delta_angle_deg)
        result['glass_high_n'] = glass_name_high_n
        result['glass_low_n'] = glass_name_low_n
        return _ok(result)
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


# =============================================================================
# Legacy XML tool wrappers (superseded by query_rays, kept for backward compat)
# =============================================================================

def find_rays_inside_glass_xml(glass_name: str) -> Dict[str, Any]:
    """
    Find rays whose midpoint is inside a named glass object.

    Args:
        glass_name: Name of the glass object in the scene.

    Returns:
        Structured dict with status and XML data, or error message.
    """
    try:
        scene, segments = _require_context()
        glass = get_object_by_name(scene, glass_name)
        rays = find_rays_inside_glass(segments, glass)
        return _ok(rays_to_xml(rays))
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


def find_rays_crossing_edge_xml(glass_name: str, edge_label: str) -> Dict[str, Any]:
    """
    Find rays that cross a specific edge of a named glass object.

    Args:
        glass_name: Name of the glass object in the scene.
        edge_label: Label of the edge (short_label, long_label, or index).

    Returns:
        Structured dict with status and XML data, or error message.
    """
    try:
        scene, segments = _require_context()
        glass = get_object_by_name(scene, glass_name)
        rays = find_rays_crossing_edge(segments, glass, edge_label)
        return _ok(rays_to_xml(rays))
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


def find_rays_by_angle_to_edge_xml(
    glass_name: str,
    edge_label: str,
    min_angle: float = 0.0,
    max_angle: float = 90.0,
) -> Dict[str, Any]:
    """
    Find rays within an angle range relative to a named glass edge.

    Args:
        glass_name: Name of the glass object in the scene.
        edge_label: Label of the reference edge.
        min_angle: Minimum angle from edge normal in degrees (default: 0).
        max_angle: Maximum angle from edge normal in degrees (default: 90).

    Returns:
        Structured dict with status and XML data, or error message.
    """
    try:
        scene, segments = _require_context()
        glass = get_object_by_name(scene, glass_name)
        rays = find_rays_by_angle_to_edge(segments, glass, edge_label,
                                           min_angle=min_angle,
                                           max_angle=max_angle)
        return _ok(rays_to_xml(rays))
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


def find_rays_by_polarization_xml(
    min_dop: float = 0.0,
    max_dop: float = 1.0,
) -> Dict[str, Any]:
    """
    Filter rays by degree of polarization.

    Args:
        min_dop: Minimum degree of polarization (0-1, default: 0).
        max_dop: Maximum degree of polarization (0-1, default: 1).

    Returns:
        Structured dict with status and XML data, or error message.
    """
    try:
        _, segments = _require_context()
        rays = find_rays_by_polarization(segments, min_dop=min_dop, max_dop=max_dop)
        return _ok(rays_to_xml(rays))
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


# =============================================================================
# Viewbox helpers
# =============================================================================

_VIEWBOX_PADDING_FACTOR = 0.05  # 5% padding on each side


def _compute_scene_bounds(scene: 'Scene') -> Tuple[float, float, float, float]:
    """
    Compute a bounding box (min_x, min_y, width, height) from all scene objects.

    Iterates over scene.objs and collects coordinates from paths, p1/p2
    endpoints, and point-source x/y attributes.

    Returns:
        (min_x, min_y, width, height) in Y-up coordinates with 5% padding.
    """
    xs: List[float] = []
    ys: List[float] = []

    for obj in scene.objs:
        if hasattr(obj, 'path') and hasattr(obj.path, '__len__'):
            for pt in obj.path:
                xs.append(pt['x'])
                ys.append(pt['y'])
        if hasattr(obj, 'p1'):
            xs.append(obj.p1['x'])
            ys.append(obj.p1['y'])
        if hasattr(obj, 'p2'):
            xs.append(obj.p2['x'])
            ys.append(obj.p2['y'])
        if hasattr(obj, 'x') and hasattr(obj, 'y'):
            xs.append(obj.x)
            ys.append(obj.y)

    if not xs:
        return (0, 0, 800, 600)

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    w = max_x - min_x
    h = max_y - min_y
    # Avoid zero-size viewbox
    if w < 1e-6:
        w = 100
    if h < 1e-6:
        h = 100

    pad_x = w * _VIEWBOX_PADDING_FACTOR
    pad_y = h * _VIEWBOX_PADDING_FACTOR
    return (min_x - pad_x, min_y - pad_y, w + 2 * pad_x, h + 2 * pad_y)


def _parse_viewbox(
    viewbox_str: str,
    scene: 'Scene',
) -> Tuple[float, float, float, float]:
    """
    Parse a viewbox string into a (min_x, min_y, width, height) tuple.

    Accepts either ``"auto"`` (computes bounds from the scene) or a
    comma-separated string like ``"0,0,400,300"``.

    Args:
        viewbox_str: ``"auto"`` or ``"min_x,min_y,width,height"``.
        scene: The Scene object (used when viewbox_str is ``"auto"``).

    Returns:
        Tuple of (min_x, min_y, width, height).
    """
    if viewbox_str == 'auto':
        return _compute_scene_bounds(scene)
    parts = [float(v.strip()) for v in viewbox_str.split(',')]
    if len(parts) != 4:
        raise ValueError(
            f"viewbox must be 'auto' or 'min_x,min_y,w,h', got: {viewbox_str!r}"
        )
    return tuple(parts)


# =============================================================================
# SVG rendering tools (Phase 7, updated in Phase 3 for RenderResult)
# =============================================================================

def render_scene_svg(
    width: int = 800,
    height: int = 600,
    viewbox: str = 'auto',
) -> Dict[str, Any]:
    """
    Render the full scene and all rays, save to file, return descriptor.

    This is the baseline rendering — no highlights, just the scene as-is.
    Returns a file descriptor with svg_path (and png_path if cairosvg is
    installed) plus a text description.

    Args:
        width: SVG width in pixels.
        height: SVG height in pixels.
        viewbox: Viewbox as "min_x,min_y,width,height" or "auto" to compute
            from scene bounds.

    Returns:
        Structured dict with status and render descriptor, or error message.
    """
    try:
        from ..core.svg_renderer import SVGRenderer
        from .render_result import save_render

        scene, segments = _require_context()
        vb = _parse_viewbox(viewbox, scene)
        renderer = SVGRenderer(width=width, height=height, viewbox=vb)
        renderer.draw_scene(scene, segments)

        render_dir = _CONTEXT.get('render_dir', tempfile.mkdtemp(prefix='ray_sim_'))
        description = (
            f"Full scene: {len(scene.objs)} objects, "
            f"{len(segments)} ray segments."
        )
        descriptor = save_render(
            svg_string=renderer.to_string(),
            render_dir=render_dir,
            prefix='scene',
            width=width,
            height=height,
            description=description,
        )
        return _ok(descriptor)
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


def highlight_rays_inside_glass_svg(
    glass_name: str,
    highlight_color: str = 'yellow',
    width: int = 800,
    height: int = 600,
    viewbox: str = 'auto',
) -> Dict[str, Any]:
    """
    Render the scene with rays inside a glass object highlighted.

    Combines find_rays_inside_glass() with highlight rendering. Returns a
    file descriptor with paths and a text description.

    Args:
        glass_name: Name of the glass object.
        highlight_color: CSS color for highlighted rays.
        width: SVG width in pixels.
        height: SVG height in pixels.
        viewbox: Viewbox as "min_x,min_y,width,height" or "auto".

    Returns:
        Structured dict with status and render descriptor, or error message.
    """
    try:
        from ..core.svg_renderer import SVGRenderer
        from .render_result import save_render

        scene, segments = _require_context()
        glass = get_object_by_name(scene, glass_name)
        rays = find_rays_inside_glass(segments, glass)
        ray_uuids = {r.uuid for r in rays}

        vb = _parse_viewbox(viewbox, scene)
        renderer = SVGRenderer(width=width, height=height, viewbox=vb)
        renderer.draw_scene_with_highlights(
            scene, segments,
            highlight_ray_uuids=ray_uuids,
            highlight_glass_names=[glass_name],
            highlight_color=highlight_color,
        )

        render_dir = _CONTEXT.get('render_dir', tempfile.mkdtemp(prefix='ray_sim_'))
        description = (
            f"Highlighted {len(ray_uuids)} rays inside "
            f"'{glass_name}' (of {len(segments)} total)."
        )
        descriptor = save_render(
            svg_string=renderer.to_string(),
            render_dir=render_dir,
            prefix='highlight_inside',
            width=width,
            height=height,
            description=description,
            highlight_summary={
                'highlighted_rays': len(ray_uuids),
                'total_rays': len(segments),
                'filter': 'inside_glass',
                'glass_name': glass_name,
            },
        )
        return _ok(descriptor)
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


def highlight_rays_crossing_edge_svg(
    glass_name: str,
    edge_label: str,
    highlight_color: str = 'yellow',
    width: int = 800,
    height: int = 600,
    viewbox: str = 'auto',
) -> Dict[str, Any]:
    """
    Render the scene with rays crossing a specific edge highlighted.

    Combines find_rays_crossing_edge() with highlight rendering. Also
    highlights the edge itself. Returns a file descriptor.

    Args:
        glass_name: Name of the glass object.
        edge_label: Label of the edge (short_label, long_label, or index).
        highlight_color: CSS color for highlighted rays.
        width: SVG width in pixels.
        height: SVG height in pixels.
        viewbox: Viewbox as "min_x,min_y,width,height" or "auto".

    Returns:
        Structured dict with status and render descriptor, or error message.
    """
    try:
        from ..core.svg_renderer import SVGRenderer
        from .render_result import save_render

        scene, segments = _require_context()
        glass = get_object_by_name(scene, glass_name)
        rays = find_rays_crossing_edge(segments, glass, edge_label)
        ray_uuids = {r.uuid for r in rays}

        vb = _parse_viewbox(viewbox, scene)
        renderer = SVGRenderer(width=width, height=height, viewbox=vb)
        renderer.draw_scene_with_highlights(
            scene, segments,
            highlight_ray_uuids=ray_uuids,
            highlight_edge_specs=[(glass_name, edge_label)],
            highlight_color=highlight_color,
        )

        render_dir = _CONTEXT.get('render_dir', tempfile.mkdtemp(prefix='ray_sim_'))
        description = (
            f"Highlighted {len(ray_uuids)} rays crossing edge "
            f"'{edge_label}' of '{glass_name}'."
        )
        descriptor = save_render(
            svg_string=renderer.to_string(),
            render_dir=render_dir,
            prefix='highlight_edge',
            width=width,
            height=height,
            description=description,
            highlight_summary={
                'highlighted_rays': len(ray_uuids),
                'total_rays': len(segments),
                'filter': 'crossing_edge',
                'glass_name': glass_name,
                'edge_label': edge_label,
            },
        )
        return _ok(descriptor)
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


def highlight_rays_by_polarization_svg(
    min_dop: float = 0.0,
    max_dop: float = 1.0,
    highlight_color: str = 'magenta',
    width: int = 800,
    height: int = 600,
    viewbox: str = 'auto',
) -> Dict[str, Any]:
    """
    Render the scene with rays filtered by degree of polarization highlighted.

    Returns a file descriptor with paths and a text description.

    Args:
        min_dop: Minimum degree of polarization (0-1).
        max_dop: Maximum degree of polarization (0-1).
        highlight_color: CSS color for highlighted rays.
        width: SVG width in pixels.
        height: SVG height in pixels.
        viewbox: Viewbox as "min_x,min_y,width,height" or "auto".

    Returns:
        Structured dict with status and render descriptor, or error message.
    """
    try:
        from ..core.svg_renderer import SVGRenderer
        from .render_result import save_render

        scene, segments = _require_context()
        rays = find_rays_by_polarization(segments, min_dop=min_dop, max_dop=max_dop)
        ray_uuids = {r.uuid for r in rays}

        vb = _parse_viewbox(viewbox, scene)
        renderer = SVGRenderer(width=width, height=height, viewbox=vb)
        renderer.draw_scene_with_highlights(
            scene, segments,
            highlight_ray_uuids=ray_uuids,
            highlight_color=highlight_color,
        )

        render_dir = _CONTEXT.get('render_dir', tempfile.mkdtemp(prefix='ray_sim_'))
        description = (
            f"Highlighted {len(ray_uuids)} rays with DOP in "
            f"[{min_dop}, {max_dop}] (of {len(segments)} total)."
        )
        descriptor = save_render(
            svg_string=renderer.to_string(),
            render_dir=render_dir,
            prefix='highlight_polar',
            width=width,
            height=height,
            description=description,
            highlight_summary={
                'highlighted_rays': len(ray_uuids),
                'total_rays': len(segments),
                'filter': 'polarization',
                'min_dop': min_dop,
                'max_dop': max_dop,
            },
        )
        return _ok(descriptor)
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))


def highlight_custom_rays_svg(
    ray_uuids_csv: str,
    highlight_color: str = 'yellow',
    width: int = 800,
    height: int = 600,
    viewbox: str = 'auto',
) -> Dict[str, Any]:
    """
    Render the scene with a specific set of rays highlighted by uuid.

    This is the escape hatch: the agent can compose arbitrary queries,
    collect uuids, and pass them here for visualization. Returns a file
    descriptor.

    Args:
        ray_uuids_csv: Comma-separated ray uuids to highlight.
        highlight_color: CSS color for highlighted rays.
        width: SVG width in pixels.
        height: SVG height in pixels.
        viewbox: Viewbox as "min_x,min_y,width,height" or "auto".

    Returns:
        Structured dict with status and render descriptor, or error message.
    """
    try:
        from ..core.svg_renderer import SVGRenderer
        from .render_result import save_render

        scene, segments = _require_context()
        ray_uuids = set(u.strip() for u in ray_uuids_csv.split(',') if u.strip())

        vb = _parse_viewbox(viewbox, scene)
        renderer = SVGRenderer(width=width, height=height, viewbox=vb)
        renderer.draw_scene_with_highlights(
            scene, segments,
            highlight_ray_uuids=ray_uuids,
            highlight_color=highlight_color,
        )

        render_dir = _CONTEXT.get('render_dir', tempfile.mkdtemp(prefix='ray_sim_'))
        description = (
            f"Highlighted {len(ray_uuids)} custom rays by uuid."
        )
        descriptor = save_render(
            svg_string=renderer.to_string(),
            render_dir=render_dir,
            prefix='highlight_custom',
            width=width,
            height=height,
            description=description,
            highlight_summary={
                'highlighted_rays': len(ray_uuids),
                'total_rays': len(segments),
                'filter': 'custom',
            },
        )
        return _ok(descriptor)
    except (ValueError, KeyError) as e:
        return _error(str(e))
    except RuntimeError as e:
        return _error(str(e))
