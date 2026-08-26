"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Agentic SQLite Database (Phase 1)
===============================================================================
In-memory SQLite database for agentic ray-tracing queries.

Creates and populates seven tables from simulation data at set_context() time:
- rays:                 One row per ray segment with all properties
- glass_objects:        One row per glass object in the scene
- edges:                One row per edge of each glass object
- ray_glass_membership: Precomputed join (which rays are inside which glass)
- ray_edge_crossing:    Precomputed join (which rays cross which edge)
- detectors:            One row per Detector object (incl. a LinearSensor's
                        internal detector)
- detector_hits:        One row per ray that crossed a detector, joinable to
                        rays.uuid via ray_uuid (ray-lineage Step A)

The LLM agent queries this database via SQL through the query_rays() tool,
which enforces SELECT-only access.
===============================================================================
"""

from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from shapely.geometry import Point, LineString

from .glass_geometry import glass_to_polygon, get_edge_descriptions
from .ray_geometry_queries import _ray_endpoints

if TYPE_CHECKING:
    from ..core.ray import Ray
    from ..core.scene import Scene


# =============================================================================
# Constants
# =============================================================================

MAX_QUERY_ROWS = 200

_FORBIDDEN_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|'
    r'PRAGMA|REPLACE|VACUUM|REINDEX)\b',
    re.IGNORECASE,
)


# =============================================================================
# Schema DDL
# =============================================================================

_SCHEMA_RAYS = """\
CREATE TABLE rays (
    uuid            TEXT PRIMARY KEY,
    parent_uuid     TEXT,
    interaction_type TEXT NOT NULL,
    p1_x            REAL NOT NULL,
    p1_y            REAL NOT NULL,
    p2_x            REAL NOT NULL,
    p2_y            REAL NOT NULL,
    midpoint_x      REAL NOT NULL,
    midpoint_y      REAL NOT NULL,
    length          REAL NOT NULL,
    brightness_s    REAL NOT NULL,
    brightness_p    REAL NOT NULL,
    brightness_total REAL NOT NULL,
    degree_of_polarization REAL NOT NULL,
    polarization_ratio REAL,
    wavelength      REAL,
    gap             INTEGER NOT NULL,
    is_new          INTEGER NOT NULL,
    is_tir_result   INTEGER NOT NULL,
    caused_tir      INTEGER NOT NULL,
    tir_count       INTEGER NOT NULL,
    is_grazing_result__angle  INTEGER NOT NULL,
    caused_grazing__angle     INTEGER NOT NULL,
    is_grazing_result__polar  INTEGER NOT NULL,
    caused_grazing__polar     INTEGER NOT NULL,
    is_grazing_result__transm INTEGER NOT NULL,
    caused_grazing__transm    INTEGER NOT NULL,
    source_uuid     TEXT,
    source_label    TEXT,
    hit_surface_uuid TEXT,
    hit_point_x     REAL,
    hit_point_y     REAL,
    hit_normal_x    REAL,
    hit_normal_y    REAL,
    incident_angle  REAL,
    tree            TEXT NOT NULL DEFAULT 'forward'
);
"""

_SCHEMA_GLASS_OBJECTS = """\
CREATE TABLE glass_objects (
    uuid            TEXT PRIMARY KEY,
    name            TEXT,
    display_name    TEXT NOT NULL,
    glass_type      TEXT NOT NULL,
    ref_index       REAL NOT NULL,
    edge_count      INTEGER NOT NULL,
    centroid_x      REAL,
    centroid_y      REAL,
    area            REAL,
    perimeter       REAL
);
"""

_SCHEMA_EDGES = """\
CREATE TABLE edges (
    glass_uuid      TEXT NOT NULL,
    glass_name      TEXT,
    edge_index      INTEGER NOT NULL,
    short_label     TEXT NOT NULL,
    long_label      TEXT NOT NULL,
    edge_type       TEXT NOT NULL,
    p1_x            REAL NOT NULL,
    p1_y            REAL NOT NULL,
    p2_x            REAL NOT NULL,
    p2_y            REAL NOT NULL,
    midpoint_x      REAL NOT NULL,
    midpoint_y      REAL NOT NULL,
    length          REAL NOT NULL,
    PRIMARY KEY (glass_uuid, edge_index)
);
"""

_SCHEMA_RAY_GLASS_MEMBERSHIP = """\
CREATE TABLE ray_glass_membership (
    ray_uuid        TEXT NOT NULL,
    glass_uuid      TEXT NOT NULL,
    glass_name      TEXT,
    PRIMARY KEY (ray_uuid, glass_uuid)
);
"""

_SCHEMA_RAY_EDGE_CROSSING = """\
CREATE TABLE ray_edge_crossing (
    ray_uuid         TEXT NOT NULL,
    glass_uuid       TEXT NOT NULL,
    glass_name       TEXT,
    edge_index       INTEGER NOT NULL,
    edge_short_label TEXT NOT NULL,
    angle_to_normal  REAL NOT NULL,
    PRIMARY KEY (ray_uuid, glass_uuid, edge_index)
);
"""

_SCHEMA_DETECTORS = """\
CREATE TABLE detectors (
    uuid        TEXT PRIMARY KEY,
    name        TEXT,
    p1_x        REAL NOT NULL,
    p1_y        REAL NOT NULL,
    p2_x        REAL NOT NULL,
    p2_y        REAL NOT NULL,
    bin_size    REAL NOT NULL
);
"""

_SCHEMA_DETECTOR_HITS = """\
CREATE TABLE detector_hits (
    detector_uuid     TEXT NOT NULL,
    ray_uuid          TEXT NOT NULL,
    bin_index         INTEGER,
    position          REAL NOT NULL,
    brightness_total  REAL NOT NULL,
    sign              INTEGER NOT NULL
);
"""

# Ray-lineage Step C (bidirectional tracing), C.5 agentic exposure. Unlike the
# seven tables above, this one is NOT created by create_database() -- it is
# optional and only appears once set_bidirectional_context() has a
# BidirectionalResult with connections to populate it from. See
# get_schema_description()'s existence check below.
_SCHEMA_CONNECTIONS = """\
CREATE TABLE connections (
    forward_uuid           TEXT NOT NULL,
    backward_uuid          TEXT NOT NULL,
    connecting_child_uuid  TEXT,
    surface_uuid           TEXT NOT NULL,
    surface_name           TEXT,
    edge_index              INTEGER NOT NULL,
    arc_forward              REAL NOT NULL,
    arc_backward             REAL NOT NULL,
    arc_distance             REAL NOT NULL,
    direction_dot            REAL NOT NULL,
    point_x                  REAL NOT NULL,
    point_y                  REAL NOT NULL
);
"""


# =============================================================================
# Column metadata (for describe_schema)
# =============================================================================

_COLUMN_DESCRIPTIONS: Dict[str, List[Dict[str, str]]] = {
    "rays": [
        {"name": "uuid", "type": "TEXT", "description": "Unique ray segment identifier"},
        {"name": "parent_uuid", "type": "TEXT", "description": "UUID of parent ray (NULL for source rays)"},
        {"name": "interaction_type", "type": "TEXT", "description": "How ray was created: 'source', 'reflect', 'refract', 'tir'"},
        {"name": "p1_x", "type": "REAL", "description": "Start point X coordinate"},
        {"name": "p1_y", "type": "REAL", "description": "Start point Y coordinate"},
        {"name": "p2_x", "type": "REAL", "description": "End point X coordinate"},
        {"name": "p2_y", "type": "REAL", "description": "End point Y coordinate"},
        {"name": "midpoint_x", "type": "REAL", "description": "Midpoint X coordinate"},
        {"name": "midpoint_y", "type": "REAL", "description": "Midpoint Y coordinate"},
        {"name": "length", "type": "REAL", "description": "Segment length in scene units"},
        {"name": "brightness_s", "type": "REAL", "description": "S-polarization brightness (0 to 1)"},
        {"name": "brightness_p", "type": "REAL", "description": "P-polarization brightness (0 to 1)"},
        {"name": "brightness_total", "type": "REAL", "description": "Total brightness (s + p)"},
        {"name": "degree_of_polarization", "type": "REAL", "description": "Degree of polarization (0=unpolarized, 1=fully polarized)"},
        {"name": "polarization_ratio", "type": "REAL", "description": "Ratio brightness_p / brightness_s (NULL if s near zero)"},
        {"name": "wavelength", "type": "REAL", "description": "Wavelength in nm (NULL for white light)"},
        {"name": "gap", "type": "INTEGER", "description": "1 if gap segment (not drawn), 0 otherwise"},
        {"name": "is_new", "type": "INTEGER", "description": "1 if not yet processed, 0 otherwise"},
        {"name": "is_tir_result", "type": "INTEGER", "description": "1 if produced by total internal reflection"},
        {"name": "caused_tir", "type": "INTEGER", "description": "1 if endpoint caused TIR"},
        {"name": "tir_count", "type": "INTEGER", "description": "Cumulative TIR count in lineage"},
        {"name": "is_grazing_result__angle", "type": "INTEGER", "description": "1 if produced by grazing incidence (angle criterion)"},
        {"name": "caused_grazing__angle", "type": "INTEGER", "description": "1 if endpoint triggered angle grazing criterion"},
        {"name": "is_grazing_result__polar", "type": "INTEGER", "description": "1 if produced by grazing incidence (polarization criterion)"},
        {"name": "caused_grazing__polar", "type": "INTEGER", "description": "1 if endpoint triggered polarization grazing criterion"},
        {"name": "is_grazing_result__transm", "type": "INTEGER", "description": "1 if produced by grazing incidence (transmission criterion)"},
        {"name": "caused_grazing__transm", "type": "INTEGER", "description": "1 if endpoint triggered transmission grazing criterion"},
        {"name": "source_uuid", "type": "TEXT", "description": "UUID of the light source that emitted this ray"},
        {"name": "source_label", "type": "TEXT", "description": "Human-readable source label (e.g. 'red', 'chief')"},
        {"name": "hit_surface_uuid", "type": "TEXT", "description": "Surface hit records (Step B): UUID of the object this segment struck (NULL unless run with record_surface_hits, or segment hit no surface)"},
        {"name": "hit_point_x", "type": "REAL", "description": "X of the surface intersection point that terminated this segment (NULL when not recorded)"},
        {"name": "hit_point_y", "type": "REAL", "description": "Y of the surface intersection point that terminated this segment (NULL when not recorded)"},
        {"name": "hit_normal_x", "type": "REAL", "description": "X of the unit surface normal at the hit, as used by the physics (NULL when not recorded)"},
        {"name": "hit_normal_y", "type": "REAL", "description": "Y of the unit surface normal at the hit (NULL when not recorded)"},
        {"name": "incident_angle", "type": "REAL", "description": "Angle of incidence in RADIANS, always in [0, pi/2] (NULL when not recorded). Use degrees(incident_angle) for degrees; compare to critical angle to find near-TIR paths"},
        {"name": "tree", "type": "TEXT", "description": "'forward' or 'backward' -- which pass produced this segment (ray-lineage Step C). 'forward' for every context populated the plain way; both values appear once set_bidirectional_context() has populated the backward rows too"},
    ],
    "glass_objects": [
        {"name": "uuid", "type": "TEXT", "description": "Unique glass object identifier"},
        {"name": "name", "type": "TEXT", "description": "User-defined name (may be NULL)"},
        {"name": "display_name", "type": "TEXT", "description": "Display name (name or type + short UUID fallback)"},
        {"name": "glass_type", "type": "TEXT", "description": "Object type (e.g. 'Glass', 'SphericalLens')"},
        {"name": "ref_index", "type": "REAL", "description": "Refractive index"},
        {"name": "edge_count", "type": "INTEGER", "description": "Number of edges"},
        {"name": "centroid_x", "type": "REAL", "description": "Centroid X coordinate"},
        {"name": "centroid_y", "type": "REAL", "description": "Centroid Y coordinate"},
        {"name": "area", "type": "REAL", "description": "Area in scene units squared"},
        {"name": "perimeter", "type": "REAL", "description": "Perimeter in scene units"},
    ],
    "edges": [
        {"name": "glass_uuid", "type": "TEXT", "description": "UUID of the owning glass object"},
        {"name": "glass_name", "type": "TEXT", "description": "Name of the glass (denormalized)"},
        {"name": "edge_index", "type": "INTEGER", "description": "Edge index (0-based)"},
        {"name": "short_label", "type": "TEXT", "description": "Short edge label (e.g. 'S', 'NE', '0')"},
        {"name": "long_label", "type": "TEXT", "description": "Long edge label (e.g. 'South Edge')"},
        {"name": "edge_type", "type": "TEXT", "description": "Geometry type: 'line', 'circular', 'equation'"},
        {"name": "p1_x", "type": "REAL", "description": "Edge start point X"},
        {"name": "p1_y", "type": "REAL", "description": "Edge start point Y"},
        {"name": "p2_x", "type": "REAL", "description": "Edge end point X"},
        {"name": "p2_y", "type": "REAL", "description": "Edge end point Y"},
        {"name": "midpoint_x", "type": "REAL", "description": "Edge midpoint X"},
        {"name": "midpoint_y", "type": "REAL", "description": "Edge midpoint Y"},
        {"name": "length", "type": "REAL", "description": "Edge length in scene units"},
    ],
    "ray_glass_membership": [
        {"name": "ray_uuid", "type": "TEXT", "description": "Ray segment UUID"},
        {"name": "glass_uuid", "type": "TEXT", "description": "Glass object UUID"},
        {"name": "glass_name", "type": "TEXT", "description": "Glass name (denormalized)"},
    ],
    "ray_edge_crossing": [
        {"name": "ray_uuid", "type": "TEXT", "description": "Ray segment UUID"},
        {"name": "glass_uuid", "type": "TEXT", "description": "Glass object UUID"},
        {"name": "glass_name", "type": "TEXT", "description": "Glass name (denormalized)"},
        {"name": "edge_index", "type": "INTEGER", "description": "Index of the crossed edge"},
        {"name": "edge_short_label", "type": "TEXT", "description": "Short label of the crossed edge"},
        {"name": "angle_to_normal", "type": "REAL",
         "description": "Angle between ray direction and edge outward normal in degrees "
                        "(0 = head-on / perpendicular to edge, 90 = grazing / parallel to edge). "
                        "Note: multiple ray segments can cross the same edge (e.g. an interior "
                        "refracted ray crosses both its entry and exit edges). Join with the rays "
                        "table and filter by interaction_type to isolate a specific segment."},
    ],
    "detectors": [
        {"name": "uuid", "type": "TEXT", "description": "Unique detector object identifier"},
        {"name": "name", "type": "TEXT",
         "description": "User-defined name (may be NULL); for a LinearSensor this is "
                        "'<sensor_name>_detector'"},
        {"name": "p1_x", "type": "REAL", "description": "Detector line start point X"},
        {"name": "p1_y", "type": "REAL", "description": "Detector line start point Y"},
        {"name": "p2_x", "type": "REAL", "description": "Detector line end point X"},
        {"name": "p2_y", "type": "REAL", "description": "Detector line end point Y"},
        {"name": "bin_size", "type": "REAL", "description": "Irradiance bin width in scene units"},
    ],
    "detector_hits": [
        {"name": "detector_uuid", "type": "TEXT", "description": "UUID of the detector this hit belongs to (join with detectors.uuid)"},
        {"name": "ray_uuid", "type": "TEXT", "description": "UUID of the incident ray segment (join with rays.uuid)"},
        {"name": "bin_index", "type": "INTEGER", "description": "Irradiance bin index the ray landed in (NULL if the detector has no bin_size)"},
        {"name": "position", "type": "REAL", "description": "Distance from the detector's p1 along the detector, in scene units"},
        {"name": "brightness_total", "type": "REAL", "description": "brightness_s + brightness_p of the incident ray at the hit"},
        {"name": "sign", "type": "INTEGER", "description": "Crossing direction relative to p1->p2: +1 or -1"},
    ],
    "connections": [
        {"name": "forward_uuid", "type": "TEXT", "description": "UUID of the forward-tree ray segment arriving at the shared surface (join with rays.uuid)"},
        {"name": "backward_uuid", "type": "TEXT", "description": "UUID of the backward-tree ray segment arriving at the shared surface (join with rays.uuid)"},
        {"name": "connecting_child_uuid", "type": "TEXT", "description": "UUID of the forward ray's outgoing continuation that lines up antiparallel with the backward arrival -- the physical ray the connection represents"},
        {"name": "surface_uuid", "type": "TEXT", "description": "UUID of the shared surface object the connection was found on"},
        {"name": "surface_name", "type": "TEXT", "description": "Name of the shared surface (may be NULL if the surface has no name)"},
        {"name": "edge_index", "type": "INTEGER", "description": "Index of the surface edge both hits lie on"},
        {"name": "arc_forward", "type": "REAL", "description": "Arc-length of the forward hit along the edge, from the edge's first vertex"},
        {"name": "arc_backward", "type": "REAL", "description": "Arc-length of the backward hit along the edge"},
        {"name": "arc_distance", "type": "REAL", "description": "abs(arc_forward - arc_backward) -- the match residual; smaller is a tighter connection"},
        {"name": "direction_dot", "type": "REAL", "description": "Dot product of the forward continuation and backward arrival directions; ~-1 for a clean (antiparallel) match"},
        {"name": "point_x", "type": "REAL", "description": "X of the connection point (the forward hit location)"},
        {"name": "point_y", "type": "REAL", "description": "Y of the connection point"},
    ],
}


# =============================================================================
# Geometry helpers for angle computation
# =============================================================================

def _outward_normal(edge_desc, centroid_x: float, centroid_y: float) -> tuple:
    """
    Compute the outward-pointing unit normal of an edge.

    Same algorithm as ray_geometry_queries._edge_outward_normal but takes
    the centroid coordinates directly, avoiding a redundant
    glass_to_polygon() call.

    Args:
        edge_desc: An EdgeDescription with p1, p2, midpoint attributes.
        centroid_x: X coordinate of the owning glass polygon centroid.
        centroid_y: Y coordinate of the owning glass polygon centroid.

    Returns:
        (nx, ny) unit normal pointing outward from the glass.
    """
    dx = edge_desc.p2.x - edge_desc.p1.x
    dy = edge_desc.p2.y - edge_desc.p1.y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-12:
        return (0.0, 0.0)

    # Two candidate normals (perpendicular to edge direction)
    n1 = (-dy / length, dx / length)
    n2 = (dy / length, -dx / length)

    # Vector from edge midpoint to centroid
    to_cx = centroid_x - edge_desc.midpoint.x
    to_cy = centroid_y - edge_desc.midpoint.y

    # The outward normal has negative dot product with to-centroid vector
    dot1 = n1[0] * to_cx + n1[1] * to_cy
    if dot1 < 0:
        return n1
    return n2


def _angle_between_ray_and_normal(
    ray_dx: float, ray_dy: float, normal: tuple,
) -> float:
    """
    Compute the angle (degrees) between a ray direction and an edge normal.

    Uses abs(dot product) so the result is independent of ray travel
    direction (entry vs exit).

    Returns:
        Angle in degrees: 0 = head-on (perpendicular to edge),
        90 = grazing (parallel to edge).
    """
    dot = abs(ray_dx * normal[0] + ray_dy * normal[1])
    dot = max(0.0, min(1.0, dot))  # clamp for numerical safety
    return math.degrees(math.acos(dot))


# =============================================================================
# Database creation and population
# =============================================================================

def create_database(
    scene: 'Scene',
    segments: List['Ray'],
    db_path: Optional[Path] = None,
) -> sqlite3.Connection:
    """
    Create and populate a SQLite database from simulation data.

    Called at set_context() time for the default in-memory case. Creates 7
    tables and precomputes spatial join tables (ray-glass containment,
    ray-edge crossing) using Shapely.

    Args:
        scene: The live Scene object.
        segments: List of Ray segments from the simulation.
        db_path: If given, write to this file path instead of an in-memory
            database (for persist_run_artifacts()'s rays.sqlite artifact).
            When None (default), behaviour is unchanged: an in-memory
            database with the journal/sync pragmas relaxed for throwaway
            speed. A file-backed database keeps SQLite's normal durability
            defaults instead -- those pragmas are safe for a connection that
            vanishes with the process, not for one meant to outlive it.

    Returns:
        A sqlite3.Connection with all tables populated.
    """
    target = str(db_path) if db_path is not None else ':memory:'
    conn = sqlite3.connect(target, check_same_thread=False)
    if db_path is None:
        conn.execute('PRAGMA journal_mode=OFF')
        conn.execute('PRAGMA synchronous=OFF')

    conn.executescript(_SCHEMA_RAYS)
    conn.executescript(_SCHEMA_GLASS_OBJECTS)
    conn.executescript(_SCHEMA_EDGES)
    conn.executescript(_SCHEMA_RAY_GLASS_MEMBERSHIP)
    conn.executescript(_SCHEMA_RAY_EDGE_CROSSING)
    conn.executescript(_SCHEMA_DETECTORS)
    conn.executescript(_SCHEMA_DETECTOR_HITS)

    _populate_rays(conn, segments)
    _populate_glass_and_spatial(conn, scene, segments)
    _populate_detectors(conn, scene)

    conn.commit()
    return conn


def _populate_rays(
    conn: sqlite3.Connection,
    segments: List['Ray'],
    tree: str = 'forward',
) -> None:
    """Insert one row per ray segment into the rays table.

    Args:
        conn: The SQLite connection.
        segments: Ray segments to insert.
        tree: 'forward' (default) or 'backward' -- tags every inserted row
            (ray-lineage Step C; see populate_backward_rays()).
    """
    rows = []
    for ray in segments:
        p1x, p1y, p2x, p2y = _ray_endpoints(ray)
        mx = (p1x + p2x) / 2.0
        my = (p1y + p2y) / 2.0
        dx = p2x - p1x
        dy = p2y - p1y
        length = math.sqrt(dx * dx + dy * dy)

        polar_ratio: Optional[float] = None
        if ray.brightness_s > 1e-10:
            polar_ratio = ray.brightness_p / ray.brightness_s

        # Surface hit records (Step B) -- nullable; populated only when the run
        # used Simulator(record_surface_hits=True) and this segment hit a surface.
        hit_point = getattr(ray, 'hit_point', None)
        hit_normal = getattr(ray, 'hit_normal', None)
        hit_point_x = hit_point['x'] if hit_point else None
        hit_point_y = hit_point['y'] if hit_point else None
        hit_normal_x = hit_normal['x'] if hit_normal else None
        hit_normal_y = hit_normal['y'] if hit_normal else None

        rows.append((
            ray.uuid,
            ray.parent_uuid,
            ray.interaction_type,
            p1x, p1y, p2x, p2y,
            mx, my,
            length,
            ray.brightness_s,
            ray.brightness_p,
            ray.total_brightness,
            ray.degree_of_polarization,
            polar_ratio,
            ray.wavelength,
            int(ray.gap),
            int(ray.is_new),
            int(ray.is_tir_result),
            int(ray.caused_tir),
            ray.tir_count,
            int(getattr(ray, 'is_grazing_result__angle', False)),
            int(getattr(ray, 'caused_grazing__angle', False)),
            int(getattr(ray, 'is_grazing_result__polar', False)),
            int(getattr(ray, 'caused_grazing__polar', False)),
            int(getattr(ray, 'is_grazing_result__transm', False)),
            int(getattr(ray, 'caused_grazing__transm', False)),
            ray.source_uuid,
            ray.source_label,
            getattr(ray, 'hit_surface_uuid', None),
            hit_point_x, hit_point_y,
            hit_normal_x, hit_normal_y,
            getattr(ray, 'incident_angle', None),
            tree,
        ))

    conn.executemany(
        'INSERT INTO rays VALUES (' + ','.join(['?'] * 36) + ')',
        rows,
    )


def _populate_glass_and_spatial(
    conn: sqlite3.Connection,
    scene: 'Scene',
    segments: List['Ray'],
) -> None:
    """
    Populate glass_objects, edges, and precompute spatial join tables.

    Iterates over all BaseGlass instances in the scene. For each glass:
    creates a Shapely polygon, tests ray midpoint containment, and tests
    ray-edge intersection.
    """
    from ..core.scene_objs.base_glass import BaseGlass

    glasses = [obj for obj in scene.objs if isinstance(obj, BaseGlass)]

    # Precompute ray geometries once
    # ray_lines stores (uuid, LineString, unit_dx, unit_dy) for angle computation
    ray_mids: List[tuple] = []
    ray_lines: List[tuple] = []
    for ray in segments:
        p1x, p1y, p2x, p2y = _ray_endpoints(ray)
        mx = (p1x + p2x) / 2.0
        my = (p1y + p2y) / 2.0
        ray_mids.append((ray.uuid, Point(mx, my)))
        dx = p2x - p1x
        dy = p2y - p1y
        ray_len = math.sqrt(dx * dx + dy * dy)
        if ray_len < 1e-12:
            rdx, rdy = 0.0, 0.0
        else:
            rdx, rdy = dx / ray_len, dy / ray_len
        ray_lines.append((ray.uuid, LineString([(p1x, p1y), (p2x, p2y)]), rdx, rdy))

    membership_rows: List[tuple] = []
    crossing_rows: List[tuple] = []

    for glass in glasses:
        glass_uuid = glass.uuid
        glass_name = getattr(glass, 'name', None)
        glass_type = getattr(glass.__class__, 'type', None) or glass.__class__.__name__
        ref_index = getattr(glass, 'refIndex', 1.5)
        display_name = glass.get_display_name()

        poly = glass_to_polygon(glass)
        centroid = poly.centroid
        area = poly.area
        perimeter = poly.length

        edge_descs = get_edge_descriptions(glass)

        # Insert glass_objects row
        conn.execute(
            'INSERT INTO glass_objects VALUES (?,?,?,?,?,?,?,?,?,?)',
            (glass_uuid, glass_name, display_name, glass_type,
             ref_index, len(edge_descs),
             centroid.x, centroid.y, area, perimeter),
        )

        # Insert edges rows
        for ed in edge_descs:
            conn.execute(
                'INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (glass_uuid, glass_name, ed.index,
                 ed.short_label, ed.long_label, ed.edge_type.value,
                 ed.p1.x, ed.p1.y, ed.p2.x, ed.p2.y,
                 ed.midpoint.x, ed.midpoint.y, ed.length),
            )

        # Precompute ray-glass membership (containment)
        for ray_uuid, mid in ray_mids:
            if poly.contains(mid):
                membership_rows.append((ray_uuid, glass_uuid, glass_name))

        # Precompute ray-edge crossings with angle to normal
        cx, cy = centroid.x, centroid.y
        for ed in edge_descs:
            edge_line = LineString([(ed.p1.x, ed.p1.y), (ed.p2.x, ed.p2.y)])
            normal = _outward_normal(ed, cx, cy)
            for ray_uuid, ray_line, rdx, rdy in ray_lines:
                if ray_line.intersects(edge_line):
                    angle = _angle_between_ray_and_normal(rdx, rdy, normal)
                    crossing_rows.append(
                        (ray_uuid, glass_uuid, glass_name,
                         ed.index, ed.short_label, angle)
                    )

    conn.executemany(
        'INSERT INTO ray_glass_membership VALUES (?,?,?)',
        membership_rows,
    )
    conn.executemany(
        'INSERT INTO ray_edge_crossing VALUES (?,?,?,?,?,?)',
        crossing_rows,
    )


def _populate_detectors(conn: sqlite3.Connection, scene: 'Scene') -> None:
    """
    Populate detectors and detector_hits from Detector objects in the scene
    (ray-lineage Step A: see core/scene_objs/other/detector.py hit_records).

    Includes a LinearSensor's internal Detector, since it is added to
    scene.objs directly by LinearSensor.__init__.
    """
    detector_rows: List[tuple] = []
    hit_rows: List[tuple] = []

    for obj in scene.objs:
        obj_type = getattr(obj.__class__, 'type', None) or obj.__class__.__name__
        if obj_type != 'Detector' or not hasattr(obj, 'get_hit_records'):
            continue

        detector_rows.append((
            obj.uuid, obj.name,
            obj.p1['x'], obj.p1['y'], obj.p2['x'], obj.p2['y'],
            obj.bin_size,
        ))
        for record in obj.get_hit_records():
            if record['ray_uuid'] is None:
                continue
            hit_rows.append((
                obj.uuid, record['ray_uuid'], record['bin_index'],
                record['position'], record['brightness_total'], record['sign'],
            ))

    conn.executemany('INSERT INTO detectors VALUES (?,?,?,?,?,?,?)', detector_rows)
    conn.executemany('INSERT INTO detector_hits VALUES (?,?,?,?,?,?)', hit_rows)


def populate_connections_table(
    conn: sqlite3.Connection,
    connections: List[Any],
    name_by_uuid: Optional[Dict[str, Optional[str]]] = None,
) -> None:
    """
    Create (or replace) and populate the optional `connections` table from a
    bidirectional trace's forward<->backward surface matches (ray-lineage
    Step C, sub-problem C.3; agentic exposure C.5).

    Unlike the seven tables create_database() always builds, this one is
    created on demand -- called from set_bidirectional_context() when a
    BidirectionalResult with connections becomes available, into the
    already-open database from set_context()/set_context_from_result(). Lets
    query_rays() rank connection quality by SQL (e.g. "which connections have
    the smallest arc_distance").

    Args:
        conn: An existing SQLite connection (typically the one already
            created by create_database()/set_context()).
        connections: List of analysis.bidirectional.Connection objects --
            pass the full (unpruned) set for topological completeness; the
            pruned best-per-forward set stays available via extract_ranked_paths.
        name_by_uuid: Optional {uuid: name} map to resolve surface_name;
            left NULL per-row when not given or the uuid isn't found.

    Idempotent: safe to call again (e.g. after re-running a bidirectional
    pass) -- drops and recreates the table rather than appending to it.
    """
    conn.execute('DROP TABLE IF EXISTS connections')
    conn.executescript(_SCHEMA_CONNECTIONS)

    name_by_uuid = name_by_uuid or {}
    rows = [
        (c.forward_uuid, c.backward_uuid, c.connecting_child_uuid,
         c.surface_uuid, name_by_uuid.get(c.surface_uuid),
         c.edge_index, c.arc_forward, c.arc_backward,
         c.arc_distance, c.direction_dot,
         c.point['x'], c.point['y'])
        for c in connections
    ]
    conn.executemany(
        'INSERT INTO connections VALUES (' + ','.join(['?'] * 12) + ')',
        rows,
    )
    conn.commit()


def populate_backward_rays(
    conn: sqlite3.Connection,
    backward_segments: List['Ray'],
) -> None:
    """
    Insert a bidirectional trace's backward-tree segments into the existing
    `rays` table (tagged tree='backward'), so a bidirectional path is
    queryable end to end via query_rays() -- not just its forward half
    (ray-lineage Step C, path-auditing follow-up:
    dev_doc/roadmap/proposed/15_p8_bidirectional_path_auditing.md item 1).

    Called on demand from set_bidirectional_context(), alongside
    populate_connections_table(), into the already-open database from
    set_context()/set_context_from_result(). Forward rows (tree='forward',
    the default) are untouched.

    Args:
        conn: An existing SQLite connection (typically the one already
            created by create_database()/set_context()).
        backward_segments: BidirectionalResult.backward_segments.

    Idempotent: deletes any previously-inserted backward rows first, so
    re-running a bidirectional pass and calling this again doesn't duplicate
    rows (mirrors populate_connections_table's DROP-then-recreate approach,
    adapted for a shared table where only DELETE, not DROP, is correct).
    """
    conn.execute("DELETE FROM rays WHERE tree = 'backward'")
    _populate_rays(conn, backward_segments, tree='backward')
    conn.commit()


# =============================================================================
# SQL validation and query execution
# =============================================================================

def _validate_sql(sql: str) -> Optional[str]:
    """
    Validate that sql is a read-only SELECT statement.

    Returns None if valid, or an error message string if invalid.
    """
    stripped = sql.strip()
    if not stripped:
        return "Empty SQL statement."
    if not stripped.upper().startswith('SELECT'):
        return "Only SELECT statements are allowed. Your query must start with SELECT."
    if _FORBIDDEN_KEYWORDS.search(stripped):
        return (
            "Statement contains forbidden keywords (INSERT, UPDATE, DELETE, DROP, etc.). "
            "Only SELECT queries are allowed."
        )
    without_trailing = stripped.rstrip('; \t\n')
    if ';' in without_trailing:
        return "Multiple statements are not allowed. Please send a single SELECT query."
    return None


def _convert_value(value: Any) -> Any:
    """Convert SQLite values for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def execute_query(
    conn: sqlite3.Connection,
    sql: str,
    max_rows: int = MAX_QUERY_ROWS,
) -> Dict[str, Any]:
    """
    Execute a validated SELECT query and return columnar results.

    Args:
        conn: The SQLite connection.
        sql: The SQL query string (must be a SELECT).
        max_rows: Maximum number of rows to return.

    Returns:
        Dict with 'columns', 'rows', 'row_count', and optionally
        'truncated'/'note' if results were capped.

    Raises:
        ValueError: If the SQL is not a valid SELECT statement.
        sqlite3.OperationalError: If the SQL has syntax errors or
            references unknown tables/columns.
    """
    validation_error = _validate_sql(sql)
    if validation_error:
        raise ValueError(validation_error)

    cursor = conn.execute(sql)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []

    rows = []
    truncated = False
    for row in cursor:
        if len(rows) >= max_rows:
            truncated = True
            break
        rows.append([_convert_value(v) for v in row])

    result: Dict[str, Any] = {
        'columns': columns,
        'rows': rows,
        'row_count': len(rows),
    }
    if truncated:
        result['truncated'] = True
        result['max_rows'] = max_rows
        result['note'] = (
            f"Results truncated to {max_rows} rows. "
            f"Add LIMIT to your query or use more specific WHERE conditions."
        )

    return result


# =============================================================================
# Schema description
# =============================================================================

def get_schema_description(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Return a structured description of all tables in the database.

    Includes column names, types, descriptions, and current row counts.

    Args:
        conn: The SQLite connection.

    Returns:
        Dict mapping table names to their schema info and row counts. Tables
        that are optional and not yet created (currently: `connections`,
        populated only after set_bidirectional_context() runs) are omitted
        rather than raising.
    """
    tables: Dict[str, Any] = {}
    existing = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    for table_name, col_descs in _COLUMN_DESCRIPTIONS.items():
        if table_name not in existing:
            continue
        cursor = conn.execute(f'SELECT COUNT(*) FROM {table_name}')
        row_count = cursor.fetchone()[0]

        tables[table_name] = {
            'columns': col_descs,
            'row_count': row_count,
        }

    return tables
